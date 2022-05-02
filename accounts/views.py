from typing import Tuple, Union
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponseRedirect
from django.http.request import QueryDict
from django.urls.base import reverse
from django.views import generic
from django.views.generic.edit import FormView
from guardian.mixins import LoginRequiredMixin
from more_itertools import bucket

from accounts import forms
from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from accounts.forms import TOTPCheckForm
from accounts.models import GoogleAuthenticatorTOTP, User


class LoginWithRedirectToTwoFactorAuthView(LoginView):
    """Step 1 of the login process."""

    def get_success_url(self) -> str:
        next_view = self.request.GET.get("next")
        user: User = self.request.user
        otp: GoogleAuthenticatorTOTP = getattr(user, "otp")
        if otp and otp.activated:
            success_url = reverse("accounts:2fa-login")
        elif user.is_researcher or user.is_staff:
            messages.warning(
                self.request,
                "If you're a researcher or Lookit staff, you'll want to set up "
                "2FA with us. Please complete the Two-Factor Auth setup below "
                "and you'll be on your way!",
            )
            success_url = reverse("accounts:2fa-setup")
        else:
            return super().get_success_url()

        if next_view:
            qs = urlencode({"next": next_view})
            return f"{success_url}?{qs}"
        else:
            return success_url


class TwoFactorAuthLoginView(UserPassesTestMixin, LoginView):
    """Semi-optional two-factor authentication login.

    Researchers must have 2FA activated and verified prior to viewing
    /exp/ pages. Participants are precluded from visiting this page.
    """

    form_class = TOTPCheckForm

    def user_is_researcher_or_staff(self):
        return getattr(self.request.user, "is_researcher") or getattr(
            self.request.user, "is_staff"
        )

    test_func = user_is_researcher_or_staff

    def form_valid(self, form):
        """Override base functionality to skip auth part.

        Since OTP was already checked during Form cleaning process, we can just
        redirect here.
        """
        self.request.session[TWO_FACTOR_AUTH_SESSION_KEY] = True
        return HttpResponseRedirect(self.get_success_url())

    def get_redirect_url(self) -> str:
        """Have a good default for researchers - the study list."""
        return super().get_redirect_url() or reverse("exp:study-list")


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
        """Researchers go to 2FA setup after they finish regular registration.

        Leverage the fact that `ModelFormMixin.form_valid` sets `self.object = form.save()`
        prior to calling the super() method (`FormMixin.form_valid`), which actually does
        the work of constructing the HttpRedirectResponse for us.
        """
        return reverse("accounts:2fa-setup")


class TwoFactorAuthSetupView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    template_name = "accounts/2fa-setup.html"
    form_class = forms.TOTPCheckForm

    permission_denied_message = (
        "For security reasons, once you've activated Two Factor Authentication, you "
        "can't access the QR code again. If you are locked out of your account and "
        "need to reset 2FA to get back in, please contact lookit-tech@mit.edu."
    )

    def get_success_url(self) -> str:
        return self.request.GET.get("next", reverse("exp:study-list"))

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
        """Executed when the OTP code has been verified.

        If the form is valid, the session should be marked as using 2FA.
        """
        otp: GoogleAuthenticatorTOTP = getattr(self.request.user, "otp")
        otp.activated = True
        otp.save()
        self.request.session[TWO_FACTOR_AUTH_SESSION_KEY] = True
        return super().form_valid(form)

    def check_researcher_status_and_otp_presence(self):
        """Guard function.

        1) Make sure they're a researcher.
        2) Don't let the user see the QR code if they've had a chance to set up OTP
           already.
        3) If they're just checking their OTP code, let the request through.
        """
        user: User = self.request.user
        method: str = self.request.method

        if not user.is_researcher:
            return False

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

    test_func = check_researcher_status_and_otp_presence


