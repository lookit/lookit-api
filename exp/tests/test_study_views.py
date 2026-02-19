import datetime
import json
from http import HTTPStatus
from unittest import skip
from unittest.mock import (
    MagicMock,
    Mock,
    PropertyMock,
    create_autospec,
    patch,
    sentinel,
)

from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms.models import model_to_dict
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.views.generic.detail import SingleObjectMixin
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm, get_objects_for_user
from parameterized import parameterized

from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from accounts.models import Child, User
from exp.views.mixins import ResearcherLoginRequiredMixin
from exp.views.study import (
    ChangeStudyStatusView,
    CloneStudyView,
    ManageResearcherPermissionsView,
    StudyDetailView,
    StudyPreviewDetailView,
)
from studies.helpers import ResponseEligibility
from studies.models import Lab, Response, Study, StudyType
from studies.permissions import LabPermission, StudyPermission


class Force2FAClient(Client):
    """For convenience, let's just pretend everyone is two-factor auth'd."""

    @property
    def session(self):
        _session = super().session
        _session[TWO_FACTOR_AUTH_SESSION_KEY] = True
        return _session


# Run celery tasks right away, but don't catch errors from them. The relevant tasks for
# this case involve S3/GCP access which we're not testing.
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
@override_settings(CELERY_TASK_EAGER_PROPAGATES=True)
class StudyViewsTestCase(TestCase):
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
        self.lab_researcher = G(
            User,
            is_active=True,
            is_researcher=True,
            given_name="Researcher 4",
            time_zone="America/New_York",
        )
        self.participant = G(User, is_active=True, is_researcher=False, nickname="Dada")
        self.approved_lab = G(Lab, name="MIT", approved_to_test=True)

        self.generator_function_string = (
            "function(child, pastSessions) {return {frames: {}, sequence: []};}"
        )
        self.structure_string = (
            "some exact text that should be displayed in place of the loaded structure"
        )
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
            study_type=StudyType.get_ember_frame_player(),
            preview_summary="preview summary",
            creator=self.study_admin,
            shared_preview=False,
            public=True,
            name="Test Study",
            lab=self.approved_lab,
            short_description="original short_description",
            structure={
                "frames": {"frame-a": {}, "frame-b": {}},
                "sequence": ["frame-a", "frame-b"],
                "exact_text": self.structure_string,
            },
            use_generator=False,
            generator=self.generator_function_string,
            criteria_expression="",
            metadata={
                "player_repo_url": "https://github.com/lookit/ember-lookit-frameplayer",
                "last_known_player_sha": "fakecommitsha",
            },
            built=True,
        )

        self.study_shared_preview = G(
            Study,
            creator=self.study_admin,
            shared_preview=True,
            name="Test Study",
            lab=self.approved_lab,
            built=True,
            image=SimpleUploadedFile(
                name="small.gif", content=small_gif, content_type="image/gif"
            ),
            study_type=StudyType.get_ember_frame_player(),
        )

        self.study.admin_group.user_set.add(self.study_admin)
        self.study.design_group.user_set.add(self.study_designer)
        self.approved_lab.researchers.add(self.study_designer)
        self.approved_lab.researchers.add(self.study_admin)
        self.approved_lab.researchers.add(self.lab_researcher)

        self.study_designer_child = G(
            Child,
            user=self.study_designer,
            given_name="Study reader child",
            birthday=datetime.date.today() - datetime.timedelta(30),
        )
        self.other_researcher_child = G(
            Child,
            user=self.other_researcher,
            given_name="Other researcher child",
            birthday=datetime.date.today() - datetime.timedelta(60),
        )

        self.study_build_url = reverse(
            "exp:study-build", kwargs={"uuid": self.study.uuid}
        )

        self.all_study_views_urls = [
            reverse("exp:study-list"),
            reverse("exp:study-create"),
            reverse("exp:study", kwargs={"pk": self.study.pk}),
            reverse("exp:study-participant-contact", kwargs={"pk": self.study.pk}),
            reverse("exp:preview-detail", kwargs={"uuid": self.study.uuid}),
            reverse(
                "exp:preview-proxy",
                kwargs={
                    "uuid": self.study.uuid,
                    "child_id": self.other_researcher_child.uuid,
                },
            ),
        ]

    def test_cannot_see_any_study_views_unauthenticated(self):
        for url in self.all_study_views_urls:
            page = self.client.get(url)
            self.assertNotEqual(
                page.status_code,
                200,
                "Unauthenticated user can see study view: " + url,
            )

    def test_can_see_study_preview_detail_as_other_researcher_if_shared(self):
        self.client.force_login(self.other_researcher)
        url = reverse(
            "exp:preview-detail", kwargs={"uuid": self.study_shared_preview.uuid}
        )
        page = self.client.get(url)
        self.assertEqual(
            page.status_code,
            200,
            "Study preview is shared but unassociated researcher cannot access: " + url,
        )

    @skip(
        "Skip testing redirect to GCP resources until build -> deploy to GCP is part of testing"
    )
    def test_can_see_study_preview_proxy_as_other_researcher_if_shared(self):
        self.client.force_login(self.other_researcher)
        url = reverse(
            "exp:preview-proxy",
            kwargs={
                "uuid": self.study_shared_preview.uuid,
                "child_id": self.other_researcher_child.uuid,
            },
        )
        page = self.client.get(url)
        self.assertEqual(
            page.status_code,
            200,
            "Study preview is shared but unassociated researcher cannot access: " + url,
        )

    def test_cannot_see_study_preview_detail_as_participant(self):
        self.client.force_login(self.participant)
        url = reverse(
            "exp:preview-detail", kwargs={"uuid": self.study_shared_preview.uuid}
        )
        page = self.client.get(url)
        self.assertEqual(
            page.status_code, 403, "Study preview is accessible by participant: " + url
        )

    def test_cannot_see_study_preview_detail_as_other_researcher_if_not_shared(self):
        self.client.force_login(self.other_researcher)
        url = reverse("exp:preview-detail", kwargs={"uuid": self.study.uuid})
        page = self.client.get(url)
        self.assertEqual(
            page.status_code,
            403,
            "Study preview is not shared but unassociated researcher can access: "
            + url,
        )

    def test_get_study_build_view(self):
        self.client.force_login(self.study_designer)
        page = self.client.get(self.study_build_url)
        self.assertIn(
            page.status_code, [403, 405], "GET method allowed on study build view"
        )

    def test_build_study_as_researcher_outside_lab(self):
        self.client.force_login(self.other_researcher)
        page = self.client.post(self.study_build_url, {})
        self.assertEqual(
            page.status_code, 403, "Study build allowed from outside researcher"
        )

    def test_build_study_already_built(self):
        self.client.force_login(self.study_designer)
        self.study.built = True
        self.study.save()
        page = self.client.post(self.study_build_url, {})
        self.assertEqual(
            page.status_code, 403, "Study build allowed when already built"
        )

    def test_build_study_currently_building(self):
        self.client.force_login(self.study_designer)
        self.study.is_building = True
        self.study.save()
        page = self.client.post(self.study_build_url, {})
        self.assertEqual(
            page.status_code, 403, "Study build allowed when already building"
        )

    def test_build_study_in_lab_without_correct_perms(self):
        self.client.force_login(self.lab_researcher)
        # Assign some permissions that should NOT grant ability to build study
        assign_perm(
            StudyPermission.READ_STUDY_DETAILS.prefixed_codename,
            self.lab_researcher,
            self.study,
        )
        assign_perm(
            LabPermission.CHANGE_STUDY_STATUS.prefixed_codename,
            self.lab_researcher,
            self.approved_lab,
        )
        page = self.client.post(self.study_build_url, {})
        self.assertEqual(
            page.status_code,
            403,
            "Study build allowed from lab researcher without specific perms",
        )

    @skip
    def test_build_study_with_correct_perms_and_current_exp_runner(self):
        self.client.force_login(self.lab_researcher)
        assign_perm(
            StudyPermission.WRITE_STUDY_DETAILS.prefixed_codename,
            self.lab_researcher,
            self.study,
        )
        page = self.client.post(self.study_build_url, {})
        self.assertEqual(
            page.status_code,
            200,
            "Study build not allowed from researcher with write study details perms",
        )
        self.assertTrue(
            self.study.built, "Study built field not True following study build"
        )

    @skip
    def test_build_study_with_correct_perms_and_specific_exp_runner(self):
        self.client.force_login(self.lab_researcher)
        self.study.metadata = {
            "player_repo_url": "https://github.com/lookit/ember-lookit-frameplayer",
            "last_known_player_sha": "bd13a209640917993247f7b6d50ce8bd7d846c82",
        }
        self.study.built = False
        self.study.save()
        assign_perm(
            StudyPermission.WRITE_STUDY_DETAILS.prefixed_codename,
            self.lab_researcher,
            self.study,
        )
        page = self.client.post(self.study_build_url, {})
        self.assertEqual(
            page.status_code,
            200,
            "Study build not allowed from researcher with write study details perms",
        )
        self.assertTrue(
            self.study.built, "Study built field not True following study build"
        )

    @patch("exp.views.mixins.StudyTypeMixin.validate_and_fetch_metadata")
    @skip("Not able to change study type on in study edit view.")
    def test_study_edit_change_study_type(self, mock_validate):
        mock_validate.return_value = {"fake": "metadata"}, []
        # Mock validation function - we should test that unit separately
        self.client.force_login(self.lab_researcher)
        url = reverse("exp:study-edit", kwargs={"pk": self.study.id})
        assign_perm(
            StudyPermission.WRITE_STUDY_DETAILS.prefixed_codename,
            self.lab_researcher,
            self.study,
        )
        data = model_to_dict(self.study)
        data["study_type"] = 2  # Other study type
        data["comments"] = "Changing the study type"
        data["structure"] = json.dumps(data["structure"])
        response = self.client.post(url, data, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            "Study edit returns invalid response when editing study type",
        )
        self.assertEqual(
            response.redirect_chain,
            [(reverse("exp:study-edit", kwargs={"pk": self.study.pk}), 302)],
        )
        updated_study = Study.objects.get(id=self.study.id)
        self.assertEqual(
            updated_study.study_type, self.other_study_type, "Study type not updated"
        )
        self.assertFalse(
            updated_study.built,
            "Study build was not invalidated after editing study type",
        )

    def test_new_user_can_create_studies_in_sandbox_lab_only(self):
        new_researcher = G(
            User, is_active=True, is_researcher=True, given_name="New researcher"
        )
        self.client.force_login(new_researcher)
        self.assertTrue(
            new_researcher.can_create_study(), "New researcher unable to create study"
        )
        sandbox_lab = Lab.objects.get(name="Sandbox lab")
        demo_lab = Lab.objects.get(name="Demo lab")
        self.assertTrue(
            new_researcher.has_perm(
                LabPermission.CREATE_LAB_ASSOCIATED_STUDY.codename, obj=sandbox_lab
            ),
            "New researcher unable to create studies in sandbox lab",
        )
        self.assertFalse(
            new_researcher.has_perm(
                LabPermission.CREATE_LAB_ASSOCIATED_STUDY.codename, obj=demo_lab
            ),
            "New researcher able to create studies in demo lab",
        )
        self.assertEqual(
            get_objects_for_user(
                new_researcher,
                LabPermission.CREATE_LAB_ASSOCIATED_STUDY.prefixed_codename,
            ).count(),
            1,
        )

    def test_create_study_buttons_shown_if_allowed(self):
        self.client.force_login(self.lab_researcher)
        assign_perm(
            StudyPermission.READ_STUDY_DETAILS.codename, self.lab_researcher, self.study
        )
        list_view_response = self.client.get(reverse("exp:study-list"))
        self.assertIn(
            "Create Study",
            list_view_response.content.decode("utf-8"),
            "Create Study button not displayed on study list view",
        )
        detail_view_response = self.client.get(
            reverse("exp:study", kwargs={"pk": self.study.pk})
        )
        self.assertIn(
            "Clone Study",
            detail_view_response.content.decode("utf-8"),
            "Clone Study button not displayed on study detail view",
        )

    def test_create_study_buttons_not_shown_if_not_allowed(self):
        assign_perm(
            StudyPermission.READ_STUDY_DETAILS.codename, self.lab_researcher, self.study
        )
        sandbox_lab = Lab.objects.get(name="Sandbox lab")
        sandbox_lab.guest_group.user_set.remove(self.lab_researcher)
        self.client.force_login(self.lab_researcher)
        self.assertFalse(
            self.lab_researcher.can_create_study(),
            "Researcher can_create_study function returns true after removing perms",
        )
        list_view_response = self.client.get(reverse("exp:study-list"))
        self.assertNotIn(
            "Create Study",
            list_view_response.content.decode("utf-8"),
            "Create Study button displayed on study list view",
        )
        detail_view_response = self.client.get(
            reverse("exp:study", kwargs={"pk": self.study.pk})
        )
        self.assertNotIn(
            "Clone Study",
            detail_view_response.content.decode("utf-8"),
            "Clone Study button displayed on study detail view",
        )


