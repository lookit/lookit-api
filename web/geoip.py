"""Country and network owner lookups for block rules (web.models.BlockRule).

Uses MaxMind's GeoLite2 Country and ASN databases, which `manage.py
download_geoip_databases` downloads into settings.GEOIP_PATH. Cloud Build
downloads them before building the image.

Lookups fail open: if a database is missing, unreadable, or too old, lookups
return None, so rules that need it don't block anyone. The problem is logged
once per process.
"""

import datetime
import logging
import os
from typing import NamedTuple

import maxminddb
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

COUNTRY_EDITION = "GeoLite2-Country"
ASN_EDITION = "GeoLite2-ASN"
EDITIONS = (COUNTRY_EDITION, ASN_EDITION)

# The GeoLite2 license requires switching to updated databases, which MaxMind
# releases twice a week, and deleting old ones within 30 days. Databases
# that are older than MAX_AGE should not be used.
MAX_AGE = datetime.timedelta(days=30)


class ASN(NamedTuple):
    number: int
    organization: str


class _Database:
    def __init__(self, path):
        self.path = path
        self.reader = None
        self.built_at = None
        self.error = None
        self.logged_problem = False
        try:
            self.reader = maxminddb.open_database(path)
        except FileNotFoundError:
            self.error = f"{path} doesn't exist"
        except (OSError, maxminddb.InvalidDatabaseError) as e:
            self.error = f"{path} couldn't be read ({e})"
        else:
            self.built_at = datetime.datetime.fromtimestamp(
                self.reader.metadata().build_epoch, tz=datetime.timezone.utc
            )

    @property
    def problem(self):
        """Why lookups can't use this database, or None if they can."""
        if self.error:
            return self.error
        if timezone.now() - self.built_at > MAX_AGE:
            return (
                f"{self.path} was built on {self.built_at:%Y-%m-%d}, more than "
                f"{MAX_AGE.days} days ago"
            )
        return None


# Opened once per process, so restart the web server after downloading new
# databases.
_databases = {}


def _database(edition):
    path = os.path.join(settings.GEOIP_PATH, f"{edition}.mmdb")
    if path not in _databases:
        _databases[path] = _Database(path)
    return _databases[path]


def problem(edition):
    """Why lookups in the `edition` database don't work, or None if they do."""
    return _database(edition).problem


def _lookup(edition, ip):
    database = _database(edition)
    reason = database.problem
    if reason:
        if not database.logged_problem:
            database.logged_problem = True
            logger.error(
                "Can't use a GeoIP database, so block rules that need it aren't "
                "blocking anyone: %s",
                reason,
            )
        return None
    try:
        return database.reader.get(ip)
    except ValueError:
        # Not an IP address.
        return None
    except maxminddb.InvalidDatabaseError:
        logger.exception("Couldn't look up an address in %s", database.path)
        return None


def country(ip):
    """The two-letter code of the country `ip` (a string) is in, or None if
    unknown.
    """
    record = _lookup(COUNTRY_EDITION, ip) or {}
    # Fall back to the country the address is registered in, for addresses
    # MaxMind can't locate.
    for key in ("country", "registered_country"):
        code = record.get(key, {}).get("iso_code")
        if code:
            return code
    return None


def asn(ip):
    """The network that `ip` (a string) is on, as an ASN, or None if unknown."""
    record = _lookup(ASN_EDITION, ip) or {}
    number = record.get("autonomous_system_number")
    if number is None:
        return None
    return ASN(number, record.get("autonomous_system_organization", ""))


def organizations(numbers):
    """MaxMind's name for the owner of each of the AS `numbers` (ints), as a
    dict. Numbers the ASN database doesn't have are left out.

    Reads the whole database, which takes a few seconds, so it's for management
    commands rather than requests. Check problem(ASN_EDITION) first.
    """
    wanted = set(numbers)
    found = {}
    for _, record in _database(ASN_EDITION).reader:
        number = record.get("autonomous_system_number")
        if number in wanted and number not in found:
            found[number] = record.get("autonomous_system_organization", "")
    return found
