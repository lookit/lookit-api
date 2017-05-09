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
from django.conf.urls import include, url

from exp.views import (AssignUserStudies, ExperimenterDashboard,
                       OrganizationCreateView, OrganizationListView,
                       StudyCreateView, StudyDetailView, StudyListView,
                       UserCreateView, UserDetailView, UserListView)

urlpatterns = [
    url(r'organizations/$', OrganizationListView.as_view(), name='organization-list'),
    url(r'organizations/create/$', OrganizationCreateView.as_view(), name='organization-create'),
    url(r'collaborators/create/$', UserCreateView.as_view(), name='collaborator-create'),
    url(r'collaborators/(?P<pk>\d+)/$', UserDetailView.as_view(), name='collaborator-detail'),
    url(r'collaborators/$', UserListView.as_view(), name='collaborator-list'),
    url(r'collaborators/(?P<pk>\d+)/assign-studies/$', AssignUserStudies.as_view(), name='assign-studies'),
    url(r'studies/$', StudyListView.as_view(), name='study-list'),
    url(r'studies/create/$', StudyCreateView.as_view(), name='study-create'),
    url(r'studies/(?P<pk>\d+)/$', StudyDetailView.as_view(), name='study-detail'),
    url(r'', ExperimenterDashboard.as_view(), name='dashboard')
]
