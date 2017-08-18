import json
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse

from guardian.shortcuts import assign_perm
from studies.models import Response, Study, Feedback
from accounts.models import Child, User
from django_dynamic_fixture import G

# class FilterByUrlKwargsMixinTestCase(TestCase):
#     def test_child_user(self):
#         user = G(User)
#         barren_user = G(User)
#         child = G(Child, user=user)
#
#         client = APIClient()
#
#         response = client.get(f'/api/v1/children/{child.uuid}/users/', format='json')
#         import ipdb; ipdb.set_trace()

class FeedbackTestCase(APITestCase):
    def setUp(self):
        self.researcher = G(User, is_active=True)
        self.participant = G(User)
        self.child = G(Child, user=self.participant)
        self.study = G(Study, creator=self.researcher)
        self.response = G(Response, child=self.child, study=self.study)
        self.url = reverse('feedback-list',  kwargs={'version':'v1'})
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
        client = APIClient()
        assign_perm('studies.can_edit_study', self.researcher, self.study)

        api_response = client.post(self.url, json.dumps(self.data), content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Feedback.objects.count(), 0)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)

    def testPostFeedbackAsAdminAuthenticated(self):
        client = APIClient()
        client.force_authenticate(user=self.researcher)
        assign_perm('studies.can_edit_study', self.researcher, self.study)

        api_response = client.post(self.url, json.dumps(self.data), content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Feedback.objects.count(), 1)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Study.objects.count(), 1)
