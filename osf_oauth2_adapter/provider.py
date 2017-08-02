from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.providers.base import ProviderAccount
from allauth.socialaccount.providers.oauth2.provider import OAuth2Provider

from accounts.models import Organization

from .apps import OsfOauth2AdapterConfig


class OSFAccount(ProviderAccount):
    def to_str(self):
        # default ... reserved word?
        dflt = super(OSFAccount, self).to_str()
        return next(
            value
            for value in (
                # try the name first, then the id, then the super value
                '{} {}'.format(
                    self.account.extra_data.get('first_name', None),
                    self.account.extra_data.get('last_name', None)
                ),
                self.account.extra_data.get('id', None),
                dflt
            )
            if value is not None
        )


class OSFProvider(OAuth2Provider):
    id = 'osf'
    name = 'Open Science Framework'
    account_class = OSFAccount

    def extract_common_fields(self, data):
        attributes = data.get('data').get('attributes')
        return dict(
            # we could put more fields here later
            # the api has much more available, just not sure how much we need right now
            username=attributes.get('email', f"{data.get('data').get('id')}@osf.io"),
            first_name=attributes.get('given_name', None),
            last_name=attributes.get('family_name', None),
            time_zone=attributes.get('timezone', None),
            locale=attributes.get('locale', None),
            profile_image_url=data.get('data').get('links').get('profile_image')
        )

    def sociallogin_from_response(self, request, response):
        """
        Instantiates and populates a `SocialLogin` model based on the data
        retrieved in `response`. The method does NOT save the model to the
        DB.

        Data for `SocialLogin` will be extracted from `response` with the
        help of the `.extract_uid()`, `.extract_extra_data()`,
        `.extract_common_fields()`, and `.extract_email_addresses()`
        methods.

        :param request: a Django `HttpRequest` object.
        :param response: object retrieved via the callback response of the
            social auth provider.
        :return: A populated instance of the `SocialLogin` model (unsaved).
        """
        # NOTE: Avoid loading models at top due to registry boot...
        from allauth.socialaccount.models import SocialLogin, SocialAccount

        adapter = get_adapter(request)
        uid = self.extract_uid(response)
        extra_data = self.extract_extra_data(response)
        common_fields = self.extract_common_fields(response)
        socialaccount = SocialAccount(extra_data=extra_data,
                                      uid=uid,
                                      provider=self.id)
        email_addresses = self.extract_email_addresses(response)
        self.cleanup_email_addresses(common_fields.get('email'),
                                     email_addresses)
        sociallogin = SocialLogin(account=socialaccount,
                                  email_addresses=email_addresses)
        user = sociallogin.user = adapter.new_user(request, sociallogin)
        user.set_unusable_password()
        adapter.populate_user(request, sociallogin, common_fields)
        return sociallogin

    def extract_uid(self, data):
        return str(data.get('data').get('id'))

    def get_default_scope(self):
        return OsfOauth2AdapterConfig.default_scopes

provider_classes = [OSFProvider]
