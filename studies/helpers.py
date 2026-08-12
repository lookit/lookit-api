import base64
import copy
import logging
import re
from datetime import datetime, timezone
from email.mime.image import MIMEImage
from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings
from django.core.mail.message import EmailMultiAlternatives
from django.db import models
from django.template.loader import get_template

from accounts.queries import (
    child_in_age_range_for_study_days_difference,
    get_child_eligibility,
    get_child_participation_eligibility,
)
from project.celery import app

logger = logging.getLogger(__name__)

# Experiment runner commits older than this date can no longer be used, but only
# for the default repo (settings.EMBER_EXP_PLAYER_REPO). Custom forks are exempt.
# Must stay timezone-aware: commit dates come back from GitHub as aware datetimes,
# and comparing those against a naive one raises TypeError.
EFP_MINIMUM_COMMIT_DATE = datetime(2024, 1, 30, tzinfo=timezone.utc)

# Formatted here rather than at each use so that the error messages and the warning on
# the study design page always have the same display date.
# (Not formatted with Django's date filter because that converts to settings.TIME_ZONE,
# which would shift a UTC midnight cutoff back a day.)
EFP_MINIMUM_COMMIT_DATE_DISPLAY = f"{EFP_MINIMUM_COMMIT_DATE:%B %-d, %Y}"

GITHUB_API_TIMEOUT = 10  # seconds

EFP_VERSION_UNVERIFIABLE = (
    "There was a problem checking your experiment runner version on GitHub just now, so we "
    "can't confirm that it is still supported. Please try again in a few minutes. If "
    "this keeps happening, contact us on Slack or at support@childrenhelpingscience.org."
)

EFP_LATEST_VERSION_UNRESOLVABLE = (
    "There was a problem looking up the latest experiment runner version on GitHub "
    "just now. Please enter a commit SHA, or leave this blank and try again in a few "
    "minutes. If this keeps happening, contact us on Slack or at "
    "support@childrenhelpingscience.org."
)

# Retrying won't help here, so this deliberately doesn't suggest it.
EFP_LATEST_VERSION_NOT_ON_GITHUB = (
    "We can only look up the latest version automatically for experiment runner "
    "repos hosted on GitHub. Please enter a commit SHA for this repo."
)


def get_absolute_url(path=""):
    return urljoin(settings.BASE_URL, path)


def get_experiment_absolute_url(path):
    return urljoin(settings.EXPERIMENT_BASE_URL, path)


def get_repo_path(full_repo_path):
    """Pull the "owner/repo" portion out of a GitHub repo URL.

    Tolerates the same variations as normalize_repo_url (scheme, case, "www.",
    trailing slash, ".git"). Returns None if this isn't a GitHub URL at all, so
    callers can fall back rather than breaking on a repo hosted elsewhere.
    """
    parsed = urlparse((full_repo_path or "").strip())
    if parsed.netloc.lower().removeprefix("www.") != "github.com":
        return None
    return parsed.path.strip("/").removesuffix(".git") or None


def normalize_repo_url(url):
    """Canonical form of a repo URL, for comparing the study's repo to the EFP default.

    Insensitive to scheme, case, "www.", trailing slashes and a ".git" suffix, so
    that e.g. "HTTP://www.GitHub.com/lookit/ember-lookit-frameplayer.git/" and
    "https://github.com/lookit/ember-lookit-frameplayer" compare equal.
    """
    parsed = urlparse((url or "").strip())
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/").lower().removesuffix(".git")
    return f"{netloc}{path}"


def is_default_player_repo(url):
    """True if this URL points at the default experiment runner repo.

    Reads the setting at call time so that it stays correct under override_settings
    and when EMBER_EXP_PLAYER_REPO is set from the environment.
    """
    return bool(url) and normalize_repo_url(url) == normalize_repo_url(
        settings.EMBER_EXP_PLAYER_REPO
    )


