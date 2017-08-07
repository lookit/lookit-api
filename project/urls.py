'''project URL Configuration

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
'''
from django.conf import settings
from django.conf.urls import include, url
from django.conf.urls.static import static
from django.contrib import admin
from django.views.generic.base import RedirectView

from api import urls as api_urls
from exp import urls as exp_urls
from project import settings
from web import urls as web_urls
from osf_oauth2_adapter import views as osf_oauth2_adapter_views

urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^api/', include(api_urls)),
    url(r'^accounts/social/login/cancelled/$', osf_oauth2_adapter_views.login_errored_cancelled),
    url(r'^accounts/social/login/error/$', osf_oauth2_adapter_views.login_errored_cancelled),
    url(r'^accounts/', include('allauth.urls')),
    url(r'^exp/', include(exp_urls, namespace='exp')),
    url(r'^', include('django.contrib.auth.urls')),
    url(r'^', include(web_urls, namespace='web')),
]

if settings.DEBUG:
    favicon_view = RedirectView.as_view(url='/static/images/favicon.ico', permanent=True)
    import debug_toolbar
    urlpatterns = [
        url(r'^favicon\.ico$', favicon_view),
        url(r'^__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
