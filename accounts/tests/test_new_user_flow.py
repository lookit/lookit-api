from urllib.parse import urlencode

from bs4 import BeautifulSoup as BS
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse
from django_dynamic_fixture import G

from accounts.models import User
from studies.models import Study


class NewUserAccountTestCase(TestCase):
    def setUp(self):
        self.study = G(Study, image="asdf", name="study name")
        self.study.state = "active"
        self.study.save()
        self.study_details_url = reverse(
            "web:study-detail", kwargs={"uuid": self.study.uuid}
        )
        self.my_account_urls = [reverse("web:demographic-data-update")]

    def get_soup(self, response: HttpResponse):
        return BS(response.content, "html.parser")

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
        response = self.client.post(
            url,
            {
                "username": "user@email.com",
                "nickname": "user",
                "password1": "asdfasdfasdfasdf",
                "password2": "asdfasdfasdfasdf",
            },
            follow=True,
        )
        user = User.objects.filter(username="user@email.com").first()
        soup = self.get_soup(response)
        buttons = soup.find_all("a", class_="disabled")

        # confirm we ended up in the correct view
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            (reverse("web:demographic-data-update"), 302), response.redirect_chain
        )

        # confirm user was created
        self.assertEqual(user.nickname, "user")

        # confirm session data was set
        self.assertEqual(self.client.session["study_uuid"], str(self.study.uuid))
        self.assertEqual(self.client.session["study_name"], self.study.name)

        # confirm buttons are disabled
        self.assertTrue(
            any(
                b.text == f'Continue to StudyGo on to "{self.study.name}".'
                and "btn-primary" in b.get("class")
                for b in buttons
            )
        )
        self.assertTrue(
            any(
                b.text == "Find Another StudySee all available studies."
                and "btn-primary" not in b.get("class")
                for b in buttons
            )
        )
