from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect


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
