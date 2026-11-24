from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from accounting import services
from accounting.invariants import check_invariants
from accounting.models import EntryType, GrantType, LedgerEntry, Lot, Unit
from accounting.tests import make_deficit, make_lab, make_study
from studies.models import Lab


def run(name, *args, **kwargs):
    out = StringIO()
    call_command(name, *args, stdout=out, stderr=StringIO(), **kwargs)
    return out.getvalue()


class SeedLedgerTestCase(TestCase):
    def setUp(self):
        make_lab()  # A lab with no studies is skipped by default.
        self.lab = make_lab()
        self.study = make_study(self.lab)

    def test_seeds_first_lab_with_a_study(self):
        out = run("seed_ledger")
        self.assertIn(f"Seeded lab {self.lab.pk}", out)

        self.assertEqual(services.lab_balance(self.lab, Unit.POINT), 1700)
        self.assertEqual(services.lab_balance(self.lab, Unit.STUDY_CREDIT), 4)
        allowance = Lot.objects.get(grant_type=GrantType.STUDY_ALLOWANCE)
        self.assertEqual(allowance.study, self.study)
        deficit = Lot.objects.get(grant_type=GrantType.DEFICIT)
        self.assertEqual(deficit.amount_remaining, 0)
        self.assertEqual(check_invariants(), [])

        # The spend uses up the 2-credit lot before overdrawing by 1, and the 5-credit
        # grant then settles that 1.
        two, five = Lot.objects.filter(grant_type=GrantType.COMPLIMENTARY).order_by(
            "id"
        )
        self.assertEqual((two.amount_remaining, five.amount_remaining), (0, 4))
        self.assertEqual(
            list(deficit.entries.order_by("id").values_list("entry_type", "amount")),
            [(EntryType.CONSUME, -1), (EntryType.ADJUSTMENT, 1)],
        )
        spend = LedgerEntry.objects.filter(
            entry_type=EntryType.CONSUME, lot__in=[two, deficit]
        )
        self.assertEqual(spend.values("group_id").distinct().count(), 1)

        for tx in LedgerEntry.objects.all():
            with self.subTest(entry_type=tx.entry_type, memo=tx.memo):
                self.assertTrue(tx.memo.endswith("Fake data from seed_ledger"))
        self.assertFalse(Lot.objects.exclude(notes="Fake data from seed_ledger"))

    def test_spend_skips_lots_that_are_not_active(self):
        now = timezone.now()
        future = services.grant(
            self.lab,
            5,
            Unit.STUDY_CREDIT,
            GrantType.COMPLIMENTARY,
            granted_at=now + timedelta(days=1),
        )
        run("seed_ledger", lab=self.lab.pk)
        future.refresh_from_db()
        self.assertEqual(future.amount_remaining, 5)
        self.assertEqual(services.lab_balance(self.lab, Unit.STUDY_CREDIT), 9)

    def test_skips_sandbox_and_demo_labs_by_default(self):
        # Both exist in every database (studies migration 0066) with the lowest pks.
        for name in ("Sandbox lab", "Demo lab"):
            make_study(Lab.objects.get(name=name))
        out = run("seed_ledger")
        self.assertIn(f"Seeded lab {self.lab.pk}", out)

    def test_sandbox_lab_can_be_chosen_explicitly(self):
        sandbox = Lab.objects.get(name="Sandbox lab")
        make_study(sandbox)
        run("seed_ledger", lab=sandbox.pk)
        self.assertEqual(services.lab_balance(sandbox, Unit.POINT), 1700)

    def test_can_run_twice(self):
        run("seed_ledger", lab=self.lab.pk)
        run("seed_ledger", lab=self.lab.pk)
        self.assertEqual(services.lab_balance(self.lab, Unit.STUDY_CREDIT), 8)
        self.assertEqual(Lot.objects.filter(grant_type="DEFICIT").count(), 1)
        self.assertEqual(check_invariants(), [])

    def test_lab_without_study_rejected(self):
        with self.assertRaisesMessage(CommandError, "has no studies"):
            run("seed_ledger", lab=make_lab().pk)
        self.assertFalse(Lot.objects.exists())

    @override_settings(ENVIRONMENT="production")
    def test_refuses_in_production(self):
        with self.assertRaisesMessage(CommandError, "development and staging only"):
            run("seed_ledger")
        self.assertFalse(Lot.objects.exists())


class ResetLedgerTestCase(TestCase):
    def setUp(self):
        lab = make_lab()
        services.grant(lab, 10, Unit.POINT, GrantType.TOP_UP)
        make_deficit(lab, Unit.STUDY_CREDIT, 2)
        self.db_name = connection.settings_dict["NAME"]
        # TRUNCATE refuses to run while deferred FK checks from setUp are pending,
        # which only happens because a TestCase never commits.
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    def assertLedgerIntact(self):
        self.assertEqual(Lot.objects.count(), 2)
        self.assertEqual(LedgerEntry.objects.count(), 2)

    def test_wipes_everything_with_confirm_flag(self):
        out = run("reset_ledger", confirm=self.db_name)
        self.assertIn("2 lot(s) and 2 ledger row(s)", out)
        self.assertFalse(Lot.objects.exists())
        self.assertFalse(LedgerEntry.objects.exists())

    def test_prompts_for_database_name(self):
        with mock.patch("builtins.input", return_value=self.db_name):
            run("reset_ledger")
        self.assertFalse(LedgerEntry.objects.exists())

    def test_wrong_name_deletes_nothing(self):
        with (
            mock.patch("builtins.input", return_value="lookit"),
            self.assertRaisesMessage(CommandError, "nothing was deleted"),
        ):
            run("reset_ledger")
        self.assertLedgerIntact()

    @override_settings(ENVIRONMENT=" Production ")
    def test_refuses_in_production(self):
        with self.assertRaisesMessage(CommandError, "development and staging only"):
            run("reset_ledger", confirm=self.db_name)
        self.assertLedgerIntact()
