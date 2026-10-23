import datetime
from unittest.mock import patch

from django.contrib import messages
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_dynamic_fixture import G
from parameterized import parameterized

from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from accounts.models import GoogleAuthenticatorTOTP, User
from web import geoip
from web.admin import (
    BlockRuleAdmin,
    activate_selected,
    deactivate_selected,
    describe,
)
from web.models import (
    BlockRule,
    Visitor,
    canonical_asn,
    canonical_country,
    canonical_ip_network,
)

Kind = BlockRule.Kind


class CanonicalIPNetworkTestCase(SimpleTestCase):
    @parameterized.expand(
        [
            ("ipv4 address", "203.0.113.7", "203.0.113.7"),
            ("ipv4 /32", "203.0.113.7/32", "203.0.113.7"),
            ("ipv4 range", "203.0.113.0/24", "203.0.113.0/24"),
            ("ipv6 address", "2001:db8::1", "2001:db8::1"),
            ("ipv6 uppercase", "2001:DB8::1", "2001:db8::1"),
            ("ipv6 /128", "2001:db8::1/128", "2001:db8::1"),
            ("ipv6 range", "2001:db8:1::/48", "2001:db8:1::/48"),
        ]
    )
    def test_valid(self, _, value, canonical):
        self.assertEqual(canonical_ip_network(value), canonical)

    @parameterized.expand(
        [
            ("garbage", "not an ip"),
            ("out of range octet", "203.0.113.300"),
            ("bad prefix", "203.0.113.0/33"),
        ]
    )
    def test_invalid(self, _, value):
        with self.assertRaisesMessage(ValidationError, "Enter a valid IP address"):
            canonical_ip_network(value)

    def test_host_bits_set_suggests_network(self):
        with self.assertRaisesMessage(ValidationError, "Did you mean 203.0.113.0/24?"):
            canonical_ip_network("203.0.113.7/24")

    @parameterized.expand(
        [
            ("ipv4 /16", "198.51.0.0/16"),
            ("ipv6 /32", "2001:db8::/32"),
        ]
    )
    def test_minimum_prefix_allowed(self, _, value):
        self.assertEqual(canonical_ip_network(value), value)

    @parameterized.expand(
        [
            ("everything ipv4", "0.0.0.0/0"),
            ("ipv4 /15", "198.50.0.0/15"),
            ("everything ipv6", "::/0"),
            ("ipv6 /31", "2001:db8::/31"),
        ]
    )
    def test_too_broad(self, _, value):
        with self.assertRaisesMessage(ValidationError, "is too broad"):
            canonical_ip_network(value)

    @override_settings(BLOCK_RULES_MIN_PREFIX_IPV4=24)
    def test_minimum_prefix_is_configurable(self):
        with self.assertRaisesMessage(ValidationError, "at most /24"):
            canonical_ip_network("198.51.0.0/23")

    @parameterized.expand(
        [
            ("private 10/8", "10.1.2.3"),
            ("docker gateway", "172.18.0.1"),
            ("private 192.168", "192.168.0.0/24"),
            ("loopback", "127.0.0.1"),
            ("link-local", "169.254.169.254"),
            ("carrier-grade nat", "100.64.0.0/16"),
            ("ipv6 loopback", "::1"),
            ("ipv6 unique local", "fd00::1"),
            ("ipv6 link-local", "fe80::1"),
            ("ipv4-mapped ipv6", "::ffff:10.0.0.1"),
        ]
    )
    def test_internal_rejected(self, _, value):
        # Internal ranges are allowed by default when ENVIRONMENT is develop,
        # which includes Cloud Build's test run.
        with (
            self.settings(BLOCK_RULES_ALLOW_INTERNAL=False),
            self.assertRaisesMessage(ValidationError, "overlaps the internal range"),
        ):
            canonical_ip_network(value)

    @override_settings(BLOCK_RULES_ALLOW_INTERNAL=True)
    def test_internal_allowed_when_configured(self):
        self.assertEqual(canonical_ip_network("172.18.0.1"), "172.18.0.1")


