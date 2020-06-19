from django.contrib.flatpages import views as flatpages_views
from django.urls import path, re_path

from web import views

app_name = "web"

urlpatterns = [
    path("signup/", views.ParticipantSignupView.as_view(), name="participant-signup"),
    path("account/", views.ParticipantUpdateView.as_view(), name="participant-update"),
    path(
        "account/demographics/",
        views.DemographicDataUpdateView.as_view(),
        name="demographic-data-update",
    ),
    path("account/children/", views.ChildrenListView.as_view(), name="children-list"),
    path(
        "account/children/<uuid:uuid>/",
        views.ChildUpdateView.as_view(),
        name="child-update",
    ),
    path(
        "account/email/",
        views.ParticipantEmailPreferencesView.as_view(),
        name="email-preferences",
    ),
    path("studies/", views.StudiesListView.as_view(), name="studies-list"),
    path(
        "studies/history/", views.StudiesHistoryView.as_view(), name="studies-history",
    ),
    path("studies/<uuid:uuid>/", views.StudyDetailView.as_view(), name="study-detail",),
    path(
        "studies/<uuid:uuid>/<uuid:child_id>/",
        views.ExperimentProxyView.as_view(),
        name="experiment-proxy",
    ),
    re_path(
        r"^studies/(?P<path>(?P<uuid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89ab][0-9a-fA-F]{3}-[0-9a-fA-F]{12}))/.*$",
        views.ExperimentAssetsProxyView.as_view(),
        name="experiment-assets-proxy",
    ),
    path("faq/", flatpages_views.flatpage, dict(url="/faq/"), name="faq"),
    path(
        "scientists/",
        flatpages_views.flatpage,
        dict(url="/scientists/"),
        name="scientists",
    ),
    path(
        "resources/",
        flatpages_views.flatpage,
        dict(url="/resources/"),
        name="resources",
    ),
    path(
        "contact_us/",
        flatpages_views.flatpage,
        dict(url="/contact_us/"),
        name="contact_us",
    ),
    re_path(
        r"^(?P<path>assets/.*)$",
        views.ExperimentAssetsProxyView.as_view(),
        name="experiment-assets-proxy",
    ),
    re_path(
        r"^(?P<path>fonts/.*)$",
        views.ExperimentAssetsProxyView.as_view(),
        name="experiment-fonts-proxy",
    ),
    path("", flatpages_views.flatpage, dict(url=""), name="home"),
    re_path(
        r"^(?P<path>(?P<filename>avc_settings\.(php|asp)|loading\.swf|translations\/.*|audio_video_quality_profiles\/.*))$",
        views.ExperimentAssetsProxyView.as_view(),
        name="experiment-assets-proxy",
    ),
]
