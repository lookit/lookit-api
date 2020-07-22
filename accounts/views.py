from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.views import LoginView, SuccessURLAllowedHostsMixin
from django.http import HttpResponseRedirect
from django.urls.base import reverse, reverse_lazy
from django.views import generic
from django.views.generic.edit import FormView
from guardian.mixins import LoginRequiredMixin

from accounts import forms
from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from accounts.forms import TOTPCheckForm, TOTPLoginForm
from accounts.models import GoogleAuthenticatorTOTP, User


class LoginWithRedirectToTwoFactorAuthView(LoginView):
    """Step 1 of the login process."""

    def get_success_url(self) -> str:
        user: User = self.request.user
        otp: GoogleAuthenticatorTOTP = getattr(user, "otp")
        if otp and otp.activated:
            return reverse("accounts:2fa-login")
        elif user.is_researcher:
            messages.warning(
                self.request,
                "If you're a researcher, you'll want to set up 2FA with us. "
                "Please complete the Two-Factor Auth setup below and you'll "
                "be on your way!",
            )
            return reverse("accounts:2fa-setup")
        else:
            return super().get_success_url()


class TwoFactorAuthLoginView(LoginView):
    """Semi-optional two-factor authentication login.

    Researchers *must* have 2FA enabled; it's optional for participants.

    Since a user *must* be logged in prior to activating 2FA, the fact that we
    require researchers to use 2FA puts us in a bit of a catch 22 unless
    we can basically log the user in anyway while restricting all views
    that would require full researcher login credentials.
    """

    form_class = TOTPCheckForm

    def form_valid(self, form):
        """Override base functionality to skip auth part.

        Since OTP was already checked during Form cleaning process, we can just
        redirect here.
        """
        self.request.session[TWO_FACTOR_AUTH_SESSION_KEY] = True
        return HttpResponseRedirect(self.get_success_url())


class ResearcherRegistrationView(generic.CreateView):
    template_name = "accounts/researcher-registration.html"
    model = User
    form_class = forms.ResearcherRegistrationForm

    def form_valid(self, form):
        """If the registration process went well, log the user in."""
        # UserRegistrationForm.is_valid() should do proper authentication
        resp = super().form_valid(form)

        # We expect user to be loaded by `ModelFormMixin.form_valid`
        user: User = getattr(self, "object")

        # Following with what django.auth.views.LoginView does here.
        login(
            self.request,
            user,
            backend="accounts.backends.TwoFactorAuthenticationBackend",
        )
        messages.success(self.request, "Researcher account created.")
        return resp

    def get_success_url(self) -> str:
        """Researchers to 2FA setup, Participants go to demographic data update.

        Leverage the fact that `ModelFormMixin.form_valid` sets `self.object = form.save()`
        prior to calling the super() method (`FormMixin.form_valid`), which actually does
        the work of constructing the HttpRedirectResponse for us.
        """
        user: User = getattr(self, "object")
        view_target = (
            "accounts:2fa-setup"
            if user.is_researcher
            else "web:demographic-data-update"
        )
        return reverse(view_target)


class TwoFactorAuthSetupView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    template_name = "accounts/2fa-setup.html"
    form_class = forms.TOTPCheckForm
    success_url = reverse_lazy("exp:study-list")

    permission_denied_message = (
        "For security reasons, once you've activated Two Factor Authentication, you "
        "can't access the QR code again. If you are locked out of your account and "
        "need to reset 2FA to get back in, please contact lookit-tech@mit.edu."
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        otp = GoogleAuthenticatorTOTP.objects.get_or_create(user=self.request.user)[0]
        context["svg_qr_code"] = otp.get_svg_qr_code()
        return context

    def get_form_kwargs(self):
        """Pass the request object to our special TOTPCheckForm."""
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        """If the form is valid, the session should be marked as using 2FA."""
        otp: GoogleAuthenticatorTOTP = getattr(self.request.user, "otp")
        otp.activated = True
        otp.save()
        self.request.session[TWO_FACTOR_AUTH_SESSION_KEY] = True
        return super().form_valid(form)

    def check_otp_presence(self):
        """Guard function.

        1) Don't let the user see the QR code if they've had a chance to set up OTP
           already.
        2) If they're just checking their OTP code, let the request through.
        """
        user: User = self.request.user
        method: str = self.request.method

        if method == "GET":
            # If the user has TOTP set up already, then they shouldn't be able to
            # see the QR code again.
            return not user.otp or not getattr(user.otp, "activated")
        elif method == "POST":
            # TOTP checks, however, only depend on the user having an OTP object
            # associated with their account.
            return bool(user.otp)
        else:
            return False

    test_func = check_otp_presence