class CanonicalCountryTestCase(SimpleTestCase):
    @parameterized.expand(
        [
            ("code", "RU"),
            ("lowercase code", "ru"),
            ("three-letter code", "RUS"),
            ("numeric code", "643"),
            ("name", "Russia"),
            ("lowercase name", "russia"),
        ]
    )
    def test_valid(self, _, value):
        self.assertEqual(canonical_country(value), "RU")

    @parameterized.expand(
        [
            # The code for the United Kingdom is GB.
            ("unknown code", "UK"),
            ("unknown name", "Narnia"),
        ]
    )
    def test_invalid(self, _, value):
        with self.assertRaisesMessage(
            ValidationError, f"{value} isn't a country we recognize"
        ):
            canonical_country(value)


class CanonicalASNTestCase(SimpleTestCase):
    @parameterized.expand(
        [
            ("with prefix", "AS16276"),
            ("lowercase prefix", "as16276"),
            ("without prefix", "16276"),
            ("space after prefix", "AS 16276"),
            ("leading zero", "AS016276"),
        ]
    )
    def test_valid(self, _, value):
        self.assertEqual(canonical_asn(value), "AS16276")

    def test_largest(self):
        self.assertEqual(canonical_asn("4294967295"), "AS4294967295")

    @parameterized.expand(
        [
            ("reserved zero", "0"),
            ("too large", "4294967296"),
            ("not a number", "ASX"),
            ("negative", "AS-1"),
        ]
    )
    def test_invalid(self, _, value):
        with self.assertRaisesMessage(ValidationError, "isn't an AS number"):
            canonical_asn(value)


class BlockRuleTestCase(TestCase):
    """Clears the cached rules around each test, and stands in for the GeoIP
    databases: visitors are in an unknown country, on an unknown network, unless
    a test sets self.country's or self.asn's return_value.
    """

    def setUp(self):
        # Rolling back a test's rules doesn't clear the cache.
        BlockRule.clear_cache()
        self.addCleanup(BlockRule.clear_cache)
        self.country = self.enterContext(patch("web.geoip.country", return_value=None))
        self.asn = self.enterContext(patch("web.geoip.asn", return_value=None))
        self.problem = self.enterContext(patch("web.geoip.problem", return_value=None))


