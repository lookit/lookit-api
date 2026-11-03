"""Write and read paths for the credits/points lots and ledger.

Credits and points share lot and ledger models/tables, so every function that
affects a balance must have a ``unit`` (POINT or STUDY_CREDIT).
Writes to the ledger run inside ``transaction.atomic()`` and lock the lots they touch.
"""

import uuid

from django.db import transaction
from django.db.models import F, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounting.models import EntryType, GrantType, LedgerEntry, Lot, Unit


def _require_unit(unit) -> str:
    if unit not in Unit.values:
        raise ValueError(
            f"A valid unit is required ({', '.join(Unit.values)}), got {unit!r}."
        )
    return unit


def _join_memo(*parts: str) -> str:
    return "; ".join(part for part in parts if part)


def _post(
    lot: Lot,
    amount: int,
    entry_type: str,
    *,
    group_id: uuid.UUID,
    effective_at,
    actor=None,
    study=None,
    response=None,
    unit_cost=None,
    reverses=None,
    memo: str = "",
) -> LedgerEntry:
    """Write one ledger row against a ``lot`` and update its cached balance.

    The caller must hold a ``select_for_update`` lock on ``lot`` (or have created it in
    the current transaction) so that ``lot_balance_after`` is exact.
    """
    lot.amount_remaining += amount
    lot.save(update_fields=["amount_remaining", "modified_at"])
    return LedgerEntry.objects.create(
        lab_id=lot.lab_id,
        lot=lot,
        unit=lot.unit,
        amount=amount,
        entry_type=entry_type,
        lot_balance_after=lot.amount_remaining,
        response=response,
        study=study,
        unit_cost=unit_cost,
        group_id=group_id,
        reverses=reverses,
        effective_at=effective_at,
        created_by=actor,
        memo=memo,
    )


def grant(
    lab,
    amount: int,
    unit: str,
    grant_type: str,
    *,
    study=None,
    granted_at=None,
    expires_at=None,
    actor=None,
    notes: str = "",
    memo: str = "",
) -> Lot:
    """Create a lot and its grant entry, then settle any matching deficit.

    The deficit settled is the one in the same lab, unit, and study scope as the new lot.
    A study credit lot settles that lab's credit deficit.
    A study's point allowance settles that study's point deficit.
    Unassigned points never settle a study's deficit, since moving points onto a study is an explicit act.
    Settlement happens only if the new lot is spendable now.

    ``notes`` goes on the lot and can be edited later.
    ``memo`` goes on every ledger row this call writes and is permanent. A settlement row
    prefixes it with what it settled.
    """
    _require_unit(unit)
    if grant_type not in GrantType.values:
        raise ValueError(f"Unknown grant type {grant_type!r}.")
    if grant_type == GrantType.DEFICIT:
        raise ValueError("Deficit lots are created by allocation, not granted.")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        raise ValueError("A grant amount must be a positive integer.")

    now = timezone.now()
    granted_at = granted_at or now
    lot = Lot(
        lab=lab,
        unit=unit,
        study=study,
        grant_type=grant_type,
        amount_granted=amount,
        amount_remaining=0,
        granted_at=granted_at,
        expires_at=expires_at,
        created_by=actor,
        notes=notes,
    )
    # Raises ValidationError for a credit with a study, a study from
    # another lab, a study allowance with no study, or an expiry before the grant date.
    lot.clean()

    with transaction.atomic():
        deficit = (
            Lot.objects.select_for_update()
            .filter(
                lab=lab,
                unit=unit,
                grant_type=GrantType.DEFICIT,
                amount_remaining__lt=0,
            )
            .filter(Q(study=study) if study is not None else Q(study__isnull=True))
            .first()
        )

        lot.save()
        _post(
            lot,
            amount,
            EntryType.GRANT,
            group_id=uuid.uuid4(),
            effective_at=granted_at,
            actor=actor,
            study=study,
            memo=memo,
        )

        is_spendable_now = granted_at <= now and (
            expires_at is None or expires_at > now
        )
        if deficit is not None and is_spendable_now:
            settle = min(amount, -deficit.amount_remaining)
            group_id = uuid.uuid4()
            _post(
                lot,
                -settle,
                EntryType.CONSUME,
                group_id=group_id,
                effective_at=now,
                actor=actor,
                study=study,
                memo=_join_memo(f"Settles deficit lot {deficit.uuid}", memo),
            )
            _post(
                deficit,
                settle,
                EntryType.ADJUSTMENT,
                group_id=group_id,
                effective_at=now,
                actor=actor,
                study=study,
                memo=_join_memo(f"Settled from lot {lot.uuid}", memo),
            )

    return lot


def lab_balance(lab, unit: str, *, at=None) -> int:
    """The lab's net balance in one unit, which is the ledger sum across all its lots.

    For points this includes every study's allowance, unassigned points, and deficits.
    With the ``at`` arg, only rows effective at or before that moment are counted.
    """
    _require_unit(unit)
    rows = LedgerEntry.objects.filter(lab=lab, unit=unit)
    if at is not None:
        rows = rows.filter(effective_at__lte=at)
    return rows.aggregate(total=Coalesce(Sum("amount"), Value(0)))["total"]


def lot_balances(lab, unit: str, *, at=None) -> QuerySet:
    """The lab's lots in one unit, annotated with ``balance`` from the ledger.

    Ordered by spend order. With the ``at`` arg, lots not yet granted at that moment are
    omitted and only rows effective at or before it are counted.
    """
    _require_unit(unit)
    lots = Lot.objects.filter(lab=lab, unit=unit)
    tx_filter = Q()
    if at is not None:
        lots = lots.filter(granted_at__lte=at)
        tx_filter = Q(entries__effective_at__lte=at)
    return lots.annotate(
        balance=Coalesce(Sum("entries__amount", filter=tx_filter), Value(0))
    ).order_by(
        "consumption_priority",
        F("expires_at").asc(nulls_last=True),
        "granted_at",
        "id",
    )
