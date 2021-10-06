from functools import cached_property
from typing import Dict, Iterable, Optional, Protocol, Type, TypeVar, Union

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.models import AnonymousUser
from django.core.handlers.wsgi import WSGIRequest
from django.db.models import Model, QuerySet
from django.http.response import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from guardian.mixins import LoginRequiredMixin

from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from accounts.models import User
from studies.models import Lab, Response, Study, StudyType, StudyTypeEnum
from studies.permissions import StudyPermission

LookitUser = Union[User, AnonymousUser]
LookitObject = Union[Lab, Study, Response]
ModelType = TypeVar("ModelType", bound=Model)


class LookitRequest(WSGIRequest):
    """Custom stub to help recognize custom AUTH_USER_MODEL.

    See: https://github.com/typeddjango/django-stubs#how-can-i-create-a-httprequest-thats-guaranteed-to-have-an-authenticated-user
    """

    user: LookitUser


class LookitHandlerBase:
    request: LookitRequest
    args: Iterable
    kwargs: Dict


class ResearcherLoginRequiredMixin(LookitHandlerBase, LoginRequiredMixin):
    """Require logged-in user; if not logged in, redirect to researcher login."""

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
                    "In order to access researcher pages, you must have two-factor "
                    "authentication enabled, and have logged in with your OTP key.",
                )
                return redirect("accounts:2fa-login")
        else:
            if user.is_authenticated:
                return HttpResponseForbidden(
                    f"Researcher account required to see Experimenter app."
                )
            else:
                messages.info(
                    request,
                    "Please sign in with your researcher account to see Experimenter app.",
                )
                return HttpResponseRedirect(reverse("login"))


class StudyLookupMixin(LookitHandlerBase):
    @cached_property
    def study(self):
        return get_object_or_404(Study, pk=self.kwargs.get("pk"))


class CanViewStudyResponsesMixin(
    ResearcherLoginRequiredMixin, UserPassesTestMixin, StudyLookupMixin
):

    raise_exception = True

    def can_view_responses(self):
        user = self.request.user
        study = self.study

        return user.is_researcher and (
            user.has_study_perms(StudyPermission.READ_STUDY_RESPONSE_DATA, study)
            or user.has_study_perms(StudyPermission.READ_STUDY_PREVIEW_DATA, study)
        )

    test_func = can_view_responses


class SingleObjectFetchProtocol(Protocol[ModelType]):

    model: Type[ModelType]
    object: ModelType

    def get_object(self, queryset: Optional[QuerySet] = None) -> ModelType:
        """Override get_object() to be smarter.

        This is to allow us to get the study for use the predicate function
        of UserPassesTestMixin without making `SingleObjectMixin.get` (called
        within the context of `View.dispatch`) issue a second expensive query.
        """
        if getattr(self, "object", None) is None:
            # Only call get_object() when self.object isn't present.
            self.object: ModelType = super().get_object(queryset)
        return self.object


class StudyTypeMixin:

    request: LookitRequest

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

    def extract_type_metadata(self, study_type: StudyType):
        """
        Pull the metadata related to the selected StudyType from the POST request
        """
        type_fields = study_type.configuration["metadata"]["fields"]

        metadata = {}

        for type_field in type_fields:
            if type_field["input_type"] == "checkbox":
                metadata[type_field["name"]] = type_field["name"] in self.request.POST
            else:
                metadata[type_field["name"]] = self.request.POST.get(
                    type_field["name"], None
                )

        if study_type.is_external:
            metadata["scheduled"] = self.request.POST.get("scheduled", "") == "on"
            metadata["other_scheduling"] = self.request.POST.get("other_scheduling", "")
            metadata["other_study_platform"] = self.request.POST.get(
                "other_study_platform", ""
            )

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


def is_valid_external(metadata):
    errors = []

    if "url" not in metadata or metadata["url"] is None:
        errors.append("External Study doesn't have URL")
    if "scheduled" not in metadata:
        errors.append("External Study doesn't have Scheduled value")

    return errors


VALIDATIONS = {
    StudyTypeEnum.ember_frame_player.value: is_valid_ember_frame_player,
    StudyTypeEnum.external.value: is_valid_external,
}
