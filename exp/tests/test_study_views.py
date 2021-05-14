import datetime
import json
from unittest import skip
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms.models import model_to_dict
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm, get_objects_for_user

from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from accounts.models import Child, User
from studies.models import Lab, Study, StudyType
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
        self.study_type = G(StudyType, name="default", id=1)
        self.other_study_type = G(StudyType, name="other", id=2)
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
            # See: https://django-dynamic-fixture.readthedocs.io/en/latest/data.html#fill-nullable-fields
            creator=self.study_admin,
            shared_preview=False,
            study_type=self.study_type,
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
            exit_url="https://lookit.mit.edu/studies/history",
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
            study_type=self.study_type,
            name="Test Study",
            lab=self.approved_lab,
            built=True,
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
            reverse("exp:study-detail", kwargs={"pk": self.study.pk}),
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

    def test_study_edit_displays_generator(self):
        self.client.force_login(self.lab_researcher)
        url = reverse("exp:study-edit", kwargs={"pk": self.study.id})
        assign_perm(
            StudyPermission.WRITE_STUDY_DETAILS.prefixed_codename,
            self.lab_researcher,
            self.study,
        )
        response = self.client.get(url)
        content = response.content.decode("utf-8")
        self.assertEqual(
            response.status_code, 200, "Study edit view returns invalid response",
        )
        self.assertIn(
            self.generator_function_string,
            content,
            "Generator function not rendered in editor on study edit page",
        )
        self.assertIn(
            self.structure_string,
            content,
            "Exact text representation of structure not displayed on study edit page",
        )
        self.assertNotIn(
            "frame-a",
            content,
            "internal structure displayed on study edit page instead of just exact text",
        )

    @patch("exp.views.mixins.StudyTypeMixin.validate_and_fetch_metadata")
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
            updated_study.study_type, self.other_study_type, "Study type not updated",
        )
        self.assertFalse(
            updated_study.built,
            "Study build was not invalidated after editing study type",
        )

    @patch("exp.views.mixins.StudyTypeMixin.validate_and_fetch_metadata")
    def test_change_study_metadata_invalidates_build(
        self, mock_validate_and_fetch_metadata
    ):
        new_metadata = {
            "player_repo_url": "https://github.com/lookit/ember-lookit-frameplayer",
            "last_known_player_sha": "2aa08ee6132cd6351eed58abc2253368c14ad184",
        }
        mock_validate_and_fetch_metadata.return_value = new_metadata, []
        self.client.force_login(self.lab_researcher)
        url = reverse("exp:study-edit", kwargs={"pk": self.study.id})
        assign_perm(
            StudyPermission.WRITE_STUDY_DETAILS.prefixed_codename,
            self.lab_researcher,
            self.study,
        )
        data = model_to_dict(self.study)
        data["metadata"] = new_metadata
        data["comments"] = "Changed experiment runner version"
        data["structure"] = json.dumps(data["structure"])
        response = self.client.post(url, data, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            "Study edit returns invalid response when editing metadata",
        )
        self.assertEqual(
            response.redirect_chain,
            [(reverse("exp:study-edit", kwargs={"pk": self.study.pk}), 302)],
        )
        updated_study = Study.objects.get(id=self.study.id)
        self.assertFalse(
            updated_study.built,
            "Study build was not invalidated after editing metadata",
        )

    @patch("exp.views.mixins.StudyTypeMixin.validate_and_fetch_metadata")
    def test_change_study_protocol_does_not_affect_build_status(
        self, mock_validate_and_fetch_metadata
    ):
        mock_validate_and_fetch_metadata.return_value = self.study.metadata, []
        self.client.force_login(self.lab_researcher)
        url = reverse("exp:study-edit", kwargs={"pk": self.study.id})
        assign_perm(
            StudyPermission.WRITE_STUDY_DETAILS.prefixed_codename,
            self.lab_researcher,
            self.study,
        )
        data = model_to_dict(self.study)
        data["structure"] = json.dumps(
            {"frames": {"frame-c": {}}, "sequence": ["frame-c"]}
        )
        data["comments"] = "Changed protocol"
        response = self.client.post(url, data, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            "Study edit returns invalid response when editing metadata",
        )
        self.assertEqual(
            response.redirect_chain,
            [(reverse("exp:study-edit", kwargs={"pk": self.study.pk}), 302)],
        )
        updated_study = Study.objects.get(id=self.study.id)
        self.assertTrue(
            updated_study.built, "Study build was invalidated upon editing protocol"
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
            reverse("exp:study-detail", kwargs={"pk": self.study.pk})
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
            reverse("exp:study-detail", kwargs={"pk": self.study.pk})
        )
        self.assertNotIn(
            "Clone Study",
            detail_view_response.content.decode("utf-8"),
            "Clone Study button displayed on study detail view",
        )


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
# TODO: StudyDetailView
# - check can get as researcher only
# - check correct links are shown given perms
# - [postpone checks of POST which will be refactored]
# TODO: StudyPreviewProxyView
# - add checks analogous to preview detail view
# - check for correct redirect
