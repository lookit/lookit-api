from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import User
from studies.models import Lab


class LabTestCase(APITestCase):
    def setUp(self):
        self.lab = G(Lab, name="ECCL", approved_to_test=True)
        self.lab2 = G(Lab, name="Practice lab")
        self.researcher = G(User, is_active=True, is_researcher=True)
        self.superuser = G(User, is_active=True, is_researcher=True, is_superuser=True)
        self.participant = G(User, is_active=True)
        self.url = (
            reverse("api:lab-list", kwargs={"version": "v1"}) + str(self.lab.uuid) + "/"
        )
        self.client = APIClient()

    def testGetLabDetailUnauthenticated(self):
        # Must be authenticated to view organization
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetLabDetailParticipant(self):
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["name"], self.lab.name)

    def testGetLabDetailResearcher(self):
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["name"], self.lab.name)

    def testGetLabListResearcher(self):
        # Should only be able to get 1 (approved) lab
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            reverse("api:lab-list", kwargs={"version": "v1"}),
            content_type="application/vnd.api+json",
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        # Migration adds one approved lab so we see two, but not the unapproved one added in setup
        self.assertEqual(api_response.data["links"]["meta"]["count"], 2)
        self.assertNotIn(
            "Practice lab", [lab["name"] for lab in api_response.data["results"]]
        )

    def testPostLab(self):
        self.client.force_authenticate(user=self.superuser)
        api_response = self.client.post(
            reverse("api:lab-list", kwargs={"version": "v1"}),
            content_type="application/vnd.api+json",
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def testUpdateLab(self):
        self.client.force_authenticate(user=self.superuser)
        api_response = self.client.patch(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def testDeleteLab(self):
        self.client.force_authenticate(user=self.superuser)
        api_response = self.client.delete(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
