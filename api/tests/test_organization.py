import json
import uuid

from django.test import TestCase
from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import Child, User
from studies.models import Feedback, Response, Study


# TODO: remove or update for lab
class OrganizationTestCase(APITestCase):
    def setUp(self):
        self.organization = G(Organization, name="COS")
        self.researcher = G(User, is_active=True, is_researcher=True)
        self.participant = G(User, is_active=True)
        self.url = (
            reverse("api:organization-list", kwargs={"version": "v1"})
            + str(self.organization.uuid)
            + "/"
        )
        self.client = APIClient()

    def testGetOrganizationDetailUnauthenticated(self):
        # Must be authenticated to view organization
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetOrganizationDetailParticipant(self):
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["name"], "COS")

    def testGetOrganizationDetailResearcher(self):
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["name"], "COS")

    def testPostOrganization(self):
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.post(
            reverse("api:organization-list", kwargs={"version": "v1"}),
            content_type="application/vnd.api+json",
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def testUpdateOrganization(self):
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.patch(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def testDeleteOrganization(self):
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.delete(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
