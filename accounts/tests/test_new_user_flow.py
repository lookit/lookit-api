import datetime
import itertools
from typing import Any, Tuple
from urllib.parse import urlencode

from bs4 import BeautifulSoup as BS
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse
from django_dynamic_fixture import G

from accounts.models import Child, DemographicData, User
from studies.models import Study, StudyType


class NewUserAccountTestCase(TestCase):
    def setUp(self):
        """Set up each test case."""

        # Study and User to be used in each case.
        self.study = self.get_study()
        self.user = G(User, is_active=True)

        # The details view for the above study
        self.study_details_url = reverse(
            "web:study-detail", kwargs={"uuid": self.study.uuid}
        )

        # List of my account urls that we should check the state of our new buttons.  This is
        # missing the update child view.
        self.my_account_urls = [
            reverse("web:demographic-data-update"),
            reverse("accounts:manage-account"),
            reverse("web:children-list"),
            reverse("web:child-add"),
        ]

    def get_study(self):
        """Create study

        Returns:
            Study: The study object after it's been set active.
        """
        study = G(
            Study,
            image="asdf",
            name="study name",
            min_age_days=6 * 30,
            max_age_days=12 * 30,
            criteria_expression="",
            study_type=StudyType.get_ember_frame_player(),
        )
        study.state = "active"
        study.save()
        return study

    def get_soup(self, response: HttpResponse) -> BS:
        """Return the beautiful soup object for a response.

        Args:
            response (HttpResponse): Response returned from client

        Returns:
            BS: BeautifulSoup object
        """
        return BS(response.content, "html.parser")

    def get_study_buttons(self, response: HttpResponse) -> Tuple[Any, Any]:
        """Use Beautiful Soup to find and return the two buttons whose state we're checking.

        Args:
            response (HttpResponse): Response returned from client

        Returns:
            Tuple[Button, Button]: Returns a tuple of our two buttons
        """
        soup = self.get_soup(response)
        study_button = soup.find("a", class_="btn-has-study")
        study_list_button = soup.find("a", class_="btn-study-list")
        return (study_button, study_list_button)

    def get_my_account_urls(self, child: Child) -> itertools.chain:
        """Get account urls with update child url.

        Args:
            child (Child): Child model object

        Returns:
            itertools.chain: Generator
        """
        return itertools.chain(
            self.my_account_urls,
            (reverse("web:child-update", kwargs={"uuid": child.uuid}),),
        )

    def set_session(self) -> None:
        """Setup session to have study values."""
        session = self.client.session
        session["study_name"] = self.study.name
        session["study_uuid"] = str(self.study.uuid)
        session.save()

    def login_user(self) -> None:
        """Login our user."""
        user = self.user
        self.client.force_login(user)
        self.set_session()

    def test_valid_study_detail(self) -> None:
        """Check if study returns a valid details page."""
        response = self.client.get(self.study_details_url)
        self.assertEqual(response.status_code, 200)

    def test_login_and_create_buttons_exist(self) -> None:
        """Check if login and create new account button exist on page when user is logged out."""

        # get our response
        response = self.client.get(self.study_details_url)

        # use response to get forms.  Login and Sign up buttons are wrapped in forms.
        soup = self.get_soup(response)
        forms = soup.find_all("form")

        # The two urls we need to check for.
        login_url = reverse("login")
        signup_url = reverse("web:participant-signup")

        # There are a few forms on the page, we'll iterate through the list to check if at least
        # one has what we're looking for.
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

    def test_create_account_has_study(self) -> None:
        """Check if when user is created,that the study is stored in session."""

        # Set up url with the query string
        query = {"next": self.study_details_url}
        qs = urlencode(query, doseq=False)
        url = f"{reverse('web:participant-signup')}?{qs}"

        # Sign up a user
        nickname = "user_asdf"
        pw = "asdfasdfasdfasdf"
        response = self.client.post(
            url,
            {
                "username": "user@email.com",
                "nickname": nickname,
                "password1": pw,
                "password2": pw,
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

    def test_no_demo_no_child(self) -> None:
        """Check buttons when user has no Demo or any child."""

        # Login user
        self.login_user()

        # confirm user has no demo and no children
        self.assertFalse(self.user.has_demographics)
        self.assertFalse(self.user.has_any_child)

        # iterate over list of urls and check the state of the buttons
        for url in self.my_account_urls:
            response = self.client.get(url, follow=True)
            study_button, study_list_button = self.get_study_buttons(response)

            self.assertIn(response.status_code, [200, 302])
            self.assertIn("disabled", study_button.attrs["class"])
            self.assertIn("disabled", study_list_button.attrs["class"])

    def test_has_demo_no_child(self) -> None:
        """Check buttons when user has Demo but no children."""

        # Create demo and log in
        G(DemographicData, user=self.user)
        self.login_user()

        # confirm user has demo and no children
        self.assertTrue(self.user.has_demographics)
        self.assertFalse(self.user.has_any_child)

        # iterate over list of urls and check the state of the buttons
        for url in self.my_account_urls:
            response = self.client.get(url)
            study_button, study_list_button = self.get_study_buttons(response)

            self.assertEqual(response.status_code, 200)
            self.assertIn("disabled", study_button.attrs["class"])
            self.assertIn("disabled", study_list_button.attrs["class"])

    def test_has_demo_ineligible_child(self) -> None:
        """Check buttons when user has Demo but an ineligible child."""

        # Create Demo, Child and log user in
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

    def test_has_demo_eligible_child(self) -> None:
        """Check buttons when user has Denmo and an eligible child."""

        # Create Demo, Child and log user in
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
