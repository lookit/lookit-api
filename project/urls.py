"""project URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.9/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Add an import:  from blog import urls as blog_urls
    2. Import the include() function: from django.conf.urls import url, include
    3. Add a URL to urlpatterns:  url(r'^blog/', include(blog_urls))
"""

from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.urls import urlpatterns as auth_urls
from django.urls import include, path
from more_itertools import locate

from accounts import urls as accounts_urls
from accounts.views import LoginWithRedirectToTwoFactorAuthView
from api import urls as api_urls
from exp import urls as exp_urls
from web import urls as web_urls

# Don't want to depend on the login always being the first view...
# plus we REALLY should be using more_itertools :)
login_path_index = next(locate(auth_urls, lambda patt: patt.name == "login"))
auth_urls[login_path_index] = path(
    "login/", LoginWithRedirectToTwoFactorAuthView.as_view(), name="login"
)
# This fixes what seems to be an issue with with Django's Password reset view.
# Once Django's version has been updated from 3.2. This should be revisited.
pass_reset_path_index = next(
    locate(auth_urls, lambda patt: patt.name == "password_reset")
)
auth_urls[pass_reset_path_index] = path(
    "password_reset/",
    auth_views.PasswordResetView.as_view(
        subject_template_name="registration/password_reset_subject_1.txt"
    ),
    name="password_reset",
)


urlpatterns = i18n_patterns(
    path("__CTRL__/", admin.site.urls),
    path("api/", include((api_urls, "api"))),
    path("exp/", include(exp_urls)),
    path("", include(accounts_urls)),
    # Default auth views need to be put here so that the url reverses
    # will map properly.
    path("", include(web_urls)),
    path("", include(auth_urls)),
    prefix_default_language=False,
)

# if settings.DEBUG:
#     urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
