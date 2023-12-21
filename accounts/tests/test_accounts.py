import datetime
from unittest import skip
from unittest.mock import MagicMock, patch

from django.contrib.sites.models import Site
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.client import Client
from django.urls import reverse
from django_dynamic_fixture import G
from lark.exceptions import UnexpectedCharacters
from parameterized import parameterized

from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from accounts.models import Child, DemographicData, GoogleAuthenticatorTOTP, User
from accounts.queries import (
    age_range_eligibility_for_study,
    child_in_age_range_for_study_days_difference,
    get_child_eligibility,
    get_child_eligibility_for_study,
    get_child_participation_eligibility,
)
from studies.fields import GESTATIONAL_AGE_CHOICES
from studies.models import ConsentRuling, Lab, Response, Study, StudyType, Video


class AuthenticationTestCase(TestCase):
    def setUp(self):
        self.researcher_email = "test@test.com"
        self.participant_email = "tom@myspace.com"
        self.test_password = "testpassword20chars"
        self.base32_secret = "GNKVX3Y2U6BKTVKU"

        # Researcher setup
        self.researcher = G(
            User,
            username=self.researcher_email,
            is_active=True,
            is_researcher=True,
            nickname="Lab Researcher",
        )
        self.researcher.set_password(self.test_password)
        self.otp = GoogleAuthenticatorTOTP.objects.create(
            user=self.researcher, secret=self.base32_secret, activated=True
        )
        self.researcher.save()

        # Lab and study setup for testing view protections
        self.lab = G(Lab, name="MIT")
        self.study = G(
            Study,
            creator=self.researcher,
            name="Fake Study",
            lab=self.lab,
            shared_preview=True,
            study_type=StudyType.get_ember_frame_player(),
        )

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

        self.child = G(
            Child,
            user=self.participant,
            given_name="Baby",
            birthday=datetime.date.today() - datetime.timedelta(180),
        )
        self.response = G(
            Response, child=self.child, study=self.study, completed_consent_frame=True
        )
        self.video = G(
            Video,
            study=self.study,
            response=self.response,
            is_consent_footage=False,
            frame_id="2-my-consent-frame",
        )

        # Site fixture enabling login
        self.fake_site = G(Site, id=1)

        # All the GET views that should be protected by 2fa
        self.mfa_protected_get_views = [
            reverse("exp:study-list"),
            reverse("exp:lab-list"),
            reverse("exp:lab-create"),
            reverse("exp:lab-detail", kwargs={"pk": self.lab.pk}),
            reverse("exp:lab-edit", kwargs={"pk": self.lab.pk}),
            reverse("exp:lab-members", kwargs={"pk": self.lab.pk}),
            reverse("exp:lab-request", kwargs={"pk": self.lab.pk}),
            reverse("exp:participant-list"),
            reverse("exp:participant-detail", kwargs={"pk": self.participant.pk}),
            reverse("exp:study-participant-analytics"),
            reverse("exp:study-create"),
            reverse("exp:study", kwargs={"pk": self.study.pk}),
            reverse("exp:study-participant-contact", kwargs={"pk": self.study.pk}),
            reverse("exp:study-edit", kwargs={"pk": self.study.pk}),
            reverse("exp:study-responses-list", kwargs={"pk": self.study.pk}),
            reverse(
                "exp:study-responses-single-download", kwargs={"pk": self.study.pk}
            ),
            reverse(
                "exp:study-response-video-download",
                kwargs={"pk": self.study.pk, "video": self.video.pk},
            ),
            reverse("exp:study-responses-all", kwargs={"pk": self.study.pk}),
            reverse(
                "exp:study-responses-consent-manager", kwargs={"pk": self.study.pk}
            ),
            reverse("exp:study-responses-download-json", kwargs={"pk": self.study.pk}),
            reverse("exp:study-responses-download-csv", kwargs={"pk": self.study.pk}),
            reverse(
                "exp:study-responses-download-summary-dict-csv",
                kwargs={"pk": self.study.pk},
            ),
            reverse(
                "exp:study-responses-children-summary-csv", kwargs={"pk": self.study.pk}
            ),
            reverse(
                "exp:study-responses-children-summary-dict-csv",
                kwargs={"pk": self.study.pk},
            ),
            reverse(
                "exp:study-hashed-id-collision-check", kwargs={"pk": self.study.pk}
            ),
            reverse(
                "exp:study-responses-download-frame-data-zip-csv",
                kwargs={"pk": self.study.pk},
            ),
            reverse(
                "exp:study-responses-download-frame-data-dict-csv",
                kwargs={"pk": self.study.pk},
            ),
            reverse("exp:study-demographics", kwargs={"pk": self.study.pk}),
            reverse(
                "exp:study-demographics-download-json", kwargs={"pk": self.study.pk}
            ),
            reverse(
                "exp:study-demographics-download-csv", kwargs={"pk": self.study.pk}
            ),
            reverse(
                "exp:study-demographics-download-dict-csv", kwargs={"pk": self.study.pk}
            ),
            reverse("exp:study-attachments", kwargs={"pk": self.study.pk}),
            reverse("exp:preview-detail", kwargs={"uuid": self.study.uuid}),
        ]
        # All the POST views that should be protected by 2fa - url, data to post tuples
        self.mfa_protected_post_views = [
            (
                reverse(
                    "exp:study-delete-preview-responses", kwargs={"pk": self.study.pk}
                ),
                {},
            ),
            (reverse("exp:study-build", kwargs={"uuid": self.study.uuid}), {}),
            (
                reverse(
                    "exp:study-response-submit-feedback", kwargs={"pk": self.study.pk}
                ),
                {"comment": "Thank you!", "response_id": self.response.pk},
            ),
        ]

    @skip("Issue with CI #1055")
    def test_proxy_auth_researcher_success(self):
        """Check if researcher can get redirected through proxy to experiment."""
        client = Force2FAClient()
        client.login(username=self.researcher_email, password=self.test_password)
        researcher_child = G(
            Child,
            user=self.researcher,
            given_name="Baby",
            birthday=datetime.date.today() - datetime.timedelta(180),
        )
        url = reverse(
            "exp:preview-proxy",
            kwargs={"uuid": self.study.uuid, "child_id": researcher_child.uuid},
        )
        response = client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(url))

    @skip("Issue with CI #1055")
    def test_proxy_auth_researcher_fail(self):
        """Check if researcher can get redirected to login page if they don't have 2fa setup."""
        self.client.login(username=self.researcher_email, password=self.test_password)
        researcher_child = G(
            Child,
            user=self.researcher,
            given_name="Baby",
            birthday=datetime.date.today() - datetime.timedelta(180),
        )
        url = reverse(
            "exp:preview-proxy",
            kwargs={"uuid": self.study.uuid, "child_id": researcher_child.uuid},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))

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
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(TWO_FACTOR_AUTH_SESSION_KEY, response.wsgi_request.session)
        self.assertEqual(
            response.redirect_chain, [(reverse("accounts:2fa-login"), 302)]
        )

    def test_researcher_regular_login_cannot_access_exp_views(self):
        self.client.login(username=self.researcher_email, password=self.test_password)
        for url in self.mfa_protected_get_views:
            response = self.client.get(url)
            self.assertEqual(
                (response.url, response.status_code),
                (reverse("accounts:2fa-login"), 302),
                f"Researcher logged in without 2FA not redirected from {url}",
            )
        for url, data in self.mfa_protected_post_views:
            response = self.client.post(url, data, follow=True)
            self.assertEqual(
                response.redirect_chain[-1],
                (reverse("accounts:2fa-login"), 302),
                f"Researcher logged in without 2FA not redirected from {url}",
            )

        # Cleanup, patch over messages as RequestFactory doesn't know about
        # middleware
        with patch("django.contrib.messages.api.add_message", autospec=True):
            self.client.logout()

    def test_researcher_2fa_login_success(self):
        self.client.login(username=self.researcher_email, password=self.test_password)
        # Test that we can actually see the page
        self.assertTrue(self.researcher.is_authenticated)
        response = self.client.get(reverse("accounts:2fa-login"))
        self.assertEqual(response.status_code, 200)
        next_url = response.context["next"]
        self.assertEqual(next_url, reverse("exp:study-list"))
        # Test that we can send a correctly formatted POST request to it.
        # Also, fully mimic posting form from the page itself by carrying `next`
        # through.
        response = self.client.post(
            reverse("accounts:2fa-login"),
            {"otp_code": self.otp.provider.now(), "next": next_url},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1], (reverse("exp:study-list"), 302))

        # Cleanup, patch over messages as RequestFactory doesn't know about
        # middleware
        with patch("django.contrib.messages.api.add_message", autospec=True):
            self.client.logout()

    def test_researcher_2fa_login_fail(self):
        self.client.login(username=self.researcher_email, password=self.test_password)
        two_factor_auth_url = reverse("accounts:2fa-login")
        # Test a bad auth code
        response = self.client.post(
            two_factor_auth_url, {"otp_code": str(int(self.otp.provider.now()) + 1)}
        )

        # We just reloaded the page, so we should get a 200
        self.assertEqual(response.status_code, 200)
        # There are form errors...
        self.assertNotEqual(len(response.context["form"].errors), 0)
        # And the session key isn't set.
        self.assertFalse(response.wsgi_request.session.get(TWO_FACTOR_AUTH_SESSION_KEY))

        # We can't access exp views
        response = self.client.get(reverse("exp:study-list"), follow=True)
        self.assertEqual(
            response.redirect_chain, [(reverse("accounts:2fa-login"), 302)]
        )

        # Cleanup, patch over messages as RequestFactory doesn't know about
        # middleware
        with patch("django.contrib.messages.api.add_message", autospec=True):
            self.client.logout()

    def test_participant_login(self):
        response = self.client.post(
            # Pretend that we have already gotten the page ("next" is loaded into
            # template context for us already, and it becomes part of the form)
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

        # Logged-in user is available
        user = response.wsgi_request.user
        self.assertFalse(user.is_anonymous)
        self.assertTrue(user.is_authenticated)
        self.assertEqual(user.username, self.participant_email)

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

        # Site fixture enabling login
        self.fake_site = G(Site, id=1)

        self.test_password = "testpassword20chars"

        # This represents the old format, of which we have plenty in the DB. We are
        # leaving these untouched, while both preventing duplicate account creation
        # and allowing case-insensitive login.
        self.bad_email_user = G(
            User, is_active=True, is_researcher=False, username="MiXeDcAsE@gmAiL.CoM"
        )
        self.bad_email_user.set_password(self.test_password)
        self.bad_email_user.save()

        self.lab = G(Lab, name="MIT", approved_to_test=True)
        self.study = G(
            Study,
            name="Test Study",
            lab=self.lab,
            built=True,
            study_type=StudyType.get_ember_frame_player(),
        )

        self.study.researcher_group.user_set.add(self.unaffiliated_researcher)

        self.lab.researchers.add(self.lab_researcher)

    def test_lab_researcher_can_create_study(self):
        self.assertTrue(self.lab_researcher.can_create_study())

    def test_unaffiliated_researcher_cannot_create_study(self):
        self.assertFalse(self.unaffiliated_researcher.can_create_study())

    def test_create_user_lowercases_username(self):
        # TODO: Do we actually use `create_user` anywhere?
        new_user = User.objects.create_user("BAD.EMAIL@GMAIL.COM")
        self.assertEqual(new_user.username, "bad.email@gmail.com")

    def test_case_insensitive_login_with_mixed_case_in_db(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": "mixedcase@gmail.com",
                "password": self.test_password,
                "next": "/",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [(reverse("web:home"), 302)])

    def test_case_insensitive_login_with_mixed_case_in_request(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": "Mixedcase@gmail.COM",
                "password": self.test_password,
                "next": "/",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [(reverse("web:home"), 302)])

    def test_no_duplicate_registrations_case_insensitive(self):
        response = self.client.post(
            reverse("accounts:researcher-registration"),
            {
                "username": "mixedcasE@gmail.com",
                "password1": self.test_password,
                "password2": self.test_password,
                "given_name": "Should",
                "family_name": "Not",
                "nickname": "Be Allowed",
            },
            follow=True,
        )

        user = response.context["user"]

        self.assertTrue(user.is_anonymous)
        self.assertFalse(user.is_authenticated)


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


class EligibilityTestCase(TestCase):
    def setUp(self):
        self.study_type = G(StudyType, name="default", id=1)
        self.lab = G(Lab, name="ECCL")
        self.preschooler_study_with_criteria_and_age_range = G(
            Study,
            study_type=self.study_type,
            lab=self.lab,
            criteria_expression="multiple_birth AND gestational_age_in_weeks <= 30",
            min_age_days=0,
            min_age_months=0,
            min_age_years=2,
            max_age_days=0,
            max_age_months=0,
            max_age_years=4,
        )

        self.almost_one_study = G(
            Study,
            study_type=self.study_type,
            lab=self.lab,
            min_age_days=30,
            min_age_months=11,
            min_age_years=0,
            max_age_days=0,
            max_age_months=0,
            max_age_years=1,
        )

        # Age range 360 - 365 days
        self.almost_one_study = G(
            Study,
            study_type=self.study_type,
            lab=self.lab,
            min_age_days=30,
            min_age_months=11,
            min_age_years=0,
            max_age_days=0,
            max_age_months=0,
            max_age_years=1,
            criteria_expression="",
        )

        self.elementary_study = G(
            Study,
            study_type=self.study_type,
            lab=self.lab,
            min_age_days=15,
            min_age_months=2,
            min_age_years=5,
            max_age_days=4,
            max_age_months=8,
            max_age_years=10,
            criteria_expression="",
        )

        self.teenager_study = G(
            Study,
            study_type=self.study_type,
            lab=self.lab,
            min_age_days=3,
            min_age_months=0,
            min_age_years=15,
            max_age_days=4,
            max_age_months=0,
            max_age_years=17,
            criteria_expression="",
        )

        self.twin_preemie_baby = G(
            Child,
            existing_conditions=Child.existing_conditions.multiple_birth,
            gender="m",
            languages_spoken=Child.languages_spoken.en,
            gestational_age_at_birth=GESTATIONAL_AGE_CHOICES.twenty_six_weeks,
            birthday=datetime.date.today() - datetime.timedelta(days=180),
        )

        self.twin_preemie_3yo = G(
            Child,
            existing_conditions=Child.existing_conditions.multiple_birth,
            gender="m",
            languages_spoken=Child.languages_spoken.en,
            gestational_age_at_birth=GESTATIONAL_AGE_CHOICES.twenty_six_weeks,
            birthday=datetime.date.today() - datetime.timedelta(days=3 * 365),
        )

        self.twin_full_term_3yo = G(
            Child,
            existing_conditions=Child.existing_conditions.multiple_birth,
            gender="m",
            languages_spoken=Child.languages_spoken.en,
            gestational_age_at_birth=GESTATIONAL_AGE_CHOICES.thirty_nine_weeks,
            birthday=datetime.date.today() - datetime.timedelta(days=3 * 365),
        )

        self.twin_preemie_4yo = G(
            Child,
            existing_conditions=Child.existing_conditions.multiple_birth,
            gender="m",
            languages_spoken=Child.languages_spoken.en,
            gestational_age_at_birth=GESTATIONAL_AGE_CHOICES.twenty_six_weeks,
            birthday=datetime.date.today() - datetime.timedelta(days=4 * 365 + 180),
        )

        self.unborn_child = G(
            Child, birthday=datetime.date.today() + datetime.timedelta(days=30)
        )

    def test_criteria_expression_used(self):
        self.assertTrue(
            get_child_eligibility_for_study(
                self.twin_preemie_3yo,
                self.preschooler_study_with_criteria_and_age_range,
            )
        )
        self.assertFalse(
            get_child_eligibility_for_study(
                self.twin_full_term_3yo,
                self.preschooler_study_with_criteria_and_age_range,
            )
        )

    def test_age_range_used(self):
        self.assertFalse(
            get_child_eligibility_for_study(
                self.twin_preemie_baby,
                self.preschooler_study_with_criteria_and_age_range,
            )
        )
        self.assertTrue(
            get_child_eligibility_for_study(
                self.twin_preemie_3yo,
                self.preschooler_study_with_criteria_and_age_range,
            )
        )
        self.assertFalse(
            get_child_eligibility_for_study(
                self.twin_preemie_4yo,
                self.preschooler_study_with_criteria_and_age_range,
            )
        )

    def test_unborn_children_ineligible(self):
        self.assertFalse(
            get_child_eligibility_for_study(self.unborn_child, self.almost_one_study)
        )
        self.assertFalse(
            get_child_eligibility_for_study(self.unborn_child, self.elementary_study)
        )
        self.assertFalse(
            get_child_eligibility_for_study(self.unborn_child, self.teenager_study)
        )

    def test_age_range_bounds(self):
        for study in [
            self.almost_one_study,
            self.elementary_study,
            self.teenager_study,
        ]:
            lower_bound = float(
                study.min_age_years * 365
                + study.min_age_months * 30
                + study.min_age_days
            )
            upper_bound = float(
                study.max_age_years * 365
                + study.max_age_months * 30
                + study.max_age_days
            )
            self.assertFalse(
                get_child_eligibility_for_study(
                    G(
                        Child,
                        birthday=datetime.date.today()
                        - datetime.timedelta(days=lower_bound - 1),
                    ),
                    study,
                ),
                "Child just below lower age bound is eligible",
            )
            self.assertTrue(
                get_child_eligibility_for_study(
                    G(
                        Child,
                        birthday=datetime.date.today()
                        - datetime.timedelta(days=lower_bound),
                    ),
                    study,
                ),
                "Child at lower age bound is not eligible",
            )
            self.assertTrue(
                get_child_eligibility_for_study(
                    G(
                        Child,
                        birthday=datetime.date.today()
                        - datetime.timedelta(days=upper_bound),
                    ),
                    study,
                ),
                f"Child at upper age bound ({upper_bound} days) is not eligible",
            )
            self.assertFalse(
                get_child_eligibility_for_study(
                    G(
                        Child,
                        birthday=datetime.date.today()
                        - datetime.timedelta(days=upper_bound + 1),
                    ),
                    study,
                ),
                "Child just above upper age bound is eligible",
            )

    def test_age_range_days_difference(self):
        lower_bound = float(
            self.almost_one_study.min_age_years * 365
            + self.almost_one_study.min_age_months * 30
            + self.almost_one_study.min_age_days
        )
        upper_bound = float(
            self.almost_one_study.max_age_years * 365
            + self.almost_one_study.max_age_months * 30
            + self.almost_one_study.max_age_days
        )
        self.assertEqual(
            child_in_age_range_for_study_days_difference(
                G(
                    Child,
                    birthday=datetime.date.today()
                    - datetime.timedelta(days=lower_bound + 1),
                ),
                self.almost_one_study,
            ),
            0,
            "Child just inside the Study's lower bound has a day difference of 0.",
        )
        self.assertEqual(
            child_in_age_range_for_study_days_difference(
                G(
                    Child,
                    birthday=datetime.date.today()
                    - datetime.timedelta(days=upper_bound - 1),
                ),
                self.almost_one_study,
            ),
            0,
            "Child just inside the Study's upper bound has a day difference of 0.",
        )
        self.assertEqual(
            child_in_age_range_for_study_days_difference(
                G(
                    Child,
                    birthday=datetime.date.today()
                    - datetime.timedelta(days=lower_bound - 1),
                ),
                self.almost_one_study,
            ),
            -1,
            "Child one day younger than Study's lower bound has a day difference of -1.",
        )
        self.assertEqual(
            child_in_age_range_for_study_days_difference(
                G(
                    Child,
                    birthday=datetime.date.today()
                    - datetime.timedelta(days=upper_bound + 1),
                ),
                self.almost_one_study,
            ),
            1,
            "Child one day older than Study's upper bound has a day difference of 1.",
        )

    @parameterized.expand(
        [
            # Study 0-5 yrs, Child is 0-1 yrs
            (
                MagicMock(
                    min_age_years=0,
                    min_age_months=0,
                    min_age_days=0,
                    max_age_years=5,
                    max_age_months=0,
                    max_age_days=0,
                ),
                [0, 1],
                True,
            ),
            # Study 1-5 yrs, Child is 0-1 yrs
            (
                MagicMock(
                    min_age_years=1,
                    min_age_months=0,
                    min_age_days=0,
                    max_age_years=5,
                    max_age_months=0,
                    max_age_days=0,
                ),
                [0, 1],
                True,
            ),
            # Study 2-5 yrs, Child is 0-1 yrs
            (
                MagicMock(
                    min_age_years=2,
                    min_age_months=0,
                    min_age_days=0,
                    max_age_years=5,
                    max_age_months=0,
                    max_age_days=0,
                ),
                [0, 1],
                False,
            ),
            # Study 0-24 months, Child is 0-1 yrs
            (
                MagicMock(
                    min_age_years=0,
                    min_age_months=0,
                    min_age_days=0,
                    max_age_years=0,
                    max_age_months=12 * 2,
                    max_age_days=0,
                ),
                [0, 1],
                True,
            ),
        ]
    )
    def test_get_child_eligibility_for_study(
        self, mock_study, child_age_range, expected
    ):
        self.assertIs(
            age_range_eligibility_for_study(child_age_range, mock_study), expected
        )

    def test_get_child_eligibilty_prior_studies_success(self):
        study = G(
            Study,
            max_age_years=2,
            criteria_expression="",
            study_type=StudyType.get_ember_frame_player(),
        )
        child = G(Child, birthday=datetime.date.today())

        self.assertTrue(get_child_participation_eligibility(child, study))
        self.assertTrue(get_child_eligibility_for_study(child, study))

    def test_get_child_eligibilty_prior_studies_must_have_participated(self):
        other_study = G(
            Study,
            max_age_years=2,
            criteria_expression="",
            study_type=StudyType.get_ember_frame_player(),
        )
        study = G(
            Study,
            max_age_years=2,
            criteria_expression="",
            must_have_participated=[other_study],
            study_type=StudyType.get_ember_frame_player(),
        )
        child = G(Child, birthday=datetime.date.today())

        # Check without response
        self.assertFalse(get_child_participation_eligibility(child, study))
        self.assertFalse(get_child_eligibility_for_study(child, study))

        # Add invalid (empty) response
        G(Response, child=child, study=other_study, sequence=[])

        # Check with invalid response
        self.assertFalse(get_child_participation_eligibility(child, study))
        self.assertFalse(get_child_eligibility_for_study(child, study))

        # Add valid response
        G(Response, child=child, study=other_study, sequence=["0-video-config"])

        # Check with response
        self.assertTrue(get_child_participation_eligibility(child, study))
        self.assertTrue(get_child_eligibility_for_study(child, study))

    def test_get_child_eligibilty_must_have_participated_external(self):
        external_study = G(
            Study,
            max_age_years=2,
            criteria_expression="",
            study_type=StudyType.get_external(),
        )
        study = G(
            Study,
            name="study",
            max_age_years=2,
            criteria_expression="",
            study_type=StudyType.get_ember_frame_player(),
            must_have_participated=[external_study],
        )
        child_1 = G(Child, birthday=datetime.date.today())
        child_2 = G(Child, birthday=datetime.date.today())

        # Check without response
        self.assertFalse(get_child_participation_eligibility(child_1, study))
        self.assertFalse(get_child_eligibility_for_study(child_1, study))
        self.assertFalse(get_child_participation_eligibility(child_2, study))
        self.assertFalse(get_child_eligibility_for_study(child_2, study))

        # For external studies, an empty response still counts as 'participated'
        G(Response, child=child_1, study=external_study)
        G(Response, child=child_2, study=external_study, sequence=[])

        self.assertTrue(get_child_participation_eligibility(child_1, study))
        self.assertTrue(get_child_eligibility_for_study(child_1, study))
        self.assertTrue(get_child_participation_eligibility(child_2, study))
        self.assertTrue(get_child_eligibility_for_study(child_2, study))

    def test_get_child_eligibilty_prior_studies_must_not_have_participated(self):
        other_study = G(
            Study,
            max_age_years=2,
            criteria_expression="",
            study_type=StudyType.get_ember_frame_player(),
        )
        study = G(
            Study,
            max_age_years=2,
            criteria_expression="",
            must_not_have_participated=[other_study],
            study_type=StudyType.get_ember_frame_player(),
        )
        child = G(Child, birthday=datetime.date.today())

        # Check without response
        self.assertTrue(get_child_participation_eligibility(child, study))
        self.assertTrue(get_child_eligibility_for_study(child, study))

        # Add response
        G(Response, child=child, study=other_study, sequence=["0-video-config"])

        # Check again with response
        self.assertFalse(get_child_participation_eligibility(child, study))
        self.assertFalse(get_child_eligibility_for_study(child, study))

    def test_get_child_eligibilty_must_not_have_participated_external(self):
        other_study = G(
            Study,
            max_age_years=2,
            criteria_expression="",
            study_type=StudyType.get_external(),
        )
        study = G(
            Study,
            max_age_years=2,
            criteria_expression="",
            must_not_have_participated=[other_study],
            study_type=StudyType.get_ember_frame_player(),
        )
        child = G(Child, birthday=datetime.date.today())

        # Check without response
        self.assertTrue(get_child_participation_eligibility(child, study))
        self.assertTrue(get_child_eligibility_for_study(child, study))

        # Add response (empty sequence still counts for external study participation)
        G(Response, child=child, study=other_study, sequence=[])

        # Check again with response
        self.assertFalse(get_child_participation_eligibility(child, study))
        self.assertFalse(get_child_eligibility_for_study(child, study))

    def test_get_child_eligibilty_multiple_studies_must_have_participated(self):
        required_study_1 = G(
            Study, max_age_years=2, study_type=StudyType.get_ember_frame_player()
        )
        required_study_2 = G(
            Study, max_age_years=2, study_type=StudyType.get_ember_frame_player()
        )
        study = G(
            Study,
            max_age_years=2,
            criteria_expression="",
            must_have_participated=[required_study_1, required_study_2],
            study_type=StudyType.get_ember_frame_player(),
        )
        child = G(Child, birthday=datetime.date.today())

        # Add response to one of the required studies
        G(Response, child=child, study=required_study_1, sequence=["0-video-config"])

        # Should not be eligible with a valid response to only one of the two required studies
        self.assertFalse(get_child_participation_eligibility(child, study))
        self.assertFalse(get_child_eligibility_for_study(child, study))

        # Should be eligible with valid responses to all of the required studies
        G(Response, child=child, study=required_study_2, sequence=["0-video-config"])
        self.assertTrue(get_child_participation_eligibility(child, study))
        self.assertTrue(get_child_eligibility_for_study(child, study))

    def test_get_child_eligibilty_multiple_studies_must_not_have_participated(self):
        disallowed_study_1 = G(
            Study,
            max_age_years=2,
            criteria_expression="",
            study_type=StudyType.get_ember_frame_player(),
        )
        disallowed_study_2 = G(
            Study,
            max_age_years=2,
            criteria_expression="",
            study_type=StudyType.get_ember_frame_player(),
        )
        study = G(
            Study,
            max_age_years=2,
            criteria_expression="",
            must_not_have_participated=[disallowed_study_1, disallowed_study_2],
            study_type=StudyType.get_ember_frame_player(),
        )
        child = G(Child, birthday=datetime.date.today())

        # Should be eligible with no responses to either of the required studies
        self.assertTrue(get_child_participation_eligibility(child, study))
        self.assertTrue(get_child_eligibility_for_study(child, study))

        # Add response to one of the disallowed studies
        G(Response, child=child, study=disallowed_study_1, sequence=["0-video-config"])

        # Should not be eligible with a response to one or both of the two disallowed studies
        self.assertFalse(get_child_participation_eligibility(child, study))
        self.assertFalse(get_child_eligibility_for_study(child, study))
        G(Response, child=child, study=disallowed_study_2, sequence=["0-video-config"])
        self.assertFalse(get_child_participation_eligibility(child, study))
        self.assertFalse(get_child_eligibility_for_study(child, study))

    def test_get_child_eligibilty_multiple_participation_criteria(self):
        required_study = G(
            Study,
            max_age_years=2,
            criteria_expression="",
            study_type=StudyType.get_ember_frame_player(),
        )
        disallowed_study = G(
            Study,
            max_age_years=2,
            criteria_expression="",
            study_type=StudyType.get_ember_frame_player(),
        )
        study = G(
            Study,
            max_age_years=2,
            criteria_expression="",
            must_have_participated=[required_study],
            must_not_have_participated=[disallowed_study],
            study_type=StudyType.get_ember_frame_player(),
        )

        # Child is not eligible if they meet the required study criteria but not the disallowed study criteria
        child_1 = G(Child, birthday=datetime.date.today())
        G(Response, child=child_1, study=required_study, sequence=["0-video-config"])
        G(Response, child=child_1, study=disallowed_study, sequence=["0-video-config"])
        self.assertFalse(get_child_participation_eligibility(child_1, study))
        self.assertFalse(get_child_eligibility_for_study(child_1, study))

        # Child is not eligible if they meet the disallowed study criteria but not the required study criteria
        child_2 = G(Child, birthday=datetime.date.today())
        self.assertFalse(get_child_participation_eligibility(child_2, study))
        self.assertFalse(get_child_eligibility_for_study(child_2, study))

        # Child is eligible if they meet both the required and disallowed study criteria
        G(Response, child=child_2, study=required_study, sequence=["0-video-config"])
        self.assertTrue(get_child_participation_eligibility(child_2, study))
        self.assertTrue(get_child_eligibility_for_study(child_2, study))


class Force2FAClient(Client):
    """For convenience when testing researcher views, let's just pretend everyone is two-factor auth'd."""

    @property
    def session(self):
        _session = super().session
        _session[TWO_FACTOR_AUTH_SESSION_KEY] = True
        return _session


class ParticipantViewsTestCase(TestCase):
    def setUp(self):
        self.client = Force2FAClient()

        self.study_admin = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 1"
        )
        self.study_designer = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 2"
        )
        self.other_researcher = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 3"
        )

        self.lab = G(Lab, name="MIT", approved_to_test=True)

        small_gif = (
            b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x00\x00\x00\x21\xf9\x04"
            b"\x01\x0a\x00\x01\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02"
            b"\x02\x4c\x01\x00\x3b"
        )
        self.study = G(
            Study,
            image=SimpleUploadedFile(
                name="small.gif", content=small_gif, content_type="image/gif"
            ),
            # See: https://django-dynamic-fixture.readthedocs.io/en/latest/data.html#fill-nullable-fields
            creator=self.study_admin,
            shared_preview=True,
            public=True,
            name="Test Study",
            lab=self.lab,
            short_description="original short_description",
            structure={
                "frames": {"frame-a": {}, "frame-b": {}},
                "sequence": ["frame-a", "frame-b"],
                "exact_text": "some exact text",
            },
            use_generator=False,
            generator="",
            criteria_expression="",
            metadata={
                "player_repo_url": "https://github.com/lookit/ember-lookit-frameplayer",
                "last_known_player_sha": "fakecommitsha",
            },
            built=True,
            study_type=StudyType.get_ember_frame_player(),
        )
        self.study.admin_group.user_set.add(self.study_admin)
        self.study.design_group.user_set.add(self.study_designer)
        self.lab.researchers.add(self.study_designer)
        self.lab.researchers.add(self.study_admin)

        self.nonparticipant = G(
            User, is_active=True, is_researcher=False, nickname="Mommy"
        )
        self.nonparticipant_child = G(
            Child,
            user=self.nonparticipant,
            given_name="Newborn",
            birthday=datetime.date.today() - datetime.timedelta(14),
        )

        self.participant = G(User, is_active=True, is_researcher=False, nickname="Dada")
        self.participant_child = G(
            Child,
            user=self.participant,
            given_name="Actual participant",
            birthday=datetime.date.today() - datetime.timedelta(14),
        )
        self.participant_other_child = G(
            Child,
            user=self.participant,
            given_name="Child who has not participated",
            birthday=datetime.date.today() - datetime.timedelta(14),
        )

        self.demo_snapshot = G(DemographicData, user=self.participant, density="urban")
        self.unconsented_response_from_participant = G(
            Response,
            child=self.participant_child,
            study=self.study,
            completed=False,
            completed_consent_frame=True,
            sequence=["0-video-config", "1-video-setup", "2-my-consent-frame"],
            exp_data={
                "0-video-config": {"frameType": "DEFAULT"},
                "1-video-setup": {"frameType": "DEFAULT"},
                "2-my-consent-frame": {"frameType": "CONSENT"},
            },
            demographic_snapshot=self.demo_snapshot,
        )
        self.consented_response = G(
            Response,
            child=self.participant_child,
            study=self.study,
            completed=False,
            completed_consent_frame=True,
            sequence=["0-video-config", "1-video-setup", "2-my-consent-frame"],
            exp_data={
                "0-video-config": {"frameType": "DEFAULT"},
                "1-video-setup": {"frameType": "DEFAULT"},
                "2-my-consent-frame": {"frameType": "CONSENT"},
            },
            demographic_snapshot=self.demo_snapshot,
        )
        self.consent_ruling = G(
            ConsentRuling,
            response=self.consented_response,
            action="accepted",
            arbiter=self.study_admin,
        )

    def test_cannot_see_participant_detail_unauthenticated(self):
        url = reverse("exp:participant-detail", kwargs={"pk": self.participant.pk})
        page = self.client.get(url)
        self.assertNotEqual(
            page.status_code,
            200,
            "Unauthenticated user can see participant detail view: " + url,
        )

    def test_cannot_see_participant_detail_as_participant(self):
        url = reverse("exp:participant-detail", kwargs={"pk": self.participant.pk})
        self.client.force_login(self.participant)
        page = self.client.get(url)
        self.assertNotEqual(
            page.status_code,
            200,
            "Participant can see participant detail view: " + url,
        )

    def test_cannot_see_participant_detail_unless_participated(self):
        url = reverse("exp:participant-detail", kwargs={"pk": self.nonparticipant.pk})
        self.client.force_login(self.study_admin)
        page = self.client.get(url)
        self.assertNotEqual(
            page.status_code,
            200,
            "Study admin can see participant detail view for someone who did not participate in their study: "
            + url,
        )

    def test_cannot_see_participant_detail_as_study_designer(self):
        url = reverse("exp:participant-detail", kwargs={"pk": self.participant.pk})
        self.client.force_login(self.study_designer)
        page = self.client.get(url)
        self.assertNotEqual(
            page.status_code,
            200,
            "Study designer can see participant detail view: " + url,
        )

    def test_can_see_participant_detail_as_study_admin(self):
        url = reverse("exp:participant-detail", kwargs={"pk": self.participant.pk})
        self.client.force_login(self.study_admin)
        page = self.client.get(url)
        self.assertEqual(
            page.status_code,
            200,
            "Study admin cannot see participant detail view: " + url,
        )

        content = page.content.decode("utf-8")
        self.assertIn(
            "Actual participant",
            content,
            "Participant child not on participant detail page",
        )
        self.assertIn(
            "urban", content, "Demographic info not on participant detail page"
        )
        self.assertNotIn(
            "Child who has not participated",
            content,
            "Participant child's sibling on participant detail page but has not participated",
        )

    def test_cannot_see_participant_list_unauthenticated(self):
        url = reverse("exp:participant-list")
        page = self.client.get(url)
        self.assertNotEqual(
            page.status_code,
            200,
            "Unauthenticated user can see participant list view: " + url,
        )

    def test_cannot_see_participant_list_as_participant(self):
        url = reverse("exp:participant-list")
        self.client.force_login(self.participant)
        page = self.client.get(url)
        self.assertNotEqual(
            page.status_code, 200, "Participant can see participant list view: " + url
        )

    def test_can_see_participant_list_as_researcher(self):
        url = reverse("exp:participant-list")
        self.client.force_login(self.study_designer)
        page = self.client.get(url)
        self.assertEqual(
            page.status_code,
            200,
            "Researcher cannot see participant list view: " + url,
        )
        content = page.content.decode("utf-8")
        self.assertNotIn(
            "Mommy", content, "Study designer sees non-participant in participant list"
        )
        self.assertNotIn(
            "Dada", content, "Study designer sees participant in participant list"
        )

    def test_only_see_participants_in_participant_list(self):
        url = reverse("exp:participant-list")
        self.client.force_login(self.study_admin)
        page = self.client.get(url)
        self.assertEqual(
            page.status_code,
            200,
            "Researcher cannot see participant list view: " + url,
        )
        content = page.content.decode("utf-8")
        self.assertNotIn(
            "Mommy", content, "Study admin sees non-participant in participant list"
        )
        self.assertIn(
            "Dada",
            content,
            "Study designer does not see participant in participant list",
        )
