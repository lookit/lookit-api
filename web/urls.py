from django.contrib.flatpages import views as flatpages_views
from django.urls import path, re_path

from web import views

app_name = "web"

urlpatterns = [
    path("signup/", views.ParticipantSignupView.as_view(), name="participant-signup"),
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
        "studies/history/", views.StudiesHistoryView.as_view(), name="studies-history"
    ),
    path("studies/<uuid:uuid>/", views.StudyDetailView.as_view(), name="study-detail"),
    path(
        "studies/<uuid:uuid>/<uuid:child_id>/",
        views.ExperimentProxyView.as_view(),
        name="experiment-proxy",
    ),
    re_path(
        r"^studies/"
        r"(?P<uuid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89ab][0-9a-fA-F]{3}-[0-9a-fA-F]{12})/"
        r"(?P<path>.*)$",
        views.ExperimentAssetsProxyView.as_view(),
        name="experiment-assets-proxy",
    ),
    path("", views.HomeView.as_view(), name="home"),
    path("faq/", views.FAQView.as_view(), name="faq"),
    path("privacy/", views.PrivacyView.as_view(), name="privacy"),
    path("scientists/", views.ScientistsView.as_view(), name="scientists"),
    path("contact_us/", views.ContactView.as_view(), name="contact"),
    # Remaining flat pages
    path(
        "resources/",
        flatpages_views.flatpage,
        dict(url="/en-us/resources/"),
        name="resources",
    ),
    path(
        "termsofuse/",
        flatpages_views.flatpage,
        dict(url="/en-us/termsofuse/"),
        name="termsofuser",
    ),
]
