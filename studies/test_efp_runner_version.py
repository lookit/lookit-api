"""Tests for deprecating old Ember Frame Player experiment runner versions.

Covers the shared helpers in studies/helpers.py and the Study methods that use them.
Form-level tests live in exp/tests/test_runner_forms.py and the build gate is covered
in exp/tests/test_study_views.py.
"""

from datetime import timedelta
from http import HTTPStatus
from unittest.mock import Mock, patch

import requests
from django.test import TestCase, override_settings
from parameterized import parameterized

from studies.helpers import (
    EFP_LATEST_VERSION_NOT_ON_GITHUB,
    EFP_LATEST_VERSION_UNRESOLVABLE,
    EFP_MINIMUM_COMMIT_DATE,
    EFP_VERSION_UNVERIFIABLE,
    efp_runner_version_error,
    get_branch_head_sha,
    get_commit_datetime,
    get_repo_path,
    is_default_player_repo,
)
from studies.models import Lab, Study, StudyType

DEFAULT_REPO = "https://github.com/lookit/ember-lookit-frameplayer"
CUSTOM_REPO = "https://github.com/someone/ember-lookit-frameplayer"
NON_GITHUB_REPO = "https://gitlab.com/someone/ember-lookit-frameplayer"

# Derived from the cutoff so these stay valid whenever the cutoff moves.
DEPRECATED_COMMIT_DATE = EFP_MINIMUM_COMMIT_DATE - timedelta(days=1)
SUPPORTED_COMMIT_DATE = EFP_MINIMUM_COMMIT_DATE + timedelta(days=1)

DEPRECATED_SHA = "0" * 40
SUPPORTED_SHA = "1" * 40
HEAD_SHA = "2" * 40


def mock_commit_response(commit_date):
    """A GitHub commits API response pinning a commit to this committer date."""
    return Mock(
        ok=True,
        status_code=HTTPStatus.OK,
        json=Mock(
            return_value={"commit": {"committer": {"date": commit_date.isoformat()}}}
        ),
    )


@override_settings(EMBER_EXP_PLAYER_REPO=DEFAULT_REPO)
class GetRepoPathTestCase(TestCase):
    @parameterized.expand(
        [
            ("plain", DEFAULT_REPO),
            ("trailing slash", f"{DEFAULT_REPO}/"),
            ("dot git", f"{DEFAULT_REPO}.git"),
            ("www", "https://www.github.com/lookit/ember-lookit-frameplayer"),
            ("http", "http://github.com/lookit/ember-lookit-frameplayer"),
            ("mixed case host", "https://GitHub.com/lookit/ember-lookit-frameplayer"),
            ("surrounding whitespace", f"  {DEFAULT_REPO}  "),
        ]
    )
    def test_extracts_owner_and_repo(self, _name, url):
        """All URL variations that are parameterized above resolve to the same owner and repo"""
        self.assertEqual(get_repo_path(url), "lookit/ember-lookit-frameplayer")

    @parameterized.expand(
        [
            ("non github host", NON_GITHUB_REPO),
            ("no host", "lookit/ember-lookit-frameplayer"),
            ("github with no path", "https://github.com/"),
            ("empty", ""),
            ("none", None),
        ]
    )
    def test_returns_none_when_not_a_github_repo_url(self, _name, url):
        """Returns None rather than raising, so callers can fall back."""
        self.assertIsNone(get_repo_path(url))


@override_settings(EMBER_EXP_PLAYER_REPO=DEFAULT_REPO)
class IsDefaultPlayerRepoTestCase(TestCase):
    @parameterized.expand(
        [
            ("plain", DEFAULT_REPO),
            ("trailing slash", f"{DEFAULT_REPO}/"),
            ("dot git", f"{DEFAULT_REPO}.git"),
            ("dot git and trailing slash", f"{DEFAULT_REPO}.git/"),
            ("www", "https://www.github.com/lookit/ember-lookit-frameplayer"),
            ("http", "http://github.com/lookit/ember-lookit-frameplayer"),
            ("mixed case", "HTTP://www.GitHub.com/lookit/Ember-Lookit-Frameplayer"),
        ]
    )
    def test_recognizes_default_repo(self, _name, url):
        """All URL variations that are parameterized above resolve to the default EFP repository"""
        self.assertTrue(is_default_player_repo(url))

    @parameterized.expand(
        [
            ("different owner of same repo (fork)", CUSTOM_REPO),
            ("same owner, different repo", "https://github.com/lookit/lookit-api"),
            ("same path, different host", NON_GITHUB_REPO),
            ("empty", ""),
            ("none", None),
        ]
    )
    def test_rejects_other_repos(self, _name, url):
        """
        All URL variations that are parameterized above are correctly identified
        as not being the default EFP repository
        """
        self.assertFalse(is_default_player_repo(url))

    @override_settings(EMBER_EXP_PLAYER_REPO=CUSTOM_REPO)
    def test_reads_the_setting_at_call_time(self):
        """The default repo is env-configurable, so it can't be captured at import."""
        self.assertTrue(is_default_player_repo(CUSTOM_REPO))
        self.assertFalse(is_default_player_repo(DEFAULT_REPO))


