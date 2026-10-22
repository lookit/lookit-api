import os
import shutil
import tarfile
import tempfile

import maxminddb
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from web import geoip

DOWNLOAD_URL = (
    "https://download.maxmind.com/geoip/databases/{edition}/download?suffix=tar.gz"
)


class Command(BaseCommand):
    help = (
        "Download MaxMind's GeoLite2 Country and ASN databases into GEOIP_PATH, "
        "for country and network owner block rules. This is for local "
        "development: deployed sites get the databases when Cloud Build builds "
        "their image (the download-geoip-databases step in cloudbuild.yaml), so "
        "there's no need to run this on them. Needs a free MaxMind account: set MAXMIND_ACCOUNT_ID "
        "and MAXMIND_LICENSE_KEY."
    )

    def handle(self, *args, **kwargs):
        account_id = os.environ.get("MAXMIND_ACCOUNT_ID")
        license_key = os.environ.get("MAXMIND_LICENSE_KEY")
        if not account_id or not license_key:
            raise CommandError(
                "Set MAXMIND_ACCOUNT_ID and MAXMIND_LICENSE_KEY to your MaxMind "
                "account ID and license key. Sign up for free at "
                "https://www.maxmind.com/en/geolite2/signup."
            )

        os.makedirs(settings.GEOIP_PATH, exist_ok=True)
        for edition in geoip.EDITIONS:
            path = os.path.join(settings.GEOIP_PATH, f"{edition}.mmdb")
            # On the same filesystem as the database, so it can be replaced in
            # one step.
            with tempfile.TemporaryDirectory(dir=settings.GEOIP_PATH) as tmp:
                archive = os.path.join(tmp, f"{edition}.tar.gz")
                database = os.path.join(tmp, f"{edition}.mmdb")
                self.download(edition, (account_id, license_key), archive)
                self.extract(edition, archive, database)
                self.check_database(edition, database)
                os.replace(database, path)
            self.stdout.write(f"Downloaded {path}")

        self.stdout.write(
            self.style.SUCCESS("Done. Restart the web server to use them.")
        )

    def download(self, edition, auth, destination):
        try:
            with requests.get(
                DOWNLOAD_URL.format(edition=edition), auth=auth, stream=True, timeout=60
            ) as response:
                if response.status_code == 401:
                    raise CommandError(
                        "MaxMind didn't accept MAXMIND_ACCOUNT_ID and "
                        "MAXMIND_LICENSE_KEY. Check them, and that the license key "
                        "is still active."
                    )
                response.raise_for_status()
                with open(destination, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        f.write(chunk)
        except requests.RequestException as e:
            raise CommandError(f"Couldn't download {edition}: {e}")

    def extract(self, edition, archive, destination):
        """Copy the database out of the archive, where it's e.g.
        GeoLite2-ASN_20261020/GeoLite2-ASN.mmdb.
        """
        filename = f"{edition}.mmdb"
        try:
            with tarfile.open(archive, "r:gz") as tar:
                member = next(
                    (
                        member
                        for member in tar.getmembers()
                        if member.isfile() and os.path.basename(member.name) == filename
                    ),
                    None,
                )
                if member is None:
                    raise CommandError(f"The {edition} download has no {filename}.")
                with tar.extractfile(member) as source, open(destination, "wb") as f:
                    shutil.copyfileobj(source, f)
        except (tarfile.TarError, OSError) as e:
            raise CommandError(f"The {edition} download isn't a valid archive: {e}")

    def check_database(self, edition, path):
        try:
            with maxminddb.open_database(path) as reader:
                database_type = reader.metadata().database_type
        except (OSError, maxminddb.InvalidDatabaseError) as e:
            raise CommandError(f"The {edition} download isn't a valid database: {e}")
        if database_type != edition:
            raise CommandError(
                f"Expected a {edition} database, but downloaded a {database_type} one."
            )
