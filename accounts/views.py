from django.contrib.auth.views import LoginView
from django.shortcuts import reverse

from accounts.forms import TOTPLoginForm


class TwoFactorAuthLoginView(LoginView):
    """Semi-optional two-factor authentication login.

    Researchers *must* have 2FA enabled; it's optional for participants.

    Since a user *must* be logged in prior to activating 2FA, the fact that we
    require researchers to use 2FA puts us in a bit of a catch 22 unless
    we can basically log the user in anyway while restricting all views
    that would require full researcher login credentials.

    ProcessFormView.post
        - puppets form.is_valid()
        - invokes self.form_invalid() and self.form_valid(), both of which return
          HTTPResponses

    LoginView invokes its own self.form_valid(), which calls
    `auth_login(self.request, form.get_user())`
    before returning HttpResponseRedirect(self.get_success_url())
    """

    form_class = TOTPLoginForm
