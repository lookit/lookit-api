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
from django.conf.urls import include
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.urls import urlpatterns as auth_urls
from django.urls import path
from django.views.generic.base import RedirectView
from more_itertools import locate

from accounts import urls as accounts_urls
from accounts.views import TwoFactorAuthLoginView
from api import urls as api_urls
from exp import urls as exp_urls
from project import settings
from web import urls as web_urls

# Just change the login path, keep everything else.
login_path_index = next(locate(auth_urls, lambda patt: patt.name == "login"))
auth_urls[login_path_index] = path(
    "login/", TwoFactorAuthLoginView.as_view(), name="login"
)

favicon_view = RedirectView.as_view(url="/static/favicon.ico", permanent=True)

urlpatterns = [
    path("favicon.ico", favicon_view),
    path("__CTRL__/", admin.site.urls),
    path("api/", include((api_urls, "api"))),
    path("exp/", include(exp_urls)),
    path("", include(accounts_urls)),
    path("", include(auth_urls)),
    path("", include(web_urls)),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns = (
        [path("__debug__/", include(debug_toolbar.urls))]
        + urlpatterns
        + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    )