def get_commit_datetime(player_repo_url, sha):
    """Look up when a commit landed, via the GitHub API.

    Returns (datetime, None) on success, or (None, error_message) when the commit
    doesn't exist or GitHub can't be reached. Exactly one of the two is ever set.

    Uses the committer date rather than the author date: the author date is when the
    patch was first written and survives rebases and cherry-picks, so a recently
    merged commit can carry a years-old author date. The committer date is when the
    code actually landed on the branch, which is what "how old is this version"
    means here.
    """
    api_url = (
        f"https://api.github.com/repos/{get_repo_path(player_repo_url)}/commits/{sha}"
    )

    try:
        response = requests.get(
            api_url,
            timeout=GITHUB_API_TIMEOUT,
            headers={"Accept": "application/vnd.github+json"},
        )
    except requests.exceptions.RequestException:
        logger.warning(f"Could not reach GitHub to check commit {sha}.")
        return None, EFP_VERSION_UNVERIFIABLE

    # 404 is an unknown SHA, 422 a malformed one. Both mean "no such commit", which
    # is the researcher's to fix. Everything else is our problem, not theirs.
    if response.status_code in (404, 422):
        return None, f"Frameplayer commit {sha} does not exist."

    if not response.ok:
        logger.warning(
            f"GitHub returned {response.status_code} when checking commit {sha}."
        )
        return None, EFP_VERSION_UNVERIFIABLE

    try:
        return datetime.fromisoformat(
            response.json()["commit"]["committer"]["date"]
        ), None
    except (ValueError, KeyError, TypeError, requests.exceptions.JSONDecodeError):
        logger.warning(f"Unexpected GitHub response when checking commit {sha}.")
        return None, EFP_VERSION_UNVERIFIABLE


def get_branch_head_sha(player_repo_url, branch):
    """Look up the commit a branch currently points at, via the GitHub API.

    Returns (sha, None) on success, or (None, error_message) on failure, matching
    get_commit_datetime's contract.

    Only works for repos hosted on GitHub. A custom repo hosted elsewhere has to
    pin its version explicitly, since there's no portable way to ask a git host
    what a branch points at over HTTP.
    """
    repo_path = get_repo_path(player_repo_url)
    if repo_path is None:
        return None, EFP_LATEST_VERSION_NOT_ON_GITHUB

    api_url = f"https://api.github.com/repos/{repo_path}/git/refs/heads/{branch}"

    try:
        response = requests.get(
            api_url,
            timeout=GITHUB_API_TIMEOUT,
            headers={"Accept": "application/vnd.github+json"},
        )
    except requests.exceptions.RequestException:
        logger.warning(f"Could not reach GitHub to resolve branch {branch}.")
        return None, EFP_LATEST_VERSION_UNRESOLVABLE

    if not response.ok:
        logger.warning(
            f"GitHub returned {response.status_code} when resolving branch {branch}."
        )
        return None, EFP_LATEST_VERSION_UNRESOLVABLE

    try:
        return response.json()["object"]["sha"], None
    except (KeyError, TypeError, requests.exceptions.JSONDecodeError):
        logger.warning(f"Unexpected GitHub response when resolving branch {branch}.")
        return None, EFP_LATEST_VERSION_UNRESOLVABLE


def efp_runner_version_error(player_repo_url, last_known_player_sha):
    """Check whether a study may use this experiment runner version.

    Returns a message ready to show the researcher, or None if the version is fine.
    Callers wrap the message in whatever their context needs (a ValidationError, a
    messages.error, a RuntimeError), which is why this returns a string rather than
    raising.
    """
    if not last_known_player_sha:
        # Nothing pinned, so the build resolves the branch HEAD, which can't be
        # out of date by definition.
        return None

    if not is_default_player_repo(player_repo_url):
        # Custom forks are exempt - we only deprecate versions of our own repo.
        return None

    commit_datetime, error = get_commit_datetime(player_repo_url, last_known_player_sha)
    if error:
        return error

    if commit_datetime < EFP_MINIMUM_COMMIT_DATE:
        return (
            f"Your experiment runner version {last_known_player_sha[:7]} is from "
            f"{commit_datetime:%B %-d, %Y} and is no longer supported. Versions from "
            f"before {EFP_MINIMUM_COMMIT_DATE_DISPLAY} use a 3rd party package that "
            f"has been deprecated. The easiest way to update is to clear the experiment "
            f"runner version field on the study design page and then save - we'll fill "
            f"in the latest version for you. You can also select a specific version "
            f"by clicking the 'Check for updates' button or from "
            f"{settings.EMBER_EXP_PLAYER_REPO}/commits/{settings.EMBER_EXP_PLAYER_BRANCH}. "
            "You will need to rebuild the experiment runner after updating and saving."
        )

    return None


