from unittest.mock import MagicMock, PropertyMock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.testcases import TestCase

from accounts.forms import PastStudiesFormTabChoices, StudyListSearchFormTabChoices
from accounts.models import Child, User
from studies.models import Lab, Response, Study, StudyType
from web.views import StudiesHistoryView, StudiesListView


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
            {"study_list_tabs": StudyListSearchFormTabChoices.all_studies.value[0]},
        )

    def set_lookit_studies_tab(self, mock_request):
        self.set_session(
            mock_request,
            {"study_list_tabs": StudyListSearchFormTabChoices.lookit_studies.value[0]},
        )

    def set_external_studies_tab(self, mock_request):
        self.set_session(
            mock_request,
            {
                "study_list_tabs": StudyListSearchFormTabChoices.external_studies.value[
                    0
                ]
            },
        )

    def set_sync_tab(self, mock_request):
        self.set_session(
            mock_request,
            {
                "study_list_tabs": StudyListSearchFormTabChoices.synchronous_studies.value[
                    0
                ]
            },
        )

    def set_async_tab(self, mock_request):
        self.set_session(
            mock_request,
            {
                "study_list_tabs": StudyListSearchFormTabChoices.asynchronous_studies.value[
                    0
                ]
            },
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
        self.set_lookit_studies_tab(mock_request)
        response = StudiesListView.as_view()(mock_request).render()
        self.assertEqual(200, response.status_code)
        self.assertIn(ember_frame_player_study_name.encode(), response.content)
        self.assertNotIn(external_study_sync_name.encode(), response.content)
        self.assertNotIn(external_study_async_name.encode(), response.content)

        # Check that only external studies are showing on external tab
        self.set_external_studies_tab(mock_request)
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


class ExternalParticipantHistoryTestCase(ExternalTestCase):
    def test_lookit_studies_history(self):
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
        child = Child.objects.create(user=user)

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
