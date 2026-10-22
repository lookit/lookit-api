from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from web import geoip
from web.models import BlockRule
from web.vpn_asns import VPN_NETWORKS


class Command(BaseCommand):
    help = (
        "Add a participation-only network owner block rule for each VPN, Tor, "
        "VPN hosting and spammers' hosting network in web/vpn_asns.py. Networks "
        "that already have a rule are left as they are, so running this again "
        "never switches back on a rule an admin deactivated. To stop blocking a "
        "network, deactivate its rule rather than deleting it, or running this "
        "again will add it back."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show which rules would be added, without adding them.",
        )

    def handle(self, *args, dry_run=False, **kwargs):
        problem = geoip.problem(geoip.ASN_EDITION)
        if problem:
            raise CommandError(
                f"Can't check who owns each network, because {problem}. Run "
                "manage.py download_geoip_databases first."
            )
        owners = geoip.organizations([network.asn for network in VPN_NETWORKS])
        existing = set(
            BlockRule.objects.filter(kind=BlockRule.Kind.ASN).values_list(
                "value", flat=True
            )
        )

        added = kept = skipped = 0
        with transaction.atomic():
            for network in VPN_NETWORKS:
                value = f"AS{network.asn}"
                name = f"{value} ({network.provider})"
                owner = owners.get(network.asn)
                if value in existing:
                    self.stdout.write(f"{name} already has a rule, so leaving it.")
                    kept += 1
                elif owner is None:
                    self.warn(f"Skipping {name}, which isn't in {geoip.ASN_EDITION}.")
                    skipped += 1
                elif owner.casefold() != network.organization.casefold():
                    self.warn(
                        f"Skipping {name}: {geoip.ASN_EDITION} says {owner!r} owns "
                        f"it now, not {network.organization!r}. If it's still "
                        "the provider's, update web/vpn_asns.py."
                    )
                    skipped += 1
                else:
                    if not dry_run:
                        BlockRule.objects.create(
                            kind=BlockRule.Kind.ASN, value=value, reason=network.reason
                        )
                    self.stdout.write(
                        f"{'Would add' if dry_run else 'Added'} a rule for {value}: "
                        f"{network.reason}"
                    )
                    added += 1

        if dry_run:
            summary = (
                f"Dry run, so nothing changed. Would add {added} rule(s), leave "
                f"{kept} existing rule(s) as they are, and skip {skipped} network(s)."
            )
        else:
            summary = (
                f"Added {added} rule(s), left {kept} existing rule(s) as they were, "
                f"and skipped {skipped} network(s)."
            )
            if added:
                summary += (
                    " The web servers start using new rules within "
                    f"{settings.BLOCK_RULES_CACHE_TIMEOUT} seconds."
                )
        self.stdout.write(self.style.SUCCESS(summary))

    def warn(self, message):
        self.stderr.write(self.style.WARNING(message))
