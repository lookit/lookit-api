from allauth.socialaccount.providers.oauth2.urls import default_urlpatterns
from osf_oauth2_adapter.provider import OSFProvider
from osf_oauth2_adapter.views import LocalUserAlreadyExistsView
from django.conf.urls import url

urlpatterns = default_urlpatterns(OSFProvider)

urlpatterns = urlpatterns + [
    url(r'accounts/already_exists/?$', LocalUserAlreadyExistsView.as_view(), name='local-user-already-exists')
]
