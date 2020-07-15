from django.urls import path

from accounts.views import ResearcherRegistrationView, TwoFactorAuthSetupView

app_name = "accounts"

urlpatterns = [
    path(
        "registration/",
        ResearcherRegistrationView.as_view(),
        name="researcher-registration",
    ),
    path("2fa/", TwoFactorAuthSetupView.as_view(), name="2fa-setup"),
]
