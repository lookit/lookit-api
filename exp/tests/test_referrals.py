import time
from unittest.mock import patch

from django.contrib.sites.models import Site
from django.test import Client, TestCase
from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm

from accounts.models import User
from exp.tests.test_lab_views import Force2FAClient
from studies.models import Lab, Study, StudyType
from studies.permissions import StudyPermission
from studies.referrals import (
    REFERRAL_COOKIE,
    REFERRAL_COOKIE_MAX_AGE,
    lab_for_referral_code,
)


class ReferralCodeTestCase(TestCase):
    def setUp(self):
        self.slug_lab = G(Lab, name="Slug lab", slug="slug-lab")
        self.no_slug_lab = G(Lab, name="No slug lab", slug=None)
        self.sandbox_lab = Lab.objects.get(name="Sandbox lab")

    def test_lab_for_referral_code(self):
        self.assertEqual(lab_for_referral_code("slug-lab"), self.slug_lab)
        self.assertEqual(
            lab_for_referral_code(str(self.no_slug_lab.uuid)), self.no_slug_lab
        )
        demo_lab = Lab.objects.get(name="Demo lab")
        for code in ["", "not-a-lab", str(self.sandbox_lab.uuid), str(demo_lab.uuid)]:
            self.assertIsNone(lab_for_referral_code(code), code)


class ReferralCookieTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.lab = G(Lab, name="Referring lab", slug="referring-lab")
        self.other_lab = G(Lab, name="Other lab", slug="other-lab")
        G(Site, id=1)
        self.url = reverse("web:home")

    def signup(self):
        password = "testpassword20chars"
        return self.client.post(
            reverse("web:participant-signup"),
            {
                "username": "new-participant@mit.edu",
                "password1": password,
                "password2": password,
                "nickname": "Testfamily",
            },
        )

    def test_cookie_set_for_valid_code(self):
        response = self.client.get(self.url, {"ref": "referring-lab"})
        cookie = response.cookies[REFERRAL_COOKIE]
        self.assertEqual(cookie["max-age"], 14 * 24 * 60 * 60)
        self.assertTrue(cookie["httponly"])

    def test_no_cookie_for_logged_in_user(self):
        self.client.force_login(G(User, is_active=True))
        response = self.client.get(self.url, {"ref": "referring-lab"})
        self.assertNotIn(REFERRAL_COOKIE, response.cookies)

    def test_signup_records_referral_and_clears_cookie(self):
        self.client.get(self.url, {"ref": "referring-lab"})
        response = self.signup()
        user = User.objects.get(username="new-participant@mit.edu")
        self.assertEqual(user.referred_by_lab, self.lab)
        self.assertEqual(user.referral_url, "http://testserver/?ref=referring-lab")
        self.assertEqual(response.cookies[REFERRAL_COOKIE].value, "")

    def test_most_recent_referral_wins(self):
        self.client.get(self.url, {"ref": "referring-lab"})
        self.client.get(self.url, {"ref": "other-lab"})
        self.signup()
        user = User.objects.get(username="new-participant@mit.edu")
        self.assertEqual(user.referred_by_lab, self.other_lab)

    def test_tampered_cookie_ignored(self):
        self.client.cookies[REFERRAL_COOKIE] = '{"lab": "%s"}' % self.lab.uuid
        self.signup()
        user = User.objects.get(username="new-participant@mit.edu")
        self.assertIsNone(user.referred_by_lab)

    def test_invalid_code_keeps_existing_referral(self):
        self.client.get(self.url, {"ref": "referring-lab"})
        response = self.client.get(self.url, {"ref": "not-a-lab"})
        self.assertNotIn(REFERRAL_COOKIE, response.cookies)
        self.signup()
        user = User.objects.get(username="new-participant@mit.edu")
        self.assertEqual(user.referred_by_lab, self.lab)

    def test_expired_cookie_ignored(self):
        # Sign the cookie as if the link had been followed just over two weeks ago.
        with patch("django.core.signing.time") as mock_time:
            mock_time.time.return_value = time.time() - REFERRAL_COOKIE_MAX_AGE - 60
            self.client.get(self.url, {"ref": "referring-lab"})
        self.signup()
        user = User.objects.get(username="new-participant@mit.edu")
        self.assertIsNone(user.referred_by_lab)

    @patch(
        "accounts.forms.ParticipantSignupForm.clean_username",
        autospec=True,
        side_effect=lambda form: form.cleaned_data["username"],
    )
    @patch("accounts.forms.ParticipantSignupForm.validate_unique")
    @patch.object(User.objects, "get_by_natural_key", side_effect=User.DoesNotExist)
    def test_failed_signup_keeps_cookie(
        self, mock_get_by_natural_key, mock_validate_unique, mock_clean_username
    ):
        # Simulate a concurrent duplicate submission, so the DB unique constraint
        # rejects the new user (see DuplicateUsernameSignupMixin).
        existing_user = G(User, username="new-participant@mit.edu")
        self.client.get(self.url, {"ref": "referring-lab"})
        response = self.signup()
        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)
        self.assertNotIn(REFERRAL_COOKIE, response.cookies)
        self.assertIn(REFERRAL_COOKIE, self.client.cookies)
        existing_user.refresh_from_db()
        self.assertIsNone(existing_user.referred_by_lab)


