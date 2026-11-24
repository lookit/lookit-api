from datetime import timedelta
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from django_dynamic_fixture import G
from parameterized import parameterized

from accounting import services
from accounting.invariants import check_invariants
from accounting.models import EntryType, GrantType, LedgerEntry, Lot, Unit
from accounting.tests import make_deficit, make_lab, make_study
from accounts.models import User


class GrantTestCase(TestCase):
    def setUp(self):
        self.lab = make_lab()
        self.study = make_study(self.lab)
        self.actor = G(User, is_staff=True)

    def test_creates_lot_and_grant_entry(self):
        granted_at = timezone.now() - timedelta(days=1)
        expires_at = granted_at + timedelta(days=365)
        lot = services.grant(
            self.lab,
            500,
            Unit.POINT,
            GrantType.TOP_UP,
            granted_at=granted_at,
            expires_at=expires_at,
            actor=self.actor,
            notes="Invoice 42",
        )

        lot.refresh_from_db()
        self.assertEqual(lot.lab, self.lab)
        self.assertEqual(lot.unit, Unit.POINT)
        self.assertIsNone(lot.study)
        self.assertEqual(lot.amount_granted, 500)
        self.assertEqual(lot.amount_remaining, 500)
        self.assertEqual(lot.granted_at, granted_at)
        self.assertEqual(lot.expires_at, expires_at)
        self.assertEqual(lot.created_by, self.actor)
        self.assertEqual(lot.notes, "Invoice 42")

        tx = lot.entries.get()
        self.assertEqual(tx.entry_type, EntryType.GRANT)
        self.assertEqual(tx.amount, 500)
        self.assertEqual(tx.unit, Unit.POINT)
        self.assertEqual(tx.lab, self.lab)
        self.assertEqual(tx.lot_balance_after, 500)
        self.assertEqual(tx.effective_at, granted_at)
        self.assertEqual(tx.created_by, self.actor)
        self.assertEqual(check_invariants(), [])

    def test_study_allowance(self):
        lot = services.grant(
            self.lab, 200, Unit.POINT, GrantType.STUDY_ALLOWANCE, study=self.study
        )
        self.assertEqual(lot.study, self.study)
        self.assertEqual(lot.entries.get().study, self.study)

    def test_granted_at_defaults_to_now(self):
        before = timezone.now()
        lot = services.grant(self.lab, 1, Unit.STUDY_CREDIT, GrantType.COMPLIMENTARY)
        self.assertGreaterEqual(lot.granted_at, before)
        self.assertLessEqual(lot.granted_at, timezone.now())

    @parameterized.expand(
        [
            ("missing", None),
            ("lowercase", "point"),
            ("unknown", "DOLLAR"),
        ]
    )
    def test_unit_is_required(self, _name, unit):
        with self.assertRaises(ValueError):
            services.grant(self.lab, 1, unit, GrantType.COMPLIMENTARY)
        self.assertFalse(Lot.objects.exists())

    @parameterized.expand([(0,), (-5,), (1.5,), (True,)])
    def test_amount_must_be_positive_integer(self, amount):
        with self.assertRaises(ValueError):
            services.grant(self.lab, amount, Unit.POINT, GrantType.COMPLIMENTARY)
        self.assertFalse(Lot.objects.exists())

    def test_deficit_cannot_be_granted(self):
        with self.assertRaises(ValueError):
            services.grant(self.lab, 1, Unit.POINT, GrantType.DEFICIT)

    def test_study_credit_with_study_rejected(self):
        # Invariant 8, refused before the database is reached.
        with self.assertRaises(ValidationError):
            services.grant(
                self.lab,
                1,
                Unit.STUDY_CREDIT,
                GrantType.COMPLIMENTARY,
                study=self.study,
            )
        self.assertFalse(Lot.objects.exists())

    def test_study_from_another_lab_rejected(self):
        with self.assertRaises(ValidationError):
            services.grant(
                make_lab(), 1, Unit.POINT, GrantType.COMPLIMENTARY, study=self.study
            )

    def test_study_allowance_requires_study(self):
        with self.assertRaises(ValidationError):
            services.grant(self.lab, 200, Unit.POINT, GrantType.STUDY_ALLOWANCE)

    def test_expiry_must_follow_grant(self):
        now = timezone.now()
        with self.assertRaises(ValidationError):
            services.grant(
                self.lab,
                1,
                Unit.POINT,
                GrantType.COMPLIMENTARY,
                granted_at=now,
                expires_at=now - timedelta(days=1),
            )

    def test_lot_and_grant_row_are_atomic(self):
        with (
            mock.patch.object(
                LedgerEntry.objects, "create", side_effect=RuntimeError("boom")
            ),
            self.assertRaises(RuntimeError),
        ):
            services.grant(self.lab, 10, Unit.POINT, GrantType.COMPLIMENTARY)
        self.assertFalse(Lot.objects.exists())
        self.assertFalse(LedgerEntry.objects.exists())

    def test_takes_lock_on_deficit_lot(self):
        make_deficit(self.lab, Unit.STUDY_CREDIT, 1)
        with mock.patch.object(
            Lot.objects,
            "select_for_update",
            wraps=Lot.objects.select_for_update,
        ) as select_for_update:
            services.grant(self.lab, 1, Unit.STUDY_CREDIT, GrantType.COMPLIMENTARY)
        select_for_update.assert_called_once()