class CloneStudyViewTestCase(TestCase):
    def test_model(self):
        clone_study_view = CloneStudyView()
        self.assertIs(clone_study_view.model, Study)

    def test_permissions(self):
        self.assertTrue(
            issubclass(CloneStudyView, ResearcherLoginRequiredMixin),
            "CloneStudyView must have ResearcherLoginRequiredMixin",
        )
        self.assertTrue(
            issubclass(CloneStudyView, UserPassesTestMixin),
            "CloneStudyView must have UserPassesTestMixin",
        )

    def test_user_can_clone_study(self):
        with patch.object(CloneStudyView, "request", create=True):
            mock_is_researcher = PropertyMock(return_value=True)
            mock_can_create_study = MagicMock(return_value=True)

            clone_study_view = CloneStudyView()
            type(clone_study_view.request.user).is_researcher = mock_is_researcher
            clone_study_view.request.user.can_create_study = mock_can_create_study

            self.assertIs(clone_study_view.user_can_clone_study(), True)
            mock_can_create_study.assert_called_with()
            mock_is_researcher.assert_called_with()

    def test_test_func(self):
        clone_study_view = CloneStudyView()
        self.assertEqual(
            clone_study_view.test_func,
            clone_study_view.user_can_clone_study,
            "CloneStudyView.test_func must be set to CloneStudyView.user_can_clone_study",
        )

    @patch.object(CloneStudyView, "request", create=True)
    def test_add_creator_to_study_admin_group(self, mock_request):
        clone_study_view = CloneStudyView()
        mock_study = create_autospec(Study)
        self.assertEqual(
            clone_study_view.add_creator_to_study_admin_group(mock_study),
            mock_study.admin_group,
        )
        mock_request.user.groups.add.assert_called_with(mock_study.admin_group)

    @patch.object(CloneStudyView, "request", create=True)
    @patch.object(SingleObjectMixin, "get_object")
    @patch("exp.views.study.HttpResponseRedirect")
    @patch("exp.views.study.reverse")
    def test_post_redirect(
        self, mock_reverse, mock_http_response_redirect, mock_get_object, mock_request
    ):
        mock_redirect_to = mock_reverse(
            "exp:study-edit", kwargs={"pk": mock_get_object().clone().pk}
        )
        mock_response = mock_http_response_redirect(mock_redirect_to)

        clone_study_view = CloneStudyView()

        self.assertEqual(clone_study_view.post(), mock_response)
        self.assertEqual(mock_request.user, mock_get_object().clone().creator)
        mock_request.user.has_perm.assert_called_with(
            LabPermission.CREATE_LAB_ASSOCIATED_STUDY.codename,
            obj=mock_get_object().lab,
        )

    @patch.object(CloneStudyView, "request", create=True)
    @patch("exp.views.study.HttpResponseForbidden")
    def test_post_forbidden(self, mock_http_response_forbidden, mock_request):
        with patch.object(SingleObjectMixin, "get_object"):
            mock_request.user.has_perm = MagicMock(return_value=False)
            mock_request.user.labs.only = MagicMock(return_value=[])

            clone_study_view = CloneStudyView()

            self.assertEqual(clone_study_view.post(), mock_http_response_forbidden())
            mock_request.user.labs.only.assert_called_with("id")

    @patch.object(CloneStudyView, "request", create=True)
    @patch.object(SingleObjectMixin, "get_object")
    @patch("exp.views.study.HttpResponseRedirect")
    @patch("exp.views.study.reverse")
    def test_post_first_lab(
        self, mock_reverse, mock_http_response_redirect, mock_get_object, mock_request
    ):
        mock_has_perm = MagicMock(side_effect=[False, True])
        mock_labs_only = MagicMock(return_value=(sentinel.lab,))
        mock_redirect_to = mock_reverse(
            "exp:study-edit", kwargs={"pk": mock_get_object().clone().pk}
        )
        mock_response = mock_http_response_redirect(mock_redirect_to)

        mock_request.user.has_perm = mock_has_perm
        mock_request.user.labs.only = mock_labs_only

        clone_study_view = CloneStudyView()

        self.assertEqual(clone_study_view.post(), mock_response)
        mock_request.user.labs.only.assert_called_with("id")
        mock_get_object().clone().creator.has_perm.assert_called_with(
            LabPermission.CREATE_LAB_ASSOCIATED_STUDY.codename, obj=sentinel.lab
        )


