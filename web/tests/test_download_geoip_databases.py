import io
import os
import tarfile
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import maxminddb
import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from web import geoip

ACCOUNT_ID = "123456"
LICENSE_KEY = "test-license-key"


def make_archive(edition, database_type=None, include_database=True):
    """A tar.gz laid out like MaxMind's downloads, holding a fake database whose
    contents are its database type (see FakeReader).
    """
    files = {"LICENSE.txt": b"license"}
    if include_database:
        files[f"{edition}.mmdb"] = (database_type or edition).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, contents in files.items():
            info = tarfile.TarInfo(f"{edition}_20261020/{name}")
            info.size = len(contents)
            tar.addfile(info, io.BytesIO(contents))
    return buffer.getvalue()


def make_response(content=b"", status_code=200):
    response = requests.Response()
    response.status_code = status_code
    response.raw = io.BytesIO(content)
    return response


class FakeReader:
    """Stands in for a maxminddb reader of the fake databases in make_archive."""

    def __init__(self, path):
        with open(path) as f:
            self.database_type = f.read()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        pass

    def metadata(self):
        return SimpleNamespace(database_type=self.database_type)


class DownloadGeoIPDatabasesTestCase(SimpleTestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(override_settings(GEOIP_PATH=self.directory))
        self.enterContext(
            patch.dict(
                os.environ,
                {"MAXMIND_ACCOUNT_ID": ACCOUNT_ID, "MAXMIND_LICENSE_KEY": LICENSE_KEY},
            )
        )
        self.enterContext(patch("maxminddb.open_database", FakeReader))
        self.archives = {edition: make_archive(edition) for edition in geoip.EDITIONS}
        self.get = self.enterContext(patch("requests.get", side_effect=self.download))

    def download(self, url, **kwargs):
        # e.g. https://download.maxmind.com/geoip/databases/GeoLite2-ASN/download?suffix=tar.gz
        edition = url.split("/")[-2]
        return make_response(self.archives[edition])

    def run_command(self):
        stdout = io.StringIO()
        # Run the system checks first, like manage.py does.
        call_command("download_geoip_databases", stdout=stdout, skip_checks=False)
        return stdout.getvalue()

    def database_path(self, edition):
        return os.path.join(self.directory, f"{edition}.mmdb")

    def read_database(self, edition):
        with open(self.database_path(edition)) as f:
            return f.read()

    def write_database(self, edition, contents):
        with open(self.database_path(edition), "w") as f:
            f.write(contents)

    def test_downloads_databases(self):
        output = self.run_command()

        # And nothing else, e.g. temporary files.
        self.assertCountEqual(
            os.listdir(self.directory), ["GeoLite2-Country.mmdb", "GeoLite2-ASN.mmdb"]
        )
        for edition in geoip.EDITIONS:
            self.assertEqual(self.read_database(edition), edition)
        self.get.assert_any_call(
            "https://download.maxmind.com/geoip/databases/GeoLite2-Country/download?suffix=tar.gz",
            auth=(ACCOUNT_ID, LICENSE_KEY),
            stream=True,
            timeout=60,
        )
        self.assertIn("Done", output)

    def test_replaces_old_databases(self):
        self.write_database(geoip.COUNTRY_EDITION, "old")
        self.run_command()
        self.assertEqual(
            self.read_database(geoip.COUNTRY_EDITION), geoip.COUNTRY_EDITION
        )

    def test_missing_credentials(self):
        del os.environ["MAXMIND_LICENSE_KEY"]
        with self.assertRaisesMessage(
            CommandError, "Set MAXMIND_ACCOUNT_ID and MAXMIND_LICENSE_KEY"
        ):
            self.run_command()
        self.get.assert_not_called()

    def test_rejected_credentials(self):
        self.get.side_effect = lambda url, **kwargs: make_response(status_code=401)
        with self.assertRaisesMessage(CommandError, "MaxMind didn't accept"):
            self.run_command()

    def test_server_error(self):
        self.get.side_effect = lambda url, **kwargs: make_response(status_code=503)
        with self.assertRaisesMessage(
            CommandError, "Couldn't download GeoLite2-Country: 503 Server Error"
        ):
            self.run_command()

    def test_network_error(self):
        self.get.side_effect = requests.ConnectionError("no network")
        with self.assertRaisesMessage(
            CommandError, "Couldn't download GeoLite2-Country: no network"
        ):
            self.run_command()

    def test_not_an_archive(self):
        self.archives[geoip.COUNTRY_EDITION] = b"<html>Sign in</html>"
        with self.assertRaisesMessage(
            CommandError, "The GeoLite2-Country download isn't a valid archive"
        ):
            self.run_command()

    def test_archive_without_database(self):
        self.archives[geoip.COUNTRY_EDITION] = make_archive(
            geoip.COUNTRY_EDITION, include_database=False
        )
        with self.assertRaisesMessage(
            CommandError, "The GeoLite2-Country download has no GeoLite2-Country.mmdb."
        ):
            self.run_command()

    def test_invalid_database(self):
        self.enterContext(
            patch(
                "maxminddb.open_database",
                side_effect=maxminddb.InvalidDatabaseError("corrupt"),
            )
        )
        with self.assertRaisesMessage(
            CommandError,
            "The GeoLite2-Country download isn't a valid database: corrupt",
        ):
            self.run_command()

    def test_wrong_database_keeps_old_one(self):
        self.write_database(geoip.COUNTRY_EDITION, "old")
        self.archives[geoip.COUNTRY_EDITION] = make_archive(
            geoip.COUNTRY_EDITION, database_type="GeoLite2-City"
        )
        with self.assertRaisesMessage(
            CommandError,
            "Expected a GeoLite2-Country database, but downloaded a GeoLite2-City one.",
        ):
            self.run_command()

        self.assertEqual(os.listdir(self.directory), ["GeoLite2-Country.mmdb"])
        self.assertEqual(self.read_database(geoip.COUNTRY_EDITION), "old")
