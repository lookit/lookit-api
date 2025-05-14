import json
from unittest.mock import Mock, patch

from django.test import TestCase

from studies.forms import EFPForm, ExternalForm, JSPsychForm, ScheduledChoice
from studies.models import default_study_structure


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
