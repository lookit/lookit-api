"""Read-only checks of the ledger invariants.

Each check is a single aggregate query.
"""

from dataclasses import dataclass, field

from django.db.models import F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from accounting.models import EntryType, GrantType, LedgerEntry, Lot, Unit

# How many offending rows to list per invariant; the count is always exact.
SAMPLE_SIZE = 20


@dataclass
class Violation:
    invariant: int
    description: str
    count: int
    sample: list = field(default_factory=list)

    def __str__(self):
        ids = ", ".join(str(s) for s in self.sample)
        more = f" (first {len(self.sample)}: {ids})" if self.sample else ""
        return f"Invariant {self.invariant}: {self.count} {self.description}{more}"


def _violation(invariant, description, queryset, sample_field):
    count = queryset.count()
    if not count:
        return None
    sample = list(
        queryset.order_by(sample_field).values_list(sample_field, flat=True)[
            :SAMPLE_SIZE
        ]
    )
    return Violation(invariant, description, count, sample)


def _lots_with_ledger_sum():
    return Lot.objects.annotate(ledger_sum=Coalesce(Sum("entries__amount"), Value(0)))


def check_invariants() -> list[Violation]:
    latest_balance = Subquery(
        LedgerEntry.objects.filter(lot=OuterRef("pk"))
        .order_by("-id")
        .values("lot_balance_after")[:1]
    )
    checks = [
        (
            1,
            "lot(s) whose amount_remaining differs from the ledger sum",
            _lots_with_ledger_sum().exclude(amount_remaining=F("ledger_sum")),
            "id",
        ),
        (
            2,
            "lot(s) whose ledger sum differs from the lot_balance_after of the latest row",
            _lots_with_ledger_sum()
            .annotate(latest_balance=latest_balance)
            .filter(latest_balance__isnull=False)
            .exclude(ledger_sum=F("latest_balance")),
            "id",
        ),
        (
            3,
            "non-deficit lot(s) with a negative balance",
            Lot.objects.exclude(grant_type=GrantType.DEFICIT).filter(
                amount_remaining__lt=0
            ),
            "id",
        ),
        (
            5,
            "ledger row(s) with a zero amount",
            LedgerEntry.objects.filter(amount=0),
            "id",
        ),
        (
            6,
            "ledger row(s) whose sign contradicts the entry type",
            LedgerEntry.objects.filter(
                Q(
                    entry_type__in=[EntryType.CONSUME, EntryType.EXPIRE],
                    amount__gte=0,
                )
                | Q(entry_type__in=[EntryType.GRANT, EntryType.RELEASE], amount__lte=0)
            ),
            "id",
        ),
        (
            7,
            "ledger row(s) whose unit differs from their lot's unit",
            LedgerEntry.objects.exclude(unit=F("lot__unit")),
            "id",
        ),
        (
            8,
            "study-credit lot(s) assigned to a study",
            Lot.objects.filter(unit=Unit.STUDY_CREDIT, study__isnull=False),
            "id",
        ),
        (
            8,
            "study-allowance lot(s) not assigned to a study",
            Lot.objects.filter(
                grant_type=GrantType.STUDY_ALLOWANCE, study__isnull=True
            ),
            "id",
        ),
        (
            14,
            "ledger row(s) whose lab differs from their lot's lab",
            LedgerEntry.objects.exclude(lab=F("lot__lab")),
            "id",
        ),
    ]
    violations = []
    for invariant, description, queryset, sample_field in checks:
        violation = _violation(invariant, description, queryset, sample_field)
        if violation:
            violations.append(violation)
    return violations
