import datetime
import ipaddress
import logging
import re
from typing import NamedTuple

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import F, Q
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.functional import cached_property
from django_countries import countries

from web import geoip

logger = logging.getLogger(__name__)


class InstitutionSection(models.Model):
    name = models.TextField(unique=True)
    order = models.IntegerField()


class Institution(models.Model):
    name = models.TextField()
    section = models.ForeignKey(InstitutionSection, on_delete=models.CASCADE)


# Addresses real visitors never have in production. Blocking them could only
# break in-cluster traffic, so they're rejected unless BLOCK_RULES_ALLOW_INTERNAL.
INTERNAL_NETWORKS = [
    ipaddress.ip_network(network)
    for network in (
        "0.0.0.0/8",  # "this network"
        "10.0.0.0/8",  # private
        "100.64.0.0/10",  # carrier-grade NAT
        "127.0.0.0/8",  # loopback
        "169.254.0.0/16",  # link-local
        "172.16.0.0/12",  # private
        "192.168.0.0/16",  # private
        "224.0.0.0/4",  # multicast
        "240.0.0.0/4",  # reserved
        "::/128",  # unspecified
        "::1/128",  # loopback
        "::ffff:0:0/96",  # IPv4-mapped
        "fc00::/7",  # unique local
        "fe80::/10",  # link-local
        "ff00::/8",  # multicast
    )
]


def canonical_ip_network(value):
    """`value`, a single IP address or a CIDR range, IPv4 or IPv6, in canonical
    form: lowercase, and single addresses without a /32 or /128 suffix.

    Raises ValidationError if it isn't valid, or is too broad or internal.
    """
    try:
        network = ipaddress.ip_network(value, strict=True)
    except ValueError:
        try:
            suggestion = ipaddress.ip_network(value, strict=False)
        except ValueError:
            raise ValidationError(
                "Enter a valid IP address (e.g. 203.0.113.7) or CIDR range "
                "(e.g. 203.0.113.0/24)."
            )
        raise ValidationError(f"{value} has host bits set. Did you mean {suggestion}?")

    min_prefix = (
        settings.BLOCK_RULES_MIN_PREFIX_IPV4
        if network.version == 4
        else settings.BLOCK_RULES_MIN_PREFIX_IPV6
    )
    if network.prefixlen < min_prefix:
        raise ValidationError(
            f"{network} is too broad. IPv{network.version} ranges can be at most "
            f"/{min_prefix}."
        )

    if not settings.BLOCK_RULES_ALLOW_INTERNAL:
        for internal in INTERNAL_NETWORKS:
            if network.version == internal.version and network.overlaps(internal):
                raise ValidationError(
                    f"{network} overlaps the internal range {internal}. Real "
                    "visitors never have these addresses."
                )

    if network.num_addresses == 1:
        return str(network.network_address)
    return str(network)


def canonical_country(value):
    """The two-letter code for `value`, a country code or name: "RU" for "ru",
    "RUS" or "Russia".
    """
    code = countries.alpha2(value) or countries.by_name(value)
    if not code:
        raise ValidationError(
            f"{value} isn't a country we recognize. Enter a two-letter code "
            "(e.g. RU) or a name (e.g. Russia)."
        )
    return code


ASN_PATTERN = re.compile(r"(?:AS)?\s*([0-9]{1,10})", re.IGNORECASE)


def canonical_asn(value):
    """`value`, an autonomous system number, as "AS" followed by the number:
    "AS16276" for "as16276" or "16276".
    """
    match = ASN_PATTERN.fullmatch(value)
    # AS numbers are 32-bit, and 0 is reserved.
    if not match or not 1 <= int(match[1]) <= 2**32 - 1:
        raise ValidationError(
            f"{value} isn't an AS number. Enter one like AS16276 or 16276."
        )
    return f"AS{int(match[1])}"


class BlockRuleQuerySet(models.QuerySet):
    def in_effect(self):
        """Rules that are switched on and haven't expired."""
        return self.filter(is_active=True).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        )


