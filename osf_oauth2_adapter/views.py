import base64

import requests
from allauth.account.utils import user_email, user_field, user_username
from allauth.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.providers.oauth2.views import (
    OAuth2Adapter,
    OAuth2CallbackView,
    OAuth2LoginView,
)
from allauth.utils import valid_email_or_none
from django.contrib.auth import get_user_model
from django.urls import reverse_lazy
from django.views.generic.base import TemplateView
from django.shortcuts import redirect

from osf_oauth2_adapter.provider import OSFProvider

from .apps import OsfOauth2AdapterConfig


class OSFOAuth2Adapter(OAuth2Adapter, DefaultSocialAccountAdapter):
    provider_id = OSFProvider.id
    base_url = "{}oauth2/{}".format(OsfOauth2AdapterConfig.osf_accounts_url, "{}")
    access_token_url = base_url.format("token")
    authorize_url = base_url.format("authorize")
    profile_url = "{}v2/users/me/".format(OsfOauth2AdapterConfig.osf_api_url)

    def get_base64_gravatar(self, url):
        resp = requests.get(url)
        return (
            "data:"
            + resp.headers["Content-Type"]
            + ";"
            + "base64,"
            + str(base64.b64encode(resp.content).decode("utf-8"))
        )

    def pre_social_login(self, request, sociallogin):
        User = get_user_model()
        if User.objects.filter(
            username=sociallogin.user.username, is_researcher=False
        ).exists():
            raise ImmediateHttpResponse(
                redirect(reverse_lazy("local-user-already-exists"))
            )
        return super().pre_social_login(request, sociallogin)

    def populate_user(self, request, sociallogin, data):
        """
        Hook that can be used to further populate the user instance.

        For convenience, we populate several common fields.

        Note that the user instance being populated represents a
        suggested User instance that represents the social user that is
        in the process of being logged in.

        The User instance need not be completely valid and conflict
        free. For example, verifying whether or not the username
        already exists, is not a responsibility.
        """
        username = data.get("username")
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        email = username
        time_zone = data.get("time_zone")
        locale = data.get("locale")
        gravatar = data.get("profile_image_url")
        user = sociallogin.user
        user_username(user, username or "")
        user_email(user, valid_email_or_none(email) or "")
        user_field(user, "given_name", first_name or "")
        user.is_active = True
        user.is_researcher = True
        user_field(user, "family_name", last_name or "")
        user_field(user, "time_zone", time_zone)
        user_field(user, "locale", locale)
        user_field(user, "_identicon", self.get_base64_gravatar(gravatar))

        return user

    def complete_login(self, request, app, access_token, **kwargs):
        extra_data = requests.get(
            self.profile_url,
            headers={"Authorization": "Bearer {}".format(access_token.token)},
        )
        return self.get_provider().sociallogin_from_response(request, extra_data.json())


oauth2_login = OAuth2LoginView.adapter_view(OSFOAuth2Adapter)
oauth2_callback = OAuth2CallbackView.adapter_view(OSFOAuth2Adapter)


class LoginErroredCancelledView(TemplateView):
    template_name = "account/login_errored_cancelled.html"


login_errored_cancelled = LoginErroredCancelledView.as_view()


class LocalUserAlreadyExistsView(TemplateView):
    template_name = "account/local_user_exists.html"
