import datetime

from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django_dynamic_fixture import G

from accounts.models import Child, DemographicData, User
from project import settings
from studies.models import Lab, Study, StudyType


class ParticipantAccountViewsTestCase(TestCase):
    def setUp(self):
        self.participant_email = "participant@mit.edu"

        self.valid_password = "testpassword20chars"
        self.too_short_password = "testpassword15c"

        # Participant Setup
        self.participant = G(
            User,
            username=self.participant_email,
            is_active=True,
            is_researcher=False,
            nickname="Participant family",
        )
        self.participant.set_password(self.valid_password)
        self.participant.save()

        self.demographic_orig = G(
            DemographicData,
            user=self.participant,
            languages_spoken_at_home="French",
            additional_comments="Original comments",
            previous=None,
            number_of_children="",
            number_of_guardians_explanation="",
            number_of_guardians="2",
            number_of_books=75,
            former_lookit_annual_income="",
            lookit_referrer="Google",
        )

        self.demographic_current = G(
            DemographicData,
            user=self.participant,
            languages_spoken_at_home="Spanish",
            previous=self.demographic_orig,
            number_of_children="",
            number_of_guardians_explanation="",
            number_of_guardians="2",
            number_of_books=75,
            former_lookit_annual_income="",
            lookit_referrer="Google",
        )

        self.child = G(
            Child,
            user=self.participant,
            existing_conditions=Child.existing_conditions.dyslexia,
            languages_spoken=Child.languages_spoken.en,
            birthday=datetime.date.today() - datetime.timedelta(days=10 * 365),
        )

        # Site fixture enabling login
        self.fake_site = G(Site, id=1)

        # FlatPage fixture enabling login redirect to work.
        self.home_page = G(FlatPage, url="/")
        self.home_page.sites.add(self.fake_site)
        self.home_page.save()

    def test_participant_signup_flow(self):
        response = self.client.post(
            reverse("web:participant-signup"),
            {
                "username": "new-participant@mit.edu",
                "password1": self.valid_password,
                "password2": self.valid_password,
                "nickname": "Testfamily",
            },
            follow=True,
        )
        # We're redirected successfully to demographic data update
        self.assertEqual(
            response.redirect_chain, [(reverse("web:demographic-data-update"), 302)]
        )
        self.assertEqual(response.status_code, 200)
        # And are a logged-in user with the expected attributes for new participant
        user = response.wsgi_request.user
        self.assertFalse(user.is_anonymous)
        self.assertTrue(user.is_authenticated)
        self.assertFalse(user.is_researcher)
        self.assertTrue(user.is_active)
        self.assertEqual(user.nickname, "Testfamily")
        self.assertEqual(user.username, "new-participant@mit.edu")
        self.assertFalse(user.labs.exists())
        self.assertFalse(user.user_permissions.exists())
        self.assertFalse(user.groups.exists())
        self.assertFalse(user.children.exists())
        self.assertFalse(user.demographics.exists())

    def test_participant_password_requirements(self):
        response = self.client.post(
            reverse("web:participant-signup"),
            {
                "username": "new-participant@mit.edu",
                "password1": self.too_short_password,
                "password2": self.too_short_password,
                "nickname": "Testfamily",
            },
            follow=True,
        )
        # There are form errors...
        self.assertNotEqual(len(response.context["form"].errors), 0)
        self.assertIn("This password is too short.", response.content.decode("utf-8"))
        # We stayed on the same page...
        self.assertEqual(response.redirect_chain, [])
        self.assertEqual(response.status_code, 200)
        # And user isn't logged in
        self.assertTrue(response.wsgi_request.user.is_anonymous)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_participant_signup_mismatched_passwords(self):
        response = self.client.post(
            reverse("web:participant-signup"),
            {
                "username": "new-participant@mit.edu",
                "password1": self.valid_password,
                "password2": self.valid_password + "q",
                "nickname": "Testfamily",
            },
            follow=True,
        )
        # There are form errors...
        self.assertIn("password2", response.context["form"].errors)
        self.assertIn(
            "The two password fields didn’t match.",
            response.context["form"].errors["password2"],
        )
        # We stayed on the same page
        self.assertEqual(response.redirect_chain, [])
        self.assertEqual(response.status_code, 200)
        # And user isn't logged in
        self.assertTrue(response.wsgi_request.user.is_anonymous)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_participant_signup_existing_user(self):
        response = self.client.post(
            reverse("web:participant-signup"),
            {
                "username": "participant@mit.edu",
                "password1": self.valid_password,
                "password2": self.valid_password,
                "nickname": "Testfamily",
            },
            follow=True,
        )
        # There are form errors...
        self.assertIn("username", response.context["form"].errors)
        self.assertIn(
            "User with this Email address already exists.",
            response.context["form"].errors["username"],
        )
        # We stayed on the same page
        self.assertEqual(response.redirect_chain, [])
        self.assertEqual(response.status_code, 200)
        # And user isn't logged in
        self.assertTrue(response.wsgi_request.user.is_anonymous)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_participant_signup_invalid_email(self):
        response = self.client.post(
            reverse("web:participant-signup"),
            {
                "username": "participantmit.edu",
                "password1": self.valid_password,
                "password2": self.valid_password,
                "nickname": "Testfamily",
            },
            follow=True,
        )
        # There are form errors...
        self.assertIn("username", response.context["form"].errors)
        self.assertIn(
            "Enter a valid email address.", response.context["form"].errors["username"]
        )
        # We stayed on the same page
        self.assertEqual(response.redirect_chain, [])
        self.assertEqual(response.status_code, 200)
        # And user isn't logged in
        self.assertTrue(response.wsgi_request.user.is_anonymous)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_participant_login_required_views_unauthenticated(self):
        login_required_views = [
            "web:demographic-data-update",
            "web:children-list",
            "web:email-preferences",
            "web:studies-history",
            "accounts:manage-account",  # TODO: move to accounts tests
        ]

        for url_name in login_required_views:
            response = self.client.get(reverse(url_name), follow=True,)
            # Redirected to login view with next set if unauthenticated
            self.assertEqual(
                response.redirect_chain,
                [(f"{reverse('login')}?next={reverse(url_name)}", 302)],
                f"Unauthenticated user not redirected to login from {url_name}",
            )
            self.assertEqual(response.status_code, 200)

    def test_demographic_data_update_authenticated(self):
        self.client.force_login(self.participant)

        # Get the form to fill out; check that initial data includes values only
        # from more recent demographic data
        response = self.client.get(reverse("web:demographic-data-update"))
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        data = form.initial
        self.assertEqual(data["languages_spoken_at_home"], "Spanish")
        self.assertNotEqual(data["additional_comments"], "Original comments")

        # Update data and save
        data["languages_spoken_at_home"] = "Swahili"
        cleaned_data = {key: val for (key, val) in data.items() if val is not None}
        response = self.client.post(
            reverse("web:demographic-data-update"), cleaned_data, follow=True
        )
        self.assertEqual(
            response.redirect_chain, [(reverse("web:studies-list"), 302)],
        )
        self.assertEqual(response.status_code, 200)

        # Make sure we can retrieve updated data
        response = self.client.get(reverse("web:demographic-data-update"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Swahili", response.content.decode("utf-8"))  # or
        self.assertEqual(
            response.context["form"].initial["languages_spoken_at_home"], "Swahili"
        )

        # Check we've created an additional demographicdata object for this
        self.assertEqual(self.participant.demographics.count(), 3)


# TODO: ParticipantUpdateView
# - check can update password (participant, researcher)
# - check can update email but only to unused (otherwise reloads, no update), can update nickname
# - check can only get own data
# - check can disable/enable 2fa
# TODO: ChildrenListView
# - check all own children are there, can only see own children
# - check can add child
# - check if invalid data sent, reloads page & does not create child
# TODO: ChildUpdateView
# - check can get but only for own child, check can change name, check cannot change DOB
# TODO: ParticipantEmailPreferencesView
# - check can get but only for own, check can un-check one preference & save


class ParticipantStudyViewsTestCase(TestCase):
    def setUp(self):
        self.participant_email = "participant@mit.edu"

        self.valid_password = "testpassword20chars"
        self.too_short_password = "testpassword15c"

        # Participant Setup
        self.participant = G(
            User,
            username=self.participant_email,
            is_active=True,
            is_researcher=False,
            nickname="Participant family",
        )
        self.participant.set_password(self.valid_password)
        self.participant.save()

        self.demographic_orig = G(
            DemographicData,
            user=self.participant,
            languages_spoken_at_home="French",
            additional_comments="Original comments",
            previous=None,
            number_of_children="",
            number_of_guardians_explanation="",
            number_of_guardians="2",
            number_of_books=75,
            former_lookit_annual_income="",
            lookit_referrer="Google",
        )

        self.child = G(
            Child,
            user=self.participant,
            existing_conditions=Child.existing_conditions.dyslexia,
            languages_spoken=Child.languages_spoken.en,
            birthday=datetime.date.today() - datetime.timedelta(days=10 * 365),
        )

        self.researcher = G(
            User, is_active=True, is_researcher=True, given_name="Researcher"
        )
        self.lab = G(Lab, name="MIT")
        self.study_type = G(StudyType, name="default", id=1)

        self.thumbnail = SimpleUploadedFile(
            name="fake_image.png",
            content=open(
                f"{settings.BASE_DIR}{settings.STATIC_URL}images/pacifier.png", "rb"
            ).read(),
            content_type="image/png",
        )
        self.public_active_study_1 = G(
            Study,
            creator=self.researcher,
            shared_preview=False,
            study_type=self.study_type,
            name="PublicActiveStudy1",
            lab=self.lab,
            public=True,
            image=self.thumbnail,
        )
        # Separately set state because it's set to "created" initially
        self.public_active_study_1.save()
        self.public_active_study_1.state = "active"
        self.public_active_study_1.save()

        self.public_active_study_2 = G(
            Study,
            creator=self.researcher,
            shared_preview=False,
            study_type=self.study_type,
            name="PublicActiveStudy2",
            lab=self.lab,
            public=True,
            image=self.thumbnail,
        )
        # Separately set state because it's set to "created" initially
        self.public_active_study_2.save()
        self.public_active_study_2.state = "active"
        self.public_active_study_2.save()

        self.private_active_study = G(
            Study,
            creator=self.researcher,
            shared_preview=False,
            study_type=self.study_type,
            name="PrivateActiveStudy",
            lab=self.lab,
            public=False,
            image=self.thumbnail,
        )
        # Separately set state because it's set to "created" initially
        self.private_active_study.save()
        self.private_active_study.state = "active"
        self.private_active_study.save()

        self.public_inactive_study = G(
            Study,
            creator=self.researcher,
            shared_preview=False,
            study_type=self.study_type,
            name="PublicInactiveStudy",
            lab=self.lab,
            public=True,
            image=self.thumbnail,
        )
        # Separately set state because it's set to "created" initially
        self.public_inactive_study.save()
        self.public_inactive_study.state = "submitted"
        self.public_inactive_study.save()

    def test_study_list_view(self):
        response = self.client.get(reverse("web:studies-list"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        # Make sure we see the two public, active studies, but not an inactive or private study
        self.assertIn("PublicActiveStudy1", content)
        self.assertIn("PublicActiveStudy2", content)
        self.assertNotIn("PrivateActiveStudy", content)
        self.assertNotIn("PublicInactiveStudy", content)
        self.assertTrue(
            response.context["study_list"]
            .filter(uuid=self.public_active_study_1.uuid)
            .exists()
        )
        self.assertTrue(
            response.context["study_list"]
            .filter(uuid=self.public_active_study_2.uuid)
            .exists()
        )
        self.assertFalse(
            response.context["study_list"]
            .filter(uuid=self.private_active_study.uuid)
            .exists()
        )
        self.assertFalse(
            response.context["study_list"]
            .filter(uuid=self.public_inactive_study.uuid)
            .exists()
        )


# TODO: StudyDetailView
# - check can see for public or private active study, unauthenticated or authenticated
# - check context[children] has own children
# TODO: StudiesHistoryView
# - check can see several sessions where consent frame was completed (but consent not marked), not for someone else's
# child, not for consent frame incomplete.
# TODO: ExperimentAssetsProxyView
# - check have to be authenticated, maybe that's it for now?
# TODO: ExperimentProxyView
# - check have to be authenticated, has to be own child
