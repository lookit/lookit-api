import io
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from parameterized import parameterized

from web import geoip
from web.models import BlockRule, canonical_asn
from web.vpn_asns import (
    BAD_ASN_LIST,
    OWNER_NAME,
    SPAM_HOSTING,
    SPAM_SIGNUPS,
    TOR,
    VPN,
    VPN_HOSTING,
    VPN_NETWORKS,
    X4BNET,
    VPNNetwork,
)

Kind = BlockRule.Kind

# MaxMind's name for each network's owner, as when the list was checked.
OWNERS = {network.asn: network.organization for network in VPN_NETWORKS}


class VPNNetworksTestCase(SimpleTestCase):
    def test_numbers_are_valid_and_unique(self):
        values = [canonical_asn(str(network.asn)) for network in VPN_NETWORKS]
        self.assertEqual(values, [f"AS{network.asn}" for network in VPN_NETWORKS])
        self.assertEqual(len(set(values)), len(values))

    def test_categories_and_sources(self):
        for network in VPN_NETWORKS:
            with self.subTest(network.asn):
                self.assertIn(network.category, (VPN, TOR, VPN_HOSTING, SPAM_HOSTING))
                self.assertIsInstance(network.sources, tuple)
                self.assertTrue(network.sources)
                self.assertLessEqual(
                    set(network.sources),
                    {X4BNET, BAD_ASN_LIST, OWNER_NAME, SPAM_SIGNUPS},
                )

    def test_leaves_out_networks_ordinary_visitors_use(self):
        # iCloud Private Relay (Akamai, Cloudflare and Fastly), Zscaler's and
        # Netskope's corporate security gateways, and home and business ISPs that
        # spammers' sign-ups came from (Verizon, AT&T, Charter and Level 3).
        never_block = {36183, 13335, 54113, 53813, 55256, 701, 7018, 33363, 20001, 3356}
        self.assertFalse(never_block & {network.asn for network in VPN_NETWORKS})

    @parameterized.expand(
        [
            (
                "provider and owner differ",
                VPN,
                "NordVPN",
                "PacketHub S.A.",
                "VPN: NordVPN (PacketHub S.A.)",
            ),
            ("provider owns it", VPN, "Windscribe", "Windscribe", "VPN: Windscribe"),
            (
                "owner in different case",
                TOR,
                "Unredacted Inc",
                "UNREDACTED INC",
                "Tor exit relays: Unredacted Inc",
            ),
            (
                "hosting",
                VPN_HOSTING,
                "M247",
                "M247 Europe SRL",
                "Hosting used by VPNs: M247 (M247 Europe SRL)",
            ),
            (
                "spammers' hosting",
                SPAM_HOSTING,
                "Leaseweb",
                "Leaseweb USA, Inc.",
                "Cloud and hosting used by spammers: Leaseweb (Leaseweb USA, Inc.)",
            ),
        ]
    )
    def test_reason(self, _, category, provider, organization, reason):
        network = VPNNetwork(64496, category, provider, organization, (OWNER_NAME,))
        self.assertEqual(network.reason, reason)