class BlockRuleModelTestCase(BlockRuleTestCase):
    @parameterized.expand(
        [
            ("ip", Kind.IP, " 203.0.113.7/32 ", "203.0.113.7"),
            ("country", Kind.COUNTRY, " russia ", "RU"),
            ("asn", Kind.ASN, "as16276", "AS16276"),
        ]
    )
    def test_save_canonicalizes_value(self, _, kind, entered, saved):
        rule = BlockRule.objects.create(kind=kind, value=entered)
        self.assertEqual(rule.value, saved)

    def test_save_validates(self):
        with self.assertRaises(ValidationError):
            BlockRule.objects.create(value="0.0.0.0/0")
        self.assertFalse(BlockRule.objects.exists())

    def test_save_rejects_unknown_kind(self):
        with self.assertRaisesMessage(ValidationError, "isn't a type of rule"):
            BlockRule.objects.create(kind="planet", value="Mars")

    def test_same_rule_written_differently_is_a_duplicate(self):
        BlockRule.objects.create(kind=Kind.COUNTRY, value="RU")
        with self.assertRaises(IntegrityError), transaction.atomic():
            BlockRule.objects.create(kind=Kind.COUNTRY, value="Russia")

    def test_clean_reports_invalid_value_on_value(self):
        with self.assertRaises(ValidationError) as cm:
            BlockRule(kind=Kind.COUNTRY, value="Narnia").clean()
        self.assertEqual(list(cm.exception.message_dict), ["value"])

    def test_full_clean_reports_blank_value_once(self):
        with self.assertRaises(ValidationError) as cm:
            BlockRule(kind=Kind.IP, value="").full_clean()
        self.assertEqual(
            cm.exception.message_dict, {"value": ["This field cannot be blank."]}
        )

    def test_full_clean_reports_unknown_kind_on_kind(self):
        with self.assertRaises(ValidationError) as cm:
            BlockRule(kind="planet", value="Mars").full_clean()
        self.assertEqual(list(cm.exception.message_dict), ["kind"])

    @parameterized.expand(
        [
            ("ip", Kind.IP, "203.0.113.0/24", "203.0.113.0/24"),
            ("country", Kind.COUNTRY, "RU", "Russia (RU)"),
            ("asn", Kind.ASN, "AS16276", "AS16276"),
        ]
    )
    def test_str(self, _, kind, value, expected):
        self.assertEqual(str(BlockRule(kind=kind, value=value)), expected)

    @override_settings(BLOCK_RULES_ENABLED=False)
    def test_kill_switch_disables_blocking_without_queries(self):
        BlockRule.objects.create(value="203.0.113.7", block_entire_site=True)
        with self.assertNumQueries(0):
            self.assertFalse(BlockRule.blocks_participation("203.0.113.7"))
            self.assertFalse(BlockRule.blocks_site("203.0.113.7"))

    def test_participation_only_rule(self):
        BlockRule.objects.create(value="203.0.113.7")
        self.assertTrue(BlockRule.blocks_participation("203.0.113.7"))
        self.assertFalse(BlockRule.blocks_site("203.0.113.7"))

    def test_entire_site_rule_also_blocks_participation(self):
        BlockRule.objects.create(value="203.0.113.7", block_entire_site=True)
        self.assertTrue(BlockRule.blocks_participation("203.0.113.7"))
        self.assertTrue(BlockRule.blocks_site("203.0.113.7"))

    def test_entire_site_rule_applies_alongside_participation_only_rule(self):
        BlockRule.objects.create(value="203.0.113.0/24", block_entire_site=True)
        BlockRule.objects.create(value="203.0.113.7")
        self.assertTrue(BlockRule.blocks_site("203.0.113.7"))

    def test_single_address(self):
        BlockRule.objects.create(value="203.0.113.7")
        self.assertTrue(BlockRule.blocks_participation("203.0.113.7"))
        self.assertFalse(BlockRule.blocks_participation("203.0.113.8"))

    def test_range(self):
        BlockRule.objects.create(value="203.0.113.0/24")
        self.assertTrue(BlockRule.blocks_participation("203.0.113.200"))
        self.assertFalse(BlockRule.blocks_participation("203.0.114.1"))

    def test_ipv6(self):
        BlockRule.objects.create(value="2001:db8::/32")
        self.assertTrue(BlockRule.blocks_participation("2001:db8:1::5"))
        self.assertFalse(BlockRule.blocks_participation("2001:db9::5"))
        self.assertFalse(BlockRule.blocks_participation("203.0.113.7"))

    def test_ipv4_mapped_address_matches_ipv4_rule(self):
        BlockRule.objects.create(value="203.0.113.0/24")
        self.assertTrue(BlockRule.blocks_participation("::ffff:203.0.113.7"))

    def test_country(self):
        BlockRule.objects.create(kind=Kind.COUNTRY, value="RU")
        self.country.return_value = "RU"
        self.assertTrue(BlockRule.blocks_participation("203.0.113.7"))
        self.country.assert_called_once_with("203.0.113.7")

        self.country.return_value = "US"
        self.assertFalse(BlockRule.blocks_participation("198.51.100.1"))

    def test_unknown_country_is_not_blocked(self):
        BlockRule.objects.create(kind=Kind.COUNTRY, value="RU")
        self.assertFalse(BlockRule.blocks_participation("203.0.113.7"))

    def test_network_owner(self):
        BlockRule.objects.create(kind=Kind.ASN, value="AS64496")
        self.asn.return_value = geoip.ASN(64496, "Example Org")
        self.assertTrue(BlockRule.blocks_participation("203.0.113.7"))

        self.asn.return_value = geoip.ASN(64497, "Other Org")
        self.assertFalse(BlockRule.blocks_participation("198.51.100.1"))

    def test_unknown_network_is_not_blocked(self):
        BlockRule.objects.create(kind=Kind.ASN, value="AS64496")
        self.assertFalse(BlockRule.blocks_participation("203.0.113.7"))

    def test_participation_block_says_which_rule_applies(self):
        rule = BlockRule.objects.create(kind=Kind.ASN, value="AS64496")
        self.asn.return_value = geoip.ASN(64496, "Example Org")

        block = BlockRule.participation_block("203.0.113.7")
        self.assertEqual(
            (block.rule.pk, block.rule.kind, block.rule.value),
            (rule.pk, Kind.ASN, "AS64496"),
        )
        self.assertEqual(str(block.visitor.address), "203.0.113.7")
        self.assertEqual(block.visitor.asn, geoip.ASN(64496, "Example Org"))

        self.asn.return_value = None
        self.assertIsNone(BlockRule.participation_block("198.51.100.1"))

    def test_geoip_only_looked_up_for_rules_that_need_it(self):
        BlockRule.objects.create(value="203.0.113.0/24")
        BlockRule.blocks_participation("198.51.100.1")
        self.country.assert_not_called()
        self.asn.assert_not_called()

    def test_geoip_looked_up_once_per_check(self):
        BlockRule.objects.create(kind=Kind.COUNTRY, value="RU")
        BlockRule.objects.create(kind=Kind.COUNTRY, value="CN")
        self.assertFalse(BlockRule.blocks_participation("203.0.113.7"))
        self.country.assert_called_once()

    @parameterized.expand([("garbage", "not an ip"), ("empty", ""), ("none", None)])
    def test_invalid_lookup_is_not_blocked(self, _, value):
        BlockRule.objects.create(value="203.0.113.0/24")
        BlockRule.objects.create(kind=Kind.COUNTRY, value="RU")
        self.assertFalse(BlockRule.blocks_participation(value))
        self.country.assert_not_called()

    def test_malformed_rules_are_skipped(self):
        # bulk_create() skips save(), which would reject these.
        BlockRule.objects.bulk_create(
            [BlockRule(value="not an ip"), BlockRule(kind=Kind.ASN, value="ASX")]
        )
        BlockRule.objects.create(value="203.0.113.7")
        with self.assertLogs("web.models", level="ERROR") as logs:
            self.assertTrue(BlockRule.blocks_participation("203.0.113.7"))
        self.assertEqual(len(logs.records), 2)

    def test_inactive_rule_not_blocked(self):
        BlockRule.objects.create(value="203.0.113.7", is_active=False)
        self.assertFalse(BlockRule.blocks_participation("203.0.113.7"))

    def test_expired_rule_not_blocked(self):
        BlockRule.objects.create(
            value="203.0.113.7",
            expires_at=timezone.now() - datetime.timedelta(minutes=1),
        )
        self.assertFalse(BlockRule.blocks_participation("203.0.113.7"))

    def test_rule_stops_blocking_when_it_expires_while_cached(self):
        expires_at = timezone.now() + datetime.timedelta(hours=1)
        BlockRule.objects.create(value="203.0.113.7", expires_at=expires_at)
        self.assertTrue(BlockRule.blocks_participation("203.0.113.7"))

        later = expires_at + datetime.timedelta(seconds=1)
        with patch("web.models.timezone.now", return_value=later):
            self.assertFalse(BlockRule.blocks_participation("203.0.113.7"))

    def test_in_effect(self):
        past = timezone.now() - datetime.timedelta(minutes=1)
        future = timezone.now() + datetime.timedelta(minutes=1)
        current = BlockRule.objects.create(value="203.0.113.1")
        not_yet_expired = BlockRule.objects.create(
            value="203.0.113.2", expires_at=future
        )
        BlockRule.objects.create(value="203.0.113.3", is_active=False)
        expired = BlockRule.objects.create(value="203.0.113.4", expires_at=past)

        self.assertCountEqual(BlockRule.objects.in_effect(), [current, not_yet_expired])
        self.assertTrue(current.in_effect)
        self.assertFalse(expired.in_effect)

    def test_lookups_are_cached(self):
        BlockRule.objects.create(value="203.0.113.7")
        BlockRule.blocks_participation("203.0.113.7")
        with self.assertNumQueries(0):
            BlockRule.blocks_participation("203.0.113.7")
            BlockRule.blocks_site("198.51.100.1")

    def test_save_clears_cache(self):
        self.assertFalse(BlockRule.blocks_participation("203.0.113.7"))
        BlockRule.objects.create(value="203.0.113.7")
        self.assertTrue(BlockRule.blocks_participation("203.0.113.7"))

    def test_delete_clears_cache(self):
        rule = BlockRule.objects.create(value="203.0.113.7")
        self.assertTrue(BlockRule.blocks_participation("203.0.113.7"))
        rule.delete()
        self.assertFalse(BlockRule.blocks_participation("203.0.113.7"))

    def test_queryset_delete_clears_cache(self):
        BlockRule.objects.create(value="203.0.113.7")
        self.assertTrue(BlockRule.blocks_participation("203.0.113.7"))
        BlockRule.objects.all().delete()
        self.assertFalse(BlockRule.blocks_participation("203.0.113.7"))


