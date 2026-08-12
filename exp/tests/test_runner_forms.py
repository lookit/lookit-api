import json
from datetime import timedelta
from http import HTTPStatus
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from studies.forms import EFPForm, ExternalForm, JSPsychForm, ScheduledChoice
from studies.helpers import (
    EFP_LATEST_VERSION_NOT_ON_GITHUB,
    EFP_LATEST_VERSION_UNRESOLVABLE,
    EFP_MINIMUM_COMMIT_DATE,
    EFP_VERSION_UNVERIFIABLE,
)
from studies.models import default_study_structure

DEFAULT_REPO = "https://github.com/lookit/ember-lookit-frameplayer"
DEFAULT_BRANCH = "master"
CUSTOM_REPO = "https://github.com/someone/my-fork"
NON_GITHUB_REPO = "https://gitlab.com/someone/my-fork"

# Derived from the cutoff so these stay valid whenever the cutoff moves.
DEPRECATED_COMMIT_DATE = EFP_MINIMUM_COMMIT_DATE - timedelta(days=1)
SUPPORTED_COMMIT_DATE = EFP_MINIMUM_COMMIT_DATE + timedelta(days=1)

DEPRECATED_SHA = "0" * 40
SUPPORTED_SHA = "1" * 40
HEAD_SHA = "2" * 40


class EFPFormTestCase(TestCase):
    def setUp(self):
        self.sha = "testsha"
        self.repo_url = "https://testrepo.com"
        self.data_structure = {
            "last_known_player_sha": self.sha,
            "player_repo_url": self.repo_url,
            "use_generator": False,
            "structure": json.dumps(default_study_structure()),
        }
        self.data_generator = {
            "last_known_player_sha": self.sha,
            "player_repo_url": self.repo_url,
            "use_generator": True,
        }
        self.data_bad_structure = {
            "last_known_player_sha": self.sha,
            "player_repo_url": self.repo_url,
            "structure": "{this is not valid json}",
        }

    def mock_get_side_effect(self, fail_commit=False, fail_repo=False):
        def side_effect(url, *args, **kwargs):
            if url == self.repo_url:
                if fail_repo:
                    return Mock(ok=False, status_code=404)
                else:
                    return Mock(ok=True, status_code=200)
            if url == f"{self.repo_url}/commit/{self.sha}":
                if fail_commit:
                    return Mock(ok=False, status_code=404)
                else:
                    return Mock(ok=True, status_code=200)
            return Mock(ok=False, status_code=404)

        return side_effect

    @patch("studies.forms.requests.get")
    def test_successful_structure(self, mock_get):
        mock_get.side_effect = self.mock_get_side_effect()

        form = EFPForm(data=self.data_structure)
        self.assertDictEqual(form.errors, {})
        self.assertTrue(form.is_valid())

    @patch("studies.forms.requests.get")
    def test_successful_generator(self, mock_get):
        mock_get.side_effect = self.mock_get_side_effect()

        form = EFPForm(data=self.data_generator)
        self.assertDictEqual(form.errors, {})
        self.assertTrue(form.is_valid())

    @patch("studies.forms.requests.get")
    def test_failed_structure(self, mock_get):
        mock_get.side_effect = self.mock_get_side_effect()

        form = EFPForm(data=self.data_bad_structure)
        self.assertDictEqual(
            form.errors,
            {
                "structure": [
                    "Saving protocol configuration failed due to invalid JSON! Please use valid JSON and save again. If you reload this page, all changes will be lost."
                ]
            },
        )
        self.assertFalse(form.is_valid())

    @patch("studies.forms.requests.get")
    def test_failed_player_repo_url(self, mock_get):
        mock_get.side_effect = self.mock_get_side_effect(fail_repo=True)

        form = EFPForm(data=self.data_structure)
        self.assertDictEqual(
            form.errors,
            {
                "player_repo_url": [
                    f"Frameplayer repo url {self.data_structure['player_repo_url']} does not work."
                ]
            },
        )
        self.assertFalse(form.is_valid())

    @patch("studies.forms.requests.get")
    def test_failed_last_known_player_sha(self, mock_get):
        mock_get.side_effect = self.mock_get_side_effect(fail_commit=True)

        form = EFPForm(data=self.data_structure)
        self.assertDictEqual(
            form.errors,
            {
                "last_known_player_sha": [
                    f"Frameplayer commit {self.data_structure['last_known_player_sha']} does not exist."
                ]
            },
        )
        self.assertFalse(form.is_valid())


