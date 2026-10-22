from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from accounting.invariants import check_invariants


class Command(BaseCommand):
    help = (
        "Check the points ledger against the invariants. "
        "Read-only and safe to run against production. Exits non-zero on any violation."
    )

    def handle(self, *args, **options):
        if connection.in_atomic_block:
            # We're already inside someone else's transaction (e.g. a test), whose isolation
            # level cannot be changed now (every check is a plain SELECT regardless).
            violations = check_invariants()
        else:
            with transaction.atomic():
                violations = self._check_in_read_only_snapshot()

        if not violations:
            self.stdout.write(self.style.SUCCESS("Ledger OK: no invariant violations."))
            return

        for violation in violations:
            self.stderr.write(self.style.ERROR(str(violation)))
        raise CommandError(
            f"Ledger check failed: {len(violations)} invariant violation(s)."
        )

    def _check_in_read_only_snapshot(self):
        # One consistent snapshot across all checks, and a guarantee from Postgres that
        # nothing here can write. Must be the first statement in the transaction.
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        return check_invariants()