class ChangeStudyStatusViewTestCase(TestCase):
    def test_model(self):
        change_study_status_view = ChangeStudyStatusView()
        self.assertIs(change_study_status_view.model, Study)

    def test_permissions(self):
        self.assertTrue(
            issubclass(ChangeStudyStatusView, ResearcherLoginRequiredMixin),
            "ChangeStudyStatusView must have ResearcherLoginRequiredMixin",
        )
        self.assertTrue(
            issubclass(ChangeStudyStatusView, UserPassesTestMixin),
            "ChangeStudyStatusView must have UserPassesTestMixin",
        )

    @patch.object(ChangeStudyStatusView, "request", create=True)
    @patch.object(SingleObjectMixin, "get_object")
    def test_user_can_change_study_status(
        self, mock_get_object: Mock, mock_request: Mock
    ):
        mock_is_researcher = PropertyMock(return_value=True)

        type(mock_request.user).is_researcher = mock_is_researcher
        mock_request.user.has_study_perms = MagicMock(return_value=True)

        change_study_status_view = ChangeStudyStatusView()

        self.assertIs(change_study_status_view.user_can_change_study_status(), True)
        mock_is_researcher.assert_called_with()
        mock_request.user.has_study_perms.assert_called_with(
            StudyPermission.CHANGE_STUDY_STATUS, mock_get_object()
        )

    def test_test_func(self):
        change_study_status_view = ChangeStudyStatusView()
        self.assertEqual(
            change_study_status_view.test_func,
            change_study_status_view.user_can_change_study_status,
            "CloneStudyView.test_func must be set to CloneStudyView.user_can_change_study_status",
        )

    @patch.object(SingleObjectMixin, "get_object")
    @patch("exp.views.study.HttpResponseRedirect")
    @patch("exp.views.study.reverse")
    def test_post(
        self,
        mock_reverse: Mock,
        mock_http_response_redirect: Mock,
        mock_get_object: Mock,
    ):
        change_study_status_view = ChangeStudyStatusView()

        change_study_status_view.update_trigger = MagicMock(return_value=True)

        self.assertEqual(change_study_status_view.post(), mock_http_response_redirect())
        mock_http_response_redirect.assert_called_with()
        mock_reverse.assert_called_with(
            "exp:study", kwargs={"pk": mock_get_object().pk}
        )
        change_study_status_view.update_trigger.assert_called_with()

    @patch.object(ChangeStudyStatusView, "request", create=True)
    @patch.object(SingleObjectMixin, "get_object")
    @patch("exp.views.study.HttpResponseRedirect")
    @patch("exp.views.study.reverse")
    @patch("exp.views.study.messages")
    def test_post_exception(
        self,
        mock_messages: Mock,
        mock_reverse: Mock,
        mock_http_response_redirect: Mock,
        mock_get_object: Mock,
        mock_request: Mock,
    ):
        change_study_status_view = ChangeStudyStatusView()
        change_study_status_view.update_trigger = MagicMock(
            side_effect=Exception(sentinel.error_message)
        )
        self.assertEqual(change_study_status_view.post(), mock_http_response_redirect())
        mock_messages.error.assert_called_with(
            mock_request, f"TRANSITION ERROR: {sentinel.error_message}"
        )
        mock_reverse.assert_called_with(
            "exp:study", kwargs={"pk": mock_get_object().pk}
        )

    @patch.object(ChangeStudyStatusView, "request", create=True)
    @patch.object(SingleObjectMixin, "get_object")
    @patch("exp.views.study.messages")
    def test_update_trigger(
        self, mock_messages: Mock, mock_get_object: Mock, mock_request: Mock
    ):
        mock_request.POST.get = MagicMock(return_value="trigger_attr")
        mock_request.POST.keys = MagicMock(return_value=("comments-text",))

        change_study_status_view = ChangeStudyStatusView()

        self.assertEqual(change_study_status_view.update_trigger(), mock_get_object())
        mock_request.POST.get.assert_called_with("trigger")
        mock_request.POST.keys.assert_called_with()
        mock_messages.success.assert_called_with(
            mock_request, f"Study {mock_get_object().name} {mock_get_object().state}."
        )
        mock_get_object().save.assert_called_with()
        mock_get_object().trigger_attr.assert_called_with(user=mock_request.user)

    @patch.object(ChangeStudyStatusView, "request", create=True)
    @patch.object(SingleObjectMixin, "get_object")
    @patch("exp.views.study.messages")
    def test_update_trigger_trigger_is_none(
        self, mock_messages: Mock, mock_get_object: Mock, mock_request: Mock
    ):
        mock_request.POST.get = MagicMock(return_value=None)

        change_study_status_view = ChangeStudyStatusView()

        self.assertEqual(change_study_status_view.update_trigger(), mock_get_object())
        mock_messages.success.assert_called_with(
            mock_request, f"Study {mock_get_object().name} {mock_get_object().state}."
        )
        mock_get_object().save.assert_not_called()
        mock_get_object().trigger_attr.assert_not_called()

    @patch.object(ChangeStudyStatusView, "request", create=True)
    @patch.object(SingleObjectMixin, "get_object")
    def test_update_trigger_object_no_attr(
        self, mock_get_object: Mock, mock_request: Mock
    ):
        mock_request.POST.get = MagicMock(return_value="trigger_attr")
        del mock_get_object().trigger_attr

        change_study_status_view = ChangeStudyStatusView()

        self.assertEqual(change_study_status_view.update_trigger(), mock_get_object())
        mock_get_object().save.assert_not_called()
        mock_request.POST.keys.assert_not_called()


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
@override_settings(CELERY_TASK_EAGER_PROPAGATES=True)
@patch("studies.helpers.send_mail")
class ActivateStudyMaxResponsesTestCase(TestCase):
    """Integration tests for the check_if_at_max_responses workflow guard.

    When a researcher tries to activate a study (from approved or paused state),
    the transition should be blocked if the study has already reached its
    max_responses limit.
    """

    def setUp(self):
        self.client = Force2FAClient()
        self.user = G(User, is_active=True, is_researcher=True)
        self.lab = G(Lab, name="Activation Test Lab", approved_to_test=True)
        self.lab.researchers.add(self.user)

        self.study = G(
            Study,
            image=SimpleUploadedFile(
                name="small.gif",
                content=(
                    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x00\x00\x00\x21\xf9\x04"
                    b"\x01\x0a\x00\x01\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02"
                    b"\x02\x4c\x01\x00\x3b"
                ),
                content_type="image/gif",
            ),
            study_type=StudyType.get_external(),
            creator=self.user,
            lab=self.lab,
            name="Activation Test Study",
            built=True,
        )
        self.study.admin_group.user_set.add(self.user)
        assign_perm(
            StudyPermission.CHANGE_STUDY_STATUS.prefixed_codename,
            self.user,
            self.study,
        )
        self.client.force_login(self.user)

        self.change_status_url = reverse(
            "exp:change-study-status", kwargs={"pk": self.study.pk}
        )

    def _create_eligible_responses(self, count):
        """Create eligible, non-preview responses for the study."""
        participant = G(User, is_active=True)
        child = G(
            Child,
            user=participant,
            given_name="Test child",
            birthday=datetime.date.today() - datetime.timedelta(days=30),
        )
        for _ in range(count):
            r = Response.objects.create(
                study=self.study,
                child=child,
                study_type=self.study.study_type,
                demographic_snapshot=participant.latest_demographics,
                completed=True,
                is_preview=False,
            )
            Response.objects.filter(pk=r.pk).update(
                eligibility=[ResponseEligibility.ELIGIBLE]
            )

    def _get_error_messages(self, response):
        """Extract error-level messages from a followed response."""
        from django.contrib.messages import constants

        return [m for m in response.context["messages"] if m.level == constants.ERROR]

    def _get_success_messages(self, response):
        """Extract success-level messages from a followed response."""
        from django.contrib.messages import constants

        return [m for m in response.context["messages"] if m.level == constants.SUCCESS]

    def test_activate_blocked_from_approved_when_at_max_responses(self, mock_send_mail):
        """Activating an approved study fails when max_responses has been reached."""
        self.study.state = "approved"
        self.study.max_responses = 3
        self.study.save()
        self._create_eligible_responses(3)

        response = self.client.post(
            self.change_status_url, {"trigger": "activate"}, follow=True
        )

        self.study.refresh_from_db()
        self.assertNotEqual(self.study.state, "active")
        errors = self._get_error_messages(response)
        self.assertEqual(len(errors), 1)
        self.assertIn("TRANSITION ERROR", str(errors[0]))
        self.assertIn("maximum number of responses", str(errors[0]))

    def test_activate_blocked_from_paused_when_at_max_responses(self, mock_send_mail):
        """Reactivating a paused study fails when max_responses has been reached."""
        self.study.state = "paused"
        self.study.max_responses = 2
        self.study.save()
        self._create_eligible_responses(3)

        response = self.client.post(
            self.change_status_url, {"trigger": "activate"}, follow=True
        )

        self.study.refresh_from_db()
        self.assertNotEqual(self.study.state, "active")
        errors = self._get_error_messages(response)
        self.assertEqual(len(errors), 1)
        self.assertIn("TRANSITION ERROR", str(errors[0]))
        self.assertIn("maximum number of responses", str(errors[0]))

    def test_activate_succeeds_when_below_max_responses(self, mock_send_mail):
        """Activating an approved study succeeds when below the max_responses limit."""
        self.study.state = "approved"
        self.study.max_responses = 10
        self.study.save()
        self._create_eligible_responses(3)

        response = self.client.post(
            self.change_status_url, {"trigger": "activate"}, follow=True
        )

        self.study.refresh_from_db()
        self.assertEqual(self.study.state, "active")
        errors = self._get_error_messages(response)
        self.assertEqual(len(errors), 0)

    def test_activate_succeeds_when_no_max_responses_set(self, mock_send_mail):
        """Activating an approved study succeeds when max_responses is not set."""
        self.study.state = "approved"
        self.study.max_responses = None
        self.study.save()
        self._create_eligible_responses(5)

        response = self.client.post(
            self.change_status_url, {"trigger": "activate"}, follow=True
        )

        self.study.refresh_from_db()
        self.assertEqual(self.study.state, "active")
        errors = self._get_error_messages(response)
        self.assertEqual(len(errors), 0)

    def test_activate_succeeds_when_exactly_at_limit_minus_one(self, mock_send_mail):
        """Activating succeeds when response count is one below max_responses."""
        self.study.state = "approved"
        self.study.max_responses = 4
        self.study.save()
        self._create_eligible_responses(3)

        response = self.client.post(
            self.change_status_url, {"trigger": "activate"}, follow=True
        )

        self.study.refresh_from_db()
        self.assertEqual(self.study.state, "active")
        errors = self._get_error_messages(response)
        self.assertEqual(len(errors), 0)


