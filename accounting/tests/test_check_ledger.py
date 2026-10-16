import uuid
from collections import defaultdict
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from accounting import services
from accounting.invariants import check_invariants
from accounting.models import EntryType, GrantType, LedgerEntry, Lot, Unit
from accounting.tests import drop_constraint, make_deficit, make_lab, make_study


class CheckLedgerTestCase(TestCase):
    """check_ledger catches each invariant it is responsible for.

    Most of these states cannot be reached through the schema, so these tests drop the
    guarding constraint for the duration of the test transaction and plant the row.
    """

    def setUp(self):
        self.lab = make_lab()
        self.study = make_study(self.lab)
        self.point_lot = services.grant(self.lab, 10, Unit.POINT, GrantType.TOP_UP)
        self.credit_lot = services.grant(
            self.lab, 2, Unit.STUDY_CREDIT, GrantType.COMPLIMENTARY
        )
        make_deficit(self.lab, Unit.POINT, 3, study=self.study)

    def run_command(self):
        out, err = StringIO(), StringIO()
        call_command("check_ledger", stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def assertViolations(self, expected):
        """Assert exactly these invariants failed, each on exactly these ids.

        ``expected`` maps invariant number to the offending ids: lot ids for the
        lot-level invariants (1, 2, 3, 8), ledger row ids for the row-level ones.
        """
        actual = defaultdict(list)
        for violation in check_invariants():
            self.assertEqual(violation.count, len(violation.sample))
            actual[violation.invariant] += violation.sample
        self.assertEqual(
            {invariant: sorted(ids) for invariant, ids in actual.items()},
            {invariant: sorted(ids) for invariant, ids in expected.items()},
        )
        with self.assertRaises(CommandError) as raised:
            self.run_command()
        self.assertIn("Ledger check failed", str(raised.exception))

    def plant(self, lot, **kwargs):
        fields = dict(
            lab=self.lab,
            lot=lot,
            unit=lot.unit,
            amount=-1,
            entry_type=EntryType.ADJUSTMENT,
            group_id=uuid.uuid4(),
            effective_at=timezone.now(),
        )
        fields.update(kwargs)
        fields.setdefault("lot_balance_after", lot.amount_remaining + fields["amount"])
        entry = LedgerEntry.objects.create(**fields)
        Lot.objects.filter(pk=lot.pk).update(
            amount_remaining=lot.amount_remaining + fields["amount"]
        )
        return entry

    def test_clean_ledger_passes(self):
        out, _ = self.run_command()
        self.assertIn("Ledger OK", out)

    def test_invariant_1_cache_drift(self):
        Lot.objects.filter(pk=self.point_lot.pk).update(amount_remaining=9)
        self.assertViolations({1: [self.point_lot.pk]})

    def test_invariant_2_balance_after_drift(self):
        self.plant(self.point_lot, lot_balance_after=42)
        self.assertViolations({2: [self.point_lot.pk]})

    def test_invariant_3_negative_non_deficit(self):
        drop_constraint("accounting_lot", "accounting_lot_non_deficit_not_negative")
        self.plant(self.credit_lot, amount=-5)
        self.assertViolations({3: [self.credit_lot.pk]})

    def test_invariant_5_zero_amount(self):
        drop_constraint(
            "accounting_ledgerentry", "accounting_ledgerentry_amount_nonzero"
        )
        entry = self.plant(self.point_lot, amount=0)
        self.assertViolations({5: [entry.pk]})

    def test_invariant_6_sign(self):
        drop_constraint(
            "accounting_ledgerentry", "accounting_ledgerentry_debit_negative"
        )
        drop_constraint(
            "accounting_ledgerentry", "accounting_ledgerentry_credit_positive"
        )
        # Raise the ceiling first so the positive CONSUME fits under amount_granted.
        Lot.objects.filter(pk=self.point_lot.pk).update(amount_granted=11)
        consume = self.plant(self.point_lot, entry_type=EntryType.CONSUME, amount=1)
        grant = self.plant(self.credit_lot, entry_type=EntryType.GRANT, amount=-1)
        release_lot = services.grant(self.lab, 2, Unit.POINT, GrantType.TOP_UP)
        release = self.plant(release_lot, entry_type=EntryType.RELEASE, amount=-1)
        self.assertViolations({6: [consume.pk, grant.pk, release.pk]})

    def test_invariant_7_unit_mismatch(self):
        drop_constraint(
            "accounting_ledgerentry", "accounting_ledgerentry_lot_lab_unit_fk"
        )
        entry = self.plant(self.point_lot, unit=Unit.STUDY_CREDIT)
        self.assertViolations({7: [entry.pk]})

    def test_invariant_14_lab_mismatch(self):
        drop_constraint(
            "accounting_ledgerentry", "accounting_ledgerentry_lot_lab_unit_fk"
        )
        entry = self.plant(self.point_lot, lab=make_lab())
        self.assertViolations({14: [entry.pk]})

    def test_invariant_8_credit_lot_with_study(self):
        drop_constraint("accounting_lot", "accounting_lot_credit_has_no_study")
        Lot.objects.filter(pk=self.credit_lot.pk).update(study=self.study)
        self.assertViolations({8: [self.credit_lot.pk]})

    def test_invariant_8_allowance_without_study(self):
        # Not a database constraint: services.grant() and Lot.clean() refuse it.
        Lot.objects.filter(pk=self.point_lot.pk).update(
            grant_type=GrantType.STUDY_ALLOWANCE
        )
        self.assertViolations({8: [self.point_lot.pk]})

    def test_reports_every_violation(self):
        Lot.objects.filter(pk=self.point_lot.pk).update(amount_remaining=9)
        Lot.objects.filter(pk=self.credit_lot.pk).update(
            grant_type=GrantType.STUDY_ALLOWANCE
        )
        self.assertViolations({1: [self.point_lot.pk], 8: [self.credit_lot.pk]})
        with self.assertRaises(CommandError) as raised:
            err = StringIO()
            call_command("check_ledger", stdout=StringIO(), stderr=err)
        self.assertIn("2 invariant violation(s)", str(raised.exception))
        self.assertIn("Invariant 1", err.getvalue())
        self.assertIn("Invariant 8", err.getvalue())
        self.assertIn(str(self.point_lot.pk), err.getvalue())


class CheckLedgerEmptyTestCase(TestCase):
    def test_empty_ledger_passes(self):
        out = StringIO()
        call_command("check_ledger", stdout=out)
        self.assertIn("Ledger OK", out.getvalue())
