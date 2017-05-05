from django.conf.urls import include, url

from web import views

urlpatterns = [
    url(r'^signup/?$', views.ParticipantSignupView.as_view(), name='participant-signup'),
    url(r'^demographic_data/?$', views.DemographicDataCreateView.as_view(), name='demographic-data-create'),
    url(r'^studies/?$', views.StudiesListView.as_view(), name='studies-list'),
    url(r'^studies/(?P<pk>\d+)/$', views.StudyDetailView.as_view(), name='study-detail'),
    url('^', include('django.contrib.auth.urls')),
    url(r'', views.HomeView.as_view(), name='home'),
]