class GetCommitDatetimeTestCase(TestCase):
    @patch("studies.helpers.requests.get")
    def test_returns_committer_date(self, mock_get):
        mock_get.return_value = mock_commit_response(SUPPORTED_COMMIT_DATE)

        commit_datetime, error = get_commit_datetime(DEFAULT_REPO, SUPPORTED_SHA)

        self.assertEqual(commit_datetime, SUPPORTED_COMMIT_DATE)
        self.assertIsNone(error)

    @patch("studies.helpers.requests.get")
    def test_queries_the_commits_api_for_the_right_repo(self, mock_get):
        mock_get.return_value = mock_commit_response(SUPPORTED_COMMIT_DATE)

        get_commit_datetime(DEFAULT_REPO, SUPPORTED_SHA)

        self.assertEqual(
            mock_get.call_args.args[0],
            f"https://api.github.com/repos/lookit/ember-lookit-frameplayer/commits/{SUPPORTED_SHA}",
        )

    @parameterized.expand([("unknown sha", 404), ("malformed sha", 422)])
    @patch("studies.helpers.requests.get")
    def test_missing_commit_is_the_researchers_to_fix(self, _name, status, mock_get):
        mock_get.return_value = Mock(ok=False, status_code=status)

        commit_datetime, error = get_commit_datetime(DEFAULT_REPO, "nonsense")

        self.assertIsNone(commit_datetime)
        self.assertEqual(error, "Frameplayer commit nonsense does not exist.")

    @patch("studies.helpers.requests.get")
    def test_rate_limited_fails_closed(self, mock_get):
        mock_get.return_value = Mock(ok=False, status_code=403)

        commit_datetime, error = get_commit_datetime(DEFAULT_REPO, SUPPORTED_SHA)

        self.assertIsNone(commit_datetime)
        self.assertEqual(error, EFP_VERSION_UNVERIFIABLE)

    @patch("studies.helpers.requests.get")
    def test_unreachable_github_fails_closed(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError

        commit_datetime, error = get_commit_datetime(DEFAULT_REPO, SUPPORTED_SHA)

        self.assertIsNone(commit_datetime)
        self.assertEqual(error, EFP_VERSION_UNVERIFIABLE)

    @parameterized.expand(
        [
            ("missing keys", {"unexpected": "shape"}),
            ("unparseable date", {"commit": {"committer": {"date": "not a date"}}}),
            ("not a dict", []),
        ]
    )
    @patch("studies.helpers.requests.get")
    def test_unexpected_response_fails_closed(self, _name, payload, mock_get):
        mock_get.return_value = Mock(
            ok=True, status_code=HTTPStatus.OK, json=Mock(return_value=payload)
        )

        commit_datetime, error = get_commit_datetime(DEFAULT_REPO, SUPPORTED_SHA)

        self.assertIsNone(commit_datetime)
        self.assertEqual(error, EFP_VERSION_UNVERIFIABLE)


class GetBranchHeadShaTestCase(TestCase):
    @patch("studies.helpers.requests.get")
    def test_returns_the_sha_the_branch_points_at(self, mock_get):
        mock_get.return_value = Mock(
            ok=True,
            status_code=HTTPStatus.OK,
            json=Mock(return_value={"object": {"sha": HEAD_SHA}}),
        )

        sha, error = get_branch_head_sha(DEFAULT_REPO, "master")

        self.assertEqual(sha, HEAD_SHA)
        self.assertIsNone(error)
        self.assertEqual(
            mock_get.call_args.args[0],
            "https://api.github.com/repos/lookit/ember-lookit-frameplayer/git/refs/heads/master",
        )

    @patch("studies.helpers.requests.get")
    def test_non_github_repo_is_told_to_pin_a_sha(self, mock_get):
        """Retrying can't help here, so the message must not suggest it."""
        sha, error = get_branch_head_sha(NON_GITHUB_REPO, "master")

        self.assertIsNone(sha)
        self.assertEqual(error, EFP_LATEST_VERSION_NOT_ON_GITHUB)
        mock_get.assert_not_called()

    @patch("studies.helpers.requests.get")
    def test_unreachable_github_is_recoverable(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout

        sha, error = get_branch_head_sha(DEFAULT_REPO, "master")

        self.assertIsNone(sha)
        self.assertEqual(error, EFP_LATEST_VERSION_UNRESOLVABLE)

    @patch("studies.helpers.requests.get")
    def test_unknown_branch_is_recoverable(self, mock_get):
        mock_get.return_value = Mock(ok=False, status_code=404)

        sha, error = get_branch_head_sha(DEFAULT_REPO, "no-such-branch")

        self.assertIsNone(sha)
        self.assertEqual(error, EFP_LATEST_VERSION_UNRESOLVABLE)

    @patch("studies.helpers.requests.get")
    def test_unexpected_response_is_recoverable(self, mock_get):
        mock_get.return_value = Mock(
            ok=True,
            status_code=HTTPStatus.OK,
            json=Mock(return_value={"unexpected": "shape"}),
        )

        sha, error = get_branch_head_sha(DEFAULT_REPO, "master")

        self.assertIsNone(sha)
        self.assertEqual(error, EFP_LATEST_VERSION_UNRESOLVABLE)


@override_settings(EMBER_EXP_PLAYER_REPO=DEFAULT_REPO)
class EFPRunnerVersionErrorTestCase(TestCase):
    @patch("studies.helpers.requests.get")
    def test_commit_before_the_cutoff_is_rejected(self, mock_get):
        mock_get.return_value = mock_commit_response(DEPRECATED_COMMIT_DATE)

        error = efp_runner_version_error(DEFAULT_REPO, DEPRECATED_SHA)

        self.assertIsNotNone(error)
        self.assertIn(DEPRECATED_SHA[:7], error)
        self.assertIn(f"{DEPRECATED_COMMIT_DATE:%B %-d, %Y}", error)
        self.assertIn(f"{EFP_MINIMUM_COMMIT_DATE:%B %-d, %Y}", error)

    @patch("studies.helpers.requests.get")
    def test_deprecation_message_offers_clearing_the_field(self, mock_get):
        """The blank-means-latest behavior is the easiest fix, so it has to be advertised.

        This is coupled to EFPForm.clean_last_known_player_sha resolving a blank SHA
        to branch HEAD - if that ever changes, this message needs to change too.
        """
        mock_get.return_value = mock_commit_response(DEPRECATED_COMMIT_DATE)

        error = efp_runner_version_error(DEFAULT_REPO, DEPRECATED_SHA)

        self.assertIn("clear the experiment runner version field", error)

    @patch("studies.helpers.requests.get")
    def test_commit_after_the_cutoff_is_allowed(self, mock_get):
        mock_get.return_value = mock_commit_response(SUPPORTED_COMMIT_DATE)

        self.assertIsNone(efp_runner_version_error(DEFAULT_REPO, SUPPORTED_SHA))

    @patch("studies.helpers.requests.get")
    def test_commit_exactly_on_the_cutoff_is_allowed(self, mock_get):
        """The cutoff is the oldest supported date, not the newest unsupported one."""
        mock_get.return_value = mock_commit_response(EFP_MINIMUM_COMMIT_DATE)

        self.assertIsNone(efp_runner_version_error(DEFAULT_REPO, DEPRECATED_SHA))

    @parameterized.expand([("blank", ""), ("none", None)])
    @patch("studies.helpers.requests.get")
    def test_unpinned_version_is_allowed(self, _name, sha, mock_get):
        """Nothing pinned means the build resolves branch HEAD, which can't be stale."""
        self.assertIsNone(efp_runner_version_error(DEFAULT_REPO, sha))
        mock_get.assert_not_called()

    @parameterized.expand(
        [("github fork", CUSTOM_REPO), ("hosted elsewhere", NON_GITHUB_REPO)]
    )
    @patch("studies.helpers.requests.get")
    def test_custom_repos_are_exempt(self, _name, repo_url, mock_get):
        """We only deprecate versions of our own repo."""
        self.assertIsNone(efp_runner_version_error(repo_url, DEPRECATED_SHA))
        mock_get.assert_not_called()

    @patch("studies.helpers.requests.get")
    def test_github_failure_fails_closed(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError

        self.assertEqual(
            efp_runner_version_error(DEFAULT_REPO, SUPPORTED_SHA),
            EFP_VERSION_UNVERIFIABLE,
        )


@override_settings(EMBER_EXP_PLAYER_REPO=DEFAULT_REPO)
class StudyEFPRunnerVersionTestCase(TestCase):
    """Study.get_efp_runner_version_error and the state transitions that use it."""

    def setUp(self):
        self.lab = Lab.objects.create(
            name="EFP Version Lab", institution="Test", contact_email="test@test.com"
        )

    def create_study(self, metadata, study_type=None, **kwargs):
        return Study.objects.create(
            name="EFP Version Study",
            lab=self.lab,
            study_type=study_type or StudyType.get_ember_frame_player(),
            metadata=metadata,
            **kwargs,
        )

    @patch("studies.models.efp_runner_version_error")
    def test_passes_the_studys_pinned_version_through(self, mock_error):
        """The metadata values are forwarded as-is; the helper owns the verdict."""
        # study.get_efp_runner_version_error:
        # - Reads player_repo_url and last_known_player_sha out of metadata and passes them to the
        # efp_runner_version_error helper in that order.
        # - Returns the helper's verdict (None) unchanged rather than deciding anything itself
        mock_error.return_value = None
        study = self.create_study(
            {"player_repo_url": CUSTOM_REPO, "last_known_player_sha": DEPRECATED_SHA}
        )

        self.assertIsNone(study.get_efp_runner_version_error())
        mock_error.assert_called_once_with(CUSTOM_REPO, DEPRECATED_SHA)

    @patch("studies.models.efp_runner_version_error")
    def test_returns_the_message_unchanged(self, mock_error):
        mock_error.return_value = "version too old"
        study = self.create_study(
            {"player_repo_url": DEFAULT_REPO, "last_known_player_sha": DEPRECATED_SHA}
        )

        self.assertEqual(study.get_efp_runner_version_error(), "version too old")

    @parameterized.expand(
        [
            ("key absent", {"last_known_player_sha": DEPRECATED_SHA}),
            (
                "key present but null",
                {"player_repo_url": None, "last_known_player_sha": DEPRECATED_SHA},
            ),
            ("no metadata at all", {}),
        ]
    )
    @patch("studies.models.efp_runner_version_error")
    def test_missing_repo_url_falls_back_to_the_default_repo(
        self, _name, metadata, mock_error
    ):
        """A null URL must not silently exempt the study as if it were a custom fork."""
        # Instead, it falls back to the default repo URL.
        mock_error.return_value = None
        study = self.create_study(metadata)

        study.get_efp_runner_version_error()

        self.assertEqual(mock_error.call_args.args[0], DEFAULT_REPO)

    @patch("studies.models.efp_runner_version_error")
    def test_non_efp_studies_are_exempt(self, mock_error):
        study = self.create_study(
            {"url": "https://mit.edu"}, study_type=StudyType.get_external()
        )

        self.assertIsNone(study.get_efp_runner_version_error())
        mock_error.assert_not_called()

    @parameterized.expand(
        [
            ("submit", "created", "submit"),
            ("resubmit after rejection", "rejected", "resubmit"),
            ("resubmit after retraction", "retracted", "resubmit"),
            ("activate", "approved", "activate"),
            ("activate after pause", "paused", "activate"),
        ]
    )
    @patch("studies.models.efp_runner_version_error")
    def test_transition_blocked_by_deprecated_version(
        self, _name, state, trigger, mock_error
    ):
        mock_error.return_value = "version too old"
        study = self.create_study(
            {"player_repo_url": DEFAULT_REPO, "last_known_player_sha": DEPRECATED_SHA},
            built=True,
        )
        study.state = state
        study.save()

        with self.assertRaises(RuntimeError) as ctx:
            getattr(study, trigger)()

        # Indirect test for check_efp_runner_version workflow callback
        self.assertEqual(
            str(ctx.exception),
            f'Cannot {trigger} the study "{study.name}" ({study.id}): version too old',
        )
        study.refresh_from_db()
        self.assertEqual(study.state, state, "State changed despite the check failing")

    @parameterized.expand(
        [
            ("submit", "created", "submit", "notify_administrators_of_submission"),
            ("resubmit", "rejected", "resubmit", "notify_administrators_of_submission"),
            ("activate", "approved", "activate", "notify_administrators_of_activation"),
        ]
    )
    @patch("studies.models.efp_runner_version_error")
    def test_transition_allowed_by_supported_version(
        self, _name, state, trigger, notify, mock_error
    ):
        mock_error.return_value = None
        study = self.create_study(
            {"player_repo_url": DEFAULT_REPO, "last_known_player_sha": SUPPORTED_SHA},
            built=True,
        )
        study.state = state
        study.save()

        # No request user in this context, so the notification callback can't run.
        with patch.object(study, notify):
            getattr(study, trigger)()

        study.refresh_from_db()
        self.assertEqual(study.state, "submitted" if "submit" in trigger else "active")

    @parameterized.expand([("reject", "submitted"), ("archive", "created")])
    @patch("studies.models.efp_runner_version_error")
    def test_ungated_transitions_ignore_the_version(self, trigger, state, mock_error):
        """Only submit/resubmit/activate are gated - a study can always be shut down."""
        mock_error.return_value = "version too old"
        study = self.create_study(
            {"player_repo_url": DEFAULT_REPO, "last_known_player_sha": DEPRECATED_SHA}
        )
        study.state = state
        study.save()

        with patch.object(study, "notify_submitter_of_rejection"):
            getattr(study, trigger)()

        study.refresh_from_db()
        self.assertNotEqual(study.state, state)
