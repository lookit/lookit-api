import datetime
from unittest.mock import Mock, patch

from django.contrib.flatpages.models import FlatPage
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sites.models import Site
from django.http import HttpRequest
from django.test import TestCase
from django.urls import reverse
from django_dynamic_fixture import G
from lark.exceptions import UnexpectedCharacters

from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from accounts.models import Child, GoogleAuthenticatorTOTP, User
from accounts.queries import get_child_eligibility
from studies.fields import GESTATIONAL_AGE_CHOICES
from studies.models import Lab, Study, StudyType


class AuthenticationTestCase(TestCase):
    def setUp(self):
        self.researcher_email = "test@test.com"
        self.participant_email = "tom@myspace.com"
        self.test_password = "testpassword20chars"

        # Researcher setup
        self.researcher = G(
            User,
            username=self.researcher_email,
            is_active=True,
            is_researcher=True,
            nickname="Lab Researcher",
        )
        self.researcher.set_password(self.test_password)
        self.otp = G(GoogleAuthenticatorTOTP, user=self.researcher, activated=True)
        self.researcher.save()

        # Participant Setup
        self.participant = G(
            User,
            username=self.participant_email,
            is_active=True,
            is_researcher=False,
            nickname="MySpace Tom",
        )
        self.participant.set_password(self.test_password)
        self.participant.save()

        # Site fixture enabling login
        self.fake_site = G(Site, id=1)

        # FlatPage fixture enabling login redirect to work.
        self.home_page = G(FlatPage, url="/")
        self.home_page.sites.add(self.fake_site)
        self.home_page.save()

    def test_researcher_registration_flow(self):
        response = self.client.post(
            reverse("accounts:researcher-registration"),
            {
                "username": "tester@test.com",
                "password1": self.test_password,
                "password2": self.test_password,
                "given_name": "Test",
                "family_name": "Person",
                "nickname": "Testman",
            },
            follow=True,
        )

        self.assertEqual(
            response.redirect_chain, [(reverse("accounts:2fa-setup"), 302)]
        )
        self.assertEqual(response.status_code, 200)

        # Mock correctly entered OTP
        otp = response.context["user"].otp
        response = self.client.post(
            reverse("accounts:2fa-setup"), {"otp_code": otp.provider.now()}, follow=True
        )

        self.assertTrue(response.wsgi_request.session[TWO_FACTOR_AUTH_SESSION_KEY])
        self.assertEqual(response.redirect_chain, [("/exp/studies/", 302)])
        self.assertEqual(response.status_code, 200)

    def test_2fa_flow_wrong_otp_reload_page(self):
        response = self.client.post(
            reverse("accounts:researcher-registration"),
            {
                "username": "another@test.com",
                "password1": self.test_password,
                "password2": self.test_password,
                "given_name": "Second",
                "family_name": "Person",
                "nickname": "Testwoman",
            },
            follow=True,
        )

        # Mock incorrectly entered OTP - off by one.
        otp = response.context["user"].otp
        correct = otp.provider.now()
        incorrect = str(int(correct) + 1)
        old_qr_svg = response.context["svg_qr_code"]
        response = self.client.post(
            reverse("accounts:2fa-setup"), {"otp_code": incorrect}, follow=True
        )
        new_qr_svg = response.context["svg_qr_code"]

        # Should have reloaded the page with the same QR code
        self.assertNotIn(TWO_FACTOR_AUTH_SESSION_KEY, response.wsgi_request.session)
        self.assertEqual(old_qr_svg, new_qr_svg)

    def test_researcher_login_redirect_to_2FA_verification(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.researcher_email, "password": self.test_password},
            follow=True,
        )
        self.assertTrue(response.status_code == 200)
        self.assertNotIn(TWO_FACTOR_AUTH_SESSION_KEY, response.wsgi_request.session)
        self.assertEqual(
            response.redirect_chain, [(reverse("accounts:2fa-login"), 302)]
        )

    def test_researcher_regular_login_cannot_access_exp_views(self):
        self.client.login(
            username=self.researcher_email, password=self.test_password,
        )
        response = self.client.get(reverse("exp:study-list"), follow=True)
        self.assertEqual(
            response.redirect_chain, [(reverse("accounts:2fa-login"), 302)]
        )

        # Cleanup, patch over messages as RequestFactory doesn't know about
        # middleware
        with patch("django.contrib.messages.api.add_message", autospec=True):
            self.client.logout()

    def test_researcher_2fa_login_success(self):
        # This is done without OTP.
        self.client.force_login(self.researcher)
        # Test that we can actually see the page
        response = self.client.get(reverse("accounts:2fa-login"))
        self.assertEqual(response.status_code, 200)
        # Test that we can send a correctly formatted POST request to it.
        response = self.client.post(
            reverse("accounts:2fa-login"),
            {"otp_code": self.otp.provider.now()},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual((reverse("exp:study-list"), 302), response.redirect_chain[-1])

        # Cleanup, patch over messages as RequestFactory doesn't know about
        # middleware
        with patch("django.contrib.messages.api.add_message", autospec=True):
            self.client.logout()

    def test_researcher_2fa_login_fail(self):
        self.client.force_login(self.researcher)
        two_factor_auth_url = reverse("accounts:2fa-login")
        # Test a bad auth code
        response = self.client.post(
            two_factor_auth_url, {"otp_code": str(int(self.otp.provider.now()) + 1)},
        )

        # We just reloaded the page, so we should get a 200
        self.assertEqual(response.status_code, 200)
        # There are form errors...
        self.assertNotEqual(len(response.context["form"].errors), 0)
        # And the session key isn't set.
        self.assertIsNot(
            response.wsgi_request.session.get(TWO_FACTOR_AUTH_SESSION_KEY), True
        )

        # Cleanup, patch over messages as RequestFactory doesn't know about
        # middleware
        with patch("django.contrib.messages.api.add_message", autospec=True):
            self.client.logout()

    def test_participant_login(self):
        response = self.client.post(
            # TODO: Technically, we shouldn't have to add the "next" query param
            #   to emulate the login link. However, this breaks the test due to
            #   the fact that settings.LOGIN_REDIRECT_URL targets /exp/. This is
            #   generally not a problem for the web application, as users will click
            #   the login link rather than entering via URL. We should change the
            #   environment variable in both environments handled by lookit-orchestrator
            #   before getting rid of this query parameter.
            reverse("login"),
            {
                "username": self.participant_email,
                "password": self.test_password,
                "next": "/",
            },
            follow=True,
        )
        self.assertTrue(response.status_code == 200)
        # Same as with researcher, we shouldn't have the 2FA session key
        self.assertFalse(response.wsgi_request.session[TWO_FACTOR_AUTH_SESSION_KEY])
        self.assertEqual(response.redirect_chain, [(reverse("web:home"), 302)])

        # Cleanup, patch over messages as RequestFactory doesn't know about
        # middleware
        with patch("django.contrib.messages.api.add_message", autospec=True):
            self.client.logout()

    def test_participant_no_access_to_2fa_views(self):
        self.client.force_login(self.participant)

        # No 2FA setup possible
        response = self.client.get(reverse("accounts:2fa-setup"))
        self.assertEqual(response.status_code, 403)

        response = self.client.get(reverse("accounts:2fa-login"))
        self.assertEqual(response.status_code, 403)

        # Cleanup, patch over messages as RequestFactory doesn't know about
        # middleware
        with patch("django.contrib.messages.api.add_message", autospec=True):
            self.client.logout()


class UserModelTestCase(TestCase):
    def setUp(self):
        self.lab_researcher = G(
            User, is_active=True, is_researcher=True, nickname="Lab Researcher"
        )

        self.unaffiliated_researcher = G(
            User, is_active=True, is_researcher=True, nickname="Study Researcher"
        )

        self.unaffiliated_researcher.labs.clear()

        self.participant = G(
            User, is_active=True, is_researcher=False, nickname="Participant"
        )
        self.lab = G(Lab, name="MIT", approved_to_test=True)
        self.study = G(Study, name="Test Study", lab=self.lab, built=True)

        self.study.researcher_group.user_set.add(self.unaffiliated_researcher)

        self.lab.researchers.add(self.lab_researcher)

    def test_lab_researcher_can_create_study(self):
        self.assertTrue(self.lab_researcher.can_create_study())

    def test_unaffiliated_researcher_cannot_create_study(self):
        self.assertFalse(self.unaffiliated_researcher.can_create_study())


class CriteriaExpressionTestCase(TestCase):
    def setUp(self):
        self.study_type = G(StudyType, name="default", id=1)
        self.lab = G(Lab, name="ECCL")
        self.fake_study = G(Study, study_type=self.study_type, lab=self.lab)
        self.complex_condition = (
            "((deaf OR hearing_impairment) OR NOT speaks_en) "
            "AND "
            "(age_in_days >= 365 AND age_in_days <= 1095)"
        )
        self.malformed_condition = "deaf or hearing_impairment or multiple_birth"

        self.compound_or_condition = "deaf OR hearing_impairment OR multiple_birth"

        self.gestational_age_range_condition = (
            "gestational_age_in_weeks <= 28 AND gestational_age_in_weeks > 24"
        )

        self.unspecified_gestational_age_range_condition = (
            "gestational_age_in_weeks = na"
        )

        self.gender_specific_condition = "gender = male OR gender = OTHER"

        self.number_of_languages_condition = "num_languages < 6 AND n_languages > 1"

        self.compound_and_condition = "deaf AND dyslexia AND age_in_days >= 1000"

        self.deaf_male_child = G(
            Child,
            existing_conditions=Child.existing_conditions.deaf,
            gender="m",
            languages_spoken=Child.languages_spoken.en,
            birthday=datetime.date.today() - datetime.timedelta(days=3 * 365),
        )

        self.hearing_impaired_child = G(
            Child,
            existing_conditions=Child.existing_conditions.hearing_impairment,
            languages_spoken=Child.languages_spoken.en,
            birthday=datetime.date.today() - datetime.timedelta(days=3 * 365),
        )

        self.french_female_twin = G(
            Child,
            existing_conditions=Child.existing_conditions.multiple_birth,
            languages_spoken=Child.languages_spoken.fr,
            gender="f",
            birthday=datetime.date.today() - datetime.timedelta(days=3 * 365),
        )

        self.older_deaf_child_with_dyslexia = G(
            Child,
            existing_conditions=Child.existing_conditions.deaf
            | Child.existing_conditions.dyslexia,
            languages_spoken=Child.languages_spoken.en,
            birthday=datetime.date.today() - datetime.timedelta(days=10 * 365),
        )

        self.born_at_25_weeks = G(
            Child,
            gestational_age_at_birth=GESTATIONAL_AGE_CHOICES.twenty_five_weeks,
            birthday=datetime.date.today() - datetime.timedelta(days=3 * 365),
        )

        self.born_at_35_weeks = G(
            Child,
            gestational_age_at_birth=GESTATIONAL_AGE_CHOICES.thirty_five_weeks,
            birthday=datetime.date.today() - datetime.timedelta(days=3 * 365),
        )

        self.child_with_unspecified_gestational_age = G(
            Child,
            gestational_age_at_birth=GESTATIONAL_AGE_CHOICES.no_answer,
            birthday=datetime.date.today() - datetime.timedelta(days=3 * 365),
        )

        self.polyglot_child = G(
            Child,
            languages_spoken=Child.languages_spoken.en
            | Child.languages_spoken.fr
            | Child.languages_spoken.ja
            | Child.languages_spoken.nl
            | Child.languages_spoken.ko,
            birthday=datetime.date.today() - datetime.timedelta(days=3 * 365),
        )

    def test_simple_condition(self):
        self.assertTrue(get_child_eligibility(self.deaf_male_child, "deaf"))

    def test_complex_condition(self):
        self.assertTrue(
            get_child_eligibility(self.deaf_male_child, self.complex_condition)
        )
        self.assertTrue(
            get_child_eligibility(self.hearing_impaired_child, self.complex_condition)
        )
        self.assertTrue(
            get_child_eligibility(self.french_female_twin, self.complex_condition)
        )
        self.assertFalse(
            get_child_eligibility(
                self.older_deaf_child_with_dyslexia, self.complex_condition
            )
        )

    def test_parse_failure(self):
        self.assertRaises(
            UnexpectedCharacters,
            get_child_eligibility,
            self.deaf_male_child,
            self.malformed_condition,
        )

    def test_compound_or(self):
        self.assertTrue(
            get_child_eligibility(self.deaf_male_child, self.compound_or_condition)
        )
        self.assertTrue(
            get_child_eligibility(
                self.hearing_impaired_child, self.compound_or_condition
            )
        )
        # Non-english speaking also multiple birth
        self.assertTrue(
            get_child_eligibility(self.french_female_twin, self.compound_or_condition)
        )

    def test_compound_and(self):
        self.assertTrue(
            get_child_eligibility(
                self.older_deaf_child_with_dyslexia, self.compound_and_condition
            )
        )

        self.assertFalse(
            get_child_eligibility(self.french_female_twin, self.compound_and_condition)
        )

    def test_gestational_age_range(self):
        self.assertTrue(
            get_child_eligibility(
                self.born_at_25_weeks, self.gestational_age_range_condition
            )
        )

        self.assertFalse(
            get_child_eligibility(
                self.born_at_35_weeks, self.gestational_age_range_condition
            )
        )

    def test_gender_specification(self):
        self.assertTrue(
            get_child_eligibility(self.deaf_male_child, self.gender_specific_condition)
        )

        self.assertFalse(
            get_child_eligibility(
                self.french_female_twin, self.gender_specific_condition
            )
        )

    def test_num_languages_spoken(self):
        self.assertTrue(
            get_child_eligibility(
                self.polyglot_child, self.number_of_languages_condition
            )
        )

        self.assertFalse(
            get_child_eligibility(
                self.french_female_twin, self.number_of_languages_condition
            )
        )

    def test_unspecified_gestational_age(self):
        self.assertTrue(
            get_child_eligibility(
                self.child_with_unspecified_gestational_age,
                self.unspecified_gestational_age_range_condition,
            )
        )

        self.assertFalse(
            get_child_eligibility(
                self.child_with_unspecified_gestational_age,
                self.gestational_age_range_condition,
            )
        )
