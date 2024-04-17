from functools import cached_property
from typing import Dict, Iterable, Optional, Protocol, Type, TypeVar, Union

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
from studies.models import Lab, Response, Study
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


class ResearcherAuthenticatedRedirectMixin(UserPassesTestMixin):
    def authenticated_redirect(self, url):
        request = self.request
        user = request.user
        is_researcher = getattr(user, "is_researcher", False)
        enabled_2fa = request.session.get(TWO_FACTOR_AUTH_SESSION_KEY)

        if is_researcher and enabled_2fa and self.test_func():
            return redirect(url)
        else:
            messages.error(
                request,
                "Please log in with a research account to view this experiment.",
            )
            return redirect("login")


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
                    "Researcher account required to see Experimenter app."
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
