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
from django.conf.urls import url

from exp.views import (AssignUserStudies, UserCreateView, UserDetailView,
                       UserListView)

urlpatterns = [
    url(r'collaborators/create/$', UserCreateView.as_view(), name='collaborator-create'),
    url(r'collaborators/(?P<pk>\d+)/$', UserDetailView.as_view(), name='collaborator-detail'),
    url(r'collaborators/$', UserListView.as_view(), name='collaborator-list'),
    url(r'collaborators/(?P<pk>\d+)/assign-studies/$', AssignUserStudies.as_view(), name='assign-studies'),
]
