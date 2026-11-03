from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from accounting.management.commands._safety import refuse_in_production
from accounting.models import LedgerEntry, Lot


class Command(BaseCommand):
    help = (
        "Delete every lot and ledger row, leaving the accounting tables empty. For "
        "development and staging only. This refuses to run when ENVIRONMENT is production, "
        "and asks you to type the database name to confirm."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            metavar="DATABASE_NAME",
            help="Skip the prompt by passing the name of the database being wiped.",
        )

    def handle(self, *args, confirm=None, **options):
        refuse_in_production("reset_ledger")

        db_name = connection.settings_dict["NAME"]
        lots = Lot.objects.count()
        rows = LedgerEntry.objects.count()
        self.stdout.write(
            f"This permanently deletes {lots} lot(s) and {rows} ledger row(s) "
            f"from database {db_name!r} on host "
            f"{connection.settings_dict.get('HOST') or 'localhost'!r}."
        )

        if confirm is None:
            confirm = input("Type the database name to confirm: ")
        if confirm != db_name:
            raise CommandError("Database name did not match; nothing was deleted.")

        # TRUNCATE is not a row operation, so the ledger's append-only trigger
        # does not fire. Both tables must be cleared together because ledger entries reference lots.
        with connection.cursor() as cursor:
            cursor.execute(
                "TRUNCATE accounting_ledgerentry, accounting_lot RESTART IDENTITY"
            )
        self.stdout.write(self.style.SUCCESS("Ledger reset: no lots, no ledger rows."))
