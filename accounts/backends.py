from typing import Any, Optional

from django.contrib.auth.backends import ModelBackend
from django.http import HttpRequest

from accounts.models import User


class TwoFactorAuthenticationBackend(ModelBackend):
    """Grabs a regular user, but checks OTP as well as password.

    TODO: get rid of otp client auto-creation, instead redirect to new page
        when there is no otp
    """

    def authenticate(
        self,
        request: HttpRequest,
        username: Optional[str] = None,
        password: Optional[str] = None,
        auth_code: Optional[str] = None,
        **kwargs: Any
    ) -> Optional[User]:
        """Authentication override."""
        user: Optional[User] = super().authenticate(
            request, username, password, **kwargs
        )

        if user:  # Implicit return of nothing, so no else statement.
            if user.otp:
                if user.otp.verify(auth_code):
                    request.session["using_2FA"] = True
                    return user
            else:
                request.session["using_2FA"] = False
                return user


two_factor_auth_backend = TwoFactorAuthenticationBackend()
