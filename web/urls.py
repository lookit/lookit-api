from django.conf.urls import include, url
from django.contrib.flatpages import views as flatpages_views

from web import views

urlpatterns = [
    url(r'^signup/?$', views.ParticipantSignupView.as_view(), name='participant-signup'),
    url(r'^demographic_data/?$', views.DemographicDataCreateView.as_view(), name='demographic-data-create'),
    url(r'^studies/?$', views.StudiesListView.as_view(), name='studies-list'),
    url(r'^studies/(?P<pk>\d+)/$', views.StudyDetailView.as_view(), name='public-study-detail'),
    url(r'^faq/?$', flatpages_views.flatpage, dict(url='/faq/'), name='faq'),
    url(r'^scientists/?$', flatpages_views.flatpage, dict(url='/scientists/'), name='scientists'),
    url(r'^resources/?$', flatpages_views.flatpage, dict(url='/resources/'), name='resources'),
    url(r'^contact_us/?$', flatpages_views.flatpage, dict(url='/contact_us/'), name='contact_us'),
    url('^', include('django.contrib.auth.urls')),
    url(r'^$', flatpages_views.flatpage, dict(url='/'), name='home'),
]
