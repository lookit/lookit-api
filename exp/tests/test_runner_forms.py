import json

from django.test import TestCase

from studies.forms import EFPForm, ExternalForm, JSPsychForm, ScheduledChoice
from studies.models import default_study_structure


class EFPFormTestCase(TestCase):
    def test_successful_structure(self):
        form = EFPForm(
            data={
                "last_known_player_sha": "862604874f7eeff8c9d72adcb8914b21bfb5427e",
                "player_repo_url": "https://github.com/lookit/ember-lookit-frameplayer",
                "use_generator": False,
                "structure": json.dumps(default_study_structure()),
            }
        )
        self.assertDictEqual(form.errors, {})
        self.assertTrue(form.is_valid())

    def test_successful_generator(self):
        form = EFPForm(
            data={
                "last_known_player_sha": "862604874f7eeff8c9d72adcb8914b21bfb5427e",
                "player_repo_url": "https://github.com/lookit/ember-lookit-frameplayer",
                "use_generator": True,
            }
        )
        self.assertDictEqual(form.errors, {})
        self.assertTrue(form.is_valid())

    def test_failed_structure(self):
        form = EFPForm(
            data={
                "last_known_player_sha": "862604874f7eeff8c9d72adcb8914b21bfb5427e",
                "player_repo_url": "https://github.com/lookit/ember-lookit-frameplayer",
                "structure": "{this is not valid json}",
            }
        )
        self.assertDictEqual(
            form.errors,
            {
                "structure": [
                    "Saving protocol configuration failed due to invalid JSON! Please use valid JSON and save again. If you reload this page, all changes will be lost."
                ]
            },
        )
        self.assertFalse(form.is_valid())

    def test_failed_player_repo_url(self):
        data = {
            "last_known_player_sha": "862604874f7eeff8c9d72adcb8914b21bfb5427e",
            "structure": json.dumps(default_study_structure()),
        }

        # Check completely invalid url
        data.update(player_repo_url="https://not-a-valid.url")
        form = EFPForm(data=data)
        self.assertDictEqual(
            form.errors,
            {
                "player_repo_url": [
                    f'Frameplayer repo url {data["player_repo_url"]} does not work.'
                ]
            },
        )
        self.assertFalse(form.is_valid())

        # Check slightly off url
        data.update(player_repo_url="https://github.com/lookit/not-a-valid-project")
        form = EFPForm(data=data)
        self.assertDictEqual(
            form.errors,
            {
                "player_repo_url": [
                    f'Frameplayer repo url {data["player_repo_url"]} does not work.'
                ]
            },
        )
        self.assertFalse(form.is_valid())

    def test_failed_last_known_player_sha(self):
        data = {
            "last_known_player_sha": "not a valid sha",
            "player_repo_url": "https://github.com/lookit/ember-lookit-frameplayer",
            "structure": json.dumps(default_study_structure()),
        }
        form = EFPForm(data=data)
        self.assertDictEqual(
            form.errors,
            {
                "last_known_player_sha": [
                    f'Frameplayer commit {data["last_known_player_sha"]} does not exist.'
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