class DeficitSettlementTestCase(TestCase):
    """A new grant settles as much of a matching deficit as it can."""

    def setUp(self):
        self.lab = make_lab()
        self.study = make_study(self.lab)
        self.other_study = make_study(self.lab)

    def settlement_rows(self, lot):
        return lot.entries.exclude(entry_type=EntryType.GRANT)

    def test_grant_with_no_deficit_writes_only_the_grant(self):
        lot = services.grant(self.lab, 5, Unit.STUDY_CREDIT, GrantType.COMPLIMENTARY)
        self.assertEqual(LedgerEntry.objects.count(), 1)
        self.assertEqual(lot.amount_remaining, 5)

    def test_full_settlement(self):
        deficit = make_deficit(self.lab, Unit.STUDY_CREDIT, 3)
        self.assertEqual(services.lab_balance(self.lab, Unit.STUDY_CREDIT), -3)

        lot = services.grant(self.lab, 5, Unit.STUDY_CREDIT, GrantType.COMPLIMENTARY)

        lot.refresh_from_db()
        deficit.refresh_from_db()
        self.assertEqual(lot.amount_remaining, 2)
        self.assertEqual(deficit.amount_remaining, 0)
        # Net balance is the deficit plus the grant: settlement itself moves nothing.
        self.assertEqual(services.lab_balance(self.lab, Unit.STUDY_CREDIT), 2)

        consume = self.settlement_rows(lot).get()
        adjustment = deficit.entries.get(entry_type=EntryType.ADJUSTMENT)
        self.assertEqual(consume.entry_type, EntryType.CONSUME)
        self.assertEqual(consume.amount, -3)
        self.assertEqual(consume.lot_balance_after, 2)
        self.assertEqual(adjustment.entry_type, EntryType.ADJUSTMENT)
        self.assertEqual(adjustment.amount, 3)
        self.assertEqual(adjustment.lot_balance_after, 0)
        self.assertEqual(consume.group_id, adjustment.group_id)
        self.assertNotEqual(
            consume.group_id, lot.entries.get(entry_type=EntryType.GRANT).group_id
        )
        self.assertEqual(check_invariants(), [])

    def test_memo_goes_on_every_row(self):
        deficit = make_deficit(self.lab, Unit.STUDY_CREDIT, 3)
        overdraw_row = deficit.entries.get()
        lot = services.grant(
            self.lab,
            5,
            Unit.STUDY_CREDIT,
            GrantType.COMPLIMENTARY,
            notes="Editable note",
            memo="Invoice 42",
        )
        self.assertEqual(lot.notes, "Editable note")
        memos = {
            tx.entry_type: tx.memo
            for tx in LedgerEntry.objects.exclude(pk=overdraw_row.pk)
        }
        self.assertEqual(
            memos,
            {
                EntryType.GRANT: "Invoice 42",
                EntryType.CONSUME: f"Settles deficit lot {deficit.uuid}; Invoice 42",
                EntryType.ADJUSTMENT: f"Settled from lot {lot.uuid}; Invoice 42",
            },
        )

    def test_partial_settlement(self):
        deficit = make_deficit(self.lab, Unit.STUDY_CREDIT, 10)
        lot = services.grant(self.lab, 4, Unit.STUDY_CREDIT, GrantType.COMPLIMENTARY)
        deficit.refresh_from_db()
        self.assertEqual(lot.amount_remaining, 0)
        self.assertEqual(deficit.amount_remaining, -6)

        # The next grant settles the rest.
        second = services.grant(
            self.lab, 10, Unit.STUDY_CREDIT, GrantType.COMPLIMENTARY
        )
        deficit.refresh_from_db()
        self.assertEqual(second.amount_remaining, 4)
        self.assertEqual(deficit.amount_remaining, 0)
        self.assertEqual(services.lab_balance(self.lab, Unit.STUDY_CREDIT), 4)
        self.assertEqual(check_invariants(), [])

    def test_study_allowance_settles_its_own_study_deficit(self):
        deficit = make_deficit(self.lab, Unit.POINT, 7, study=self.study)
        lot = services.grant(
            self.lab, 200, Unit.POINT, GrantType.STUDY_ALLOWANCE, study=self.study
        )
        deficit.refresh_from_db()
        self.assertEqual(lot.amount_remaining, 193)
        self.assertEqual(deficit.amount_remaining, 0)
        self.assertTrue(self.settlement_rows(lot).filter(study=self.study).exists())

    def test_does_not_settle_another_studys_deficit(self):
        # Points for one study never pay for another.
        deficit = make_deficit(self.lab, Unit.POINT, 7, study=self.study)
        lot = services.grant(
            self.lab, 200, Unit.POINT, GrantType.STUDY_ALLOWANCE, study=self.other_study
        )
        deficit.refresh_from_db()
        self.assertEqual(lot.amount_remaining, 200)
        self.assertEqual(deficit.amount_remaining, -7)

    def test_unassigned_points_do_not_settle_a_study_deficit(self):
        # Moving points onto a study is an explicit TRANSFER, never implicit.
        deficit = make_deficit(self.lab, Unit.POINT, 7, study=self.study)
        lot = services.grant(self.lab, 500, Unit.POINT, GrantType.TOP_UP)
        deficit.refresh_from_db()
        self.assertEqual(lot.amount_remaining, 500)
        self.assertEqual(deficit.amount_remaining, -7)

    def test_does_not_settle_across_units(self):
        # Points never pay off a credit deficit, or the reverse.
        credit_deficit = make_deficit(self.lab, Unit.STUDY_CREDIT, 1)
        point_deficit = make_deficit(self.lab, Unit.POINT, 5)
        services.grant(self.lab, 500, Unit.POINT, GrantType.TOP_UP)
        credit_deficit.refresh_from_db()
        self.assertEqual(credit_deficit.amount_remaining, -1)
        point_deficit.refresh_from_db()
        self.assertEqual(point_deficit.amount_remaining, 0)

        services.grant(self.lab, 3, Unit.STUDY_CREDIT, GrantType.COMPLIMENTARY)
        credit_deficit.refresh_from_db()
        self.assertEqual(credit_deficit.amount_remaining, 0)
        self.assertEqual(services.lab_balance(self.lab, Unit.POINT), 495)
        self.assertEqual(services.lab_balance(self.lab, Unit.STUDY_CREDIT), 2)

    def test_does_not_settle_another_labs_deficit(self):
        deficit = make_deficit(make_lab(), Unit.STUDY_CREDIT, 2)
        services.grant(self.lab, 5, Unit.STUDY_CREDIT, GrantType.COMPLIMENTARY)
        deficit.refresh_from_db()
        self.assertEqual(deficit.amount_remaining, -2)

    def test_future_dated_grant_does_not_settle(self):
        # A lot is not spendable before granted_at, so it cannot pay a deficit yet.
        deficit = make_deficit(self.lab, Unit.STUDY_CREDIT, 2)
        lot = services.grant(
            self.lab,
            5,
            Unit.STUDY_CREDIT,
            GrantType.COMPLIMENTARY,
            granted_at=timezone.now() + timedelta(days=1),
        )
        deficit.refresh_from_db()
        self.assertEqual(lot.amount_remaining, 5)
        self.assertEqual(deficit.amount_remaining, -2)

    def test_already_expired_grant_does_not_settle(self):
        deficit = make_deficit(self.lab, Unit.STUDY_CREDIT, 2)
        now = timezone.now()
        services.grant(
            self.lab,
            5,
            Unit.STUDY_CREDIT,
            GrantType.COMPLIMENTARY,
            granted_at=now - timedelta(days=30),
            expires_at=now - timedelta(days=1),
        )
        deficit.refresh_from_db()
        self.assertEqual(deficit.amount_remaining, -2)


