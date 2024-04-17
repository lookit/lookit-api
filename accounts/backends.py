from typing import Any, Optional

from django.contrib.auth.backends import ModelBackend
from django.http import HttpRequest

from accounts.models import User

TWO_FACTOR_AUTH_SESSION_KEY = "using_2FA"


class TwoFactorAuthenticationBackend(ModelBackend):
    """Grabs a regular user, but checks OTP as well as password."""

    def authenticate(
        self,
        request: HttpRequest,
        username: Optional[str] = None,
        password: Optional[str] = None,
        auth_code: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[User]:
        """Authentication override."""

        # Use normal ModelBackend.authenticate to get user the normal way.
        user: Optional[User] = super().authenticate(
            request, username, password, **kwargs
        )

        # Now, we check if the user has 2FA activated. If they do, we must verify the
        # code that they provided. In downstream requests, the `using_2FA` flag will be used
        # in conjunction with User.is_researcher to make sure certain views are properly
        # guarded.
        if user:  # Implicit return of nothing, so no else statement.
            if user.otp:
                if user.otp.verify(auth_code):
                    request.session[TWO_FACTOR_AUTH_SESSION_KEY] = True
                    return user
            else:
                request.session[TWO_FACTOR_AUTH_SESSION_KEY] = False
                return user


two_factor_auth_backend = TwoFactorAuthenticationBackend()
