import datetime
from unittest.mock import MagicMock, PropertyMock, patch
from urllib.parse import parse_qs, urlparse

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.testcases import TestCase
from django_dynamic_fixture import G

from accounts.forms import PastStudiesFormTabChoices, StudyListSearchForm
from accounts.models import Child, User
from studies.models import Lab, Response, Study, StudyType
from web.views import (
    StudiesHistoryView,
    StudiesListView,
    create_external_response,
    get_external_url,
)


class ExternalTestCase(TestCase):
    def set_active(self, study):
        study.state = "active"
        study.save()
        return study

    def set_session(self, mock_request, return_value):
        type(mock_request).session = PropertyMock(return_value=return_value)


class ExternalStudiesViewTestCase(ExternalTestCase):
    def set_all_studies_tab(self, mock_request):
        self.set_session(
            mock_request,
            {"study_list_tabs": StudyListSearchForm.Tabs.all_studies.value[0]},
        )

    def set_lookit_studies_location(self, mock_request):
        self.set_session(
            mock_request,
            {"study_location": StudyListSearchForm.StudyLocation.lookit.value[0]},
        )

    def set_external_studies_location(self, mock_request):
        self.set_session(
            mock_request,
            {"study_location": StudyListSearchForm.StudyLocation.external.value[0]},
        )

    def set_sync_tab(self, mock_request):
        self.set_session(
            mock_request,
            {"study_list_tabs": StudyListSearchForm.Tabs.synchronous_studies.value[0]},
        )

    def set_async_tab(self, mock_request):
        self.set_session(
            mock_request,
            {"study_list_tabs": StudyListSearchForm.Tabs.asynchronous_studies.value[0]},
        )

    def test_all_studies(self):
        mock_request = MagicMock(method="GET")
        self.set_all_studies_tab(mock_request)

        # Check for reasonable language when there's no studies
        response = StudiesListView.as_view()(mock_request).render()
        self.assertEqual(200, response.status_code)
        self.assertIn(b"No studies found.", response.content)

        # Get existing lab
        lab = Lab.objects.get(name="Sandbox lab")

        # Create Frame Player study
        ember_frame_player_study_name = "Ember Frame Player Study"
        self.set_active(
            Study.objects.create(
                study_type=StudyType.get_ember_frame_player(),
                name=ember_frame_player_study_name,
                image=SimpleUploadedFile(
                    "fake_image.png", b"fake-stuff", content_type="image/png"
                ),
                public=True,
                built=True,
                lab=lab,
            )
        )

        # Check that Frame Player study is showing
        self.set_all_studies_tab(mock_request)
        response = StudiesListView.as_view()(mock_request).render()
        self.assertEqual(200, response.status_code)
        self.assertIn(ember_frame_player_study_name.encode(), response.content)

        # Create async external study
        external_study_async_name = "External Study Async"
        external_study_async = self.set_active(
            Study.objects.create(
                study_type=StudyType.get_external(),
                name=external_study_async_name,
                image=SimpleUploadedFile(
                    "fake_image.png", b"fake-stuff", content_type="image/png"
                ),
                metadata={"url": "", "scheduled": True},
                public=False,
                lab=lab,
            )
        )

        # Create sync external study
        external_study_sync_name = "External Study Sync"
        external_study_sync = self.set_active(
            Study.objects.create(
                study_type=StudyType.get_external(),
                name=external_study_sync_name,
                image=SimpleUploadedFile(
                    "fake_image.png", b"fake-stuff", content_type="image/png"
                ),
                public=False,
                metadata={"url": "", "scheduled": False},
                lab=lab,
            )
        )

        # Check that still only the Frame Player study is showing
        self.set_all_studies_tab(mock_request)
        response = StudiesListView.as_view()(mock_request).render()
        self.assertEqual(200, response.status_code)
        self.assertIn(ember_frame_player_study_name.encode(), response.content)
        self.assertNotIn(external_study_sync_name.encode(), response.content)
        self.assertNotIn(external_study_async_name.encode(), response.content)

        # Set external as public viewable
        external_study_sync.public = True
        external_study_sync.save()
        external_study_async.public = True
        external_study_async.save()

        # Check that both studies are showing
        self.set_all_studies_tab(mock_request)
        response = StudiesListView.as_view()(mock_request).render()
        self.assertEqual(200, response.status_code)
        self.assertIn(ember_frame_player_study_name.encode(), response.content)
        self.assertIn(external_study_sync_name.encode(), response.content)
        self.assertIn(external_study_async_name.encode(), response.content)

        # Check that only frame player is showing on lookit study tab
        self.set_lookit_studies_location(mock_request)
        response = StudiesListView.as_view()(mock_request).render()
        self.assertEqual(200, response.status_code)
        self.assertIn(ember_frame_player_study_name.encode(), response.content)
        self.assertNotIn(external_study_sync_name.encode(), response.content)
        self.assertNotIn(external_study_async_name.encode(), response.content)

        # Check that only external studies are showing on external tab
        self.set_external_studies_location(mock_request)
        response = StudiesListView.as_view()(mock_request).render()
        self.assertEqual(200, response.status_code)
        self.assertNotIn(ember_frame_player_study_name.encode(), response.content)
        self.assertIn(external_study_sync_name.encode(), response.content)
        self.assertIn(external_study_async_name.encode(), response.content)

        # Check that only async studies are showing on async tab
        self.set_async_tab(mock_request)
        response = StudiesListView.as_view()(mock_request).render()
        self.assertEqual(200, response.status_code)
        self.assertNotIn(ember_frame_player_study_name.encode(), response.content)
        self.assertNotIn(external_study_sync_name.encode(), response.content)
        self.assertIn(external_study_async_name.encode(), response.content)

        # Check that only sync studies are showing on sync tab.  This should include lookit studies.
        self.set_sync_tab(mock_request)
        response = StudiesListView.as_view()(mock_request).render()
        self.assertEqual(200, response.status_code)
        self.assertIn(ember_frame_player_study_name.encode(), response.content)
        self.assertIn(external_study_sync_name.encode(), response.content)
        self.assertNotIn(external_study_async_name.encode(), response.content)

    def test_studies_without_completed_consent_frame_functional(self):
        # Create user
        user = User.objects.create()

        # Create child
        child = Child.objects.create(
            user=user, birthday=datetime.date.today() - datetime.timedelta(days=365)
        )

        study_type = StudyType.get_external()

        # Create study
        study = Study.objects.create(study_type=study_type, name="1")

        view = StudiesListView()

        # Check that all studies return with no responses
        self.assertEqual(Response.objects.count(), 0)
        studies_no_ccf = view.studies_without_completed_consent_frame(
            Study.objects.all(), child
        )
        self.assertEqual(studies_no_ccf.count(), 1)

        Response.objects.create(study=study, child=child)

        # Check that all studies return even with one response for study "1"
        self.assertEqual(Response.objects.count(), 1)
        studies_no_ccf = view.studies_without_completed_consent_frame(
            Study.objects.all(), child
        )
        self.assertEqual(studies_no_ccf.count(), 1)

        # Set completed consent frame in response.
        response = Response.objects.first()
        response.completed_consent_frame = True
        response.save()

        # Check that study "1" is not returned
        studies_no_ccf = view.studies_without_completed_consent_frame(
            Study.objects.all(), child
        )
        self.assertEqual(studies_no_ccf.count(), 0)
        self.assertEqual(studies_no_ccf.filter(name="1").count(), 0)

        # Create second response without completed consent frame
        Response.objects.create(study=study, child=child)
        self.assertEqual(Response.objects.count(), 2)

        # Check that the same experiments return
        studies_no_ccf = view.studies_without_completed_consent_frame(
            Study.objects.all(), child
        )
        self.assertEqual(studies_no_ccf.count(), 0)
        self.assertEqual(studies_no_ccf.filter(name="1").count(), 0)