class ManageResearcherPermissionsViewTestCase(TestCase):
    def test_model(self) -> None:
        manage_researcher_permissions_view = ManageResearcherPermissionsView()
        self.assertIs(manage_researcher_permissions_view.model, Study)

    def test_permissions(self) -> None:
        self.assertTrue(
            issubclass(ManageResearcherPermissionsView, ResearcherLoginRequiredMixin),
            "ManageResearcherPermissionsView must have ResearcherLoginRequiredMixin",
        )
        self.assertTrue(
            issubclass(ManageResearcherPermissionsView, UserPassesTestMixin),
            "ManageResearcherPermissionsView must have UserPassesTestMixin",
        )

    @patch.object(ManageResearcherPermissionsView, "request", create=True)
    @patch.object(SingleObjectMixin, "get_object")
    def test_user_can_change_study_permissions(
        self, mock_get_object: Mock, mock_request: Mock
    ) -> None:
        mock_request.user.has_study_perms = MagicMock(return_value=True)
        mock_is_researcher = PropertyMock(return_value=True)
        type(mock_request.user).is_researcher = mock_is_researcher

        manage_researcher_permissions_view = ManageResearcherPermissionsView()

        self.assertIs(
            manage_researcher_permissions_view.user_can_change_study_permissions(), True
        )
        mock_request.user.has_study_perms.assert_called_once_with(
            StudyPermission.MANAGE_STUDY_RESEARCHERS, mock_get_object()
        )
        mock_is_researcher.assert_called_with()

    def test_test_func(self):
        manage_researcher_permissions_view = ManageResearcherPermissionsView()
        self.assertEqual(
            manage_researcher_permissions_view.test_func,
            manage_researcher_permissions_view.user_can_change_study_permissions,
            "ManageResearcherPermissionsView.test_func must be set to ManageResearcherPermissionsView.user_can_change_study_permissions",
        )

    @patch.object(SingleObjectMixin, "get_object")
    @patch(
        "exp.views.study.ManageResearcherPermissionsView.manage_researcher_permissions"
    )
    @patch("exp.views.study.HttpResponseRedirect")
    @patch("exp.views.study.reverse")
    def test_post(
        self,
        mock_reverse: Mock,
        mock_https_response_redirect: Mock,
        mock_manage_researcher_permissions: Mock,
        mock_get_object: Mock,
    ):
        manage_researcher_permissions_view = ManageResearcherPermissionsView()
        self.assertEqual(
            manage_researcher_permissions_view.post(), mock_https_response_redirect()
        )
        mock_https_response_redirect.assert_called_with()
        mock_reverse.assert_called_once_with(
            "exp:study", kwargs={"pk": mock_get_object().pk}
        )
        mock_manage_researcher_permissions.assert_called_once_with()

    @patch(
        "exp.views.study.ManageResearcherPermissionsView.manage_researcher_permissions",
        return_value=False,
    )
    @patch("exp.views.study.HttpResponseForbidden")
    def test_post_403(
        self,
        mock_https_response_forbidden: Mock,
        mock_manage_researcher_permissions: Mock,
    ):
        manage_researcher_permissions_view = ManageResearcherPermissionsView()
        self.assertEqual(
            manage_researcher_permissions_view.post(), mock_https_response_forbidden()
        )
        mock_manage_researcher_permissions.assert_called_once_with()

    @patch("exp.views.study.send_mail")
    @patch.object(SingleObjectMixin, "get_object")
    def test_send_study_email(self, mock_get_object: Mock, mock_send_mail: Mock):
        mock_user = MagicMock()
        mock_permission = MagicMock()
        manage_researcher_permissions_view = ManageResearcherPermissionsView()
        manage_researcher_permissions_view.send_study_email(mock_user, mock_permission)
        mock_send_mail.delay.assert_called_with(
            "notify_researcher_of_study_permissions",
            f"New access granted for study {mock_get_object().name}",
            mock_user.username,
            reply_to=[mock_get_object().lab.contact_email],
            permission=mock_permission,
            study_name=mock_get_object().name,
            study_id=mock_get_object().id,
            lab_name=mock_get_object().lab.name,
            researcher_name=mock_user.get_short_name(),
        )

    @patch("exp.views.study.ManageResearcherPermissionsView.remove_user")
    @patch("exp.views.study.ManageResearcherPermissionsView.add_user")
    @patch("exp.views.study.ManageResearcherPermissionsView.update_user")
    @patch.object(ManageResearcherPermissionsView, "request", create=True)
    @patch.object(SingleObjectMixin, "get_object")
    def test_manage_researcher_permissions_update_user(
        self,
        mock_get_object: Mock,
        mock_request: Mock,
        mock_update_user: Mock,
        mock_add_user: Mock,
        mock_remove_user: Mock,
    ) -> None:
        mock_request.POST.get = MagicMock(side_effect=[None, None, "update_user"])
        manage_researcher_permissions_view = ManageResearcherPermissionsView()
        manage_researcher_permissions_view.manage_researcher_permissions()
        mock_update_user.assert_called_once_with(mock_get_object())
        mock_add_user.assert_not_called()
        mock_remove_user.assert_not_called()

    @patch("exp.views.study.ManageResearcherPermissionsView.remove_user")
    @patch("exp.views.study.ManageResearcherPermissionsView.add_user")
    @patch("exp.views.study.ManageResearcherPermissionsView.update_user")
    @patch.object(ManageResearcherPermissionsView, "request", create=True)
    @patch.object(SingleObjectMixin, "get_object")
    def test_manage_researcher_permissions_remove_user(
        self,
        mock_get_object: Mock,
        mock_request: Mock,
        mock_update_user: Mock,
        mock_add_user: Mock,
        mock_remove_user: Mock,
    ) -> None:
        mock_request.POST.get = MagicMock(
            side_effect=[None, sentinel.remove_user_id, None]
        )
        manage_researcher_permissions_view = ManageResearcherPermissionsView()
        manage_researcher_permissions_view.manage_researcher_permissions()
        mock_update_user.assert_not_called()
        mock_add_user.assert_not_called()
        mock_remove_user.assert_called_once_with(
            mock_get_object(), sentinel.remove_user_id
        )

    @patch("exp.views.study.ManageResearcherPermissionsView.remove_user")
    @patch("exp.views.study.ManageResearcherPermissionsView.add_user")
    @patch("exp.views.study.ManageResearcherPermissionsView.update_user")
    @patch.object(ManageResearcherPermissionsView, "request", create=True)
    @patch.object(SingleObjectMixin, "get_object")
    def test_manage_researcher_permissions_add_user(
        self,
        mock_get_object: Mock,
        mock_request: Mock,
        mock_update_user: Mock,
        mock_add_user: Mock,
        mock_remove_user: Mock,
    ) -> None:
        mock_request.POST.get = MagicMock(
            side_effect=[sentinel.update_user_id, None, None]
        )
        manage_researcher_permissions_view = ManageResearcherPermissionsView()
        manage_researcher_permissions_view.manage_researcher_permissions()
        mock_update_user.assert_not_called()
        mock_add_user.assert_called_once_with(
            mock_get_object(), sentinel.update_user_id
        )
        mock_remove_user.assert_not_called()

    @patch("exp.views.study.messages")
    @patch.object(ManageResearcherPermissionsView, "send_study_email")
    @patch("accounts.models.User.objects")
    @patch.object(ManageResearcherPermissionsView, "request", create=True)
    def test_update_user(
        self,
        mock_request: Mock,
        mock_user_objects: Mock,
        mock_send_study_email: Mock,
        mock_messages: None,
    ):
        user_group = "study_preview"

        mock_update_user = MagicMock(name="update_user")
        mock_study_group = MagicMock(name="study_group")
        mock_study = MagicMock(name="study")

        mock_request.POST.get.side_effect = [sentinel.user_update_id, user_group]
        mock_user_objects.get.side_effect = [mock_update_user]

        mock_update_user.groups.all.return_value = [mock_study.admin_group]
        mock_study.all_study_groups.return_value = [mock_study_group]
        mock_study.admin_group.user_set.count.return_value = 2

        manage_researcher_permissions_view = ManageResearcherPermissionsView()

        self.assertTrue(manage_researcher_permissions_view.update_user(mock_study))

        mock_update_user.groups.all.assert_called_once_with()
        mock_study.admin_group.user_set.count.assert_called_once_with()
        mock_messages.error.assert_not_called()
        mock_study.all_study_groups.assert_called_once_with()
        mock_study_group.user_set.remove.assert_called_once_with(mock_update_user)
        mock_update_user.groups.add.assert_called_once_with(mock_study.preview_group)
        mock_send_study_email.assert_called_once_with(mock_update_user, user_group)

    @patch.object(ManageResearcherPermissionsView, "user_only_admin", return_value=True)
    @patch("exp.views.study.messages")
    @patch("accounts.models.User.objects")
    @patch.object(ManageResearcherPermissionsView, "request", create=True)
    def test_update_user_not_enough_admins(
        self,
        mock_request: Mock,
        mock_user_objects: Mock,
        mock_messages: Mock,
        mock_user_only_admin: Mock,
    ):
        mock_update_user = MagicMock(name="update_user")
        mock_study = MagicMock(name="study")

        mock_user_objects.get.return_value = mock_update_user

        manage_researcher_permissions_view = ManageResearcherPermissionsView()

        self.assertFalse(manage_researcher_permissions_view.update_user(mock_study))

        mock_messages.error.assert_called_once_with(
            mock_request,
            "Could not change permissions for this researcher. There must be at least one study admin.",
            extra_tags="user_removed",
        )
        mock_user_only_admin.assert_called_once_with(mock_study, mock_update_user)

    @patch.object(
        ManageResearcherPermissionsView, "user_only_admin", return_value=False
    )
    @patch("exp.views.study.messages")
    @patch.object(ManageResearcherPermissionsView, "send_study_email")
    @patch("accounts.models.User.objects")
    @patch.object(ManageResearcherPermissionsView, "request", create=True)
    def test_update_user_already_one_admin(
        self,
        mock_request: Mock,
        mock_user_objects: Mock,
        mock_send_study_email: Mock,
        mock_messages: Mock,
        mock_user_only_admin: Mock,
    ):
        user_group = "study_admin"

        mock_study = MagicMock(name="study")
        mock_update_user = MagicMock(name="update_user")
        mock_study_group = MagicMock(name="study_group")

        mock_study.all_study_groups.return_value = [mock_study_group]
        mock_user_objects.get.return_value = mock_update_user

        mock_request.POST.get.side_effect = [sentinel.user_update_id, user_group]

        manage_researcher_permissions_view = ManageResearcherPermissionsView()

        self.assertTrue(manage_researcher_permissions_view.update_user(mock_study))

        mock_messages.error.assert_not_called()
        mock_study.all_study_groups.assert_called_once_with()
        mock_study_group.user_set.remove.assert_called_once_with(mock_update_user)
        mock_update_user.groups.add.assert_called_once_with(mock_study.admin_group)
        mock_send_study_email.assert_called_once_with(mock_update_user, user_group)
        mock_user_only_admin.assert_called_once_with(mock_study, mock_update_user)

    @patch("exp.views.study.messages")
    @patch.object(ManageResearcherPermissionsView, "send_study_email")
    @patch.object(ManageResearcherPermissionsView, "request", create=True)
    @patch("accounts.models.User.objects")
    def test_add_user(
        self,
        mock_user_objects: Mock,
        mock_request: Mock,
        mock_send_study_email: Mock,
        mock_messages: Mock,
    ):
        mock_study = MagicMock(name="study")

        manage_researcher_permissions_view = ManageResearcherPermissionsView()
        self.assertTrue(
            manage_researcher_permissions_view.add_user(
                mock_study, sentinel.add_user_id
            )
        )
        mock_user_objects.get().groups.add.assert_called_once_with(
            mock_study.preview_group
        )
        mock_messages.success.assert_called_once_with(
            mock_request,
            f"{mock_user_objects.get().get_short_name()} given {mock_study.name} Preview Permissions.",
            extra_tags="user_added",
        )
        mock_send_study_email.assert_called_once_with(
            mock_user_objects.get(), "study_preview"
        )

    @patch("exp.views.study.messages")
    @patch.object(ManageResearcherPermissionsView, "request", create=True)
    @patch.object(
        ManageResearcherPermissionsView, "user_only_admin", return_value=False
    )
    @patch("accounts.models.User.objects")
    def test_remove_user(
        self,
        mock_user_objects: Mock,
        mock_user_only_admin: Mock,
        mock_request: Mock,
        mock_messages: Mock,
    ):
        mock_study = MagicMock(name="study")
        mock_study_group = MagicMock(name="study_group")
        mock_study.all_study_groups.return_value = [mock_study_group]

        manage_researcher_permissions_view = ManageResearcherPermissionsView()
        self.assertTrue(
            manage_researcher_permissions_view.remove_user(
                mock_study, sentinel.remove_user_id
            )
        )
        mock_messages.error.assert_not_called()
        mock_user_only_admin.assert_called_once_with(
            mock_study, mock_user_objects.get()
        )
        mock_study_group.user_set.remove.assert_called_once_with(
            mock_user_objects.get()
        )
        mock_messages.success.assert_called_once_with(
            mock_request,
            f"{mock_user_objects.get().get_short_name()} removed from {mock_study.name}.",
            extra_tags="user_removed",
        )

    @patch("exp.views.study.messages")
    @patch.object(ManageResearcherPermissionsView, "request", create=True)
    @patch.object(ManageResearcherPermissionsView, "user_only_admin", return_value=True)
    @patch("accounts.models.User.objects")
    def test_remove_user_one_admin(
        self,
        mock_user_objects: Mock,
        mock_user_only_admin: Mock,
        mock_request: Mock,
        mock_messages: Mock,
    ):
        mock_study = MagicMock(name="study")
        mock_study_group = MagicMock(name="study_group")
        mock_study.all_study_groups.return_value = [mock_study_group]

        manage_researcher_permissions_view = ManageResearcherPermissionsView()
        self.assertFalse(
            manage_researcher_permissions_view.remove_user(
                mock_study, sentinel.remove_user_id
            )
        )

        mock_user_only_admin.assert_called_once_with(
            mock_study, mock_user_objects.get()
        )
        mock_study_group.user_set.remove.assert_not_called()
        mock_messages.error.assert_called_once_with(
            mock_request,
            "Could not delete this researcher. There must be at least one study admin.",
            extra_tags="user_removed",
        )

    def test_user_only_admin_user_not_admin(self):
        mock_study = MagicMock()
        mock_user = MagicMock()

        mock_user.groups.all.return_value = []

        manage_researcher_permissions_view = ManageResearcherPermissionsView()
        self.assertFalse(
            manage_researcher_permissions_view.user_only_admin(mock_study, mock_user)
        )
        mock_user.groups.all.assert_called_once_with()

    def test_user_only_admin_user_no_other_admins(self):
        mock_study = MagicMock()
        mock_user = MagicMock()

        mock_user.groups.all.return_value = [mock_study.admin_group]
        mock_study.admin_group.user_set.count.return_value = 1

        manage_researcher_permissions_view = ManageResearcherPermissionsView()
        self.assertTrue(
            manage_researcher_permissions_view.user_only_admin(mock_study, mock_user)
        )
        mock_user.groups.all.assert_called_once_with()

    def test_only_one_admin_user_other_admins(self):
        mock_study = MagicMock()
        mock_user = MagicMock()

        mock_user.groups.all.return_value = [mock_study.admin_group]
        mock_study.admin_group.user_set.count.return_value = 2

        manage_researcher_permissions_view = ManageResearcherPermissionsView()
        self.assertFalse(
            manage_researcher_permissions_view.user_only_admin(mock_study, mock_user)
        )
        mock_user.groups.all.assert_called_once_with()