class BalanceTestCase(TestCase):
    def setUp(self):
        self.lab = make_lab()
        self.study = make_study(self.lab)

    def test_units_are_never_mixed(self):
        # A lab holding 3 credits and 400 points reports 3 and 400 (not 403).
        services.grant(self.lab, 3, Unit.STUDY_CREDIT, GrantType.COMPLIMENTARY)
        services.grant(self.lab, 200, Unit.POINT, GrantType.TOP_UP)
        services.grant(
            self.lab, 200, Unit.POINT, GrantType.STUDY_ALLOWANCE, study=self.study
        )

        self.assertEqual(services.lab_balance(self.lab, Unit.STUDY_CREDIT), 3)
        self.assertEqual(services.lab_balance(self.lab, Unit.POINT), 400)

        credit_lots = services.lot_balances(self.lab, Unit.STUDY_CREDIT)
        point_lots = services.lot_balances(self.lab, Unit.POINT)
        self.assertEqual({lot.unit for lot in credit_lots}, {Unit.STUDY_CREDIT})
        self.assertEqual({lot.unit for lot in point_lots}, {Unit.POINT})
        self.assertEqual(sum(lot.balance for lot in credit_lots), 3)
        self.assertEqual(sum(lot.balance for lot in point_lots), 400)

    def test_no_unitless_entry_point(self):
        for fn in (services.lab_balance, services.lot_balances):
            with self.subTest(fn=fn.__name__):
                with self.assertRaises(TypeError):
                    fn(self.lab)
                with self.assertRaises(ValueError):
                    fn(self.lab, None)
                with self.assertRaises(ValueError):
                    fn(self.lab, "points")

    def test_balance_of_empty_lab_is_zero(self):
        self.assertEqual(services.lab_balance(self.lab, Unit.POINT), 0)
        self.assertEqual(list(services.lot_balances(self.lab, Unit.POINT)), [])

    def test_balances_are_per_lab(self):
        services.grant(make_lab(), 50, Unit.POINT, GrantType.TOP_UP)
        services.grant(self.lab, 10, Unit.POINT, GrantType.TOP_UP)
        self.assertEqual(services.lab_balance(self.lab, Unit.POINT), 10)
        self.assertEqual(services.lot_balances(self.lab, Unit.POINT).count(), 1)

    def test_lab_balance_includes_deficits(self):
        services.grant(self.lab, 10, Unit.POINT, GrantType.TOP_UP)
        make_deficit(self.lab, Unit.POINT, 4, study=self.study)
        self.assertEqual(services.lab_balance(self.lab, Unit.POINT), 6)

    def test_balance_at_a_point_in_time(self):
        now = timezone.now()
        services.grant(
            self.lab,
            10,
            Unit.POINT,
            GrantType.TOP_UP,
            granted_at=now - timedelta(days=10),
        )
        services.grant(
            self.lab,
            5,
            Unit.POINT,
            GrantType.TOP_UP,
            granted_at=now - timedelta(days=2),
        )
        self.assertEqual(services.lab_balance(self.lab, Unit.POINT), 15)
        self.assertEqual(
            services.lab_balance(self.lab, Unit.POINT, at=now - timedelta(days=5)), 10
        )
        self.assertEqual(
            services.lab_balance(self.lab, Unit.POINT, at=now - timedelta(days=11)), 0
        )

        lots = services.lot_balances(self.lab, Unit.POINT, at=now - timedelta(days=5))
        self.assertEqual([lot.balance for lot in lots], [10])

    def test_lot_balance_counts_only_rows_up_to_at(self):
        now = timezone.now()
        deficit = make_deficit(self.lab, Unit.STUDY_CREDIT, 2)
        lot = services.grant(
            self.lab,
            5,
            Unit.STUDY_CREDIT,
            GrantType.COMPLIMENTARY,
            granted_at=now - timedelta(days=3),
        )
        # The settlement happened now; three days ago the lot still held all five.
        (current,) = services.lot_balances(self.lab, Unit.STUDY_CREDIT).filter(
            pk=lot.pk
        )
        (earlier,) = services.lot_balances(
            self.lab, Unit.STUDY_CREDIT, at=now - timedelta(days=1)
        ).filter(pk=lot.pk)
        self.assertEqual(current.balance, 3)
        self.assertEqual(earlier.balance, 5)
        self.assertNotIn(
            deficit.pk,
            services.lot_balances(
                self.lab, Unit.STUDY_CREDIT, at=now - timedelta(days=1)
            ).values_list("pk", flat=True),
        )

    def test_lot_balances_in_spend_order(self):
        now = timezone.now()

        def lot(**kwargs):
            return services.grant(self.lab, 1, Unit.POINT, GrantType.TOP_UP, **kwargs)

        never_expires = lot(granted_at=now - timedelta(days=5))
        later = lot(expires_at=now + timedelta(days=60))
        sooner = lot(expires_at=now + timedelta(days=30))
        older_never_expires = lot(granted_at=now - timedelta(days=9))
        promo = lot(expires_at=now + timedelta(days=90))
        promo.consumption_priority = -10
        promo.save()

        self.assertEqual(
            list(services.lot_balances(self.lab, Unit.POINT)),
            [promo, sooner, later, older_never_expires, never_expires],
        )

    def test_balance_matches_ledger_not_cache(self):
        lot = services.grant(self.lab, 10, Unit.POINT, GrantType.TOP_UP)
        Lot.objects.filter(pk=lot.pk).update(amount_remaining=7)
        self.assertEqual(services.lab_balance(self.lab, Unit.POINT), 10)
        (row,) = services.lot_balances(self.lab, Unit.POINT)
        self.assertEqual(row.balance, 10)


