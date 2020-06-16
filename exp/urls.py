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
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from exp.views import (
    ExperimenterDashboardView,
    LabCreateView,
    LabDetailView,
    LabListView,
    LabMembershipRequestView,
    LabMembersView,
    LabUpdateView,
    ParticipantDetailView,
    ParticipantListView,
    PreviewProxyView,
    RenameVideoView,
    StudyAttachments,
    StudyBuildView,
    StudyChildrenSummaryCSV,
    StudyChildrenSummaryDictCSV,
    StudyCollisionCheck,
    StudyCreateView,
    StudyDemographics,
    StudyDemographicsDownloadCSV,
    StudyDemographicsDownloadDictCSV,
    StudyDemographicsDownloadJSON,
    StudyDetailView,
    StudyListView,
    StudyParticipantAnalyticsView,
    StudyParticipantContactView,
    StudyPreviewDetailView,
    StudyResponsesAll,
    StudyResponsesAllDownloadJSON,
    StudyResponsesConsentManager,
    StudyResponsesFrameDataCSV,
    StudyResponsesFrameDataDictCSV,
    StudyResponsesFrameDataIndividualCSV,
    StudyResponsesList,
    StudyResponsesSummaryDictCSV,
    StudyResponsesSummaryDownloadCSV,
    StudyUpdateView,
)

app_name = "exp"

urlpatterns = [
    path("labs/", LabListView.as_view(), name="lab-list"),
    path("labs/create/", LabCreateView.as_view(), name="lab-create"),
    path("labs/<int:pk>/", LabDetailView.as_view(), name="lab-detail"),
    path("labs/<int:pk>/edit/", LabUpdateView.as_view(), name="lab-edit"),
    path("labs/<int:pk>/members/", LabMembersView.as_view(), name="lab-members"),
    path(
        "labs/request/<int:pk>/", LabMembershipRequestView.as_view(), name="lab-request"
    ),
    path("participants/", ParticipantListView.as_view(), name="participant-list"),
    path(
        "participants/<int:pk>/",
        ParticipantDetailView.as_view(),
        name="participant-detail",
    ),
    path("renamevideo/", csrf_exempt(RenameVideoView.as_view()), name="rename-video"),
    path("studies/", StudyListView.as_view(), name="study-list"),
    path(
        "studies/analytics/",
        StudyParticipantAnalyticsView.as_view(),
        name="study-participant-analytics",
    ),
    path(r"studies/create/", StudyCreateView.as_view(), name="study-create"),
    path(r"studies/<int:pk>/", StudyDetailView.as_view(), name="study-detail"),
    path(
        "studies/<int:pk>/contact/",
        StudyParticipantContactView.as_view(),
        name="study-participant-contact",
    ),
    path("studies/<int:pk>/edit/", StudyUpdateView.as_view(), name="study-edit"),
    path(
        "studies/<int:pk>/responses/",
        StudyResponsesList.as_view(),
        name="study-responses-list",
    ),
    path(
        "studies/<int:pk>/responses/all/",
        StudyResponsesAll.as_view(),
        name="study-responses-all",
    ),
    path(
        "studies/<int:pk>/responses/consent_videos/",
        StudyResponsesConsentManager.as_view(),
        name="study-responses-consent-manager",
    ),
    path(
        "studies/<int:pk>/responses/all/download_json/",
        StudyResponsesAllDownloadJSON.as_view(),
        name="study-responses-download-json",
    ),
    path(
        "studies/<int:pk>/responses/all/download_summary_csv/",
        StudyResponsesSummaryDownloadCSV.as_view(),
        name="study-responses-download-csv",
    ),
    path(
        "studies/<int:pk>/responses/all/download_summary_dict_csv/",
        StudyResponsesSummaryDictCSV.as_view(),
        name="study-responses-download-summary-dict-csv",
    ),
    path(
        "studies/<int:pk>/responses/all/download_summary_children_csv/",
        StudyChildrenSummaryCSV.as_view(),
        name="study-responses-children-summary-csv",
    ),
    path(
        "studies/<int:pk>/responses/all/download_summary_children_dict_csv/",
        StudyChildrenSummaryDictCSV.as_view(),
        name="study-responses-children-summary-dict-csv",
    ),
    path(
        "studies/<int:pk>/responses/all/collision_check/",
        StudyCollisionCheck.as_view(),
        name="study-hashed-id-collision-check",
    ),
    path(
        "studies/<int:pk>/responses/all/download_frame_csv/",
        StudyResponsesFrameDataCSV.as_view(),
        name="study-responses-download-frame-data-csv",
    ),
    path(
        "studies/<int:pk>/responses/all/download_frame_zip_csv/",
        StudyResponsesFrameDataIndividualCSV.as_view(),
        name="study-responses-download-frame-data-zip-csv",
    ),
    path(
        "studies/<int:pk>/responses/all/download_frame_dict_csv/",
        StudyResponsesFrameDataDictCSV.as_view(),
        name="study-responses-download-frame-data-dict-csv",
    ),
    path(
        "studies/<int:pk>/responses/demographics/",
        StudyDemographics.as_view(),
        name="study-demographics",
    ),
    path(
        "studies/<int:pk>/responses/demographics/download_json/",
        StudyDemographicsDownloadJSON.as_view(),
        name="study-demographics-download-json",
    ),
    path(
        "studies/<int:pk>/responses/demographics/download_csv/",
        StudyDemographicsDownloadCSV.as_view(),
        name="study-demographics-download-csv",
    ),
    path(
        "studies/<int:pk>/responses/demographics/download_csv_dict/",
        StudyDemographicsDownloadDictCSV.as_view(),
        name="study-demographics-download-dict-csv",
    ),
    path(
        "studies/<int:pk>/responses/attachments/",
        StudyAttachments.as_view(),
        name="study-attachments",
    ),
    path("studies/<uuid:uuid>/build/", StudyBuildView.as_view(), name="study-build"),
    path(
        "studies/<uuid:uuid>/preview-detail/",
        StudyPreviewDetailView.as_view(),
        name="preview-detail",
    ),
    path(
        "studies/<uuid:uuid>/<uuid:child_id>/preview/",
        PreviewProxyView.as_view(),
        name="preview-proxy",
    ),
    path("", ExperimenterDashboardView.as_view(), name="dashboard"),
]
