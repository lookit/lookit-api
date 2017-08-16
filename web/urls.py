from django.conf.urls import include, url
from django.contrib.flatpages import views as flatpages_views

from web import views

urlpatterns = [
    url(r'^signup/$', views.ParticipantSignupView.as_view(), name='participant-signup'),
    url(r'^account/$', views.ParticipantUpdateView.as_view(), name='participant-update'),
    url(r'^account/demographics/$', views.DemographicDataUpdateView.as_view(), name='demographic-data-update'),
    url(r'^account/children/$', views.ChildrenListView.as_view(), name='children-list'),
    url(r'^account/children/(?P<uuid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89ab][0-9a-fA-F]{3}-[0-9a-fA-F]{12})/$', views.ChildUpdateView.as_view(), name='child-update'),
    url(r'^account/email/$', views.ParticipantEmailPreferencesView.as_view(), name='email-preferences'),
    url(r'^studies/$', views.StudiesListView.as_view(), name='studies-list'),
    url(r'^studies/(?P<uuid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89ab][0-9a-fA-F]{3}-[0-9a-fA-F]{12})/$', views.StudyDetailView.as_view(), name='study-detail'),
    url(r'^studies/(?P<path>(?P<uuid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89ab][0-9a-fA-F]{3}-[0-9a-fA-F]{12})/(?P<child_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89ab][0-9a-fA-F]{3}-[0-9a-fA-F]{12}))/$', views.ExperimentProxyView.as_view(), name='experiment-proxy'),
    url(r'^studies/(?P<path>(?P<uuid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89ab][0-9a-fA-F]{3}-[0-9a-fA-F]{12}))/.*$', views.ExperimentAssetsProxyView.as_view(), name='experiment-assets-proxy'),
    url(r'^faq/$', flatpages_views.flatpage, dict(url='/faq/'), name='faq'),
    url(r'^scientists/$', flatpages_views.flatpage, dict(url='/scientists/'), name='scientists'),
    url(r'^resources/$', flatpages_views.flatpage, dict(url='/resources/'), name='resources'),
    url(r'^contact_us/$', flatpages_views.flatpage, dict(url='/contact_us/'), name='contact_us'),
    url(r'^(?P<path>assets/.*)$', views.ExperimentAssetsProxyView.as_view(), name='experiment-assets-proxy'),
    url(r'^(?P<path>fonts/.*)$', views.ExperimentAssetsProxyView.as_view(), name='experiment-fonts-proxy'),
    url(r'^$', flatpages_views.flatpage, dict(url=''), name='home'),
    url(r'^(?P<path>.*)$', views.ExperimentAssetsProxyView.as_view(), name='experiment-catchall-proxy'),
]