class AccountManagementView(LoginRequiredMixin, generic.TemplateView):
    """Handles user info, password change, and 2FA management."""

    ACCOUNT_FORM_PREFIX = "account"
    PASSWORD_FORM_PREFIX = "password"
    OTP_FORM_PREFIX = "otp"

    template_name = "accounts/account-update.html"

    update_account_form_class = forms.AccountUpdateForm
    change_password_form_class = forms.PasswordChangeForm
    otp_check_form_class = forms.TOTPCheckForm

    def post(self, request: WSGIRequest):
        """Process forms dependent on state, then render as with `get`.

        We only allow submission for one form at a time. Furthermore, out OTP
        check form only validates the given auth code; what we do with the
        validated auth code depends on the form handle associated with the
        particular submit button on the form.
        """
        post_data = self.request.POST
        user, otp = self._get_user_and_otp()

        action = post_data["form-handle"]
        form = next(f for f in self._get_forms() if f.is_bound)

        if form.is_valid():
            # Execute the action indicated by the form handle.
            if action == "update-account":
                user = form.save()
                messages.success(request, f"{user} Successfully saved")
            elif action == "change-password":
                user = form.save()
                # Re-cycle session for user.
                update_session_auth_hash(request, user)
                # Nuke old form data - otherwise the validation will kick in.
                # TODO: We probably don't have to trick _get_forms here. Find a better way?
                self.request.POST = QueryDict()
                messages.success(request, "Password successfully changed")
            elif action == "activate-otp":
                otp.activated = True
                otp.save()
                request.session[TWO_FACTOR_AUTH_SESSION_KEY] = True
                messages.success(request, "Two factor auth activated!")
            elif action == "deactivate-otp":
                otp.delete()
                request.session[TWO_FACTOR_AUTH_SESSION_KEY] = False
                messages.success(
                    request,
                    "Two factor auth deactivated. You will need to reset with "
                    "a new QR code if you want to activate it again.",
                )
        else:
            messages.error(request, "There was an error.")

        return super().get(request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user, otp = self._get_user_and_otp()
        update_account_form, change_password_form, otp_check_form = self._get_forms()

        context.update(
            {
                "update_account_form": update_account_form,
                "change_password_form": change_password_form,
                "otp_check_form": otp_check_form,
                "user": user,
                "otp": otp,
                "has_study_child": user.has_study_child(self.request),
            }
        )

        return context

    def _get_user_and_otp(self) -> Tuple[User, Union[GoogleAuthenticatorTOTP, None]]:
        user: User = self.request.user
        otp: Union[GoogleAuthenticatorTOTP, None]
        try:
            otp = GoogleAuthenticatorTOTP.objects.get(user=user)
        except GoogleAuthenticatorTOTP.DoesNotExist:
            otp = None

        return user, otp

    def _get_forms(
        self,
    ) -> Tuple[forms.AccountUpdateForm, forms.PasswordChangeForm, forms.TOTPCheckForm]:
        """Bind forms appropriately for method."""
        request = self.request
        # TODO: switch to normal attribute access after this is fixed
        #    https://youtrack.jetbrains.com/issue/PY-37457
        post_data: QueryDict = getattr(request, "POST")

        # Bucket into new QueryDicts based on prefix. Must use MultiValueDict.update
        # to enforce list containers for values.
        buckets = bucket(post_data.items(), lambda pair: pair[0].partition("-")[0])
        account_update = QueryDict(mutable=True)
        account_update.update(dict(buckets[self.ACCOUNT_FORM_PREFIX]))
        password_change = QueryDict(mutable=True)
        password_change.update(dict(buckets[self.PASSWORD_FORM_PREFIX]))
        otp_check = QueryDict(mutable=True)
        otp_check.update(dict(buckets[self.OTP_FORM_PREFIX]))

        # When data is set to None, the form will not bind.
        return (
            self.update_account_form_class(
                instance=request.user,
                data=account_update or None,
                prefix=self.ACCOUNT_FORM_PREFIX,
            ),
            self.change_password_form_class(
                request.user,
                data=password_change or None,
                prefix=self.PASSWORD_FORM_PREFIX,
            ),
            self.otp_check_form_class(
                request=request, data=otp_check or None, prefix=self.OTP_FORM_PREFIX
            ),
        )
