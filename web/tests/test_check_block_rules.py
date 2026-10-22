import csv
import io
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from web import geoip
from web.models import BlockRule

SITE_IP = "203.0.113.7"
PARTICIPATION_IP = "198.51.100.1"
OTHER_IP = "192.0.2.1"


class CheckBlockRulesTestCase(TestCase):
    def setUp(self):
        # Rolling back a test's rules doesn't clear the cache.
        BlockRule.clear_cache()
        self.addCleanup(BlockRule.clear_cache)
        self.country = self.enterContext(patch("web.geoip.country", return_value=None))
        self.asn = self.enterContext(patch("web.geoip.asn", return_value=None))
        self.problem = self.enterContext(patch("web.geoip.problem", return_value=None))
        self.site_rule = BlockRule.objects.create(value=SITE_IP, block_entire_site=True)
        self.participation_rule = BlockRule.objects.create(value="198.51.100.0/24")

    def check(self, *args, stdin=None):
        out, err = io.StringIO(), io.StringIO()
        # Run the system checks too, like manage.py does.
        options = {"stdout": out, "stderr": err, "skip_checks": False}
        if stdin is not None:
            options["stdin"] = io.StringIO(stdin)
        call_command("check_block_rules", *args, **options)
        return out.getvalue(), err.getvalue()

    def test_addresses_as_arguments(self):
        out, err = self.check(SITE_IP, PARTICIPATION_IP, OTHER_IP, "nonsense")
        self.assertEqual(err, "")
        lines = out.splitlines()
        self.assertEqual(
            lines[:4],
            [
                f"{SITE_IP} is in an unknown country, on an unknown network: blocked "
                f"from the entire site by rule {self.site_rule.pk} ({SITE_IP})",
                f"{PARTICIPATION_IP} is in an unknown country, on an unknown "
                "network: blocked from participating by rule "
                f"{self.participation_rule.pk} (198.51.100.0/24)",
                f"{OTHER_IP} is in an unknown country, on an unknown network: "
                "not blocked",
                "nonsense: not an IP address",
            ],
        )
        self.assertIn(
            "Checked 4 address(es): 1 blocked from the entire site, 1 blocked from "
            "participating, 1 not blocked, and 1 not IP addresses.",
            out,
        )

    def test_reads_standard_input(self):
        out, _ = self.check(
            "-",
            stdin=f"# Known spammers\n{SITE_IP}\n\n  {OTHER_IP}  # from the form\n",
        )
        self.assertIn(f"{SITE_IP} is in", out)
        self.assertIn(f"{OTHER_IP} is in", out)
        self.assertIn("Checked 2 address(es)", out)

    def test_summarizes_unblocked_addresses(self):
        self.country.return_value = "GB"
        self.asn.return_value = geoip.ASN(9009, "M247 Europe SRL")
        out, _ = self.check(OTHER_IP, "192.0.2.2", SITE_IP)
        self.assertIn(
            "The unblocked addresses' commonest networks:\n"
            "  AS9009 (M247 Europe SRL): 2",
            out,
        )
        self.assertIn("The unblocked addresses' commonest countries:\n  GB: 2", out)

    def test_no_summary_of_unblocked_addresses_when_all_blocked(self):
        out, _ = self.check(SITE_IP)
        self.assertNotIn("commonest", out)

    def test_csv(self):
        self.country.return_value = "GB"
        self.asn.return_value = geoip.ASN(9009, "M247 Europe SRL")
        out, err = self.check("--csv", PARTICIPATION_IP, "nonsense")
        self.assertEqual(
            list(csv.reader(io.StringIO(out))),
            [
                [
                    "address",
                    "blocked from",
                    "rule",
                    "rule value",
                    "country",
                    "asn",
                    "network owner",
                ],
                [
                    PARTICIPATION_IP,
                    "participation",
                    str(self.participation_rule.pk),
                    "198.51.100.0/24",
                    "GB",
                    "AS9009",
                    "M247 Europe SRL",
                ],
                ["nonsense", "not an IP address", "", "", "", "", ""],
            ],
        )
        self.assertIn("Checked 2 address(es)", err)

    @override_settings(BLOCK_RULES_ENABLED=False)
    def test_warns_when_switched_off(self):
        out, err = self.check(SITE_IP)
        self.assertIn("Block rules are switched off", err)
        self.assertIn(f"{SITE_IP} is in an unknown country", out)

    def test_warns_about_unusable_geoip_databases(self):
        self.problem.side_effect = lambda edition: (
            "it's missing" if edition == geoip.EDITIONS[0] else None
        )
        _, err = self.check(SITE_IP)
        self.assertIn(
            f"Can't look up countries or network owners in {geoip.EDITIONS[0]}, "
            "because it's missing",
            err,
        )