class DescribeTestCase(SimpleTestCase):
    @parameterized.expand(
        [
            (
                "known",
                "RU",
                geoip.ASN(64496, "Example Org"),
                "203.0.113.7 is in Russia (RU), on network AS64496 (Example Org)",
            ),
            (
                "unknown",
                None,
                None,
                "203.0.113.7 is in an unknown country, on an unknown network",
            ),
            (
                "no names",
                "ZZ",
                geoip.ASN(64496, ""),
                "203.0.113.7 is in ZZ, on network AS64496",
            ),
        ]
    )
    def test_describe(self, _, country, asn, description):
        visitor = Visitor("203.0.113.7")
        # Instead of looking them up.
        visitor.country = country
        visitor.asn = asn
        self.assertEqual(describe(visitor), description)


class BlockRuleAdminTestCase(BlockRuleTestCase):
    def setUp(self):
        super().setUp()
        self.admin = BlockRuleAdmin(BlockRule, AdminSite())
        self.user = G(User, is_staff=True, is_superuser=True)
        self.request = self.get()

    def get(self, data=None, **extra):
        request = RequestFactory().get("/", data, **extra)
        request.user = self.user
        return request

    def activate(self, request=None):
        """Run the activate action on every rule, returning the (message, level)
        pairs it shows.
        """
        with patch.object(self.admin, "message_user") as message_user:
            activate_selected(
                self.admin, request or self.request, BlockRule.objects.all()
            )
        return [call.args[1:] for call in message_user.call_args_list]

    def search(self, term, queryset=None):
        if queryset is None:
            queryset = BlockRule.objects.all()
        results, _ = self.admin.get_search_results(self.request, queryset, term)
        return results

    def status_messages(self, **query):
        """The (message, level) pairs that the changelist adds."""
        with patch.object(self.admin, "message_user") as message_user:
            self.admin.add_status_messages(self.get(query))
        return [call.args[1:] for call in message_user.call_args_list]

    def test_save_model_sets_created_by_on_add(self):
        rule = BlockRule(value="203.0.113.7")
        self.admin.save_model(self.request, rule, form=None, change=False)
        self.assertEqual(rule.created_by, self.user)

    def test_save_model_keeps_created_by_on_change(self):
        creator = G(User)
        rule = BlockRule.objects.create(value="203.0.113.7", created_by=creator)
        self.admin.save_model(self.request, rule, form=None, change=True)
        self.assertEqual(rule.created_by, creator)

    def test_search_by_ip_finds_rules_that_apply(self):
        self.country.return_value = "RU"
        self.asn.return_value = geoip.ASN(64496, "Example Org")
        apply = [
            BlockRule.objects.create(value="203.0.113.7"),
            BlockRule.objects.create(value="203.0.113.0/24"),
            BlockRule.objects.create(kind=Kind.COUNTRY, value="RU"),
            BlockRule.objects.create(kind=Kind.ASN, value="AS64496"),
        ]
        BlockRule.objects.create(value="198.51.100.0/24")
        BlockRule.objects.create(kind=Kind.COUNTRY, value="CN")
        BlockRule.objects.create(kind=Kind.ASN, value="AS64497")

        self.assertCountEqual(self.search("203.0.113.7"), apply)

    def test_search_by_ip_respects_existing_filters(self):
        BlockRule.objects.create(value="203.0.113.0/24", is_active=False)
        active = BlockRule.objects.create(value="203.0.113.0/28")

        results = self.search("203.0.113.7", BlockRule.objects.filter(is_active=True))
        self.assertCountEqual(results, [active])

    def test_search_by_ip_skips_malformed_rules(self):
        BlockRule.objects.bulk_create([BlockRule(value="not an ip")])
        rule = BlockRule.objects.create(value="203.0.113.7")
        self.assertCountEqual(self.search("203.0.113.7"), [rule])

    def test_search_by_country_name(self):
        russia = BlockRule.objects.create(kind=Kind.COUNTRY, value="RU")
        BlockRule.objects.create(kind=Kind.COUNTRY, value="CN")
        self.assertCountEqual(self.search("russia"), [russia])

    def test_search_by_reason(self):
        spam = BlockRule.objects.create(value="203.0.113.7", reason="spam signups")
        BlockRule.objects.create(value="198.51.100.1", reason="scraping")
        self.assertCountEqual(self.search("spam"), [spam])

    def test_deactivate_action_clears_cache(self):
        BlockRule.objects.create(value="203.0.113.7")
        self.assertTrue(BlockRule.blocks_participation("203.0.113.7"))

        with patch.object(self.admin, "message_user") as message_user:
            deactivate_selected(self.admin, self.request, BlockRule.objects.all())

        self.assertFalse(BlockRule.objects.get().is_active)
        self.assertFalse(BlockRule.blocks_participation("203.0.113.7"))
        message_user.assert_called_once_with(
            self.request, "Deactivated 1 block rule(s).", messages.SUCCESS
        )

    def test_activate_action_clears_cache(self):
        BlockRule.objects.create(value="203.0.113.7", is_active=False)
        self.assertFalse(BlockRule.blocks_participation("203.0.113.7"))

        self.assertEqual(
            self.activate(), [("Activated 1 block rule(s).", messages.SUCCESS)]
        )
        self.assertTrue(BlockRule.objects.get().is_active)
        self.assertTrue(BlockRule.blocks_participation("203.0.113.7"))

    def test_activate_action_wont_block_own_ip_from_entire_site(self):
        BlockRule.objects.create(
            value="203.0.113.0/24", block_entire_site=True, is_active=False
        )
        other_network = BlockRule.objects.create(
            value="198.51.100.0/24", block_entire_site=True, is_active=False
        )
        # Blocking only participation doesn't lock admins out.
        own_ip = BlockRule.objects.create(value="203.0.113.7", is_active=False)

        self.assertEqual(
            self.activate(self.get(HTTP_X_REAL_IP="203.0.113.7")),
            [
                (
                    "Didn't activate 203.0.113.0/24, which blocks the entire site: "
                    "203.0.113.0/24 includes your own IP address (203.0.113.7), so "
                    "this would lock you out of the admin. Edit it to block only "
                    "participation instead.",
                    messages.ERROR,
                ),
                ("Activated 2 block rule(s).", messages.SUCCESS),
            ],
        )
        self.assertCountEqual(
            BlockRule.objects.filter(is_active=True), [other_network, own_ip]
        )

    def test_activate_action_wont_block_entire_site_when_geoip_database_unusable(
        self,
    ):
        self.problem.return_value = "GeoLite2-Country.mmdb doesn't exist"
        BlockRule.objects.create(
            kind=Kind.COUNTRY, value="CN", block_entire_site=True, is_active=False
        )

        [(message, level)] = self.activate()
        self.assertIn(
            "Didn't activate China (CN), which blocks the entire site: Can't check "
            "whether this rule includes your own IP address (127.0.0.1)",
            message,
        )
        self.assertEqual(level, messages.ERROR)
        self.assertFalse(BlockRule.objects.get().is_active)

    def test_activate_action_doesnt_check_rules_already_active(self):
        # Activating them changes nothing.
        BlockRule.objects.create(value="203.0.113.0/24", block_entire_site=True)
        self.assertEqual(
            self.activate(self.get(HTTP_X_REAL_IP="203.0.113.7")),
            [("Activated 1 block rule(s).", messages.SUCCESS)],
        )

    @parameterized.expand(
        [
            ("activate", activate_selected, False),
            ("deactivate", deactivate_selected, True),
        ]
    )
    def test_action_sets_updated_at(self, _, action, is_active):
        BlockRule.objects.create(value="203.0.113.7", is_active=is_active)
        # update() skips auto_now, so this sticks.
        long_ago = timezone.now() - datetime.timedelta(days=1)
        BlockRule.objects.update(updated_at=long_ago)

        with patch.object(self.admin, "message_user"):
            action(self.admin, self.request, BlockRule.objects.all())

        rule = BlockRule.objects.get()
        self.assertEqual(rule.is_active, not is_active)
        self.assertGreater(rule.updated_at, long_ago)

    def test_no_status_messages_when_all_is_well(self):
        BlockRule.objects.create(kind=Kind.COUNTRY, value="RU")
        self.assertEqual(self.status_messages(), [])

    @override_settings(BLOCK_RULES_ENABLED=False)
    def test_warns_when_switched_off(self):
        [(message, level)] = self.status_messages()
        self.assertIn("Block rules are switched off", message)
        self.assertEqual(level, messages.WARNING)

    @override_settings(BLOCK_RULES_REPORT_ONLY=True)
    def test_warns_when_report_only(self):
        [(message, level)] = self.status_messages()
        self.assertIn("Block rules are in report-only mode", message)
        self.assertEqual(level, messages.WARNING)

    def test_warns_when_rules_in_effect_need_unusable_geoip_database(self):
        self.problem.side_effect = lambda edition: (
            "GeoLite2-Country.mmdb doesn't exist"
            if edition == geoip.COUNTRY_EDITION
            else None
        )
        BlockRule.objects.create(kind=Kind.COUNTRY, value="RU")
        BlockRule.objects.create(kind=Kind.ASN, value="AS64496")
        self.assertEqual(
            self.status_messages(),
            [
                (
                    "Country rules aren't blocking anyone, because "
                    "GeoLite2-Country.mmdb doesn't exist.",
                    messages.WARNING,
                )
            ],
        )

    def test_no_geoip_warning_without_rules_in_effect_that_need_it(self):
        self.problem.return_value = "it doesn't exist"
        BlockRule.objects.create(value="203.0.113.7")
        BlockRule.objects.create(kind=Kind.COUNTRY, value="RU", is_active=False)
        self.assertEqual(self.status_messages(), [])

    def test_describes_ip_searched_for(self):
        self.country.return_value = "RU"
        self.asn.return_value = geoip.ASN(64496, "Example Org")
        self.assertEqual(
            self.status_messages(q=" 203.0.113.7 "),
            [
                (
                    "203.0.113.7 is in Russia (RU), on network AS64496 (Example "
                    "Org). Showing the rules that apply to it.",
                    messages.INFO,
                )
            ],
        )

    def test_ip_search_warns_about_unusable_geoip_databases(self):
        self.problem.return_value = "it doesn't exist"
        warnings = [
            message
            for message, level in self.status_messages(q="203.0.113.7")
            if level == messages.WARNING
        ]
        self.assertEqual(
            warnings,
            [
                "Country rules aren't blocking anyone, because it doesn't exist.",
                "Network owner (ASN) rules aren't blocking anyone, because it "
                "doesn't exist.",
            ],
        )