class RealisticSequenceTestCase(TestCase):
    def test_invariants_hold(self):
        lab = make_lab()
        other_lab = make_lab()
        study = make_study(lab)
        now = timezone.now()

        make_deficit(lab, Unit.STUDY_CREDIT, 1)
        make_deficit(lab, Unit.POINT, 12, study=study)
        services.grant(lab, 3, Unit.STUDY_CREDIT, GrantType.MEMBERSHIP)
        services.grant(
            lab, 500, Unit.POINT, GrantType.TOP_UP, expires_at=now + timedelta(days=365)
        )
        services.grant(lab, 200, Unit.POINT, GrantType.STUDY_ALLOWANCE, study=study)
        services.grant(
            lab,
            5,
            Unit.POINT,
            GrantType.PROMOTIONAL,
            granted_at=now + timedelta(days=7),
        )
        services.grant(other_lab, 2, Unit.STUDY_CREDIT, GrantType.COMPLIMENTARY)

        self.assertEqual(check_invariants(), [])
        self.assertEqual(services.lab_balance(lab, Unit.STUDY_CREDIT), 2)
        self.assertEqual(services.lab_balance(lab, Unit.POINT), 500 + 200 + 5 - 12)
        self.assertEqual(services.lab_balance(other_lab, Unit.STUDY_CREDIT), 2)
