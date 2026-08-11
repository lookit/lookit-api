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
    def test_successful(self):
        # JavaScript is validated client side
        form = JSPsychForm(
            data={
                "experiment": "function thisIsValidJavaScript(){}",
            }
        )
        self.assertDictEqual(form.errors, {})
        self.assertTrue(form.is_valid())