class StudyDetailViewTestCase(TestCase):
    def setUp(self):
        self.client = Force2FAClient()

        user = G(User, is_active=True, is_researcher=True, username="lab researcher")
        self.client.force_login(user)

        lab = Lab.objects.get(name="Early Childhood Cognition Lab")

        self.frame_player_study = G(
            Study,
            image=SimpleUploadedFile(
                name="small.gif", content="", content_type="image/gif"
            ),
            study_type=StudyType.get_ember_frame_player(),
            public=True,
            lab=lab,
            built=True,
        )

        self.external_study = G(
            Study,
            image=SimpleUploadedFile(
                name="small.gif", content="", content_type="image/gif"
            ),
            study_type=StudyType.get_external(),
            public=True,
            lab=lab,
            built=True,
        )

        # set permissions for both external and frame player studies
        assign_perm(
            StudyPermission.READ_STUDY_DETAILS.codename, user, self.frame_player_study
        )
        assign_perm(
            StudyPermission.CODE_STUDY_CONSENT.prefixed_codename,
            user,
            self.frame_player_study,
        )
        assign_perm(
            StudyPermission.READ_STUDY_DETAILS.codename, user, self.external_study
        )
        assign_perm(
            StudyPermission.CODE_STUDY_CONSENT.prefixed_codename,
            user,
            self.external_study,
        )

    def test_model(self) -> None:
        study_list_view = StudyDetailView()
        self.assertIs(study_list_view.model, Study)

    def test_permissions(self) -> None:
        self.assertTrue(
            issubclass(StudyDetailView, ResearcherLoginRequiredMixin),
            "StudyDetailView must have ResearcherLoginRequiredMixin",
        )
        self.assertTrue(
            issubclass(StudyDetailView, UserPassesTestMixin),
            "StudyDetailView must have UserPassesTestMixin",
        )

    def test_test_func(self):
        manage_researcher_permissions_view = StudyDetailView()
        self.assertEqual(
            manage_researcher_permissions_view.test_func,
            manage_researcher_permissions_view.user_can_see_or_edit_study_details,
            "StudyDetailView.test_func must be set to StudyDetailView.user_can_see_or_edit_study_details",
        )

    @parameterized.expand(
        [(True, True, True), (True, False, False), (False, True, False)]
    )
    @patch.object(StudyDetailView, "request", create=True)
    @patch.object(SingleObjectMixin, "get_object")
    def test_user_can_see_or_edit_study_details(
        self,
        has_study_perms: bool,
        is_researcher: bool,
        expected: bool,
        mock_get_object: Mock,
        mock_request: Mock,
    ) -> None:
        mock_request.user.has_study_perms.return_value = has_study_perms
        mock_is_researcher = PropertyMock(return_value=is_researcher)
        type(mock_request.user).is_researcher = mock_is_researcher

        study_detail_view = StudyDetailView()

        self.assertIs(study_detail_view.user_can_see_or_edit_study_details(), expected)

        mock_request.user.has_study_perms.assert_called_once_with(
            StudyPermission.READ_STUDY_DETAILS, mock_get_object()
        )
        mock_is_researcher.assert_called_with()

    def test_study_detail_review_consent(self):
        # check if review consent is viewable on a frame player study
        response = self.client.get(
            reverse("exp:study", kwargs={"pk": self.frame_player_study.pk})
        )
        self.assertEqual(200, response.status_code)
        self.assertIn(b"Review Consent", response.content)

        # check that review consent is not view on an external study
        response = self.client.get(
            reverse("exp:study", kwargs={"pk": self.external_study.pk})
        )
        self.assertEqual(200, response.status_code)
        self.assertNotIn(b"Review Consent", response.content)


