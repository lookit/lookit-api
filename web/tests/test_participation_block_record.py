import datetime
import ipaddress
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from django_dynamic_fixture import G
from parameterized import parameterized

from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from accounts.models import GoogleAuthenticatorTOTP, User
from web import geoip
from web.models import BlockRule, ParticipationBlockRecord, recorded_network


class RecordedNetworkTestCase(SimpleTestCase):
    @parameterized.expand(
        [
            ("IPv4", "203.0.113.7", "203.0.113.0/24"),
            ("IPv6", "2001:db8:1234:5678::1", "2001:db8:1234::/48"),
        ]
    )
    def test_recorded_network(self, _, address, network):
        self.assertEqual(str(recorded_network(ipaddress.ip_address(address))), network)


class ParticipationBlockRecordTestCase(TestCase):
    def setUp(self):
        # Rolling back a test's rules doesn't clear the cache.
        BlockRule.clear_cache()
        self.addCleanup(BlockRule.clear_cache)
        self.country = self.enterContext(patch("web.geoip.country", return_value=None))
        self.asn = self.enterContext(patch("web.geoip.asn", return_value=None))
        self.rule = BlockRule.objects.create(value="203.0.113.0/24")
        self.user = G(User)

    def record(self, ip="203.0.113.7"):
        block = BlockRule.participation_block(ip)
        ParticipationBlockRecord.record(self.user, block)

    def test_first_block_creates_record(self):
        self.country.return_value = "GB"
        self.asn.return_value = geoip.ASN(9009, "M247 Europe SRL")
        self.record()
        record = ParticipationBlockRecord.objects.get()
        self.assertEqual(
            (
                record.user,
                record.rule,
                record.times_blocked,
                record.network,
                record.country,
                record.asn,
                record.asn_organization,
            ),
            (self.user, self.rule, 1, "203.0.113.0/24", "GB", 9009, "M247 Europe SRL"),
        )
        self.assertEqual(record.first_blocked_at, record.last_blocked_at)

    def test_unknown_country_and_network(self):
        self.record()
        record = ParticipationBlockRecord.objects.get()
        self.assertEqual(
            (record.country, record.asn, record.asn_organization), ("", None, "")
        )

    def test_ipv4_mapped_address_recorded_as_ipv4(self):
        self.record("::ffff:203.0.113.7")
        self.assertEqual(
            ParticipationBlockRecord.objects.get().network, "203.0.113.0/24"
        )

    def test_later_blocks_update_record(self):
        self.record()
        first = ParticipationBlockRecord.objects.get()
        later = first.first_blocked_at + datetime.timedelta(hours=1)
        self.country.return_value = "FR"
        with patch("django.utils.timezone.now", return_value=later):
            self.record("203.0.113.200")

        record = ParticipationBlockRecord.objects.get()
        self.assertEqual(record.times_blocked, 2)
        self.assertEqual(record.first_blocked_at, first.first_blocked_at)
        self.assertEqual(record.last_blocked_at, later)
        self.assertEqual(record.country, "FR")

    def test_one_record_per_user_and_rule(self):
        other_rule = BlockRule.objects.create(value="198.51.100.0/24")
        other_user = G(User)
        self.record()
        self.record("198.51.100.1")
        ParticipationBlockRecord.record(
            other_user, BlockRule.participation_block("203.0.113.7")
        )
        self.assertEqual(
            set(
                ParticipationBlockRecord.objects.values_list(
                    "user", "rule", "times_blocked"
                )
            ),
            {
                (self.user.pk, self.rule.pk, 1),
                (self.user.pk, other_rule.pk, 1),
                (other_user.pk, self.rule.pk, 1),
            },
        )

    def test_rule_deleted_while_cached_not_recorded(self):
        block = BlockRule.participation_block("203.0.113.7")
        BlockRule.objects.filter(pk=self.rule.pk).delete()
        ParticipationBlockRecord.record(self.user, block)
        self.assertFalse(ParticipationBlockRecord.objects.exists())

    def test_deleting_rule_deletes_records(self):
        self.record()
        self.rule.delete()
        self.assertFalse(ParticipationBlockRecord.objects.exists())

    def test_str(self):
        self.record()
        self.assertEqual(
            str(ParticipationBlockRecord.objects.get()),
            f"Rule {self.rule.pk} stopped user {self.user.pk}",
        )


class ParticipationBlockRecordAdminTestCase(TestCase):
    def setUp(self):
        BlockRule.clear_cache()
        self.addCleanup(BlockRule.clear_cache)
        admin = G(User, is_active=True, is_staff=True, is_superuser=True)
        GoogleAuthenticatorTOTP.objects.create(user=admin, activated=True)
        self.client.force_login(admin)
        session = self.client.session
        session[TWO_FACTOR_AUTH_SESSION_KEY] = True
        session.save()

        self.rule = BlockRule.objects.create(value="203.0.113.0/24")
        self.other_rule = BlockRule.objects.create(value="198.51.100.0/24")
        now = timezone.now()
        self.record = ParticipationBlockRecord.objects.create(
            user=G(User),
            rule=self.rule,
            first_blocked_at=now,
            last_blocked_at=now,
            network="203.0.113.0/24",
            country="GB",
            asn=9009,
            asn_organization="M247 Europe SRL",
        )
        self.changelist_url = reverse("admin:web_participationblockrecord_changelist")

    def test_changelist(self):
        response = self.client.get(self.changelist_url)
        self.assertContains(response, self.record.user.uuid)
        self.assertContains(response, "203.0.113.0/24")
        self.assertContains(response, "M247 Europe SRL")

    def test_filter_by_rule(self):
        response = self.client.get(self.changelist_url, {"rule": self.other_rule.pk})
        self.assertEqual(list(response.context["cl"].result_list), [])
        response = self.client.get(self.changelist_url, {"rule": self.rule.pk})
        self.assertEqual(list(response.context["cl"].result_list), [self.record])

    def test_view_only(self):
        self.assertEqual(
            self.client.get(
                reverse("admin:web_participationblockrecord_add")
            ).status_code,
            403,
        )
        change_url = reverse(
            "admin:web_participationblockrecord_change", args=[self.record.pk]
        )
        response = self.client.get(change_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="_save"')

    def test_rules_show_participants_stopped(self):
        response = self.client.get(reverse("admin:web_blockrule_changelist"))
        rules = {rule.pk: rule for rule in response.context["cl"].result_list}
        self.assertEqual(rules[self.rule.pk].participants, 1)
        self.assertEqual(rules[self.other_rule.pk].participants, 0)
        self.assertContains(
            response, f'href="{self.changelist_url}?rule={self.rule.pk}"'
        )
