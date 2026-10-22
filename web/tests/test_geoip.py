import datetime
import ipaddress
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import maxminddb
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from web import geoip


class FakeReader:
    """Stands in for a maxminddb reader, since the tests can't make real
    databases.
    """

    def __init__(self, records=None, age=datetime.timedelta(days=1)):
        self.records = records or {}
        self.build_epoch = int((timezone.now() - age).timestamp())

    def metadata(self):
        return SimpleNamespace(build_epoch=self.build_epoch)

    def get(self, ip):
        # Raises ValueError for anything else, like the real reader.
        ipaddress.ip_address(ip)
        return self.records.get(ip)

    def __iter__(self):
        # The real reader yields every network in the database with its record.
        for ip, record in self.records.items():
            yield ipaddress.ip_network(ip), record


class GeoIPTestCase(SimpleTestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(override_settings(GEOIP_PATH=self.directory))
        # So each test opens the databases afresh.
        self.enterContext(patch.dict(geoip._databases, clear=True))

    def use_reader(self, reader):
        return self.enterContext(patch("maxminddb.open_database", return_value=reader))

    def test_missing_database(self):
        path = os.path.join(self.directory, "GeoLite2-Country.mmdb")
        self.assertEqual(geoip.problem(geoip.COUNTRY_EDITION), f"{path} doesn't exist")

        with self.assertLogs("web.geoip", level="ERROR") as logs:
            self.assertIsNone(geoip.country("203.0.113.7"))
            self.assertIsNone(geoip.country("198.51.100.1"))
        # Once, not for every lookup.
        self.assertEqual(len(logs.records), 1)
        self.assertIn(f"{path} doesn't exist", logs.output[0])

    def test_unreadable_database(self):
        path = os.path.join(self.directory, "GeoLite2-ASN.mmdb")
        with open(path, "wb") as f:
            f.write(b"not a database")
        self.assertIn(f"{path} couldn't be read", geoip.problem(geoip.ASN_EDITION))

        with self.assertLogs("web.geoip", level="ERROR"):
            self.assertIsNone(geoip.asn("203.0.113.7"))

    def test_old_database(self):
        self.use_reader(
            FakeReader(
                {"203.0.113.7": {"country": {"iso_code": "RU"}}},
                age=datetime.timedelta(days=31),
            )
        )
        self.assertIn("more than 30 days ago", geoip.problem(geoip.COUNTRY_EDITION))

        with self.assertLogs("web.geoip", level="ERROR"):
            self.assertIsNone(geoip.country("203.0.113.7"))

    def test_database_becomes_too_old_while_open(self):
        self.use_reader(FakeReader(age=datetime.timedelta(days=29)))
        self.assertIsNone(geoip.problem(geoip.COUNTRY_EDITION))

        later = timezone.now() + datetime.timedelta(days=2)
        with patch("web.geoip.timezone.now", return_value=later):
            self.assertIn("more than 30 days ago", geoip.problem(geoip.COUNTRY_EDITION))

    def test_database_is_opened_once(self):
        open_database = self.use_reader(FakeReader())
        geoip.country("203.0.113.7")
        geoip.country("198.51.100.1")
        open_database.assert_called_once()

    def test_country(self):
        self.use_reader(
            FakeReader(
                {
                    "203.0.113.7": {
                        "country": {"iso_code": "RU"},
                        "registered_country": {"iso_code": "NL"},
                    },
                    # MaxMind couldn't locate this one, so only knows where it's
                    # registered.
                    "198.51.100.1": {"registered_country": {"iso_code": "NL"}},
                }
            )
        )
        self.assertEqual(geoip.country("203.0.113.7"), "RU")
        self.assertEqual(geoip.country("198.51.100.1"), "NL")
        self.assertIsNone(geoip.country("192.0.2.1"))

    def test_asn(self):
        self.use_reader(
            FakeReader(
                {
                    "203.0.113.7": {
                        "autonomous_system_number": 64496,
                        "autonomous_system_organization": "Example Org",
                    },
                    "198.51.100.1": {"autonomous_system_number": 64497},
                }
            )
        )
        self.assertEqual(geoip.asn("203.0.113.7"), geoip.ASN(64496, "Example Org"))
        self.assertEqual(geoip.asn("198.51.100.1"), geoip.ASN(64497, ""))
        self.assertIsNone(geoip.asn("192.0.2.1"))

    def test_organizations(self):
        example_org = {
            "autonomous_system_number": 64496,
            "autonomous_system_organization": "Example Org",
        }
        self.use_reader(
            FakeReader(
                {
                    # Two of the same network's ranges.
                    "203.0.113.7": example_org,
                    "203.0.113.8": example_org,
                    "198.51.100.1": {"autonomous_system_number": 64497},
                    "192.0.2.1": {
                        "autonomous_system_number": 64498,
                        "autonomous_system_organization": "Other Org",
                    },
                }
            )
        )
        self.assertEqual(
            geoip.organizations([64496, 64497, 64499]),
            {64496: "Example Org", 64497: ""},
        )

    def test_invalid_ip(self):
        self.use_reader(FakeReader())
        self.assertIsNone(geoip.country("not an ip"))
        self.assertIsNone(geoip.asn(""))

    def test_lookup_error_is_logged(self):
        reader = FakeReader()
        self.use_reader(reader)
        with (
            patch.object(
                reader, "get", side_effect=maxminddb.InvalidDatabaseError("corrupt")
            ),
            self.assertLogs("web.geoip", level="ERROR"),
        ):
            self.assertIsNone(geoip.country("203.0.113.7"))
