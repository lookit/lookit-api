from django.contrib import admin
from django.core.handlers.wsgi import WSGIRequest

from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from accounts.forms import TOTPLoginForm


class TwoFactorAuthProtectedAdminSite(admin.AdminSite):
    login_form = TOTPLoginForm
    login_template = "registration/login.html"

    def has_permission(self, request: WSGIRequest) -> bool:
        is_active_staff = super().has_permission(request)

        # probably overkill, but just making sure.
        user_activated_2fa = (
            otp := getattr(request.user, "otp", None)
        ) and otp.activated

        session_has_2fa = request.session.get(TWO_FACTOR_AUTH_SESSION_KEY, False)

        return is_active_staff and user_activated_2fa and session_has_2fa