class BlockRuleAdminFormTestCase(BlockRuleTestCase):
    def setUp(self):
        super().setUp()
        self.admin = BlockRuleAdmin(BlockRule, AdminSite())
        self.request = RequestFactory().get("/", HTTP_X_REAL_IP="203.0.113.7")
        self.request.user = G(User, is_staff=True, is_superuser=True)

    def make_form(self, instance=None, **data):
        form_class = self.admin.get_form(self.request, instance)
        return form_class(
            data={"kind": Kind.IP, "is_active": True, "reason": "", **data},
            instance=instance,
        )

    def test_cannot_block_own_ip_from_entire_site(self):
        form = self.make_form(value="203.0.113.0/24", block_entire_site=True)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors["block_entire_site"],
            [
                "203.0.113.0/24 includes your own IP address (203.0.113.7), so this "
                "would lock you out of the admin. Uncheck this to block only "
                "participation."
            ],
        )

    def test_cannot_block_own_country_from_entire_site(self):
        self.country.return_value = "RU"
        form = self.make_form(kind=Kind.COUNTRY, value="Russia", block_entire_site=True)
        self.assertFalse(form.is_valid())
        self.assertIn(
            "Russia (RU) includes your own IP address",
            form.errors["block_entire_site"][0],
        )

    def test_cannot_block_own_network_from_entire_site(self):
        self.asn.return_value = geoip.ASN(64496, "Example Org")
        form = self.make_form(kind=Kind.ASN, value="64496", block_entire_site=True)
        self.assertFalse(form.is_valid())
        self.assertIn(
            "AS64496 includes your own IP address",
            form.errors["block_entire_site"][0],
        )

    def test_cannot_block_entire_site_when_geoip_database_unusable(self):
        self.problem.return_value = "GeoLite2-Country.mmdb doesn't exist"
        form = self.make_form(kind=Kind.COUNTRY, value="CN", block_entire_site=True)
        self.assertFalse(form.is_valid())
        [error] = form.errors["block_entire_site"]
        self.assertIn(
            "Can't check whether this rule includes your own IP address (203.0.113.7)",
            error,
        )
        self.assertIn("because GeoLite2-Country.mmdb doesn't exist", error)

    @parameterized.expand(
        [
            ("participation only", {"value": "203.0.113.0/24"}),
            (
                "inactive",
                {
                    "value": "203.0.113.0/24",
                    "block_entire_site": True,
                    "is_active": False,
                },
            ),
            ("other network", {"value": "198.51.100.0/24", "block_entire_site": True}),
            (
                "other country",
                {"kind": Kind.COUNTRY, "value": "CN", "block_entire_site": True},
            ),
        ]
    )
    def test_allowed(self, _, data):
        self.country.return_value = "RU"
        form = self.make_form(**data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_ip_rules_dont_need_geoip_databases(self):
        self.problem.return_value = "it doesn't exist"
        form = self.make_form(value="198.51.100.0/24", block_entire_site=True)
        self.assertTrue(form.is_valid(), form.errors)

    @parameterized.expand(
        [
            ("internal ip", Kind.IP, "10.0.0.1", "overlaps the internal range"),
            ("unknown country", Kind.COUNTRY, "Narnia", "isn't a country we recognize"),
            ("not an AS number", Kind.ASN, "ASX", "isn't an AS number"),
        ]
    )
    def test_invalid_value_shown_on_value_field(self, _, kind, value, error):
        with self.settings(BLOCK_RULES_ALLOW_INTERNAL=False):
            form = self.make_form(kind=kind, value=value, block_entire_site=True)
            self.assertFalse(form.is_valid())
        self.assertEqual(list(form.errors), ["value"])
        self.assertIn(error, form.errors["value"][0])

    def test_duplicate_rule(self):
        BlockRule.objects.create(kind=Kind.COUNTRY, value="RU")
        form = self.make_form(kind=Kind.COUNTRY, value="Russia")
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors["__all__"],
            ["There's already a rule for this. Edit that rule instead."],
        )

    def test_editing_rule_is_not_a_duplicate(self):
        rule = BlockRule.objects.create(kind=Kind.COUNTRY, value="RU")
        form = self.make_form(
            instance=rule, kind=Kind.COUNTRY, value="Russia", reason="spam"
        )
        self.assertTrue(form.is_valid(), form.errors)