@app.task
def send_mail(
    template_name,
    subject,
    to_addresses,
    cc=None,
    bcc=None,
    reply_to=None,
    headers=None,
    **context,
):
    """
    Helper for sending templated email

    Note: we no longer allow an argument for the 'from' address because new email deliverability requirements say
    that the 'from' address must match the domain that the email was actually sent from (in our case, mit.edu).

    :param str template_name: Name of the template to send. There should exist a txt and html version
    :param str subject: Subject line of the email
    :param list to_addresses: List of addresses to email. If str is provided, wrapped in list
    :param list cc: List of addresses to carbon copy
    :param list bcc: List of addresses to blind carbon copy
    :param str custom_message Custom email message - for use instead of a template
    :kwargs: Context vars for the email template
    """
    # For text version: replace images with [IMAGE] so they're not removed entirely
    context_plain_text = copy.deepcopy(context)
    # TODO: use a custom filter rather than striptags to preserve image placeholders in the
    # custom_email template
    if template_name == "custom_email" and "custom_message" in context_plain_text:
        image_scheme = re.compile(r"<img .*?>", re.MULTILINE)
        context_plain_text["custom_message"] = re.sub(
            image_scheme, "[IMAGE]", context_plain_text["custom_message"]
        )

    # Render into template
    text_content = get_template("emails/{}.txt".format(template_name)).render(
        context_plain_text
    )
    html_content = get_template("emails/{}.html".format(template_name)).render(context)

    if not isinstance(to_addresses, list):
        to_addresses = [to_addresses]

    from_address = settings.EMAIL_FROM_ADDRESS

    email = EmailMultiAlternatives(
        subject,
        text_content,
        from_address,
        to_addresses,
        cc=cc,
        bcc=bcc,
        reply_to=reply_to,
        headers=headers,
    )

    # For HTML version: Replace inline images with attachments referenced. See
    # https://gist.github.com/osantana/833045a89ccbc6fc50c1 for reference
    inline_scheme = re.compile(
        r' src="data:image/(?P<subtype>.*?);base64,(?P<path>.*?)" ?', re.MULTILINE
    )
    images_data = []

    def repl(match):
        images_data.append((match.group("subtype"), match.group("path")))
        return ' src="cid:image-%05d" ' % (len(images_data),)

    html_content = re.sub(inline_scheme, repl, html_content)

    for index, (subtype, data) in enumerate(images_data):
        image = MIMEImage(base64.b64decode(data), _subtype=subtype)
        image_id = "image-%05d" % (index + 1)
        image.add_header("Content-ID", image_id)
        image.add_header("Content-Disposition", "inline")
        image.add_header("Filename", image_id + "." + subtype)
        email.attach(image)

    email.attach_alternative(html_content, "text/html")
    email.send()
    return email


def get_eligibility_for_response(child_obj, study_obj):
    """Get current eligibility for a child and study at the time that the Response object is created.
    Args:
        child (Child): Child model object
        study (Study): Study model object

    Returns:
        Set: one or more possible string eligibility values (defined in the ResponseEligibility class).
        The set can contain one or more 'ineligible' values, but if the child is eligible then that should be the only value in the set.
    """
    resp_elig = ResponseEligibility
    eligibility_set = {resp_elig.ELIGIBLE.value}

    age_range_diff = child_in_age_range_for_study_days_difference(child_obj, study_obj)
    ineligible_participation = not get_child_participation_eligibility(
        child_obj, study_obj
    )
    ineligible_criteria = not get_child_eligibility(
        child_obj, study_obj.criteria_expression
    )

    if age_range_diff != 0 or ineligible_participation or ineligible_criteria:
        eligibility_set = set()

        if age_range_diff > 0:
            eligibility_set.add(resp_elig.INELIGIBLE_OLD.value)
        elif age_range_diff < 0:
            eligibility_set.add(resp_elig.INELIGIBLE_YOUNG.value)

        if ineligible_participation:
            eligibility_set.add(resp_elig.INELIGIBLE_PARTICIPATION.value)

        if ineligible_criteria:
            eligibility_set.add(resp_elig.INELIGIBLE_CRITERIA.value)

    return sorted(list(eligibility_set))