@override_settings(
    EMBER_EXP_PLAYER_REPO=DEFAULT_REPO, EMBER_EXP_PLAYER_BRANCH=DEFAULT_BRANCH
)
class EFPFormRunnerVersionTestCase(TestCase):
    """Version deprecation and blank-means-latest handling in EFPForm."""

    def form_data(self, sha, repo_url=DEFAULT_REPO):
        return {
            "last_known_player_sha": sha,
            "player_repo_url": repo_url,
            "use_generator": False,
            "structure": json.dumps(default_study_structure()),
        }

    def mock_get_side_effect(
        self,
        commit_date=SUPPORTED_COMMIT_DATE,
        commit_status=HTTPStatus.OK,
        head_status=HTTPStatus.OK,
        repo_status=HTTPStatus.OK,
    ):
        """URL-keyed stand-in for requests.get, covering every call the form makes.

        Note that studies.forms and studies.helpers share the one requests module, so
        patching studies.forms.requests.get covers the helpers' API calls too.
        """

        def side_effect(url, *args, **kwargs):
            if "/git/refs/heads/" in url:
                return Mock(
                    ok=head_status == HTTPStatus.OK,
                    status_code=head_status,
                    json=Mock(return_value={"object": {"sha": HEAD_SHA}}),
                )
            if url.startswith("https://api.github.com/"):
                return Mock(
                    ok=commit_status == HTTPStatus.OK,
                    status_code=commit_status,
                    json=Mock(
                        return_value={
                            "commit": {"committer": {"date": commit_date.isoformat()}}
                        }
                    ),
                )
            # Whatever's left is the form probing the repo URL, or a custom repo's
            # <url>/commit/<sha> existence check.
            return Mock(ok=repo_status == HTTPStatus.OK, status_code=repo_status)

        return side_effect

    @patch("studies.forms.requests.get")
    def test_supported_version_saves(self, mock_get):
        mock_get.side_effect = self.mock_get_side_effect()

        form = EFPForm(data=self.form_data(SUPPORTED_SHA))

        self.assertDictEqual(form.errors, {})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["last_known_player_sha"], SUPPORTED_SHA)

    @patch("studies.forms.requests.get")
    def test_deprecated_version_is_rejected(self, mock_get):
        mock_get.side_effect = self.mock_get_side_effect(
            commit_date=DEPRECATED_COMMIT_DATE
        )

        form = EFPForm(data=self.form_data(DEPRECATED_SHA))

        self.assertIn("no longer supported", form.errors["last_known_player_sha"][0])
        self.assertFalse(form.is_valid())

    @patch("studies.forms.requests.get")
    def test_unknown_commit_is_rejected(self, mock_get):
        mock_get.side_effect = self.mock_get_side_effect(
            commit_status=HTTPStatus.NOT_FOUND
        )

        form = EFPForm(data=self.form_data(SUPPORTED_SHA))

        self.assertEqual(
            form.errors["last_known_player_sha"],
            [f"Frameplayer commit {SUPPORTED_SHA} does not exist."],
        )
        self.assertFalse(form.is_valid())

    @patch("studies.forms.requests.get")
    def test_unverifiable_version_fails_closed(self, mock_get):
        """A rate-limited or unreachable GitHub blocks the save rather than waving it through."""
        mock_get.side_effect = self.mock_get_side_effect(
            commit_status=HTTPStatus.FORBIDDEN
        )

        form = EFPForm(data=self.form_data(SUPPORTED_SHA))

        self.assertEqual(
            form.errors["last_known_player_sha"], [EFP_VERSION_UNVERIFIABLE]
        )
        self.assertFalse(form.is_valid())

    @patch("studies.forms.requests.get")
    def test_custom_repo_keeps_its_old_version(self, mock_get):
        """Forks are exempt from the cutoff, and are checked without the GitHub API."""
        mock_get.side_effect = self.mock_get_side_effect(
            commit_date=DEPRECATED_COMMIT_DATE
        )

        form = EFPForm(data=self.form_data(DEPRECATED_SHA, repo_url=CUSTOM_REPO))

        self.assertDictEqual(form.errors, {})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["last_known_player_sha"], DEPRECATED_SHA)
        for call in mock_get.call_args_list:
            self.assertNotIn("api.github.com", call.args[0])

    @patch("studies.forms.requests.get")
    def test_custom_repo_commit_must_still_exist(self, mock_get):
        mock_get.side_effect = self.mock_get_side_effect(
            repo_status=HTTPStatus.NOT_FOUND
        )

        form = EFPForm(data=self.form_data(DEPRECATED_SHA, repo_url=CUSTOM_REPO))

        # The repo URL check fails first here, which short-circuits the SHA check.
        self.assertIn("player_repo_url", form.errors)
        self.assertFalse(form.is_valid())

    @patch("studies.forms.requests.get")
    def test_blank_sha_pins_to_branch_head(self, mock_get):
        """Blank means "use the latest", and the resolved SHA is stored, not the blank."""
        mock_get.side_effect = self.mock_get_side_effect()

        form = EFPForm(data=self.form_data(""))

        self.assertDictEqual(form.errors, {})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["last_known_player_sha"], HEAD_SHA)

    @patch("studies.forms.requests.get")
    def test_blank_sha_does_not_date_check_the_head_commit(self, mock_get):
        """Whatever HEAD is today is current by definition, so no commits API call."""
        mock_get.side_effect = self.mock_get_side_effect()

        form = EFPForm(data=self.form_data(""))

        self.assertDictEqual(form.errors, {})
        self.assertTrue(form.is_valid())
        for call in mock_get.call_args_list:
            self.assertNotIn("/commits/", call.args[0])

    @patch("studies.forms.requests.get")
    def test_blank_sha_fails_closed_when_head_cannot_be_resolved(self, mock_get):
        mock_get.side_effect = self.mock_get_side_effect(
            head_status=HTTPStatus.FORBIDDEN
        )

        form = EFPForm(data=self.form_data(""))

        self.assertEqual(
            form.errors["last_known_player_sha"], [EFP_LATEST_VERSION_UNRESOLVABLE]
        )
        self.assertFalse(form.is_valid())

    @patch("studies.forms.requests.get")
    def test_blank_sha_on_a_non_github_repo_asks_for_an_explicit_sha(self, mock_get):
        """There's no portable way to ask a non-GitHub host what a branch points at."""
        mock_get.side_effect = self.mock_get_side_effect()

        form = EFPForm(data=self.form_data("", repo_url=NON_GITHUB_REPO))

        self.assertEqual(
            form.errors["last_known_player_sha"], [EFP_LATEST_VERSION_NOT_ON_GITHUB]
        )
        self.assertFalse(form.is_valid())

    @patch("studies.forms.requests.get")
    def test_bad_repo_url_does_not_also_report_a_sha_error(self, mock_get):
        """clean_last_known_player_sha bails when the URL it depends on didn't clean.

        Otherwise a single typo in the URL field produces a second, misleading error
        against the SHA field.
        """
        mock_get.side_effect = self.mock_get_side_effect(
            repo_status=HTTPStatus.NOT_FOUND
        )

        form = EFPForm(data=self.form_data(SUPPORTED_SHA))

        self.assertIn("player_repo_url", form.errors)
        self.assertNotIn("last_known_player_sha", form.errors)
        self.assertFalse(form.is_valid())