class StudiesHistoryViewTestCase(ExternalTestCase):
    def test_lookit_studies_history_view(self):
        # Request object
        mock_request = MagicMock(method="GET")

        # Get the lab object
        lab = Lab.objects.get(name="Sandbox lab")

        # Create frame player study
        ember_frame_player_study_name = "Ember Frame Player Study"
        frame_player_study = self.set_active(
            Study.objects.create(
                study_type=StudyType.get_ember_frame_player(),
                name=ember_frame_player_study_name,
                image=SimpleUploadedFile(
                    "fake_image.png", b"fake-stuff", content_type="image/png"
                ),
                public=True,
                built=True,
                lab=lab,
            )
        )

        # Create external study
        external_study_name = "External Study"
        external_study = self.set_active(
            Study.objects.create(
                study_type=StudyType.get_external(),
                name=external_study_name,
                image=SimpleUploadedFile(
                    "fake_image.png", b"fake-stuff", content_type="image/png"
                ),
                public=False,
                lab=lab,
            )
        )

        # Create user and attach it to the request
        user = User.objects.create()
        type(mock_request).user = PropertyMock(return_value=user)

        # Create child
        child = Child.objects.create(
            user=user, birthday=datetime.date.today() - datetime.timedelta(days=365)
        )

        # Create response for this child/study
        Response.objects.create(
            study=frame_player_study, child=child, completed_consent_frame=True
        )
        Response.objects.create(
            study=external_study, child=child, completed_consent_frame=True
        )

        # Check that lookit studies responses are on the lookit history view
        self.set_session(
            mock_request,
            {"past_studies_tabs": PastStudiesFormTabChoices.lookit_studies.value[0]},
        )
        response = StudiesHistoryView.as_view()(mock_request).render()
        self.assertEqual(200, response.status_code)
        self.assertIn(ember_frame_player_study_name.encode(), response.content)
        self.assertNotIn(external_study_name.encode(), response.content)

        # Check that lookit studies responses are on the lookit history view
        self.set_session(
            mock_request,
            {"past_studies_tabs": PastStudiesFormTabChoices.external_studies.value[0]},
        )
        response = StudiesHistoryView.as_view()(mock_request).render()
        self.assertEqual(200, response.status_code)
        self.assertNotIn(ember_frame_player_study_name.encode(), response.content)
        self.assertIn(external_study_name.encode(), response.content)

    @patch.object(StudiesHistoryView, "request", create=True)
    def test_history_view_only_users_responses(self, mock_request):

        user = G(User)
        child = G(Child, user=user)
        study = G(Study, study_type=StudyType.get_ember_frame_player())
        response = G(Response, child=child, study=study)

        other_user = G(User)
        other_child = G(Child, user=other_user)
        G(Response, child=other_child, study=study)

        type(mock_request).user = PropertyMock(return_value=user)
        view = StudiesHistoryView()

        # There are two responses
        self.assertEqual(Response.objects.count(), 2)

        # We only get back the response for our "logged in" user
        self.assertEqual(list(view.get_queryset()), [response.study])


class ExternalResponseTestCase(TestCase):
    def test_create_external_response(self):
        child = G(Child)
        study = G(Study, study_type=StudyType.get_external())
        response = create_external_response(study, child.uuid)

        # Verify response was created correctly
        self.assertEqual(child, response.child)
        self.assertEqual(study, response.study)
        self.assertEqual(study.study_type, response.study_type)
        self.assertFalse(response.is_preview)

        # Verify preview response
        response = create_external_response(study, child.uuid, preview=True)
        self.assertTrue(response.is_preview)

    def test_get_external_url(self):
        url = "https://lookit.mit.edu/"
        study = G(Study, metadata={"url": url}, study_type=StudyType.get_external())
        child = G(Child)
        response = G(Response, child=child, study=study)
        external_url = get_external_url(study, response)
        parsed = urlparse(external_url)
        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}{parsed.path}", url)
        query = parse_qs(parsed.query)

        # Verify response uuid is in query string
        self.assertEqual(query["response"], [str(response.uuid)])
        # Verify child key in query string
        self.assertIn("child", query)