class BlockRule(models.Model):
    """Blocks visitors by IP address or range, country, or network owner from
    participating in studies, or from the entire site.
    """

    class Kind(models.TextChoices):
        IP = "ip", "IP address or range"
        COUNTRY = "country", "Country"
        ASN = "asn", "Network owner (ASN)"

    # The GeoIP database each kind of rule needs to match visitors, if any.
    GEOIP_EDITIONS = {
        Kind.COUNTRY: geoip.COUNTRY_EDITION,
        Kind.ASN: geoip.ASN_EDITION,
    }
    CACHE_KEY = "web.block_rules"

    kind = models.CharField(
        "type", max_length=16, choices=Kind.choices, default=Kind.IP
    )
    value = models.CharField(
        max_length=64,
        help_text="For an IP address or range: an address (e.g. 203.0.113.7) or CIDR range (e.g. 203.0.113.0/24), IPv4 or IPv6. For a country: a two-letter code (e.g. RU) or name. For a network owner: an AS number (e.g. AS16276). Search the rules for an IP address to see its country and network owner.",
    )
    reason = models.TextField(
        blank=True, help_text="Why this is blocked, for future reference."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to stop blocking without deleting the rule.",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional. The rule stops applying after this time. Leave blank to block indefinitely.",
    )
    block_entire_site = models.BooleanField(
        default=False,
        help_text="Unchecked: visitors can browse the site but can't participate in studies. Checked: visitors see a block page on every request, including the admin.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BlockRuleQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "value"],
                name="unique_block_rule",
                violation_error_message="There's already a rule for this. Edit that rule instead.",
            )
        ]

    def __str__(self):
        name = self.kind == self.Kind.COUNTRY and countries.name(self.value)
        return f"{name} ({self.value})" if name else self.value

    def canonical_value(self):
        """self.value in canonical form, so the same rule can't be added twice
        written differently. Raises ValidationError if it isn't valid.
        """
        canonical = {
            self.Kind.IP: canonical_ip_network,
            self.Kind.COUNTRY: canonical_country,
            self.Kind.ASN: canonical_asn,
        }.get(self.kind)
        if canonical is None:
            raise ValidationError(f"{self.kind!r} isn't a type of rule.")
        return canonical(self.value.strip())

    def clean(self):
        # Field validation reports blank values and unknown types.
        if self.value and self.kind in self.Kind.values:
            try:
                self.value = self.canonical_value()
            except ValidationError as e:
                raise ValidationError({"value": e})

    def save(self, *args, **kwargs):
        # Validate here too so rules made outside the admin (e.g. the shell) get
        # the same checks. bulk_create() and update() still bypass this.
        self.value = self.canonical_value()
        super().save(*args, **kwargs)

    @property
    def in_effect(self):
        return self.is_active and (
            self.expires_at is None or self.expires_at > timezone.now()
        )

    @classmethod
    def match_value(cls, kind, value):
        """What visitors are compared with for a rule: an ip_network for IP
        rules, the number for network owner rules, and the two-letter code for
        country rules.

        Raises ValueError if `value` is malformed, which can only happen if it
        bypassed save().
        """
        if kind == cls.Kind.IP:
            return ipaddress.ip_network(value)
        if kind == cls.Kind.ASN:
            return int(value.removeprefix("AS"))
        return value

    @classmethod
    def _cached_rules(cls):
        """The rules in effect, as _CachedRules.

        Cached per process, so changes reach every web pod within
        BLOCK_RULES_CACHE_TIMEOUT seconds. Expiry is checked at lookup time so a
        rule stops applying as soon as it expires, regardless of the cache.
        """
        rules = cache.get(cls.CACHE_KEY)
        if rules is None:
            rules = []
            for (
                pk,
                kind,
                value,
                expires_at,
                block_entire_site,
            ) in cls.objects.in_effect().values_list(
                "pk", "kind", "value", "expires_at", "block_entire_site"
            ):
                try:
                    match_value = cls.match_value(kind, value)
                except ValueError:
                    logger.error(
                        "Skipping block rule %s, whose value %r is malformed", pk, value
                    )
                    continue
                rules.append(
                    _CachedRule(
                        pk, kind, value, match_value, expires_at, block_entire_site
                    )
                )
            cache.set(cls.CACHE_KEY, rules, settings.BLOCK_RULES_CACHE_TIMEOUT)
        return rules

    @classmethod
    def clear_cache(cls):
        cache.delete(cls.CACHE_KEY)

    @classmethod
    def _find_block(cls, ip, entire_site_only):
        """The first rule in effect that blocks the visitor at `ip`, as a Block,
        or None if none does.
        """
        if not settings.BLOCK_RULES_ENABLED:
            return None
        try:
            visitor = Visitor(ip)
        except ValueError:
            return None
        now = timezone.now()
        for rule in cls._cached_rules():
            if (
                (rule.block_entire_site or not entire_site_only)
                and (rule.expires_at is None or rule.expires_at > now)
                and visitor.matches(rule.kind, rule.match_value)
            ):
                return Block(rule, visitor)
        return None

    @classmethod
    def participation_block(cls, ip):
        """The rule that stops the visitor at `ip` (a string) participating in
        studies, as a Block, or None if they may participate.

        Every rule in effect blocks participation, whether or not it also blocks
        the entire site.
        """
        return cls._find_block(ip, entire_site_only=False)

    @classmethod
    def blocks_participation(cls, ip):
        """True if the visitor at `ip` (a string) may not participate in studies."""
        return cls.participation_block(ip) is not None

    @classmethod
    def site_block(cls, ip):
        """The rule that blocks the visitor at `ip` (a string) from the entire
        site, as a Block, or None if none does.
        """
        return cls._find_block(ip, entire_site_only=True)

    @classmethod
    def blocks_site(cls, ip):
        """True if a rule blocks the visitor at `ip` (a string) from the entire site."""
        return cls.site_block(ip) is not None


