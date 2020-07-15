from typing import Optional

import requests
from django.conf import settings
from django.contrib import messages
from django.db.models import Model
from django.http.request import HttpRequest
from django.http.response import HttpResponseForbidden
from django.shortcuts import redirect
from django.views.generic.detail import SingleObjectMixin
from guardian.mixins import LoginRequiredMixin

from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from studies.models import StudyType


class ExperimenterLoginRequiredMixin(LoginRequiredMixin):
    """Require logged-in user; if not logged in, redirect to experimenter login."""

    def dispatch(self, request, *args, **kwargs):
        """Dispatch override."""
        user = request.user
        # Potential anonymous user should not break the view.
        is_researcher = getattr(user, "is_researcher", False)
        two_factor_auth_enabled = request.session.get(TWO_FACTOR_AUTH_SESSION_KEY)
        if is_researcher:
            if two_factor_auth_enabled:
                return super().dispatch(request, *args, **kwargs)
            else:
                messages.error(
                    request,
                    "In order to access experimenter pages, you must have two-factor "
                    "authentication enabled, and have logged in with your OTP key.",
                )
                return redirect("accounts:login")
        else:
            return HttpResponseForbidden(
                f"Unauthorized: {user} is not a Researcher account."
            )


class SingleObjectParsimoniousQueryMixin(SingleObjectMixin):

    object: Model

    def get_object(self, queryset=None):
        """Override get_object() to be smarter.

        This is to allow us to get the study for use the predicate function
        of UserPassesTestMixin without making `SingleObjectMixin.get` (called
        within the context of `View.dispatch`) issue a second expensive query.
        """
        if getattr(self, "object", None) is None:
            # Only call get_object() when self.object isn't present.
            self.object = super().get_object()
        return self.object


class StudyTypeMixin:

    request: HttpRequest

    def validate_and_fetch_metadata(self, study_type: Optional[StudyType] = None):
        """Gets the study type and runs hardcoded validations.

        TODO: this is obviously a fragile pattern, and there's probably a better way to do this.
            Let's think of a way to do this more dynamically in the future.

        :return: A tuple of boolean and tuple, the inner tuple containing error data.
        """
        if not study_type:
            target_study_type_id = self.request.POST["study_type"]
            study_type = StudyType.objects.get(id=target_study_type_id)
        metadata = self.extract_type_metadata(study_type=study_type)

        errors = VALIDATIONS.get(study_type.name, is_valid_ember_frame_player)(metadata)

        return metadata, errors

    def extract_type_metadata(self, study_type):
        """
        Pull the metadata related to the selected StudyType from the POST request
        """
        type_fields = study_type.configuration["metadata"]["fields"]

        metadata = {}

        for key in type_fields:
            metadata[key] = self.request.POST.get(key, None)

        return metadata


def is_valid_ember_frame_player(metadata):
    """Checks commit sha and player repo url.

    This must fulfill the contract of returning a list. We are exploiting the fact that empty
    lists evaluate falsey.

    :param metadata: the metadata object containing shas for both frameplayer and addons repo
    :type metadata: dict
    :return: a list of errors.
    :rtype: list.
    """
    player_repo_url = metadata.get("player_repo_url", settings.EMBER_EXP_PLAYER_REPO)
    frameplayer_commit_sha = metadata.get("last_known_player_sha", "")

    errors = []

    if not requests.get(player_repo_url).ok:
        errors.append(f"Frameplayer repo url {player_repo_url} does not work.")
    if not requests.get(f"{player_repo_url}/commit/{frameplayer_commit_sha}").ok:
        errors.append(f"Frameplayer commit {frameplayer_commit_sha} does not exist.")

    return errors


VALIDATIONS = {"Ember Frame Player (default)": is_valid_ember_frame_player}
