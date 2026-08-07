from http import HTTPStatus
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm

from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from accounts.models import Child, User
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
        self.efp_study_details = "exp:efp-study-edit-design"
        self.study_edit_design = "exp:study-edit-design"

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
            reverse("exp:external-study-edit-design", kwargs={"pk": study.id}),
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
            reverse(self.study_edit_design, kwargs={"pk": efp.id}), follow=True
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
            reverse(self.study_edit_design, kwargs={"pk": external.id}), follow=True
        )
        self.assertEqual(
            response.redirect_chain,
            [
                (
                    reverse(
                        "exp:external-study-edit-design", kwargs={"pk": external.id}
                    ),
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
            reverse(self.study_edit_design, kwargs={"pk": jspsych.id}), follow=True
        )
        self.assertEqual(
            response.redirect_chain,
            [
                (
                    reverse("exp:jspsych-study-edit-design", kwargs={"pk": jspsych.id}),
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


class JSPsychEditViewTestCase(TestCase):
    def setUp(self):
        """Set up test data."""
        from studies.models import JSPsychPlugin

        self.client = Force2FAClient()
        self.user = G(User, is_active=True, is_researcher=True)
        self.lab = G(Lab)
        self.study = G(
            Study, creator=self.user, lab=self.lab, study_type=StudyType.get_jspsych()
        )

        # Create test plugins
        self.jspsych_library_plugin = JSPsychPlugin.objects.create(
            name="jsPsych Core",
            url="https://unpkg.com/jspsych@8.0.3",
            integrity="sha384-test1",
            category="jspsych-library",
            show_in_ui=True,
        )
        self.hidden_jspsych_library_plugin = JSPsychPlugin.objects.create(
            name="jsPsych CSS",
            url="https://unpkg.com/jspsych@8.0.3/css/jspsych.css",
            integrity="sha384-test2",
            category="jspsych-library",
            file_type="css",
            show_in_ui=False,
        )
        self.chs_plugin = JSPsychPlugin.objects.create(
            name="CHS Templates",
            url="https://unpkg.com/@lookit/templates@3.2.0",
            integrity="sha384-test3",
            category="chs-jspsych",
            show_in_ui=True,
        )
        self.hidden_chs_plugin = JSPsychPlugin.objects.create(
            name="CHS Init jsPsych",
            url="https://unpkg.com/@lookit/lookit-initjspsych@3.2.0",
            integrity="sha384-test4",
            category="chs-jspsych",
            show_in_ui=False,
        )
        self.autoload_plugin = JSPsychPlugin.objects.create(
            name="Fullscreen",
            url="https://unpkg.com/@jspsych/plugin-fullscreen@1.0.0",
            integrity="sha384-test5",
            category="jspsych",
            autoload=True,
        )

        assign_perm(StudyPermission.WRITE_STUDY_DETAILS.codename, self.user, self.study)
        assign_perm(StudyPermission.READ_STUDY_DETAILS.codename, self.user, self.study)

    def test_jspsych_edit_view_context_contains_library_plugins(self):
        """Test that context includes jspsych_library_plugins."""
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("exp:jspsych-study-edit-design", kwargs={"pk": self.study.id})
        )

        self.assertIn("jspsych_library_plugins", response.context)
        library_plugins = list(response.context["jspsych_library_plugins"])

        # Should include visible plugin
        self.assertIn(self.jspsych_library_plugin, library_plugins)
        # Should NOT include hidden plugin
        self.assertNotIn(self.hidden_jspsych_library_plugin, library_plugins)

    def test_jspsych_edit_view_context_contains_chs_plugins(self):
        """Test that context includes chs_plugins."""
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("exp:jspsych-study-edit-design", kwargs={"pk": self.study.id})
        )

        self.assertIn("chs_plugins", response.context)
        chs_plugins = list(response.context["chs_plugins"])

        # Should include visible plugin
        self.assertIn(self.chs_plugin, chs_plugins)
        # Should NOT include hidden plugin
        self.assertNotIn(self.hidden_chs_plugin, chs_plugins)

    def test_jspsych_edit_view_context_contains_autoload_plugins(self):
        """Test that context includes autoload_plugins."""
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("exp:jspsych-study-edit-design", kwargs={"pk": self.study.id})
        )

        self.assertIn("autoload_plugins", response.context)
        autoload_plugins = list(response.context["autoload_plugins"])

        # Should include the autoload plugin
        self.assertIn(self.autoload_plugin, autoload_plugins)

    def test_jspsych_edit_view_autoload_plugins_excludes_library_and_chs(self):
        """Test that autoload_plugins excludes jspsych-library and chs-jspsych categories."""
        from studies.models import JSPsychPlugin

        # Create an autoload plugin in jspsych-library category (should be excluded)
        autoload_library = JSPsychPlugin.objects.create(
            name="AutoLoad Library",
            url="https://unpkg.com/test-lib@1.0.0",
            integrity="sha384-test6",
            category="jspsych-library",
            autoload=True,
            show_in_ui=True,
        )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("exp:jspsych-study-edit-design", kwargs={"pk": self.study.id})
        )

        autoload_plugins = list(response.context["autoload_plugins"])

        # Should include jspsych autoload plugin
        self.assertIn(self.autoload_plugin, autoload_plugins)
        # Should NOT include jspsych-library autoload plugin
        self.assertNotIn(autoload_library, autoload_plugins)


class JsPsychPreviewViewTestCase(TestCase):
    def setUp(self):
        """Set up test data for preview view."""
        from studies.models import JSPsychPlugin

        self.client = Force2FAClient()
        self.user = G(User, is_active=True, is_researcher=True)
        self.lab = G(Lab)
        self.study = G(
            Study, creator=self.user, lab=self.lab, study_type=StudyType.get_jspsych()
        )
        self.child = G(Child, user=self.user)

        # Create test plugins
        self.jspsych_library_plugin = JSPsychPlugin.objects.create(
            name="jsPsych Core",
            url="https://unpkg.com/jspsych@8.0.3",
            integrity="sha384-test1",
            category="jspsych-library",
            autoload=True,
        )
        self.chs_plugin = JSPsychPlugin.objects.create(
            name="CHS Templates",
            url="https://unpkg.com/@lookit/templates@3.2.0",
            integrity="sha384-test3",
            category="chs-jspsych",
            autoload=True,
        )
        self.autoload_plugin = JSPsychPlugin.objects.create(
            name="Fullscreen",
            url="https://unpkg.com/@jspsych/plugin-fullscreen@1.0.0",
            integrity="sha384-test5",
            category="jspsych",
            autoload=True,
        )

        assign_perm(StudyPermission.READ_STUDY_DETAILS.codename, self.user, self.study)

    @patch("exp.views.study.get_jspsych_aws_values")
    def test_jspsych_preview_context_contains_library_plugins(self, mock_aws):
        """Test that preview context includes jspsych_library plugins."""
        mock_aws.return_value = {
            "accessKeyId": "test-key",
            "secretAccessKey": "test-secret",
            "sessionToken": "test-token",
            "expiration": "2099-12-31T23:59:59Z",
        }
        self.client.force_login(self.user)
        response = self.client.get(
            reverse(
                "exp:preview-jspsych",
                kwargs={"uuid": self.study.uuid, "child_id": self.child.uuid},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("jspsych_library", response.context)
        library_plugins = list(response.context["jspsych_library"])

        # Should include library plugin (no show_in_ui filter for preview view)
        self.assertIn(self.jspsych_library_plugin, library_plugins)

    @patch("exp.views.study.get_jspsych_aws_values")
    def test_jspsych_preview_context_contains_chs_plugins(self, mock_aws):
        """Test that preview context includes chs_plugins."""
        mock_aws.return_value = {
            "accessKeyId": "test-key",
            "secretAccessKey": "test-secret",
            "sessionToken": "test-token",
            "expiration": "2099-12-31T23:59:59Z",
        }
        self.client.force_login(self.user)
        response = self.client.get(
            reverse(
                "exp:preview-jspsych",
                kwargs={"uuid": self.study.uuid, "child_id": self.child.uuid},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("chs_plugins", response.context)
        chs_plugins = list(response.context["chs_plugins"])

        # Should include CHS plugin (no show_in_ui filter for preview view)
        self.assertIn(self.chs_plugin, chs_plugins)

    @patch("exp.views.study.get_jspsych_aws_values")
    def test_jspsych_preview_context_contains_autoload_plugins(self, mock_aws):
        """Test that preview context includes autoload_plugins."""
        mock_aws.return_value = {
            "accessKeyId": "test-key",
            "secretAccessKey": "test-secret",
            "sessionToken": "test-token",
            "expiration": "2099-12-31T23:59:59Z",
        }
        self.client.force_login(self.user)
        response = self.client.get(
            reverse(
                "exp:preview-jspsych",
                kwargs={"uuid": self.study.uuid, "child_id": self.child.uuid},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("autoload_plugins", response.context)
        autoload_plugins = list(response.context["autoload_plugins"])

        # Should include the autoload plugin
        self.assertIn(self.autoload_plugin, autoload_plugins)