class StudyPreviewDetailViewTestCase(TestCase):
    @patch.object(StudyPreviewDetailView, "request", create=True)
    def test_get_context_data_not_deleted_children(self, mock_request):
        with patch.object(StudyPreviewDetailView, "object", create=True):
            study_preview_detail_view = StudyPreviewDetailView()
            study_preview_detail_view.get_context_data()
            mock_request.user.children.filter.assert_called_once_with(deleted=False)


class StudyParticipatedViewTestCase(TestCase):
    def setUp(self):
        self.client = Force2FAClient()

    def data(self):
        return {
            "min_age_years": 0,
            "min_age_months": 0,
            "min_age_days": 0,
            "max_age_years": 1,
            "max_age_months": 0,
            "max_age_days": 0,
            "name": "study",
            "priority": 1,
            "image": SimpleUploadedFile(
                name="test_image.jpg",
                content=open("exp/tests/static/study_image.png", "rb").read(),
                content_type="image/jpeg",
            ),
            "preview_summary": "n/a",
            "short_description": "n/a",
            "purpose": "n/a",
            "exit_url": "https://mit.edu",
            "criteria": "n/a",
            "duration": "n/a",
            "contact_info": "n/a",
            "structure": "{}",
        }

    def error_check(self, response):
        if "form" in response.context:
            self.assertEqual(response.context_data["form"].errors, {})
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_must_have_participated(self):
        user = G(User, is_active=True, is_researcher=True)
        lab = G(Lab)
        study = G(
            Study, creator=user, lab=lab, study_type=StudyType.get_ember_frame_player()
        )
        another_study = G(
            Study, creator=user, lab=lab, study_type=StudyType.get_ember_frame_player()
        )

        # login
        self.client.force_login(user)

        # set permissions
        assign_perm(StudyPermission.WRITE_STUDY_DETAILS.prefixed_codename, user, study)

        # Confirm that field is empty
        self.assertDictEqual(dict(study.must_have_participated.all()), {})

        # Submit data
        data = self.data()
        data.update(must_have_participated=[study.id, another_study.id])
        response = self.client.post(
            reverse("exp:study-edit", kwargs={"pk": study.id}), data, follow=True
        )
        self.error_check(response)

        # Check that field has data
        study = Study.objects.get(pk=study.id)
        self.assertSetEqual(
            set(study.must_have_participated.all()), {study, another_study}
        )

        # Remove data from field
        data = self.data()
        data.update(must_have_participated=[])
        response = self.client.post(
            reverse("exp:study-edit", kwargs={"pk": study.id}), data, follow=True
        )
        self.error_check(response)

        self.assertSetEqual(set(study.must_have_participated.all()), set())

    def test_must_not_have_participated(self):
        user = G(User, is_active=True, is_researcher=True)
        lab = G(Lab)
        study = G(
            Study, creator=user, lab=lab, study_type=StudyType.get_ember_frame_player()
        )
        another_study = G(
            Study, creator=user, lab=lab, study_type=StudyType.get_ember_frame_player()
        )

        # login
        self.client.force_login(user)

        # set permissions
        assign_perm(StudyPermission.WRITE_STUDY_DETAILS.prefixed_codename, user, study)

        # Confirm that field is empty
        self.assertDictEqual(dict(study.must_not_have_participated.all()), {})

        # Submit data
        data = self.data()
        data.update(must_not_have_participated=[study.id, another_study.id])
        response = self.client.post(
            reverse("exp:study-edit", kwargs={"pk": study.id}), data, follow=True
        )
        self.error_check(response)

        # Check that field has data
        study = Study.objects.get(pk=study.id)
        self.assertSetEqual(
            set(study.must_not_have_participated.all()), {study, another_study}
        )

        # Remove data from field
        data = self.data()
        data.update(must_not_have_participated=[])
        response = self.client.post(
            reverse("exp:study-edit", kwargs={"pk": study.id}), data, follow=True
        )
        self.error_check(response)

        self.assertSetEqual(set(study.must_not_have_participated.all()), set())


