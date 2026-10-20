import uuid
from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone
from django_dynamic_fixture import G
from parameterized import parameterized

from accounting import services
from accounting.models import (
    EntryType,
    GrantType,
    LedgerEntry,
    LedgerImmutableError,
    Lot,
    Unit,
)
from accounting.tests import make_lab, make_study
from accounts.models import User


class LotConstraintTestCase(TestCase):
    """Constraints on lots, checked by creating rows directly so that only the database
    stands between a bad row and the table."""

    def setUp(self):
        self.lab = make_lab()
        self.study = make_study(self.lab)
        self.now = timezone.now()

    def make_lot(self, **kwargs):
        fields = {
            "lab": self.lab,
            "unit": Unit.POINT,
            "grant_type": GrantType.COMPLIMENTARY,
            "amount_granted": 10,
            "amount_remaining": 10,
            "granted_at": self.now,
        }
        fields.update(kwargs)
        with transaction.atomic():
            return Lot.objects.create(**fields)

    def test_valid_lots(self):
        self.make_lot()
        self.make_lot(unit=Unit.STUDY_CREDIT)
        self.make_lot(study=self.study, grant_type=GrantType.STUDY_ALLOWANCE)

    def test_study_credit_lot_cannot_have_study(self):
        # Invariant 8
        with self.assertRaises(IntegrityError):
            self.make_lot(unit=Unit.STUDY_CREDIT, study=self.study)

    def test_unknown_unit_rejected(self):
        with self.assertRaises(IntegrityError):
            self.make_lot(unit="point")

    def test_remaining_cannot_exceed_granted(self):
        with self.assertRaises(IntegrityError):
            self.make_lot(amount_remaining=11)

    def test_expiry_must_follow_grant(self):
        with self.assertRaises(IntegrityError):
            self.make_lot(expires_at=self.now)
        self.make_lot(expires_at=self.now + timedelta(seconds=1))

    def test_non_deficit_lot_cannot_go_negative(self):
        # Invariant 3
        with self.assertRaises(IntegrityError):
            self.make_lot(amount_remaining=-1)
        self.make_lot(
            grant_type=GrantType.DEFICIT, amount_granted=0, amount_remaining=-1
        )

    def test_one_lab_deficit_per_unit(self):
        deficit = {
            "grant_type": GrantType.DEFICIT,
            "amount_granted": 0,
            "amount_remaining": 0,
        }
        self.make_lot(**deficit)
        self.make_lot(unit=Unit.STUDY_CREDIT, **deficit)
        with self.assertRaises(IntegrityError):
            self.make_lot(**deficit)

    def test_one_deficit_per_study(self):
        deficit = {
            "grant_type": GrantType.DEFICIT,
            "amount_granted": 0,
            "amount_remaining": 0,
        }
        self.make_lot(study=self.study, **deficit)
        # A lab-level deficit does not collide with a study's.
        self.make_lot(**deficit)
        self.make_lot(study=make_study(self.lab), **deficit)
        with self.assertRaises(IntegrityError):
            self.make_lot(study=self.study, **deficit)

    def test_identity_fields_are_immutable(self):
        lot = services.grant(self.lab, 10, Unit.POINT, GrantType.COMPLIMENTARY)
        for field, value in [
            ("amount_granted", 20),
            ("unit", Unit.STUDY_CREDIT),
            ("grant_type", GrantType.PROMOTIONAL),
            ("study", self.study),
            ("lab", make_lab()),
            ("granted_at", self.now - timedelta(days=1)),
        ]:
            lot.refresh_from_db()
            setattr(lot, field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                lot.save()

        lot.refresh_from_db()
        lot.notes = "Renewal for 2027"
        lot.expires_at = self.now + timedelta(days=30)
        lot.consumption_priority = -1
        lot.save()

    def test_lot_unit_and_lab_cannot_change_once_it_has_entries(self):
        # The composite foreign key behind invariants 7 and 14 also pins the lot's unit
        # and lab, even for writes that bypass save().
        lot = services.grant(self.lab, 10, Unit.POINT, GrantType.COMPLIMENTARY)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Lot.objects.filter(pk=lot.pk).update(unit=Unit.STUDY_CREDIT)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Lot.objects.filter(pk=lot.pk).update(lab=make_lab())


class LedgerEntryConstraintTestCase(TestCase):
    def setUp(self):
        self.lab = make_lab()
        self.point_lot = services.grant(
            self.lab, 10, Unit.POINT, GrantType.COMPLIMENTARY
        )
        self.credit_lot = services.grant(
            self.lab, 3, Unit.STUDY_CREDIT, GrantType.COMPLIMENTARY
        )

    def row(self, lot, **kwargs):
        fields = {
            "lab": self.lab,
            "lot": lot,
            "unit": lot.unit,
            "amount": -1,
            "entry_type": EntryType.CONSUME,
            "lot_balance_after": lot.amount_remaining - 1,
            "group_id": uuid.uuid4(),
            "effective_at": timezone.now(),
        }
        fields.update(kwargs)
        return LedgerEntry(**fields)

    def test_unit_must_match_lot_in_database(self):
        # Invariant 7: nothing in Python checks this. The row reaches the database and
        # is rejected there through both save() and bulk_create.
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.row(self.credit_lot, unit=Unit.POINT).save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerEntry.objects.bulk_create(
                [self.row(self.point_lot, unit=Unit.STUDY_CREDIT)]
            )
        with (
            self.assertRaises(IntegrityError),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                INSERT INTO accounting_ledgerentry
                    (uuid, lab_id, lot_id, unit, amount, entry_type, lot_balance_after,
                     group_id, effective_at, created_at, memo)
                VALUES (%s, %s, %s, 'POINT', -1, 'CONSUME', 2, %s, now(), now(), '')
                """,
                [uuid.uuid4(), self.lab.pk, self.credit_lot.pk, uuid.uuid4()],
            )
        self.assertEqual(self.credit_lot.entries.count(), 1)

    def test_lab_must_match_lot_in_database(self):
        # Invariant 14: the row's denormalised lab is checked against its lot's lab.
        other_lab = make_lab()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.row(self.point_lot, lab=other_lab).save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerEntry.objects.bulk_create([self.row(self.credit_lot, lab=other_lab)])
        self.assertEqual(LedgerEntry.objects.filter(lab=other_lab).count(), 0)

    def test_matching_unit_accepted(self):
        with transaction.atomic():
            self.row(self.credit_lot).save()
            self.row(self.point_lot).save()

    @parameterized.expand(
        [
            ("zero", EntryType.ADJUSTMENT, 0),  # invariant 5
            ("positive_consume", EntryType.CONSUME, 1),  # invariant 6
            ("positive_expire", EntryType.EXPIRE, 1),
            ("negative_grant", EntryType.GRANT, -1),
            ("negative_release", EntryType.RELEASE, -1),
            ("unknown_unit", EntryType.CONSUME, -1, "point"),
        ]
    )
    def test_invalid_rows_rejected(self, _name, entry_type, amount, unit=None):
        row = self.row(self.point_lot, entry_type=entry_type, amount=amount)
        if unit:
            row.unit = unit
        with self.assertRaises(IntegrityError), transaction.atomic():
            row.save()

    @parameterized.expand(
        [
            (EntryType.RELEASE, 1),
            (EntryType.ADJUSTMENT, -1),
            (EntryType.ADJUSTMENT, 1),
            (EntryType.TRANSFER, -1),
            (EntryType.TRANSFER, 1),
        ]
    )
    def test_valid_sign_allowed(self, entry_type, amount):
        with transaction.atomic():
            self.row(self.point_lot, entry_type=entry_type, amount=amount).save()


class LedgerImmutabilityTestCase(TestCase):
    """no UPDATE, no DELETE, by any route."""

    def setUp(self):
        self.lab = make_lab()
        self.actor = G(User, is_staff=True)
        services.grant(
            self.lab, 10, Unit.POINT, GrantType.COMPLIMENTARY, actor=self.actor
        )
        self.tx = LedgerEntry.objects.get()

    def assertUnchanged(self):
        fresh = LedgerEntry.objects.get(pk=self.tx.pk)
        self.assertEqual(fresh.amount, 10)
        self.assertEqual(fresh.memo, "")

    def test_save_on_existing_row_raises(self):
        self.tx.memo = "edited"
        with self.assertRaises(LedgerImmutableError):
            self.tx.save()
        self.assertUnchanged()

    def test_delete_raises(self):
        with self.assertRaises(LedgerImmutableError):
            self.tx.delete()
        self.assertUnchanged()

    def test_queryset_update_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerEntry.objects.filter(pk=self.tx.pk).update(amount=99)
        self.assertUnchanged()

    def test_queryset_delete_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerEntry.objects.filter(pk=self.tx.pk).delete()
        self.assertUnchanged()

    @parameterized.expand(
        [
            ("UPDATE accounting_ledgerentry SET memo = 'x' WHERE id = %s",),
            ("DELETE FROM accounting_ledgerentry WHERE id = %s",),
        ]
    )
    def test_raw_sql_rejected_by_database(self, sql):
        with (
            self.assertRaises(IntegrityError),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(sql, [self.tx.pk])
        self.assertUnchanged()

    def test_update_that_also_clears_created_by_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerEntry.objects.filter(pk=self.tx.pk).update(created_by=None, amount=99)
        self.assertUnchanged()

    def test_deleting_the_creating_user_is_allowed(self):
        # on_delete=SET_NULL issues an UPDATE; the trigger permits exactly that one.
        self.actor.delete()
        fresh = LedgerEntry.objects.get(pk=self.tx.pk)
        self.assertIsNone(fresh.created_by)
        self.assertEqual(fresh.amount, 10)
