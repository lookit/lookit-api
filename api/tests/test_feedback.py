import json
import uuid
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse

from guardian.shortcuts import assign_perm
from studies.models import Response, Study, Feedback
from accounts.models import Child, User
from django_dynamic_fixture import G


class FeedbackPostTestCase(APITestCase):
    def setUp(self):
        self.researcher = G(User, is_active=True, is_researcher=True)
        self.participant = G(User, is_active=True)
        self.child = G(Child, user=self.participant)
        self.study = G(Study, creator=self.researcher)
        self.response = G(Response, child=self.child, study=self.study)
        self.url = reverse('feedback-list',  kwargs={'version':'v1'})
        self.client = APIClient()

        self.data = {
          "data": {
            "attributes": {
              "comment": "This is a test"
            },
            "relationships": {
              "response": {
                "data": {
                  "type": "responses",
                  "id": str(self.response.uuid)
                }
              }
            },
            "type": "feedback"
          }
        }

    def testPostFeedbackUnauthenticated(self):
        assign_perm('studies.can_edit_study', self.researcher, self.study)

        api_response = self.client.post(self.url, json.dumps(self.data), content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Feedback.objects.count(), 0)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)

    def testPostFeedbackAsAdminAuthenticated(self):
        self.client.force_authenticate(user=self.researcher)
        assign_perm('studies.can_edit_study', self.researcher, self.study)

        api_response = self.client.post(self.url, json.dumps(self.data), content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Feedback.objects.count(), 1)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)

    def testPostFeedbackAsReadAuthenticated(self):
        self.client.force_authenticate(user=self.researcher)
        assign_perm('studies.can_view_study', self.researcher, self.study)

        api_response = self.client.post(self.url, json.dumps(self.data), content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Feedback.objects.count(), 0)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)

    def testPostFeedbackAsParticipant(self):
        self.client.force_authenticate(user=self.participant)

        api_response = self.client.post(self.url, json.dumps(self.data), content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Feedback.objects.count(), 0)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)

    def testPostFeedbackInvalidResponseUUID(self):
        self.client.force_authenticate(user=self.researcher)
        assign_perm('studies.can_edit_study', self.researcher, self.study)

        data = {
          "data": {
            "attributes": {
              "comment": "This is a test"
            },
            "relationships": {
              "response": {
                "data": {
                  "type": "responses",
                  "id": str(uuid.uuid4())
                }
              }
            },
            "type": "feedback"
          }
        }
        api_response = self.client.post(self.url, json.dumps(data), content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Feedback.objects.count(), 0)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)

    def testPostFeedbackInvalidType(self):
        self.client.force_authenticate(user=self.researcher)
        assign_perm('studies.can_edit_study', self.researcher, self.study)
        data = {
          "data": {
            "attributes": {
              "comment": "This is a test"
            },
            "relationships": {
              "response": {
                "data": {
                  "type": "responses",
                  "id": str(self.response.uuid)
                }
              }
            },
            "type": "hello"
          }
        }

        api_response = self.client.post(self.url, json.dumps(data), content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Feedback.objects.count(), 0)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)

    def testPostFeedbackMissingResponse(self):
        self.client.force_authenticate(user=self.researcher)
        assign_perm('studies.can_edit_study', self.researcher, self.study)
        data = {
          "data": {
            "attributes": {
              "comment": "This is a test"
            },
            "type": "feedback"
          }
        }

        api_response = self.client.post(self.url, json.dumps(data), content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Feedback.objects.count(), 0)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)

    def testPostFeedbackMissingComment(self):
        self.client.force_authenticate(user=self.researcher)
        assign_perm('studies.can_edit_study', self.researcher, self.study)
        data = {
          "data": {
            "attributes": {
            },
            "relationships": {
              "response": {
                "data": {
                  "type": "responses",
                  "id": str(self.response.uuid)
                }
              }
            },
            "type": "feedback"
          }
        }

        api_response = self.client.post(self.url, json.dumps(data), content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Feedback.objects.count(), 0)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)
