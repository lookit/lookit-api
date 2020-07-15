from django.conf.urls import include
from django.contrib.auth.urls import urlpatterns as auth_urls
from django.urls import path
from more_itertools import locate

from accounts.views import (
    ResearcherRegistrationView,
    TwoFactorAuthLoginView,
    TwoFactorAuthSetupView,
)

app_name = "accounts"

# Don't want to depend on the login always being the first view...
# plus we REALLY should be using more_itertools :)
login_path_index = next(locate(auth_urls, lambda patt: patt.name == "login"))
auth_urls[login_path_index] = path(
    "login/", TwoFactorAuthLoginView.as_view(), name="login"
)

urlpatterns = [
    path(
        "registration/",
        ResearcherRegistrationView.as_view(),
        name="researcher-registration",
    ),
    path("2fa/", TwoFactorAuthSetupView.as_view(), name="2fa-setup"),
    path("", include(auth_urls)),
]
