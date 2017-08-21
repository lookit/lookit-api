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


class UserTestCase(APITestCase):
    def setUp(self):
        self.researcher = G(User, is_active=True, is_researcher=True, given_name="Researcher 1")
        self.participant = G(User, is_active=True, given_name="Participant 1")
        self.child = G(Child, user=self.participant, given_name='Sally')
        self.study = G(Study, creator=self.researcher)
        self.response = G(Response, child=self.child, study=self.study)
        self.url = reverse('user-list',  kwargs={'version':'v1'})
        self.user_detail_url = reverse('user-list',  kwargs={'version':'v1'}) + str(self.participant.uuid) + '/'
        self.client = APIClient()

    # Participant GET LIST Tests
    def testGetParticipantListUnauthenticated(self):
        # Must be authenticated to view participants
        api_response = self.client.get(self.url, content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetResearchersInParticipantList(self):
        # Researchers do not show up in user list, only participants
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(self.url, content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data['links']['meta']['count'], 0)

    def testParticipantCanViewThemselves(self):
        # As a participant, can view yourself
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(self.url, content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data['results'][0]['given_name'], "Participant 1")

    def testGetParticipantsIncorrectPermissions(self):
        # Can_view_study permissions not sufficient for viewing participants
        assign_perm('studies.can_view_study', self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(self.url, content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data['links']['meta']['count'], 0)

    def testGetParticipantListCanViewStudyResponsesPermissions(self):
        # As a researcher, need can_view_study_responses permissions to view participants
        assign_perm('studies.can_view_study_responses', self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(self.url, content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data['results'][0]['given_name'], "Participant 1")

    # Participant GET Detail Tests
    def testGetParticipantDetailUnauthenticated(self):
        # Must be authenticated to view participants
        api_response = self.client.get(self.user_detail_url, content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetResearcherDetail(self):
        # Researchers do not show up in user list, only participants
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(str(self.researcher.uuid) + '/', content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testParticipantCanViewOwnDetailEndpoint(self):
        # As a participant, can view yourself
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(self.user_detail_url, content_type="application/vnd.api+json")
        print(self.user_detail_url)

        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data['given_name'], "Participant 1")

    def testGetParticipantDetailIncorrectPermissions(self):
        # Can_view_study permissions not sufficient for viewing participants
        assign_perm('studies.can_view_study', self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(self.user_detail_url, content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testGetParticipantDetailCanViewStudyResponsesPermissions(self):
        # As a researcher, need can_view_study_responses permissions to view participant detail
        assign_perm('studies.can_view_study_responses', self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(self.user_detail_url, content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data['given_name'], "Participant 1")

    # POST User Tests
    def testPostUser(self):
        # Cannot POST to users
        assign_perm('studies.can_view_study_responses', self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.post(self.url, content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # PATCH User Tests
    def testUpdateUser(self):
        # Cannot Update User
        assign_perm('studies.can_view_study_responses', self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.patch(self.user_detail_url, content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # DELETE User Tests
    def testDeleteUser(self):
        # Cannot Delete User
        assign_perm('studies.can_view_study_responses', self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.delete(self.user_detail_url, content_type="application/vnd.api+json")
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
