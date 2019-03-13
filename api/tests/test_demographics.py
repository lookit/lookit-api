import json
import uuid

from django.test import TestCase
from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import Child, DemographicData, User
from studies.models import Feedback, Response, Study, ConsentRuling


class DemographicsTestCase(APITestCase):
    def setUp(self):
        self.researcher = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 1"
        )
        self.participant = G(User, is_active=True, given_name="Participant 1")
        self.demographics = G(
            DemographicData, user=self.participant, languages_spoken_at_home="French"
        )
        self.child = G(Child, user=self.participant, given_name="Sally")
        self.study = G(Study, creator=self.researcher)
        self.response = G(
            Response,
            child=self.child,
            study=self.study,
            demographic_snapshot=self.demographics,
            completed_consent_frame=True
        )
        self.positive_consent_ruling = G(
            ConsentRuling,
            study=self.study,
            response=self.response,
            action="accepted")
        self.url = "/api/v1/demographics/"
        self.demo_data_url = f"/api/v1/demographics/{str(self.demographics.uuid)}/"
        self.client = APIClient()

    # Demographics GET LIST Tests
    def testGetDemographicsListUnauthenticated(self):
        # Must be authenticated to view demographic data
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetDemographicsInactiveUsers(self):
        # Inactive users' demographic data does not show up in API
        self.participant.is_active = True
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 0)

    def testParticipantCanViewOwnDemographicData(self):
        # As a participant, can view your own demographic data
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            api_response.data["results"][0]["languages_spoken_at_home"], "French"
        )

    def testGetDemographicsIncorrectPermissions(self):
        # Can_view_study permissions not sufficient for viewing demographics
        assign_perm("studies.can_view_study", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 0)

    def testGetDemographicsListWithCanViewStudyResponsesPermissions(self):
        # As a researcher, need can_view_study_responses permissions to view demographics
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            api_response.data["results"][0]["languages_spoken_at_home"], "French"
        )

    def testSuperusersCanViewAllDemographics(self):
        # Superusers can see all demographics of active participants
        self.superuser = G(User, is_active=True, is_researcher=True, is_superuser=True)
        self.demographics2 = G(
            DemographicData, user=self.researcher, languages_spoken_at_home="English"
        )
        self.client.force_authenticate(user=self.superuser)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertGreater(api_response.data["links"]["meta"]["count"], 1)

    # Demo Data GET Detail Tests
    def testGetDemographicsDetailUnauthenticated(self):
        # Must be authenticated to view demographic data
        api_response = self.client.get(
            self.demo_data_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetInactiveUserDemographicData(self):
        # An inactive user's demographic data can't be retrieved
        self.participant.is_active = False
        self.participant.save()
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.demo_data_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testParticipantCanViewOwnDemographicData(self):
        # As a participant, can view own demographic data
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.demo_data_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["languages_spoken_at_home"], "French")

    #
    def testGetDemographicDataIncorrectPermissions(self):
        # Can_view_study permissions not sufficient for viewing participants
        assign_perm("studies.can_view_study", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.demo_data_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testGetDemographicDataWithCanViewStudyResponsesPermissions(self):
        # As a researcher, need can_view_study_responses permissions to view demo data
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.demo_data_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["languages_spoken_at_home"], "French")

    # POST Demo Data Tests
    def testPostDemoData(self):
        # Cannot POST to users
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.post(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # PATCH Demo Data Tests
    def testUpdateDemoData(self):
        # Cannot Update Demo Data
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.patch(
            self.demo_data_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # DELETE Demo Data Tests
    def testDeleteDemoData(self):
        # Cannot Delete Demo Data
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.delete(
            self.demo_data_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
