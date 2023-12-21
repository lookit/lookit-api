import json
import uuid

from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import Child, User
from studies.models import ConsentRuling, Feedback, Lab, Response, Study, StudyType
from studies.permissions import LabPermission, StudyPermission


class FeedbackTestCase(APITestCase):
    def setUp(self):
        self.researcher = G(User, is_active=True, is_researcher=True)
        self.participant = G(User, is_active=True)
        self.child = G(Child, user=self.participant)
        self.lab = G(Lab, name="MIT")
        self.lab.researchers.add(self.researcher)
        self.lab.save()
        self.study = G(
            Study,
            creator=self.researcher,
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )
        # completed_consent_frame is important - won't be included in queryset regardless of consent ruling if not
        self.response = G(
            Response,
            child=self.child,
            study=self.study,
            is_preview=False,
            completed_consent_frame=True,
        )
        self.positive_consent_ruling = G(
            ConsentRuling, response=self.response, action="accepted"
        )
        self.feedback = G(
            Feedback,
            response=self.response,
            researcher=self.researcher,
            comment="This was very helpful.",
        )
        self.url = reverse("api:feedback-list", kwargs={"version": "v1"})
        self.client = APIClient()

        self.data = {
            "data": {
                "attributes": {"comment": "This is a test"},
                "relationships": {
                    "response": {
                        "data": {"type": "responses", "id": str(self.response.uuid)}
                    }
                },
                "type": "feedback",
            }
        }

    # Feedback GET LIST Tests
    def testGetFeedbackListUnauthenticated(self):
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetFeedbackListWithReadStudyResponsePermissions(self):
        # Researcher should be able to read existing feedback along with other response data
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 1)

    def testGetFeedbackListWithLabwideReadResponsePermissions(self):
        # Lab-wide response data read perms also grant access to feedback on this study
        assign_perm(
            LabPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study.lab,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 1)

    def testGetFeedbackListWithIncorrectPermissions(self):
        # None of these perms/groups should grant access
        assign_perm(
            LabPermission.READ_STUDY_DETAILS.prefixed_codename,
            self.researcher,
            self.study.lab,
        )
        self.study.lab.admin_group.user_set.add(self.researcher)
        self.study.lab.save()
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 0)

    def testGetFeedbackListAsParticipant(self):
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 1)

    def testGetFeedbackListAsUnaffiliatedParticipant(self):
        self.participant2 = G(User, is_active=True)
        self.client.force_authenticate(user=self.participant2)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 0)

    # Feedback GET DETAIL Tests
    def testGetFeedbackDetailUnauthenticated(self):
        api_response = self.client.get(
            self.url + str(self.feedback.uuid) + "/",
            content_type="application/vnd.api+json",
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetFeedbackDetailWithResponseReadPerms(self):
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url + str(self.feedback.uuid) + "/",
            content_type="application/vnd.api+json",
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["comment"], self.feedback.comment)

    def testGetFeedbackDetailWithLabwideResponseReadPerms(self):
        assign_perm(
            LabPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study.lab,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url + str(self.feedback.uuid) + "/",
            content_type="application/vnd.api+json",
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["comment"], self.feedback.comment)

    def testGetFeedbackDetailWithInsufficientPerms(self):
        # None of the following should be sufficient to look up feedback
        assign_perm(
            StudyPermission.READ_STUDY_DETAILS.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            LabPermission.READ_STUDY_DETAILS.prefixed_codename,
            self.researcher,
            self.study.lab,
        )
        self.study.design_group.user_set.add(self.researcher)
        self.study.lab.admin_group.user_set.add(self.researcher)
        self.study.save()
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url + str(self.feedback.uuid) + "/",
            content_type="application/vnd.api+json",
        )
        # Is throwing Not Found because feedback not in queryset that user can access
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testGetFeedbackDetailAsParticipant(self):
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.url + str(self.feedback.uuid) + "/",
            content_type="application/vnd.api+json",
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["comment"], self.feedback.comment)

    def testGetFeedbackDetailAsUnaffiliatedParticipant(self):
        self.participant2 = G(User, is_active=True)
        self.client.force_authenticate(user=self.participant2)
        api_response = self.client.get(
            self.url + str(self.feedback.uuid) + "/",
            content_type="application/vnd.api+json",
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    # Feedback POST Tests
    def testPostFeedbackUnauthenticated(self):
        api_response = self.client.post(
            self.url, json.dumps(self.data), content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            Feedback.objects.count(), 1
        )  # only single feedback already there
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)

    def testPostFeedbackWithEditFeedbackPerms(self):
        # edit_study_feedback perms allow creating new feedback
        assign_perm(
            StudyPermission.EDIT_STUDY_FEEDBACK.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.post(
            self.url, json.dumps(self.data), content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Feedback.objects.count(), 2)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)

    def testPostFeedbackWithReadResponsePerms(self):
        # Need edit_study_feedback perms to create new feedback
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.post(
            self.url, json.dumps(self.data), content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Feedback.objects.count(), 1)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)

    def testPostFeedbackAsParticipant(self):
        self.client.force_authenticate(user=self.participant)

        api_response = self.client.post(
            self.url, json.dumps(self.data), content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Feedback.objects.count(), 1)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)

    def testPostFeedbackBadResponseUUID(self):
        self.client.force_authenticate(user=self.researcher)
        assign_perm(
            StudyPermission.EDIT_STUDY_FEEDBACK.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        data = {
            "data": {
                "attributes": {"comment": "This is a test"},
                "relationships": {
                    "response": {"data": {"type": "responses", "id": str(uuid.uuid4())}}
                },
                "type": "feedback",
            }
        }
        api_response = self.client.post(
            self.url, json.dumps(data), content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Feedback.objects.count(), 1)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)

    def testPostFeedbackInvalidType(self):
        self.client.force_authenticate(user=self.researcher)
        assign_perm(
            StudyPermission.EDIT_STUDY_FEEDBACK.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        data = {
            "data": {
                "attributes": {"comment": "This is a test"},
                "relationships": {
                    "response": {
                        "data": {"type": "responses", "id": str(self.response.uuid)}
                    }
                },
                "type": "hello",
            }
        }

        api_response = self.client.post(
            self.url, json.dumps(data), content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Feedback.objects.count(), 1)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)

    def testPostFeedbackMissingResponse(self):
        self.client.force_authenticate(user=self.researcher)
        assign_perm(
            StudyPermission.EDIT_STUDY_FEEDBACK.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        data = {
            "data": {"attributes": {"comment": "This is a test"}, "type": "feedback"}
        }

        api_response = self.client.post(
            self.url, json.dumps(data), content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Feedback.objects.count(), 1)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)

    def testPostFeedbackMissingComment(self):
        self.client.force_authenticate(user=self.researcher)
        assign_perm(
            StudyPermission.EDIT_STUDY_FEEDBACK.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        data = {
            "data": {
                "attributes": {},
                "relationships": {
                    "response": {
                        "data": {"type": "responses", "id": str(self.response.uuid)}
                    }
                },
                "type": "feedback",
            }
        }

        api_response = self.client.post(
            self.url, json.dumps(data), content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Feedback.objects.count(), 1)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)

    def testPatchFeedback(self):
        self.client.force_authenticate(user=self.researcher)
        assign_perm(
            StudyPermission.EDIT_STUDY_FEEDBACK.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        data = {
            "data": {
                "attributes": {"comment": "changed feedback"},
                "relationships": {
                    "response": {
                        "data": {"type": "responses", "id": str(self.response.uuid)}
                    }
                },
                "type": "feedback",
                "id": str(self.feedback.uuid),
            }
        }

        api_response = self.client.patch(
            self.url + str(self.feedback.uuid) + "/",
            json.dumps(data),
            content_type="application/vnd.api+json",
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["comment"], "changed feedback")

    def testDeleteFeedback(self):
        self.client.force_authenticate(user=self.researcher)
        assign_perm(
            StudyPermission.EDIT_STUDY_FEEDBACK.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )

        api_response = self.client.delete(
            self.url + str(self.feedback.uuid) + "/",
            content_type="application/vnd.api+json",
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