class BlockRuleAdminPagesTestCase(BlockRuleTestCase):
    """The admin pages, through the full middleware stack."""

    def setUp(self):
        super().setUp()
        self.user = G(User, is_active=True, is_staff=True, is_superuser=True)
        GoogleAuthenticatorTOTP.objects.create(user=self.user, activated=True)
        self.client.force_login(self.user)
        session = self.client.session
        session[TWO_FACTOR_AUTH_SESSION_KEY] = True
        session.save()
        self.changelist_url = reverse("admin:web_blockrule_changelist")
        self.add_url = reverse("admin:web_blockrule_add")

    def test_changelist(self):
        BlockRule.objects.create(value="203.0.113.0/24")
        BlockRule.objects.create(kind=Kind.COUNTRY, value="RU")
        response = self.client.get(self.changelist_url)
        self.assertContains(response, "203.0.113.0/24")
        self.assertContains(response, "Russia (RU)")

    def test_search_by_ip(self):
        self.country.return_value = "RU"
        rule = BlockRule.objects.create(kind=Kind.COUNTRY, value="RU")
        BlockRule.objects.create(kind=Kind.COUNTRY, value="CN")
        response = self.client.get(self.changelist_url, {"q": "203.0.113.7"})
        self.assertContains(
            response, "203.0.113.7 is in Russia (RU), on an unknown network."
        )
        self.assertEqual(list(response.context["cl"].result_list), [rule])

    def test_add_rule(self):
        self.assertEqual(self.client.get(self.add_url).status_code, 200)
        response = self.client.post(
            self.add_url,
            {
                "kind": Kind.COUNTRY,
                "value": "Russia",
                "reason": "Spam signups",
                "is_active": "on",
            },
        )
        self.assertRedirects(response, self.changelist_url)
        rule = BlockRule.objects.get()
        self.assertEqual(
            (rule.kind, rule.value, rule.created_by), (Kind.COUNTRY, "RU", self.user)
        )

    @override_settings(BLOCK_RULES_ENABLED=False)
    def test_status_messages_shown_once_after_action(self):
        rule = BlockRule.objects.create(value="203.0.113.7")
        response = self.client.post(
            self.changelist_url,
            {
                "action": "deactivate_selected",
                "_selected_action": [rule.pk],
                "index": 0,
            },
            follow=True,
        )
        self.assertContains(response, "Deactivated 1 block rule(s).")
        self.assertContains(response, "Block rules are switched off", count=1)

    def test_activate_action(self):
        rule = BlockRule.objects.create(value="203.0.113.7", is_active=False)
        response = self.client.post(
            self.changelist_url,
            {
                "action": "activate_selected",
                "_selected_action": [rule.pk],
                "index": 0,
            },
            follow=True,
        )
        self.assertContains(response, "Activated 1 block rule(s).")
        rule.refresh_from_db()
        self.assertTrue(rule.is_active)
