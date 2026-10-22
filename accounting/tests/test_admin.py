from http import HTTPStatus

from django.contrib.admin.sites import site
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounting import services
from accounting.models import EntryType, GrantType, LedgerEntry, Lot, Unit
from accounting.tests import make_deficit, make_lab, make_study
from accounts.models import GoogleAuthenticatorTOTP, User
from accounts.tests.test_accounts import Force2FAClient


class AccountingAdminTestCase(TestCase):
    def setUp(self):
        self.client = Force2FAClient()
        self.admin_user = User.objects.create_superuser("accounting-admin", "pw")
        GoogleAuthenticatorTOTP.objects.create(user=self.admin_user, activated=True)
        self.client.force_login(self.admin_user)
        self.lab = make_lab()
        self.study = make_study(self.lab)

    def add_data(self, **overrides):
        data = {
            "lab": self.lab.pk,
            "unit": Unit.POINT,
            "study": "",
            "grant_type": GrantType.TOP_UP,
            "amount_granted": 500,
            "granted_at_0": "2026-10-01",
            "granted_at_1": "09:00:00",
            "expires_at_0": "2027-10-01",
            "expires_at_1": "09:00:00",
            "consumption_priority": 0,
            "notes": "Invoice 42",
        }
        data.update(overrides)
        return data

    def test_add_grant_writes_ledger(self):
        response = self.client.post(
            reverse("admin:accounting_lot_add"), self.add_data()
        )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

        lot = Lot.objects.get()
        self.assertEqual(lot.amount_remaining, 500)
        self.assertEqual(lot.created_by, self.admin_user)
        tx = lot.entries.get()
        self.assertEqual(tx.entry_type, EntryType.GRANT)
        self.assertEqual(tx.amount, 500)
        self.assertEqual(tx.created_by, self.admin_user)

    def test_add_grant_settles_deficit(self):
        deficit = make_deficit(self.lab, Unit.STUDY_CREDIT, 1)
        self.client.post(
            reverse("admin:accounting_lot_add"),
            self.add_data(
                unit=Unit.STUDY_CREDIT,
                grant_type=GrantType.COMPLIMENTARY,
                amount_granted=3,
                granted_at_0="2026-01-01",
                expires_at_0="",
                expires_at_1="",
            ),
        )
        deficit.refresh_from_db()
        self.assertEqual(deficit.amount_remaining, 0)
        self.assertEqual(services.lab_balance(self.lab, Unit.STUDY_CREDIT), 2)

    def test_add_credit_with_study_shows_error(self):
        response = self.client.post(
            reverse("admin:accounting_lot_add"),
            self.add_data(unit=Unit.STUDY_CREDIT, study=self.study.pk),
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn("study", response.context["adminform"].form.errors)
        self.assertFalse(Lot.objects.exists())

    def test_add_zero_amount_shows_error(self):
        response = self.client.post(
            reverse("admin:accounting_lot_add"), self.add_data(amount_granted=0)
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn("amount_granted", response.context["adminform"].form.errors)
        self.assertFalse(Lot.objects.exists())

    def test_deficit_not_offered(self):
        response = self.client.get(reverse("admin:accounting_lot_add"))
        choices = dict(response.context["adminform"].form.fields["grant_type"].choices)
        self.assertNotIn(GrantType.DEFICIT, choices)
        self.assertIn(GrantType.STUDY_ALLOWANCE, choices)

    def test_change_only_touches_editable_fields(self):
        lot = services.grant(self.lab, 10, Unit.POINT, GrantType.TOP_UP)
        url = reverse("admin:accounting_lot_change", args=[lot.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        form_fields = set(response.context["adminform"].form.fields)
        self.assertEqual(form_fields, {"expires_at", "consumption_priority", "notes"})

        response = self.client.post(
            url,
            {
                "expires_at_0": "2030-01-01",
                "expires_at_1": "00:00:00",
                "consumption_priority": -5,
                "notes": "Promo",
                # Read-only fields are ignored even if posted.
                "amount_granted": 9999,
                "unit": Unit.STUDY_CREDIT,
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        lot.refresh_from_db()
        self.assertEqual(lot.consumption_priority, -5)
        self.assertEqual(lot.notes, "Promo")
        self.assertEqual(lot.amount_granted, 10)
        self.assertEqual(lot.unit, Unit.POINT)

    def test_list_views_render(self):
        services.grant(
            self.lab, 10, Unit.POINT, GrantType.STUDY_ALLOWANCE, study=self.study
        )
        services.grant(self.lab, 1, Unit.STUDY_CREDIT, GrantType.COMPLIMENTARY)
        for name in ("accounting_lot", "accounting_ledgerentry"):
            with self.subTest(name=name):
                url = reverse(f"admin:{name}_changelist")
                self.assertEqual(self.client.get(url).status_code, HTTPStatus.OK)
                self.assertEqual(
                    self.client.get(url, {"unit": Unit.STUDY_CREDIT}).status_code,
                    HTTPStatus.OK,
                )
                self.assertEqual(
                    self.client.get(url, {"q": self.lab.name}).status_code,
                    HTTPStatus.OK,
                )

    def test_ledger_entry_admin_is_read_only(self):
        services.grant(self.lab, 10, Unit.POINT, GrantType.TOP_UP)
        tx = LedgerEntry.objects.get()
        model_admin = site._registry[LedgerEntry]
        request = RequestFactory().get("/")
        request.user = self.admin_user
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_change_permission(request, tx))
        self.assertFalse(model_admin.has_delete_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request, tx))

        self.assertEqual(
            self.client.get(reverse("admin:accounting_ledgerentry_add")).status_code,
            HTTPStatus.FORBIDDEN,
        )
        change_url = reverse("admin:accounting_ledgerentry_change", args=[tx.pk])
        self.assertEqual(self.client.get(change_url).status_code, HTTPStatus.OK)
        self.client.post(change_url, {"memo": "edited", "amount": 99})
        delete_url = reverse("admin:accounting_ledgerentry_delete", args=[tx.pk])
        self.assertEqual(
            self.client.post(delete_url, {"post": "yes"}).status_code,
            HTTPStatus.FORBIDDEN,
        )
        tx = LedgerEntry.objects.get()
        self.assertEqual((tx.amount, tx.memo), (10, ""))

    def test_grant_admin_cannot_delete(self):
        lot = services.grant(self.lab, 10, Unit.POINT, GrantType.TOP_UP)
        model_admin = site._registry[Lot]
        request = RequestFactory().get("/")
        request.user = self.admin_user
        self.assertTrue(model_admin.has_add_permission(request))
        self.assertTrue(model_admin.has_change_permission(request, lot))
        self.assertFalse(model_admin.has_delete_permission(request, lot))