class ResponseEligibility(models.TextChoices):
    """Participant eligibility categories for Response model"""

    # This must be determined at the point of the study participation/response, because child eligibility can change over time for a given study
    ELIGIBLE = "Eligible"
    INELIGIBLE_YOUNG = "Ineligible_TooYoung"
    INELIGIBLE_OLD = "Ineligible_TooOld"
    INELIGIBLE_CRITERIA = "Ineligible_CriteriaExpression"
    INELIGIBLE_PARTICIPATION = "Ineligible_Participation"


class FrameActionDispatcher(object):
    """Dispatches an action based on the latest frame type of a given response.

    The idea with this class is that it's easy to extend - you just add a method with the lower-case
    name matching the frame type you want to act on, and make sure to include the response, frame_data,
    and current_frame_id as named arguments, plus optional args/kwargs that can be passed in at call time.
    """

    def __call__(self, response, *args, **kwargs):
        """Dispatcher that delegates to inner methods."""

        if not response.sequence:
            return

        current_frame_id = response.sequence[-1]

        if response.study_type.is_jspsych:
            exp_data = response.exp_data[-1]
            if not isinstance(exp_data, dict):
                return
            frame_data = exp_data.get("response")
            frame_type = exp_data.get("chs_type")
        elif response.study_type.is_ember_frame_player:
            frame_data = response.exp_data[current_frame_id]
            if not isinstance(frame_data, dict):
                return
            frame_type = frame_data.get("frameType")

        if not frame_type:
            return

        try:
            return getattr(self, frame_type.lower())(
                response, frame_data, current_frame_id, *args, **kwargs
            )
        except AttributeError as e:
            logger.warning(f"{e.args} is not registered for frame-specific action.")

    def default(self, response, frame_data: dict, current_frame_id, *args, **kwargs):
        """Default frame hook.

        Args:
            response: Response Model.
            frame_data: dictionary of frame data.
            current_frame_id: ID of the current frame (e.g. 1-my-video-consent)
        """

    def exit(self, response, frame_data: dict, *args, **kwargs):
        """Exit frame hook.

        Args:
            response: Response Model.
            frame_data: dictionary of frame data.
            current_frame_id: ID of the current frame (e.g. 1-my-video-consent)
        """
        withdrawal = frame_data.get("withdrawal", None)
        if withdrawal:
            for video in response.videos.filter(is_consent_footage=False):
                video.delete()
        elif withdrawal is None:
            logger.warning(
                f"withdrawal property not found in exit frame for {response}"
            )
        else:  # Withdrawal is false, do nothing.
            pass

    def consent(self, response, frame_data: dict, current_frame_id, *args, **kwargs):
        """Upon saving data from a consent frame, mark the video collected as consent footage.
        This means the participant will have to proceed from the consent frame before
        consent footage is accessible to researchers. Video model is ALSO marked as consent
        footage upon creation if exp_data already has the consent frame added. This hook
        covers the case where the Video is created first and then exp_data is updated; that
        hook covers the case where exp_data is updated before the Video model is created.

        Args:
            response: Response Model.
            frame_data: dictionary of frame data.
            current_frame_id: ID of the current frame (e.g. 1-my-video-consent)
        """
        for video in response.videos.filter(frame_id=current_frame_id):
            video.is_consent_footage = True
            video.save()
        # Using frame_id as likely to be most robust, even with slightly convoluted generation
        # of frame IDs during randomizer-generated frames (there should at least never be
        # duplicate frame IDs because of the incrementing frame number at the start of the
        # ID). But alternative in case needed in future is to use video filenames -
        # video.full_name includes extension (.mp4), videoList is filename w/o extension:
        #
        # if any([consentFilename in video.full_name for consentFilename in frame_data.get("videoList", [])]):
