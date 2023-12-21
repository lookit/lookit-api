from http import HTTPStatus

from django.test import Client, TestCase
from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm

from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from accounts.models import User
from project import settings
from studies.forms import ScheduledChoice
from studies.models import Lab, Study, StudyType
from studies.permissions import StudyPermission


class Force2FAClient(Client):
    @property
    def session(self):
        _session = super().session
        _session[TWO_FACTOR_AUTH_SESSION_KEY] = True
        return _session


class RunnerDetailsViewsTestCase(TestCase):
    def setUp(self):
        self.client = Force2FAClient()
        self.efp_study_details = "exp:efp-study-details"
        self.study_details = "exp:study-details"

    def test_external_details_view(self):
        user = G(User, is_active=True, is_researcher=True)
        lab = G(Lab)
        study = G(Study, creator=user, lab=lab, study_type=2)
        metadata = {
            "url": "https://mit.edu",
            "scheduled": ScheduledChoice.scheduled.value == "Scheduled",
            "scheduling": "",
            "study_platform": "",
            "other_scheduling": "",
            "other_study_platform": "",
        }

        assign_perm(StudyPermission.WRITE_STUDY_DETAILS.codename, user, study)
        assign_perm(StudyPermission.READ_STUDY_DETAILS.codename, user, study)

        self.client.force_login(user)
        response = self.client.post(
            reverse("exp:external-study-details", kwargs={"pk": study.id}),
            {"scheduled": ScheduledChoice.scheduled.value, "url": metadata["url"]},
            follow=True,
        )

        if "form" in response.context:
            self.assertEqual(response.context_data["form"].errors, {})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(Study.objects.get(id=study.id).metadata, metadata)

    def test_efp_details_view(self):
        user = G(User, is_active=True, is_researcher=True)
        lab = G(Lab)
        study = G(Study, creator=user, lab=lab, study_type=1)
        metadata = {
            "player_repo_url": settings.EMBER_EXP_PLAYER_REPO,
            "last_known_player_sha": "862604874f7eeff8c9d72adcb8914b21bfb5427e",
        }

        assign_perm(StudyPermission.WRITE_STUDY_DETAILS.codename, user, study)
        assign_perm(StudyPermission.READ_STUDY_DETAILS.codename, user, study)

        self.client.force_login(user)
        response = self.client.post(
            reverse(self.efp_study_details, kwargs={"pk": study.id}),
            {
                "structure": "{}",
                "player_repo_url": metadata["player_repo_url"],
                "last_known_player_sha": metadata["last_known_player_sha"],
            },
            follow=True,
        )

        if "form" in response.context:
            self.assertEqual(response.context_data["form"].errors, {})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(Study.objects.get(id=study.id).metadata, metadata)

    def test_study_details_redirect_efp(self):
        user = G(User, is_active=True, is_researcher=True)
        lab = G(Lab)
        efp = G(
            Study, creator=user, lab=lab, study_type=StudyType.get_ember_frame_player()
        )

        assign_perm(StudyPermission.WRITE_STUDY_DETAILS.codename, user, efp)
        assign_perm(StudyPermission.READ_STUDY_DETAILS.codename, user, efp)

        self.client.force_login(user)

        response = self.client.get(
            reverse(self.study_details, kwargs={"pk": efp.id}), follow=True
        )
        self.assertEqual(
            response.redirect_chain,
            [
                (
                    reverse(self.efp_study_details, kwargs={"pk": efp.id}),
                    HTTPStatus.FOUND,
                )
            ],
        )

    def test_study_details_redirect_external(self):
        user = G(User, is_active=True, is_researcher=True)
        lab = G(Lab)
        external = G(Study, creator=user, lab=lab, study_type=StudyType.get_external())

        assign_perm(StudyPermission.WRITE_STUDY_DETAILS.codename, user, external)
        assign_perm(StudyPermission.READ_STUDY_DETAILS.codename, user, external)

        self.client.force_login(user)

        response = self.client.get(
            reverse(self.study_details, kwargs={"pk": external.id}), follow=True
        )
        self.assertEqual(
            response.redirect_chain,
            [
                (
                    reverse("exp:external-study-details", kwargs={"pk": external.id}),
                    HTTPStatus.FOUND,
                )
            ],
        )

    def test_study_details_redirect_jspsych(self):
        user = G(User, is_active=True, is_researcher=True)
        lab = G(Lab)
        jspsych = G(Study, creator=user, lab=lab, study_type=StudyType.get_jspsych())

        assign_perm(StudyPermission.WRITE_STUDY_DETAILS.codename, user, jspsych)
        assign_perm(StudyPermission.READ_STUDY_DETAILS.codename, user, jspsych)

        self.client.force_login(user)
        response = self.client.get(
            reverse(self.study_details, kwargs={"pk": jspsych.id}), follow=True
        )
        self.assertEqual(
            response.redirect_chain,
            [
                (
                    reverse("exp:jspsych-study-details", kwargs={"pk": jspsych.id}),
                    HTTPStatus.FOUND,
                )
            ],
        )

    def test_efp_study_set_not_built(self):
        user = G(User, is_active=True, is_researcher=True)
        lab = G(Lab)
        study = G(
            Study, creator=user, lab=lab, study_type=1, built=True, is_building=True
        )

        assign_perm(StudyPermission.WRITE_STUDY_DETAILS.codename, user, study)
        assign_perm(StudyPermission.READ_STUDY_DETAILS.codename, user, study)

        self.assertTrue(study.built)
        self.assertTrue(study.is_building)

        self.client.force_login(user)
        response = self.client.post(
            reverse(self.efp_study_details, kwargs={"pk": study.id}),
            {
                "structure": "{}",
                "last_known_player_sha": "862604874f7eeff8c9d72adcb8914b21bfb5427e",
                "player_repo_url": settings.EMBER_EXP_PLAYER_REPO,
            },
            follow=True,
        )

        if "form" in response.context:
            self.assertEqual(response.context_data["form"].errors, {})
        self.assertEqual(response.status_code, HTTPStatus.OK)

        study = Study.objects.get(id=study.id)

        self.assertFalse(study.built)
        self.assertFalse(study.is_building)