# TODO: StudyCreateView
# - check user has to be in a lab with perms to create study to get
# TODO: StudyUpdateView
# - check user has to be researcher and have edit perms on study details to get
# - check posting change works
# - check invalid metadata not saved
# - check can't change lab to one you're not in, or at all w/o perms to change lab
# TODO: StudyListView
# - check can get as researcher only
# - check you see exactly studies you have view details perms for
# TODO: StudyPreviewProxyView
# - add checks analogous to preview detail view
# - check for correct redirect


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
@override_settings(CELERY_TASK_EAGER_PROPAGATES=True)
@patch("studies.helpers.send_mail")
class StudyUpdateMaxResponsesTestCase(TestCase):
    """Tests for banner messages when max_responses is edited via StudyUpdateView."""

    def setUp(self):
        self.client = Force2FAClient()
        self.user = G(User, is_active=True, is_researcher=True)
        self.lab = G(Lab, name="Max Resp Lab", approved_to_test=True)
        self.lab.researchers.add(self.user)

        self.study = G(
            Study,
            image=SimpleUploadedFile(
                name="small.gif",
                content=(
                    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x00\x00\x00\x21\xf9\x04"
                    b"\x01\x0a\x00\x01\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02"
                    b"\x02\x4c\x01\x00\x3b"
                ),
                content_type="image/gif",
            ),
            study_type=StudyType.get_ember_frame_player(),
            creator=self.user,
            lab=self.lab,
            name="Max Resp Study",
            short_description="test",
            preview_summary="test",
            purpose="test",
            criteria="test",
            duration="test",
            contact_info="test",
            exit_url="https://mit.edu",
        )
        self.study.admin_group.user_set.add(self.user)
        assign_perm(
            StudyPermission.WRITE_STUDY_DETAILS.prefixed_codename,
            self.user,
            self.study,
        )
        self.client.force_login(self.user)

    def _form_data(self, include_image=True, **overrides):
        """Build minimal valid form data for the StudyEditForm.

        Set include_image=False to avoid triggering the pre_save signal that
        rejects approved/active studies when monitored fields change.
        """
        data = {
            "name": self.study.name,
            "lab": self.study.lab_id,
            "study_type": self.study.study_type_id,
            "min_age_years": 0,
            "min_age_months": 0,
            "min_age_days": 0,
            "max_age_years": 1,
            "max_age_months": 0,
            "max_age_days": 0,
            "priority": 1,
            "preview_summary": self.study.preview_summary,
            "short_description": self.study.short_description,
            "purpose": self.study.purpose,
            "compensation_description": self.study.compensation_description,
            "exit_url": self.study.exit_url,
            "criteria": self.study.criteria,
            "duration": self.study.duration,
            "contact_info": self.study.contact_info,
        }
        if include_image:
            data["image"] = SimpleUploadedFile(
                name="test_image.jpg",
                content=open("exp/tests/static/study_image.png", "rb").read(),
                content_type="image/jpeg",
            )
        data.update(overrides)
        return data

    def _create_eligible_responses(self, count):
        """Create eligible, completed, non-preview responses for the study."""
        participant = G(User, is_active=True)
        child = G(
            Child,
            user=participant,
            given_name="Test child",
            birthday=datetime.date.today() - datetime.timedelta(days=30),
        )
        for _ in range(count):
            r = Response.objects.create(
                study=self.study,
                child=child,
                study_type=self.study.study_type,
                demographic_snapshot=participant.latest_demographics,
                completed=True,
                is_preview=False,
            )
            Response.objects.filter(pk=r.pk).update(
                eligibility=[ResponseEligibility.ELIGIBLE]
            )

    def _get_warning_messages(self, response):
        """Extract warning-level messages from a followed response."""
        from django.contrib.messages import constants

        return [m for m in response.context["messages"] if m.level == constants.WARNING]

    def test_banner_when_max_responses_reached_non_active_study(self, mock_send_mail):
        """Warning banner shown when max_responses is set at/below response count on non-active study."""
        self.assertEqual(self.study.state, "created")
        self._create_eligible_responses(3)
        data = self._form_data(set_response_limit=True, max_responses=3)
        response = self.client.post(
            reverse("exp:study-edit", kwargs={"pk": self.study.id}),
            data,
            follow=True,
        )
        warnings = self._get_warning_messages(response)
        self.assertEqual(len(warnings), 1)
        self.assertIn("reached the response limit", str(warnings[0]))

        # Study should NOT be paused (was not active)
        self.study.refresh_from_db()
        self.assertNotEqual(self.study.state, "paused")

    def test_study_paused_when_max_responses_reached_active_study(self, mock_send_mail):
        """Active study is paused and warning shown when max_responses is set at response count."""
        self.assertEqual(self.study.state, "created")
        self.study.state = "active"
        self.study.save()
        self._create_eligible_responses(3)
        # include_image=False to avoid triggering the pre_save signal that
        # rejects active studies when monitored fields (like image) change.
        data = self._form_data(
            include_image=False, set_response_limit=True, max_responses=3
        )
        response = self.client.post(
            reverse("exp:study-edit", kwargs={"pk": self.study.id}),
            data,
            follow=True,
        )
        warnings = self._get_warning_messages(response)
        self.assertEqual(len(warnings), 1)
        self.assertIn("automatically paused", str(warnings[0]))

        self.study.refresh_from_db()
        self.assertEqual(self.study.state, "paused")

    def test_no_banner_when_max_responses_not_reached(self, mock_send_mail):
        """No warning when max_responses is set above the current response count."""
        self._create_eligible_responses(2)
        data = self._form_data(set_response_limit=True, max_responses=10)
        response = self.client.post(
            reverse("exp:study-edit", kwargs={"pk": self.study.id}),
            data,
            follow=True,
        )
        warnings = self._get_warning_messages(response)
        self.assertEqual(len(warnings), 0)
        self.assertNotEqual(self.study.state, "paused")

    def test_no_banner_when_max_responses_unchanged(self, mock_send_mail):
        """No warning when max_responses is submitted but hasn't changed."""
        self.study.max_responses = 5
        self.study.save()
        self._create_eligible_responses(5)
        data = self._form_data(set_response_limit=True, max_responses=5)
        response = self.client.post(
            reverse("exp:study-edit", kwargs={"pk": self.study.id}),
            data,
            follow=True,
        )
        warnings = self._get_warning_messages(response)
        self.assertEqual(len(warnings), 0)

    def test_banner_when_max_responses_lowered_below_count(self, mock_send_mail):
        """Warning shown when max_responses is lowered below existing response count."""
        self.assertEqual(self.study.state, "created")
        self.study.max_responses = 10
        self.study.save()
        self._create_eligible_responses(5)
        data = self._form_data(set_response_limit=True, max_responses=3)
        response = self.client.post(
            reverse("exp:study-edit", kwargs={"pk": self.study.id}),
            data,
            follow=True,
        )
        warnings = self._get_warning_messages(response)
        self.assertEqual(len(warnings), 1)
        self.assertIn("reached the response limit", str(warnings[0]))
        self.assertEqual(self.study.state, "created")
