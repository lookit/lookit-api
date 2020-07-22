from django.conf.urls import include
from django.urls import path

from accounts.views import (
    ResearcherRegistrationView,
    TwoFactorAuthLoginView,
    TwoFactorAuthSetupView,
)

app_name = "accounts"


urlpatterns = [
    path(
        "registration/",
        ResearcherRegistrationView.as_view(),
        name="researcher-registration",
    ),
    path("2fa-setup/", TwoFactorAuthSetupView.as_view(), name="2fa-setup"),
    path("2fa-login/", TwoFactorAuthLoginView.as_view(), name="2fa-login"),
]
