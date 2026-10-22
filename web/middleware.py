import logging

from django.conf import settings
from django.db import transaction
from django.shortcuts import render

from web.models import BlockRule, ParticipationBlockRecord, recorded_network

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """The visitor's IP address.

    In production ingress-nginx sets X-Real-IP to the connecting address and
    overwrites any value the client sent, so it can be trusted. Without the
    header (local development, in-cluster health checks) fall back to
    REMOTE_ADDR.
    """
    ip = request.META.get(settings.CLIENT_IP_HEADER, "").strip()
    return ip or request.META.get("REMOTE_ADDR", "")


def _check_block_rules(lookup, client_ip):
    try:
        return lookup(client_ip)
    except Exception:
        # Fail open: a missing table (new pods can start before the migration
        # job finishes), a database hiccup or a bug in the block rules
        # shouldn't take the site down.
        logger.exception("Could not check the block rules")
        return False


def participation_blocked(request):
    """True if a block rule stops the visitor participating in studies."""
    block = _check_block_rules(BlockRule.participation_block, get_client_ip(request))
    if not block:
        return False
    if request.user.is_authenticated:
        _log_participation_block(request, block)
        _record_participation_block(request, block)
    return True


def _record_participation_block(request, block):
    try:
        # In a savepoint, so a failure doesn't break the rest of the request's
        # transaction.
        with transaction.atomic():
            ParticipationBlockRecord.record(request.user, block)
    except Exception:
        # Fail open, like checking the rules.
        logger.exception("Could not record a participation block")


def _log_participation_block(request, block):
    """Log which rule stopped a logged-in participant, so admins can find it if
    they say they can't participate. Leaves out their IP address, but includes
    the /24 (IPv4) or /48 (IPv6) range it's in.
    """
    rule = block.rule
    # An IP address rule's value can be the participant's own address.
    if rule.kind == BlockRule.Kind.IP:
        what = BlockRule.Kind.IP.label
    else:
        what = rule.value
    visitor = block.visitor
    network = "an unknown network"
    if visitor.asn:
        network = f"AS{visitor.asn.number}"
        if visitor.asn.organization:
            network += f" ({visitor.asn.organization})"
    logger.info(
        "Block rule %s (%s) stopped user %s participating in studies, at %s %s. "
        "They're in %s, on %s, in IP range %s.",
        rule.pk,
        what,
        request.user.pk,
        request.method,
        request.path,
        visitor.country or "an unknown country",
        network,
        recorded_network(visitor.address),
    )


class BlockRuleMiddleware:
    """Show the block page to visitors that a rule blocks from the entire site.

    Rules that only block participation are enforced by the study views; see
    web.mixins.ParticipationBlockedMixin.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        client_ip = get_client_ip(request)
        if _check_block_rules(BlockRule.blocks_site, client_ip):
            return render(
                request,
                "web/blocked.html",
                {"client_ip": client_ip},
                status=403,
            )
        return self.get_response(request)
