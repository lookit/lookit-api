"""Points and study-credit accounting: lots and ledger models.

Two units share one set of tables, so every aggregate over
these models must filter on ``unit``.
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Unit(models.TextChoices):
    POINT = "POINT", "Point"
    STUDY_CREDIT = "STUDY_CREDIT", "Study credit"


class GrantType(models.TextChoices):
    """These are the allowable types of 'grants' (lots of one or more points/credits).

    This is used to track the different sources of points/credits and handle them
    differently when necessary. For instance, they may have different expiration dates, or
    if the grant type is 'study allowance', then the points must be linked to a specific study.
    The 'deficit' type is created on demand when a lab overdraws (it cannot actually be
    'granted' by an admin).
    """

    MEMBERSHIP = "MEMBERSHIP", "Membership"
    TOP_UP = "TOP_UP", "Top-up"
    REFERRAL_BONUS = "REFERRAL_BONUS", "Referral bonus"
    PROMOTIONAL = "PROMOTIONAL", "Promotional"
    DISCOUNTED = "DISCOUNTED", "Discounted"
    COMPLIMENTARY = "COMPLIMENTARY", "Complimentary"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"
    STUDY_ALLOWANCE = "STUDY_ALLOWANCE", "Study allowance"
    DEFICIT = "DEFICIT", "Deficit"


class EntryType(models.TextChoices):
    """Reason for the adjustment to point/credit balance in the ledger.

    Grant = Awarded (positive).
    Consume = Used (negative).
    Release = Value that was consumed goes back into the lot (positive).
    Expire = No longer usable due to expiration (negative).
    Adjustment = Corrections/changes that aren't a grant, charge, release, expiry or transfer.
      These can move in either direction, e.g. grant pays off deficit = positive;
      fixing a charge after response has settled = either.
    Transfer = Moves points from unassigned to a specific study.
      Operates in pairs (shared group_id), amount in both directions that add up to 0.
    """

    GRANT = "GRANT", "Grant"
    CONSUME = "CONSUME", "Consume"
    RELEASE = "RELEASE", "Release"
    EXPIRE = "EXPIRE", "Expire"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"
    TRANSFER = "TRANSFER", "Transfer"


class LedgerImmutableError(Exception):
    """Raised on any attempt to modify or delete a LedgerEntry."""


class Lot(models.Model):
    """A lot is one grant to one lab in one unit.

    ``amount_remaining`` is a cache of the ledger sum for this lot and the row that is
    locked when spending. Only accounting.services should write it.
    """

    # Fields that are fixed at creation. A lot's identity and unit never change.
    # Moving points onto a study is recorded as a TRANSFER to a new lot, not an edit to the lot.
    IMMUTABLE_FIELDS = (
        "lab_id",
        "unit",
        "study_id",
        "grant_type",
        "amount_granted",
        "granted_at",
    )

    uuid = models.UUIDField(default=uuid.uuid4, unique=True)
    lab = models.ForeignKey(
        "studies.Lab", on_delete=models.PROTECT, related_name="lots"
    )
    unit = models.CharField(max_length=16, choices=Unit.choices)
    study = models.ForeignKey(
        "studies.Study",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="lots",
        help_text="The study this allowance belongs to. This is always empty for study credits, "
        "and empty for points that are not applied to a specific study.",
    )
    grant_type = models.CharField(max_length=32, choices=GrantType.choices)
    amount_granted = models.PositiveIntegerField(
        help_text="Cannot be changed after creation."
    )
    amount_remaining = models.IntegerField(
        help_text="Cached balance for this lot based on the ledger sum."
    )
    granted_at = models.DateTimeField(help_text="When the lot becomes spendable.")
    expires_at = models.DateTimeField(
        null=True, blank=True, help_text="Leave empty for a lot that never expires."
    )
    expired_at = models.DateTimeField(null=True, blank=True)
    consumption_priority = models.IntegerField(
        default=0,
        help_text="Lower priority is spent first. When lots have the same consumption priority value, the lot with the soonest expiry will be spent first.",
    )
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=("lab", "unit", "expires_at")),
            models.Index(fields=("study", "unit")),
            models.Index(fields=("lab", "grant_type")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(unit__in=Unit.values),
                name="accounting_lot_unit_valid",
            ),
            models.CheckConstraint(
                condition=Q(amount_remaining__lte=models.F("amount_granted")),
                name="accounting_lot_remaining_lte_granted",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True)
                | Q(expires_at__gt=models.F("granted_at")),
                name="accounting_lot_expires_after_granted",
            ),
            models.CheckConstraint(
                condition=Q(grant_type=GrantType.DEFICIT) | Q(amount_remaining__gte=0),
                name="accounting_lot_non_deficit_not_negative",
            ),
            models.CheckConstraint(
                condition=~Q(unit=Unit.STUDY_CREDIT) | Q(study__isnull=True),
                name="accounting_lot_credit_has_no_study",
            ),
            models.UniqueConstraint(
                fields=("lab", "unit"),
                condition=Q(grant_type=GrantType.DEFICIT, study__isnull=True),
                name="accounting_lot_one_lab_deficit_per_unit",
            ),
            models.UniqueConstraint(
                fields=("study",),
                condition=Q(grant_type=GrantType.DEFICIT, study__isnull=False),
                name="accounting_lot_one_study_deficit",
            ),
            # Target of the composite foreign key from LedgerEntry(lot_id, lab_id, unit)
            # This is used to check that a ledger entry's unit and lab matches its lot's
            # unit and lab (see migration 0002).
            models.UniqueConstraint(
                fields=("id", "lab", "unit"),
                name="accounting_lot_id_lab_unit_uniq",
            ),
        ]

    def __str__(self):
        scope = f" for study {self.study_id}" if self.study_id else ""
        return (
            f"{self.get_grant_type_display()} {self.amount_granted} "
            f"{self.get_unit_display().lower()}(s){scope} ({self.uuid})"
        )

    def clean(self):
        errors = {}
        if (
            self.grant_type != GrantType.DEFICIT
            and self.amount_granted is not None
            and self.amount_granted <= 0
        ):
            errors["amount_granted"] = "A grant must be for at least one unit."
        if self.unit == Unit.STUDY_CREDIT and self.study_id is not None:
            errors["study"] = (
                "Study credits are held by the lab and cannot belong to a specific study."
            )
        if self.grant_type == GrantType.STUDY_ALLOWANCE and self.study_id is None:
            errors["study"] = "A study allowance must belong to a specific study."
        if (
            self.study_id is not None
            and self.lab_id is not None
            and self.study.lab_id != self.lab_id
        ):
            errors["study"] = "The specified study belongs to a different lab."
        if (
            self.expires_at is not None
            and self.granted_at is not None
            and self.expires_at <= self.granted_at
        ):
            errors["expires_at"] = "Expiry must be after the grant date."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self._state.adding and self.pk is not None:
            original = (
                type(self)
                .objects.filter(pk=self.pk)
                .values(*self.IMMUTABLE_FIELDS)
                .first()
            )
            if original is not None:
                changed = [
                    f for f in self.IMMUTABLE_FIELDS if getattr(self, f) != original[f]
                ]
                if changed:
                    raise ValueError(
                        f"Cannot change {', '.join(changed)} on an existing lot."
                    )
        super().save(*args, **kwargs)


class LedgerEntry(models.Model):
    """A ledger entry records one signed movement against one lot.

    This is append only. Rows must be written through accounting.services,
    which sets ``unit``, ``lab`` and ``lot_balance_after`` from the locked lot.
    """

    uuid = models.UUIDField(default=uuid.uuid4, unique=True)
    lab = models.ForeignKey(
        "studies.Lab", on_delete=models.PROTECT, related_name="ledger_entries"
    )
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="entries")
    unit = models.CharField(max_length=16, choices=Unit.choices)
    amount = models.IntegerField()
    entry_type = models.CharField(max_length=16, choices=EntryType.choices)
    lot_balance_after = models.IntegerField()
    response = models.ForeignKey(
        "studies.Response",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )
    study = models.ForeignKey(
        "studies.Study",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    unit_cost = models.IntegerField(null=True, blank=True)
    group_id = models.UUIDField(db_index=True)
    reverses = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversed_by",
    )
    effective_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    memo = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "ledger entries"
        indexes = [
            models.Index(fields=("lab", "unit", "effective_at")),
            models.Index(fields=("lot", "id")),
            models.Index(fields=("response",)),
            models.Index(fields=("study", "effective_at")),
            models.Index(fields=("entry_type", "effective_at")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(unit__in=Unit.values),
                name="accounting_ledgerentry_unit_valid",
            ),
            models.CheckConstraint(
                condition=~Q(amount=0),
                name="accounting_ledgerentry_amount_nonzero",
            ),
            models.CheckConstraint(
                condition=~Q(entry_type__in=[EntryType.CONSUME, EntryType.EXPIRE])
                | Q(amount__lt=0),
                name="accounting_ledgerentry_debit_negative",
            ),
            models.CheckConstraint(
                condition=~Q(entry_type__in=[EntryType.GRANT, EntryType.RELEASE])
                | Q(amount__gt=0),
                name="accounting_ledgerentry_credit_positive",
            ),
        ]

    def __str__(self):
        return f"{self.entry_type} {self.amount:+d} {self.unit} on lot {self.lot_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise LedgerImmutableError(
                "Ledger rows cannot be modified. Write a correcting entry instead."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutableError(
            "Ledger rows cannot be deleted. Write a correcting entry instead."
        )
