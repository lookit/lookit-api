import datetime
from unittest import skip
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms.models import model_to_dict
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm

from accounts.models import Child, User
from studies.models import Lab, Study, StudyType
from studies.permissions import LabPermission, StudyPermission


# Run celery tasks right away, but don't catch errors from them. The relevant tasks for
# this case involve S3/GCP access which we're not testing.
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
@override_settings(CELERY_TASK_EAGER_PROPAGATES=True)
class ResponseViewsTestCase(TestCase):
    def setUp(self):
        self.client = Client()

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
            User, is_active=True, is_researcher=True, given_name="Researcher 4"
        )
        self.participant = G(User, is_active=True, is_researcher=False, nickname="Dada")
        self.study_type = G(StudyType, name="default", id=1)
        self.other_study_type = G(StudyType, name="other", id=2)
        self.approved_lab = G(Lab, name="MIT", approved_to_test=True)
        self.unapproved_lab = G(Lab, name="Harvard", approved_to_test=True)

        self.study = G(
            Study,
            image=SimpleUploadedFile(
                "fake_image.png", b"fake-stuff", content_type="image/png"
            ),  # we could also pass fill_nullable_fields=True
            # See: https://django-dynamic-fixture.readthedocs.io/en/latest/data.html#fill-nullable-fields
            creator=self.study_admin,
            shared_preview=False,
            study_type=self.study_type,
            name="Test Study",
            lab=self.approved_lab,
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

    def testCanSeeStudyPreviewDetailAsOtherResearcherIfShared(self):
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
    def testCanSeeStudyPreviewProxyAsOtherResearcherIfShared(self):
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

    def testCannotSeeStudyPreviewDetailAsParticipant(self):
        self.client.force_login(self.participant)
        url = reverse(
            "exp:preview-detail", kwargs={"uuid": self.study_shared_preview.uuid}
        )
        page = self.client.get(url)
        self.assertEqual(
            page.status_code, 403, "Study preview is accessible by participant: " + url
        )

    def testCannotSeeStudyPreviewDetailAsOtherResearcherIfNotShared(self):
        self.client.force_login(self.other_researcher)
        url = reverse("exp:preview-detail", kwargs={"uuid": self.study.uuid})
        page = self.client.get(url)
        self.assertEqual(
            page.status_code,
            403,
            "Study preview is not shared but unassociated researcher can access: "
            + url,
        )

    def testGetStudyBuildView(self):
        self.client.force_login(self.study_designer)
        page = self.client.get(self.study_build_url)
        self.assertIn(
            page.status_code, [403, 405], "GET method allowed on study build view"
        )

    def testBuildStudyOutsideLab(self):
        self.client.force_login(self.other_researcher)
        page = self.client.post(self.study_build_url, {})
        self.assertEqual(
            page.status_code, 403, "Study build allowed from outside researcher"
        )

    def testBuildStudyAlreadyBuilt(self):
        self.client.force_login(self.study_designer)
        self.study.built = True
        self.study.save()
        page = self.client.post(self.study_build_url, {})
        self.assertEqual(
            page.status_code, 403, "Study build allowed when already built"
        )

    def testBuildStudyCurrentlyBuilding(self):
        self.client.force_login(self.study_designer)
        self.study.is_building = True
        self.study.save()
        page = self.client.post(self.study_build_url, {})
        self.assertEqual(
            page.status_code, 403, "Study build allowed when already building"
        )

    def testBuildStudyInLabWithoutCorrectPerms(self):
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
    def testBuildStudyWithCorrectPermsAndCurrentExpRunner(self):
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
    def testBuildStudyWithCorrectPermsAndSpecificExpRunner(self):
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
    def test_study_edit_change_study_type(self, mock_validate):
        mock_validate.return_value = {"fake": "metadata"}, None
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
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code, 200, "Study edit returns a valid response"
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
# - [postpone checks of POST which will be refactored]
# TODO: StudyPreviewProxyView
# - add checks analogous to preview detail view
# - check for correct redirect
