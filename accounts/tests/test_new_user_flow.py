import datetime
import itertools
from urllib.parse import urlencode

from bs4 import BeautifulSoup as BS
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse
from django_dynamic_fixture import G

from accounts.models import Child, DemographicData, User
from studies.models import Study


class NewUserAccountTestCase(TestCase):
    def setUp(self):
        self.study = self.get_study()

        self.user = G(User, is_active=True)

        self.study_details_url = reverse(
            "web:study-detail", kwargs={"uuid": self.study.uuid}
        )

        self.my_account_urls = [
            reverse("web:demographic-data-update"),
            reverse("accounts:manage-account"),
            reverse("web:children-list"),
            reverse("web:child-add"),
        ]

    def get_study(self):
        study = G(
            Study,
            image="asdf",
            name="study name",
            min_age_days=6 * 30,
            max_age_days=12 * 30,
            criteria_expression="",
        )
        study.state = "active"
        study.save()
        return study

    def get_soup(self, response: HttpResponse):
        return BS(response.content, "html.parser")

    def get_study_buttons(self, response):
        soup = self.get_soup(response)
        study_button = soup.find("a", class_="btn-has-study")
        study_list_button = soup.find("a", class_="btn-study-list")
        return (study_button, study_list_button)

    def get_my_account_urls(self, child: Child) -> itertools.chain:
        return itertools.chain(
            self.my_account_urls,
            (reverse("web:child-update", kwargs={"uuid": child.uuid}),),
        )

    def set_session(self):
        session = self.client.session
        session["study_name"] = self.study.name
        session["study_uuid"] = str(self.study.uuid)
        session.save()

    def login_user(self):
        user = self.user
        self.client.force_login(user)
        self.set_session()

    def test_valid_study_detail(self):
        """Check if study returns a valid details page."""
        response = self.client.get(self.study_details_url)
        self.assertEqual(response.status_code, 200)

    def test_login_and_create_buttons_exist(self):
        """Check if login and create account buttons are on page.

        Along with with the correct button text, check that the hidden input has the correct next
        value and the action url is correct.
        """
        response = self.client.get(self.study_details_url)
        soup = self.get_soup(response)
        forms = soup.find_all("form")
        login_url = reverse("login")
        signup_url = reverse("web:participant-signup")

        self.assertTrue(
            any(
                f.button.text == "Log in to participate"
                and f.attrs["action"] == login_url
                and f.input.attrs["value"] == self.study_details_url
                for f in forms
            )
        )
        self.assertTrue(
            any(
                f.button.text == "Create a new account"
                and f.attrs["action"] == signup_url
                and f.input.attrs["value"] == self.study_details_url
                for f in forms
            )
        )

    def test_create_account_has_study(self):
        """Check if when user is created, that the study is stored in session."""
        query = {"next": self.study_details_url}
        qs = urlencode(query, doseq=False)
        url = f"{reverse('web:participant-signup')}?{qs}"
        nickname = "user_asdf"
        response = self.client.post(
            url,
            {
                "username": "user@email.com",
                "nickname": nickname,
                "password1": "asdfasdfasdfasdf",
                "password2": "asdfasdfasdfasdf",
            },
            follow=True,
        )

        # confirm we ended up in the correct view
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            (reverse("web:demographic-data-update"), 302), response.redirect_chain
        )

        # confirm user was created
        self.assertEqual(
            User.objects.filter(username="user@email.com").first().nickname, nickname
        )

        # confirm session data was set
        self.assertEqual(self.client.session["study_uuid"], str(self.study.uuid))
        self.assertEqual(self.client.session["study_name"], self.study.name)

    def test_no_demo_no_child(self):
        self.login_user()

        # confirm user has no demo and no children
        self.assertFalse(self.user.has_demographics)
        self.assertFalse(self.user.has_any_child)

        for url in self.my_account_urls:
            response = self.client.get(url)
            soup = self.get_soup(response)
            study_button = soup.find("a", class_="has-study")
            study_list_button = soup.find("a", class_="study-list")

            self.assertEqual(response.status_code, 200)
            self.assertIn("disabled", study_button.attrs["class"])
            self.assertIn("disabled", study_list_button.attrs["class"])

    def test_has_demo_no_child(self):
        G(DemographicData, user=self.user)
        self.login_user()

        # confirm user has demo and no children
        self.assertTrue(self.user.has_demographics)
        self.assertFalse(self.user.has_any_child)

        for url in self.my_account_urls:
            response = self.client.get(url)
            study_button, study_list_button = self.get_study_buttons(response)

            self.assertEqual(response.status_code, 200)
            self.assertIn("disabled", study_button.attrs["class"])
            self.assertIn("disabled", study_list_button.attrs["class"])

    def test_has_demo_ineligible_child(self):
        G(DemographicData, user=self.user)
        child = G(Child, user=self.user, birthday=datetime.datetime.now())
        self.login_user()

        # confirm user has demo and has a child
        self.assertTrue(self.user.has_demographics)
        self.assertTrue(self.user.has_any_child)

        # in addition the my account views, lets check the update child view as well.
        for url in self.get_my_account_urls(child):
            response = self.client.get(url)
            study_button, study_list_button = self.get_study_buttons(response)

            self.assertEqual(response.status_code, 200)
            self.assertIn("disabled", study_button.attrs["class"])
            self.assertNotIn("disabled", study_list_button.attrs["class"])

    def test_has_demo_eligible_child(self):
        G(DemographicData, user=self.user)
        seven_months_old = datetime.datetime.now() - datetime.timedelta(30 * 7)
        child = G(Child, user=self.user, birthday=seven_months_old)
        self.login_user()

        # in addition the my account views, lets check the update child view as well.
        for url in self.get_my_account_urls(child):
            response = self.client.get(url)
            study_button, study_list_button = self.get_study_buttons(response)

            self.assertEqual(response.status_code, 200)
            self.assertNotIn("disabled", study_button.attrs["class"])
            self.assertNotIn("disabled", study_list_button.attrs["class"])
