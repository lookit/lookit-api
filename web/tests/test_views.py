import datetime
import uuid
from unittest import skip
from unittest.mock import MagicMock, PropertyMock, patch, sentinel

from django.contrib.sites.models import Site
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.views.generic.list import MultipleObjectMixin
from django_dynamic_fixture import G
from parameterized import parameterized

from accounts.models import Child, DemographicData, User
from studies.models import Lab, Response, Study, StudyType
from web.views import (
    ChildrenListView,
    DemographicDataUpdateView,
    LabStudiesListView,
    StudiesListView,
    StudyDetailView,
)


class ParticipantAccountViewsTestCase(TestCase):
    def setUp(self):
        self.participant_email = "participant@mit.edu"

        self.valid_password = "testpassword20chars"
        self.too_short_password = "testpas9c"  # NOSONAR

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
            additional_comments="Original comments",
            previous=None,
            number_of_children="",
            number_of_guardians="2",
            former_lookit_annual_income="",
            lookit_referrer="Google",
        )

        self.demographic_current = G(
            DemographicData,
            user=self.participant,
            previous=self.demographic_orig,
            number_of_children="",
            number_of_guardians="2",
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
            response = self.client.get(reverse(url_name), follow=True)
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

        self.assertEqual(data["country"], "US")
        self.assertNotEqual(data["additional_comments"], "Original comments")

        # Update data and save
        data["country"] = "BR"
        cleaned_data = {key: val for (key, val) in data.items() if val is not None}
        response = self.client.post(
            reverse("web:demographic-data-update"), cleaned_data, follow=True
        )
        self.assertEqual(
            response.redirect_chain, [(reverse("web:demographic-data-update"), 302)]
        )
        self.assertEqual(response.status_code, 200)

        # Make sure we can retrieve updated data
        response = self.client.get(reverse("web:demographic-data-update"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].initial["country"], "BR")

        # Check we've created an additional demographicdata object for this
        self.assertEqual(self.participant.demographics.count(), 3)


class ChildrenListViewTestCase(TestCase):
    @patch.object(ChildrenListView, "request", create=True)
    @patch("accounts.models.Child.objects", name="child_objects")
    def test_get_context_data_not_deleted_children(
        self, mock_child_objects, mock_request
    ):
        with patch.object(ChildrenListView, "object", create=True):
            children_list_view = ChildrenListView()
            children_list_view.get_context_data()
            mock_child_objects.filter.assert_called_once_with(
                deleted=False, user=mock_request.user
            )


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
            additional_comments="Original comments",
            previous=None,
            number_of_children="",
            number_of_guardians="2",
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
        small_gif = (
            b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x00\x00\x00\x21\xf9\x04"
            b"\x01\x0a\x00\x01\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02"
            b"\x02\x4c\x01\x00\x3b"
        )
        self.thumbnail = SimpleUploadedFile(
            name="small.gif", content=small_gif, content_type="image/gif"
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

        studies = response.context["object_list"]
        self.assertTrue(any(s.uuid == self.public_active_study_1.uuid for s in studies))
        self.assertTrue(any(s.uuid == self.public_active_study_2.uuid for s in studies))
        self.assertFalse(any(s.uuid == self.private_active_study.uuid for s in studies))
        self.assertFalse(
            any(s.uuid == self.public_inactive_study.uuid for s in studies)
        )


class StudyDetailViewTestCase(TestCase):
    @patch.object(StudyDetailView, "request", create=True)
    def test_get_context_not_deleted_children(self, mock_request):
        with patch.object(StudyDetailView, "object", create=True):
            study_detail_view = StudyDetailView()
            study_detail_view.get_context_data()
            mock_request.user.children.filter.assert_called_once_with(deleted=False)


class DemographicDataUpdateViewTestCase(TestCase):
    @patch.object(DemographicDataUpdateView, "request", create=True)
    def test_get_success_url_not_deleted_children(self, mock_request):
        demographic_data_update_view = DemographicDataUpdateView()
        demographic_data_update_view.get_success_url()
        mock_request.user.children.filter.assert_called_once_with(deleted=False)
        mock_request.user.children.filter().exists.assert_called_once_with()


class StudiesListViewTestCase(TestCase):
    @parameterized.expand([(True, 302), (False, 200)])
    @patch("web.views.StudiesListView.get_form")
    @patch.object(StudiesListView, "request", create=True)
    def test_post(self, is_valid, status_code, mock_request, mock_get_form):
        with patch.object(StudiesListView, "object_list", create=True):
            mock_get_form().is_valid.return_value = is_valid
            view = StudiesListView()
            response = view.post(mock_request)
            self.assertEqual(response.status_code, status_code)

    def test_search_options_auth_user(self):
        mock_request = MagicMock(method="GET")
        type(mock_request.user).is_authenticated = PropertyMock(return_value=True)
        type(mock_request).session = {}

        response = StudiesListView.as_view()(mock_request).render()

        self.assertIn(b'for="id_hide_studies_we_have_done"', response.content)
        self.assertIn(b'for="id_child"', response.content)
        self.assertIn(b'for="id_search"', response.content)

    def test_search_options_anon_user(self):
        mock_request = MagicMock(method="GET")
        type(mock_request.user).is_authenticated = PropertyMock(return_value=False)

        response = StudiesListView.as_view()(mock_request).render()

        self.assertNotIn(b'for="id_show_experiments_already_done"', response.content)
        self.assertIn(b'for="id_child"', response.content)
        self.assertIn(b'for="id_search"', response.content)

    @patch.object(StudiesListView, "sort_fn")
    @patch.object(MultipleObjectMixin, "get_queryset")
    @patch("web.views.get_child_eligibility_for_study")
    @patch.object(StudiesListView, "studies_without_completed_consent_frame")
    @patch("accounts.models.Child.objects")
    @patch.object(StudiesListView, "request", create=True)
    def test_get_queryset_auth_user(
        self,
        mock_request,
        mock_child_objects,
        mock_studies_without_completed_consent_frame,
        mock_get_child_eligibility_for_study,
        mock_super_get_queryset,
        mock_sort_fn,
    ):
        mock_study = MagicMock(name="study")
        mock_studies = [mock_study]

        type(mock_request).session = PropertyMock(
            return_value={
                "search": sentinel.search_value,
                "child": "1",
                "hide_studies_we_have_done": True,
            },
        )
        type(mock_request.user).is_authenticated = PropertyMock(return_value=True)
        mock_super_get_queryset().filter().filter.return_value = mock_studies
        mock_studies_without_completed_consent_frame.return_value = mock_studies

        view = StudiesListView()
        studies = view.get_queryset()

        mock_super_get_queryset().filter.assert_called_with(state="active", public=True)
        mock_super_get_queryset().filter().filter.assert_called_once_with(
            name__icontains=sentinel.search_value
        )

        mock_child_objects.get.assert_called_once_with(pk="1", user=mock_request.user)

        mock_studies_without_completed_consent_frame.assert_called_once_with(
            mock_studies, mock_child_objects.get()
        )
        mock_get_child_eligibility_for_study.assert_called_once_with(
            mock_child_objects.get(), mock_study
        )
        mock_sort_fn.assert_called_once_with()

        self.assertListEqual(studies, mock_studies)

    @patch("web.views.age_range_eligibility_for_study", return_value=True)
    @patch.object(StudiesListView, "sort_fn")
    @patch.object(MultipleObjectMixin, "get_queryset")
    @patch.object(StudiesListView, "studies_without_completed_consent_frame")
    @patch.object(StudiesListView, "request", create=True)
    def test_get_queryset_anon_user(
        self,
        mock_request,
        mock_studies_without_completed_consent_frame,
        mock_super_get_queryset,
        mock_sort_fn,
        mock_age_range_eligibility_for_study,
    ):
        mock_study = MagicMock(name="study")
        mock_studies = [mock_study]

        type(mock_request).session = PropertyMock(
            return_value={"child": "1,2", "search": sentinel.search_value}
        )

        type(mock_request.user).is_authenticated = PropertyMock(return_value=False)
        mock_super_get_queryset().filter().filter.return_value = mock_studies
        mock_studies_without_completed_consent_frame.return_value = mock_studies

        view = StudiesListView()
        studies = view.get_queryset()

        mock_super_get_queryset().filter.assert_called_with(state="active", public=True)
        mock_super_get_queryset().filter().filter.assert_called_once_with(
            name__icontains=sentinel.search_value
        )
        mock_age_range_eligibility_for_study.assert_called_once_with([1, 2], mock_study)
        mock_sort_fn.assert_called_once_with()

        self.assertListEqual(studies, mock_studies)

    @patch.object(StudiesListView, "request", create=True)
    def test_get_form_kwargs(self, mock_request):
        view = StudiesListView()
        kwargs = view.get_form_kwargs()

        self.assertIn("user", kwargs)
        self.assertEqual(kwargs["user"], mock_request.user)

    @patch.object(StudiesListView, "request", create=True)
    @patch.object(StudiesListView, "form_class")
    def test_get_initial(self, mock_form_class, mock_request):
        mock_form_class().fields.__iter__.return_value = [sentinel.field]
        type(mock_request).session = PropertyMock(
            return_value={sentinel.field: sentinel.field}
        )

        view = StudiesListView()
        kwargs = view.get_initial()

        mock_form_class().fields.__iter__.assert_called_once_with()

        self.assertIn(sentinel.field, kwargs)
        self.assertIn(sentinel.field, mock_request.session)

    def test_get_success_url(self):
        view = StudiesListView()
        url = view.get_success_url()
        self.assertEqual(url, "/studies/")

    @patch("studies.models.Response.objects", name="response_objects")
    def test_studies_without_completed_consent_frame(self, response_objects):
        mock_studies = MagicMock(name="studies")
        mock_child = MagicMock(name="child")

        mock_studies.exclude.return_value = sentinel.studies

        view = StudiesListView()
        studies = view.studies_without_completed_consent_frame(mock_studies, mock_child)

        self.assertEqual(studies, sentinel.studies)

        mock_studies.exclude.assert_called_once_with(
            responses__in=response_objects.filter()
        )

    def test_studies_without_completed_consent_frame_functional(self):
        number_of_studies = 3

        # Create user
        user = User.objects.create()

        # Create child
        child = Child.objects.create(
            user=user, birthday=datetime.date.today() - datetime.timedelta(days=365)
        )

        study_type = StudyType.get_ember_frame_player()

        # Create studies
        for name in range(number_of_studies):
            Study.objects.create(study_type=study_type, name=str(name))

        view = StudiesListView()

        # Check that all studies return with no responses
        self.assertEqual(Response.objects.count(), 0)
        studies_no_ccf = view.studies_without_completed_consent_frame(
            Study.objects.all(), child
        )
        self.assertEqual(studies_no_ccf.count(), number_of_studies)

        study1 = Study.objects.get(name="1", study_type=study_type)
        Response.objects.create(study=study1, child=child)

        # Check that all studies return even with one response for study "1"
        self.assertEqual(Response.objects.count(), 1)
        studies_no_ccf = view.studies_without_completed_consent_frame(
            Study.objects.all(), child
        )
        self.assertEqual(studies_no_ccf.count(), number_of_studies)

        # Set completed consent frame in response.
        response = Response.objects.first()
        response.completed_consent_frame = True
        response.save()

        # Check that study "1" is not returned
        studies_no_ccf = view.studies_without_completed_consent_frame(
            Study.objects.all(), child
        )
        self.assertEqual(studies_no_ccf.count(), number_of_studies - 1)
        self.assertEqual(studies_no_ccf.filter(name="1").count(), 0)

        # Create second response without completed consent frame
        Response.objects.create(study=study1, child=child)
        self.assertEqual(Response.objects.count(), 2)

        # Check that the same experiments return
        studies_no_ccf = view.studies_without_completed_consent_frame(
            Study.objects.all(), child
        )
        self.assertEqual(studies_no_ccf.count(), number_of_studies - 1)
        self.assertEqual(studies_no_ccf.filter(name="1").count(), 0)

        # Finally, check the name of the two studies that return
        self.assertEqual(studies_no_ccf.filter(name="0").count(), 1)
        self.assertEqual(studies_no_ccf.filter(name="2").count(), 1)

    @patch.object(StudiesListView, "request", create=True)
    def test_sort_fn_anon_user(self, mock_request):
        """Ordering of the studies needs to be seemingly random, but constant. To ensure a "random"
        ordering, the method will sort by a study's UUID.  This will verify that the ordering is
        constant.

        Args:
            mock_request (mock.Mock): mocked out request object
        """
        type(mock_request.user).is_anonymous = PropertyMock(return_value=True)

        mock_study_a = MagicMock(name="a")
        type(mock_study_a).uuid = PropertyMock(
            return_value=uuid.UUID("{11111111-1234-5678-1234-567812345678}")
        )

        mock_study_b = MagicMock(name="b")
        type(mock_study_b).uuid = PropertyMock(
            return_value=uuid.UUID("{33333333-1234-5678-1234-567812345678}")
        )

        mock_study_c = MagicMock(name="c")
        type(mock_study_c).uuid = PropertyMock(
            return_value=uuid.UUID("{22222222-1234-5678-1234-567812345678}")
        )

        mock_studies = [mock_study_a, mock_study_b, mock_study_c]

        view = StudiesListView()
        mock_studies.sort(key=view.sort_fn())

        self.assertListEqual(mock_studies, [mock_study_a, mock_study_c, mock_study_b])

    @patch.object(StudiesListView, "request", create=True)
    def test_sort_fn_auth_user(self, mock_request):
        """Ordering of the studies needs to be seemingly random, but constant.  Additionally, the
        "random" order needs to be different for each authenticated user.  To ensure a "random"
        ordering, the method will hash a study's UUID and seed it with the user's UUID.  This test
        will verify that the ordering is constant.

        Args:
            mock_request (mock.Mock): mocked out request object
        """

        type(mock_request.user).is_anonymous = PropertyMock(return_value=False)
        type(mock_request.user).uuid = PropertyMock(
            return_value=uuid.UUID("{12345678-1234-5678-1234-567812345678}")
        )

        mock_study_a = MagicMock(name="a")
        type(mock_study_a).uuid = PropertyMock(
            return_value=uuid.UUID("{11111111-1234-5678-1234-567812345678}")
        )

        mock_study_b = MagicMock(name="b")
        type(mock_study_b).uuid = PropertyMock(
            return_value=uuid.UUID("{33333333-1234-5678-1234-567812345678}")
        )

        mock_study_c = MagicMock(name="c")
        type(mock_study_c).uuid = PropertyMock(
            return_value=uuid.UUID("{22222222-1234-5678-1234-567812345678}")
        )

        mock_studies = [mock_study_a, mock_study_b, mock_study_c]

        view = StudiesListView()
        mock_studies.sort(key=view.sort_fn())

        self.assertListEqual(mock_studies, [mock_study_b, mock_study_a, mock_study_c])


class LabStudiesListViewTestCase(TestCase):
    @patch.object(StudiesListView, "filter_studies")
    @patch.object(LabStudiesListView, "request", create=True)
    def test_filter_studies(self, mock_request, mock_super_filter_studies):
        mock_studies = MagicMock(name="studies")
        view = LabStudiesListView()
        type(view).kwargs = PropertyMock(return_value={"lab_slug": sentinel.lab_slug})
        view.filter_studies(mock_studies)

        # confirm studies were filted by lab slug
        mock_studies.filter.assert_called_once_with(lab__slug=sentinel.lab_slug)
        mock_super_filter_studies.assert_called_once_with(mock_studies.filter())

    @patch("web.views.reverse")
    def test_get_success_url(self, mock_reverse):
        view = LabStudiesListView()
        # attach lab_slug to view kwargs
        type(view).kwargs = PropertyMock(return_value={"lab_slug": sentinel.lab_slug})

        url = view.get_success_url()
        # confirm correct success url is created
        mock_reverse.assert_called_once_with(
            "web:lab-studies-list", args=[sentinel.lab_slug]
        )
        # verify that url is returned
        self.assertEqual(url, mock_reverse())


class ExperimentProxyViewTestCase(TestCase):
    def setUp(self):
        # Create user
        self.user: User = G(User, is_active=True)

        # Create user's child
        self.child = G(Child, user=self.user)

        # Create child that's not user's
        self.other_child = G(Child)

        # Some study
        self.study = G(Study, study_type=StudyType.get_ember_frame_player())
        self.study_url = reverse(
            "web:experiment-proxy",
            kwargs={"uuid": self.study.uuid, "child_id": self.child.uuid},
        )
        self.other_child_study_url = reverse(
            "web:experiment-proxy",
            kwargs={"uuid": self.study.uuid, "child_id": self.other_child.uuid},
        )

    @skip("Issue with CI #1055")
    def test_proxy_auth_success(self):
        "Authenticated user can access experiment with their child."
        self.client.force_login(self.user)
        response = self.client.get(self.study_url)
        self.assertNotEqual(self.user, self.other_child.user)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(self.study_url))

    def test_proxy_auth_fail_no_logged_in(self):
        "Unauthenticated user is redirected to login when not logged in."
        response = self.client.get(self.study_url)
        self.assertEqual(self.user, self.child.user)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    @skip("Issue with CI #1055")
    def test_proxy_auth_fail_not_their_child(self):
        "Unauthenticated user get redirecte to login when not their child."
        self.client.force_login(self.user)
        response = self.client.get(self.other_child_study_url)
        self.assertNotEqual(self.user, self.other_child.user)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))


# TODO: StudyDetailView
# - check can see for public or private active study, unauthenticated or authenticated
# - check context[children] has own children
# TODO: StudiesHistoryView
# - check can see several sessions where consent frame was completed (but consent not marked), not for someone else's
# child, not for consent frame incomplete.
# TODO: ExperimentAssetsProxyView
# - check have to be authenticated, maybe that's it for now?
