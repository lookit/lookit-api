from django.urls import path, re_path
from django.views.generic.base import TemplateView

from web import views

app_name = "web"

urlpatterns = [
    path("404", TemplateView.as_view(template_name="404.html")),
    path(
        "studies/babies/",
        views.StudiesListViewBabies.as_view(),
        name="studies-list-babies",
    ),
    path(
        "studies/toddlers/",
        views.StudiesListViewToddlers.as_view(),
        name="studies-list-toddlers",
    ),
    path(
        "studies/preschoolers/",
        views.StudiesListViewPreschoolers.as_view(),
        name="studies-list-preschoolers",
    ),
    path(
        "studies/school-age-kids/",
        views.StudiesListViewSchoolAgeKids.as_view(),
        name="studies-list-school-age",
    ),
    path(
        "studies/adults/",
        views.StudiesListViewAdults.as_view(),
        name="studies-list-adults",
    ),
    path("signup/", views.ParticipantSignupView.as_view(), name="participant-signup"),
    path(
        "account/demographics/",
        views.DemographicDataUpdateView.as_view(),
        name="demographic-data-update",
    ),
    path("account/children/", views.ChildrenListView.as_view(), name="children-list"),
    path("account/add-child/", views.ChildAddView.as_view(), name="child-add"),
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
    path(
        "studies/jspsych/<uuid:uuid>/<uuid:child_id>/",
        views.JsPsychExperimentView.as_view(),
        name="jspsych-experiment",
    ),
    re_path(
        r"^studies/"
        r"(?P<uuid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89ab][0-9a-fA-F]{3}-[0-9a-fA-F]{12})/"
        r"(?P<path>.*)$",
        views.ExperimentAssetsProxyView.as_view(),
        name="experiment-assets-proxy",
    ),
    path("", TemplateView.as_view(template_name="web/home.html"), name="home"),
    path("faq/", TemplateView.as_view(template_name="web/faq.html"), name="faq"),
    path(
        "privacy/",
        TemplateView.as_view(template_name="web/privacy.html"),
        name="privacy",
    ),
    path(
        "scientists/",
        views.ScientistsView.as_view(),
        name="scientists",
    ),
    path(
        "contact_us/",
        TemplateView.as_view(template_name="web/contact.html"),
        name="contact",
    ),
    path(
        "resources/",
        TemplateView.as_view(template_name="web/resources.html"),
        name="resources",
    ),
    path(
        "termsofuse/",
        TemplateView.as_view(template_name="web/termsofuse.html"),
        name="termsofuse",
    ),
    path(
        r"studies/<slug:lab_slug>/",
        views.LabStudiesListView.as_view(),
        name="lab-studies-list",
    ),
    path(
        "publications/",
        TemplateView.as_view(template_name="web/publications.html"),
        name="publications",
    ),
    path(
        "garden/",
        TemplateView.as_view(template_name="web/garden/home.html"),
        name="garden-home",
    ),
    path(
        "garden/about",
        TemplateView.as_view(template_name="web/garden/about.html"),
        name="garden-about",
    ),
    path(
        "garden/participate",
        TemplateView.as_view(template_name="web/garden/participate.html"),
        name="garden-participate",
    ),
    path(
        "garden/scientists",
        TemplateView.as_view(template_name="web/garden/scientists.html"),
        name="garden-scientists",
    ),
]
