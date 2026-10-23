from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect

from web.middleware import participation_blocked


class AuthenticatedRedirectMixin(UserPassesTestMixin):
    def authenticated_redirect(self, url):
        request = self.request
        user = request.user

        if user.is_authenticated and self.test_func():
            return redirect(url)
        else:
            messages.error(
                request,
                "Please log in to view this experiment.",
            )
            return redirect("login")


def blocked_participation_redirect(study_uuid):
    """Send a visitor that a block rule stops participating back to the study
    detail page, where the participate button only spins and reloads the page,
    so they can't tell they're blocked.
    """
    return redirect("web:study-detail", uuid=study_uuid)


class ParticipationBlockedMixin:
    def dispatch(self, request, *args, **kwargs):
        if participation_blocked(request):
            return blocked_participation_redirect(kwargs["uuid"])
        return super().dispatch(request, *args, **kwargs)