class _CachedRule(NamedTuple):
    pk: int
    kind: str
    value: str
    match_value: object
    expires_at: datetime.datetime | None
    block_entire_site: bool


class Block(NamedTuple):
    """A block rule that applies to a visitor."""

    rule: _CachedRule
    visitor: "Visitor"


class Visitor:
    """The details of a visitor's IP address that block rules match. The country
    and network owner are only looked up when a rule needs them.

    Raises ValueError if `ip` isn't an IP address.
    """

    def __init__(self, ip):
        address = ipaddress.ip_address(ip)
        # So IPv4 rules match e.g. ::ffff:203.0.113.7.
        if address.version == 6 and address.ipv4_mapped:
            address = address.ipv4_mapped
        self.address = address

    @cached_property
    def country(self):
        """The two-letter country code, or None if unknown."""
        return geoip.country(str(self.address))

    @cached_property
    def asn(self):
        """The network owner, as a geoip.ASN, or None if unknown."""
        return geoip.asn(str(self.address))

    def matches(self, kind, match_value):
        """True if a rule of this kind, with this BlockRule.match_value, applies
        to the visitor.
        """
        if kind == BlockRule.Kind.IP:
            return self.address in match_value
        if kind == BlockRule.Kind.COUNTRY:
            return self.country == match_value
        if kind == BlockRule.Kind.ASN:
            return self.asn is not None and self.asn.number == match_value
        return False


def describe(visitor):
    """E.g. "203.0.113.7 is in Russia (RU), on network AS64496 (Example Org)"."""
    if visitor.country:
        name = countries.name(visitor.country)
        where = f"in {name} ({visitor.country})" if name else f"in {visitor.country}"
    else:
        where = "in an unknown country"
    if visitor.asn:
        network = f"on network AS{visitor.asn.number}"
        if visitor.asn.organization:
            network += f" ({visitor.asn.organization})"
    else:
        network = "on an unknown network"
    return f"{visitor.address} is {where}, {network}"


# How much of a participant's IP address is recorded when a rule stops them:
# enough to look up who owns the network, but not which household it is.
RECORDED_PREFIX_LENGTHS = {4: 24, 6: 48}


def recorded_network(address):
    """The /24 (IPv4) or /48 (IPv6) range containing `address`, an ip_address."""
    prefix = RECORDED_PREFIX_LENGTHS[address.version]
    return ipaddress.ip_network(f"{address}/{prefix}", strict=False)


class ParticipationBlockRecord(models.Model):
    """A logged-in participant that a block rule stopped participating in
    studies, so admins can see who each rule catches. There's one per participant
    and rule, updated each time the rule stops them.

    Keeps the IP range they were in, not their IP address.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    rule = models.ForeignKey(
        BlockRule,
        on_delete=models.CASCADE,
        related_name="participation_block_records",
    )
    times_blocked = models.PositiveIntegerField(
        default=1, help_text="How many of their requests the rule blocked."
    )
    first_blocked_at = models.DateTimeField()
    last_blocked_at = models.DateTimeField()
    # Where they were the last time the rule stopped them.
    network = models.CharField(
        "IP range",
        max_length=43,
        help_text="The /24 (IPv4) or /48 (IPv6) range their IP address was in.",
    )
    country = models.CharField(max_length=2, blank=True)
    asn = models.PositiveBigIntegerField("AS number", null=True, blank=True)
    asn_organization = models.CharField("network owner", max_length=255, blank=True)

    class Meta:
        ordering = ["-last_blocked_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "rule"], name="unique_participation_block_record"
            )
        ]

    def __str__(self):
        return f"Rule {self.rule_id} stopped user {self.user_id}"

    @classmethod
    def record(cls, user, block):
        """Record that `block` (a Block) stopped `user` participating."""
        now = timezone.now()
        visitor = block.visitor
        details = {
            "last_blocked_at": now,
            "network": str(recorded_network(visitor.address)),
            "country": visitor.country or "",
            "asn": visitor.asn.number if visitor.asn else None,
            "asn_organization": visitor.asn.organization if visitor.asn else "",
        }
        records = cls.objects.filter(user=user, rule_id=block.rule.pk)
        if records.update(times_blocked=F("times_blocked") + 1, **details):
            return
        # The rules are cached, so this one may have been deleted since. The
        # foreign key is only checked when the request's transaction commits,
        # which would fail the request.
        if not BlockRule.objects.filter(pk=block.rule.pk).exists():
            return
        try:
            with transaction.atomic():
                cls.objects.create(
                    user=user, rule_id=block.rule.pk, first_blocked_at=now, **details
                )
        except IntegrityError:
            # Another of their requests got there first.
            records.update(times_blocked=F("times_blocked") + 1, **details)


@receiver(post_save, sender=BlockRule)
@receiver(post_delete, sender=BlockRule)
def clear_block_rule_cache(sender, **kwargs):
    BlockRule.clear_cache()