class LoadVPNASNRulesTestCase(TestCase):
    def setUp(self):
        self.problem = self.enterContext(patch("web.geoip.problem", return_value=None))
        self.organizations = self.enterContext(
            patch("web.geoip.organizations", return_value=OWNERS)
        )

    def run_command(self, *args):
        """Run the command, returning what it wrote to stdout and stderr."""
        stdout, stderr = io.StringIO(), io.StringIO()
        call_command(
            "load_vpn_asn_rules", *args, stdout=stdout, stderr=stderr, no_color=True
        )
        return stdout.getvalue(), stderr.getvalue()

    def test_adds_participation_only_rule_for_each_network(self):
        stdout, stderr = self.run_command()

        self.assertCountEqual(
            BlockRule.objects.values_list(
                "kind",
                "value",
                "reason",
                "is_active",
                "block_entire_site",
                "expires_at",
                "created_by",
            ),
            [
                (Kind.ASN, f"AS{network.asn}", network.reason, True, False, None, None)
                for network in VPN_NETWORKS
            ],
        )
        self.organizations.assert_called_once_with(
            [network.asn for network in VPN_NETWORKS]
        )
        self.assertIn(
            "Added a rule for AS136787: VPN: NordVPN (PacketHub S.A.)", stdout
        )
        self.assertIn(
            f"Added {len(VPN_NETWORKS)} rule(s), left 0 existing rule(s) as they "
            "were, and skipped 0 network(s). The web servers start using new rules "
            "within",
            stdout,
        )
        self.assertEqual(stderr, "")

    def test_dry_run_adds_nothing(self):
        stdout, _ = self.run_command("--dry-run")
        self.assertFalse(BlockRule.objects.exists())
        self.assertIn(
            "Would add a rule for AS136787: VPN: NordVPN (PacketHub S.A.)", stdout
        )
        self.assertIn(
            f"Dry run, so nothing changed. Would add {len(VPN_NETWORKS)} rule(s), "
            "leave 0 existing rule(s) as they are, and skip 0 network(s).",
            stdout,
        )

    def test_leaves_existing_rules_as_they_are(self):
        # e.g. one an admin deactivated because it blocked people it shouldn't.
        rule = BlockRule.objects.create(
            kind=Kind.ASN,
            value="AS9009",
            reason="Too many false positives",
            is_active=False,
        )

        stdout, _ = self.run_command()

        rule.refresh_from_db()
        self.assertFalse(rule.is_active)
        self.assertEqual(rule.reason, "Too many false positives")
        self.assertEqual(BlockRule.objects.count(), len(VPN_NETWORKS))
        self.assertIn("AS9009 (M247) already has a rule, so leaving it.", stdout)
        self.assertIn(
            f"Added {len(VPN_NETWORKS) - 1} rule(s), left 1 existing rule(s) as they "
            "were",
            stdout,
        )

    def test_running_again_adds_nothing(self):
        self.run_command()
        stdout, _ = self.run_command()
        self.assertEqual(BlockRule.objects.count(), len(VPN_NETWORKS))
        self.assertIn(
            f"Added 0 rule(s), left {len(VPN_NETWORKS)} existing rule(s) as they were, "
            "and skipped 0 network(s).",
            stdout,
        )
        self.assertNotIn("start using new rules", stdout)

    def test_skips_network_whose_owner_changed(self):
        self.organizations.return_value = {**OWNERS, 9009: "Someone Else Ltd"}

        stdout, stderr = self.run_command()

        self.assertFalse(BlockRule.objects.filter(value="AS9009").exists())
        self.assertEqual(BlockRule.objects.count(), len(VPN_NETWORKS) - 1)
        self.assertIn(
            "Skipping AS9009 (M247): GeoLite2-ASN says 'Someone Else Ltd' owns it "
            "now, not 'M247 Europe SRL'.",
            stderr,
        )
        self.assertIn("and skipped 1 network(s).", stdout)

    def test_owner_names_compared_ignoring_case(self):
        self.organizations.return_value = {**OWNERS, 136787: "PACKETHUB S.A."}
        _, stderr = self.run_command()
        self.assertTrue(BlockRule.objects.filter(value="AS136787").exists())
        self.assertEqual(stderr, "")

    def test_skips_network_not_in_database(self):
        self.organizations.return_value = {
            asn: organization for asn, organization in OWNERS.items() if asn != 9009
        }

        stdout, stderr = self.run_command()

        self.assertFalse(BlockRule.objects.filter(value="AS9009").exists())
        self.assertIn("Skipping AS9009 (M247), which isn't in GeoLite2-ASN.", stderr)
        self.assertIn("and skipped 1 network(s).", stdout)

    def test_unusable_database(self):
        self.problem.return_value = "/geoip/GeoLite2-ASN.mmdb doesn't exist"
        with self.assertRaisesMessage(
            CommandError,
            "Can't check who owns each network, because /geoip/GeoLite2-ASN.mmdb "
            "doesn't exist. Run manage.py download_geoip_databases first.",
        ):
            self.run_command()
        self.problem.assert_called_once_with(geoip.ASN_EDITION)
        self.organizations.assert_not_called()
        self.assertFalse(BlockRule.objects.exists())