class ReferralLinkViewsTestCase(TestCase):
    def setUp(self):
        self.client = Force2FAClient()
        self.researcher = G(User, is_active=True, is_researcher=True)
        self.lab = G(Lab, name="My lab", slug="my-lab")
        self.second_lab = G(Lab, name="Another lab", slug=None)
        self.sandbox_lab = Lab.objects.get(name="Sandbox lab")
        for lab in [self.lab, self.second_lab, self.sandbox_lab]:
            lab.researchers.add(self.researcher)
        self.study = G(
            Study,
            lab=self.lab,
            creator=self.researcher,
            study_type=StudyType.get_external(),
        )
        assign_perm(
            StudyPermission.READ_STUDY_DETAILS.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.client.force_login(self.researcher)

    def test_study_page_links(self):
        response = self.client.get(reverse("exp:study", kwargs={"pk": self.study.pk}))
        study_url = "http://testserver" + reverse(
            "web:study-detail", kwargs={"uuid": self.study.uuid}
        )
        links = response.context["referral_links"]
        # The study's own lab comes first; Sandbox is excluded.
        self.assertEqual([link["lab"] for link in links], [self.lab, self.second_lab])
        self.assertEqual(links[0]["url"], f"{study_url}?ref=my-lab")
        self.assertEqual(links[1]["url"], f"{study_url}?ref={self.second_lab.uuid}")
        self.assertContains(response, 'id="study-referral-link"')

    def test_lab_page_links_only_for_labs_with_slug(self):
        response = self.client.get(
            reverse("exp:lab-detail", kwargs={"pk": self.lab.pk})
        )
        page_url = "http://testserver" + reverse(
            "web:lab-studies-list", args=["my-lab"]
        )
        self.assertEqual(
            response.context["referral_links"][0]["url"], f"{page_url}?ref=my-lab"
        )
        self.assertContains(response, 'id="lab-referral-link"')

        response = self.client.get(
            reverse("exp:lab-detail", kwargs={"pk": self.second_lab.pk})
        )
        self.assertNotContains(response, 'id="lab-referral-link"')


class LabStudiesPageReferralTestCase(TestCase):
    def setUp(self):
        self.lab = G(Lab, name="Page lab", slug="page-lab")
        self.other_lab = G(Lab, name="Another lab", slug=None)
        self.page = reverse("web:lab-studies-list", args=["page-lab"])

    def test_researcher_sees_referral_links(self):
        researcher = G(User, is_active=True, is_researcher=True)
        self.lab.researchers.add(researcher)
        self.other_lab.researchers.add(researcher)
        Lab.objects.get(name="Sandbox lab").researchers.add(researcher)
        client = Client()
        client.force_login(researcher)
        response = client.get(self.page)
        links = response.context["referral_links"]
        # The page's own lab comes first; Sandbox is excluded.
        self.assertEqual([link["lab"] for link in links], [self.lab, self.other_lab])
        self.assertEqual(links[0]["url"], f"http://testserver{self.page}?ref=page-lab")
        self.assertEqual(
            links[1]["url"], f"http://testserver{self.page}?ref={self.other_lab.uuid}"
        )
        self.assertContains(response, 'id="lab-page-referral-link"')

    def test_participants_and_visitors_do_not_see_it(self):
        participant = G(User, is_active=True, is_researcher=False)
        logged_in = Client()
        logged_in.force_login(participant)
        for client in [Client(), logged_in]:
            response = client.get(self.page)
            self.assertNotIn("referral_links", response.context)
            self.assertNotContains(response, "lab-page-referral-link")