class ExternalFormTestCase(TestCase):
    def test_successful(self):
        form = ExternalForm(
            data={
                "scheduled": ScheduledChoice.scheduled.value,
                "url": "https://google.com",
            }
        )
        self.assertDictEqual(form.errors, {})
        self.assertTrue(form.is_valid())


class JsPsychFormTestCase(TestCase):
    def setUp(self):
        """Set up test data with JSPsychPlugin instances."""
        from studies.models import JSPsychPlugin

        # Create plugins in different categories
        self.jspsych_plugin = JSPsychPlugin.objects.create(
            name="HTML Button Response",
            url="https://unpkg.com/@jspsych/plugin-html-button-response@2.0.0",
            integrity="sha384-test1",
            category="jspsych",
            autoload=False,
        )
        self.jspsych_contrib_plugin = JSPsychPlugin.objects.create(
            name="Image Hotspots",
            url="https://unpkg.com/@jspsych-contrib/plugin-image-hotspots@1.1.0",
            integrity="sha384-test2",
            category="jspsych-contrib",
            autoload=False,
        )
        self.autoload_plugin = JSPsychPlugin.objects.create(
            name="Fullscreen",
            url="https://unpkg.com/@jspsych/plugin-fullscreen@1.0.0",
            integrity="sha384-test3",
            category="jspsych",
            autoload=True,
        )
        self.chs_plugin = JSPsychPlugin.objects.create(
            name="CHS Templates",
            url="https://unpkg.com/@lookit/templates@3.2.0",
            integrity="sha384-test4",
            category="chs-jspsych",
            autoload=False,
        )

    def test_successful(self):
        """Test basic form validation with just experiment code."""
        form = JSPsychForm(
            data={
                "experiment": "function thisIsValidJavaScript(){}",
            }
        )
        self.assertDictEqual(form.errors, {})
        self.assertTrue(form.is_valid())

    def test_jspsych_plugins_core_excludes_autoload(self):
        """Test that jspsych_plugins_core field excludes autoload=True plugins."""

        form = JSPsychForm()
        core_queryset = form.fields["jspsych_plugins_core"].queryset
        core_plugins = list(core_queryset)

        # Should include the non-autoload jspsych plugin
        self.assertIn(self.jspsych_plugin, core_plugins)
        # Should NOT include the autoload jspsych plugin
        self.assertNotIn(self.autoload_plugin, core_plugins)

    def test_jspsych_plugins_contrib_excludes_autoload(self):
        """Test that jspsych_plugins_contrib field excludes autoload=True plugins."""
        form = JSPsychForm()
        contrib_queryset = form.fields["jspsych_plugins_contrib"].queryset
        contrib_plugins = list(contrib_queryset)

        # Should include the non-autoload contrib plugin
        self.assertIn(self.jspsych_contrib_plugin, contrib_plugins)
        # Should NOT include the autoload jspsych plugin
        self.assertNotIn(self.autoload_plugin, contrib_plugins)

    def test_form_initialization_with_study_instance(self):
        """Test that form correctly initializes with existing study plugins."""
        from studies.models import Study, StudyType

        study = Study.objects.create(
            name="Test Study",
            study_type=StudyType.get_jspsych(),
        )
        # Add plugins to the study
        study.jspsych_plugins.set([self.jspsych_plugin, self.jspsych_contrib_plugin])

        form = JSPsychForm(instance=study)

        # Check that initial values are set correctly
        self.assertIn(self.jspsych_plugin, form.initial["jspsych_plugins_core"])
        self.assertIn(
            self.jspsych_contrib_plugin, form.initial["jspsych_plugins_contrib"]
        )

    def test_form_save_combines_split_fields(self):
        """Test that form.save() correctly combines split plugin fields."""
        from studies.models import Study, StudyType

        study = Study.objects.create(
            name="Test Study",
            study_type=StudyType.get_jspsych(),
        )

        form = JSPsychForm(
            data={
                "experiment": "function thisIsValidJavaScript(){}",
                "jspsych_plugins_core": [self.jspsych_plugin.id],
                "jspsych_plugins_contrib": [self.jspsych_contrib_plugin.id],
                "jspsych_plugins_chs": [],
            },
            instance=study,
        )

        self.assertTrue(form.is_valid())
        form.save()

        # Refresh from DB to ensure changes were saved
        study.refresh_from_db()
        plugins = list(study.jspsych_plugins.all())

        # Should have both plugins
        self.assertIn(self.jspsych_plugin, plugins)
        self.assertIn(self.jspsych_contrib_plugin, plugins)
        self.assertEqual(len(plugins), 2)

    def test_form_save_overwrites_previous_plugins(self):
        """Test that form.save() correctly overwrites previously selected plugins."""
        from studies.models import Study, StudyType

        study = Study.objects.create(
            name="Test Study",
            study_type=StudyType.get_jspsych(),
        )
        # Initially set one plugin
        study.jspsych_plugins.set([self.jspsych_plugin])

        # Submit form with different plugins
        form = JSPsychForm(
            data={
                "experiment": "function thisIsValidJavaScript(){}",
                "jspsych_plugins_core": [],
                "jspsych_plugins_contrib": [self.jspsych_contrib_plugin.id],
                "jspsych_plugins_chs": [],
            },
            instance=study,
        )

        self.assertTrue(form.is_valid())
        form.save()

        study.refresh_from_db()
        plugins = list(study.jspsych_plugins.all())

        # Should only have the contrib plugin now
        self.assertNotIn(self.jspsych_plugin, plugins)
        self.assertIn(self.jspsych_contrib_plugin, plugins)
        self.assertEqual(len(plugins), 1)

    def test_form_with_no_plugins_selected(self):
        """Test that form can be saved with no plugins selected."""
        from studies.models import Study, StudyType

        study = Study.objects.create(
            name="Test Study",
            study_type=StudyType.get_jspsych(),
        )

        form = JSPsychForm(
            data={
                "experiment": "function thisIsValidJavaScript(){}",
                "jspsych_plugins_core": [],
                "jspsych_plugins_contrib": [],
                "jspsych_plugins_chs": [],
            },
            instance=study,
        )

        self.assertTrue(form.is_valid())
        form.save()

        study.refresh_from_db()
        self.assertEqual(study.jspsych_plugins.count(), 0)

    def test_form_multiple_plugins_per_category(self):
        """Test form with multiple plugins in same category."""
        from studies.models import JSPsychPlugin, Study, StudyType

        # Create a second jspsych plugin
        second_jspsych = JSPsychPlugin.objects.create(
            name="Image Keyboard Response",
            url="https://unpkg.com/@jspsych/plugin-image-keyboard-response@2.0.0",
            integrity="sha384-test5",
            category="jspsych",
            autoload=False,
        )

        study = Study.objects.create(
            name="Test Study",
            study_type=StudyType.get_jspsych(),
        )

        form = JSPsychForm(
            data={
                "experiment": "function thisIsValidJavaScript(){}",
                "jspsych_plugins_core": [
                    self.jspsych_plugin.id,
                    second_jspsych.id,
                ],
                "jspsych_plugins_contrib": [self.jspsych_contrib_plugin.id],
                "jspsych_plugins_chs": [],
            },
            instance=study,
        )

        self.assertTrue(form.is_valid())
        form.save()

        study.refresh_from_db()
        plugins = list(study.jspsych_plugins.all())

        self.assertIn(self.jspsych_plugin, plugins)
        self.assertIn(second_jspsych, plugins)
        self.assertIn(self.jspsych_contrib_plugin, plugins)
        self.assertEqual(len(plugins), 3)
