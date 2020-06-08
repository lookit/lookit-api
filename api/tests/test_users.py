import json
import uuid
from unittest import skip

from django.test import TestCase
from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import Child, User
from studies.models import Feedback, Lab, Response, Study, StudyType


class UserTestCase(APITestCase):
    def setUp(self):
        self.researcher = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 1"
        )
        self.participant = G(User, is_active=True, given_name="Participant 1")
        self.participant2 = G(User, is_active=True, given_name="Participant 2")
        self.participant3 = G(User, is_active=True, given_name="Participant 3")
        self.child = G(Child, user=self.participant, given_name="Sally")
        self.study_type = G(StudyType, name="default", id=1)
        self.lab = G(Lab, name="MIT")
        self.study = G(
            Study, creator=self.researcher, study_type=self.study_type, lab=self.lab
        )
        self.response = G(Response, child=self.child, study=self.study)
        self.url = reverse("api:user-list", kwargs={"version": "v1"})
        self.user_detail_url = (
            reverse("api:user-list", kwargs={"version": "v1"})
            + str(self.participant.uuid)
            + "/"
        )
        self.client = APIClient()

    # Participant GET LIST Tests
    def testGetParticipantListUnauthenticated(self):
        # Must be authenticated to view participants
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetResearchersInParticipantList(self):
        # As a researcher, can view yourself
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 1)

    def testParticipantCanViewThemselves(self):
        # As a participant, can view yourself
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["results"][0]["given_name"], "Participant 1")

    def testGetParticipantsIncorrectPermissions(self):
        # Can_view_study permissions not sufficient for viewing participants
        assign_perm("studies.can_view_study", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 1)

    def testGetParticipantListCanViewStudyResponsesPermissions(self):
        # As a researcher, need can_view_study_responses permissions to view participants
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 2)
        self.assertEqual(api_response.data["results"][0]["given_name"], "Researcher 1")
        self.assertEqual(api_response.data["results"][1]["given_name"], "Participant 1")

    def testSuperusersCanViewAllUsers(self):
        # Superusers can see all users
        self.superuser = G(User, is_active=True, is_researcher=True, is_superuser=True)
        self.client.force_authenticate(user=self.superuser)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertGreater(api_response.data["links"]["meta"]["count"], 1)

    @skip(
        "To make someone an org admin, currently need to add them to group with appropriate name. Re-implement with new Lab model."
    )
    def testAdminsCannotAutomaticallyViewEmails(self):
        # Regular org admin permissions and even ability to read all user data are insufficient to see usernames
        self.lab = G(Lab, name="MIT")
        self.admin = G(User, is_active=True, is_researcher=True)
        self.admin.labs.add(lab)
        assign_perm("accounts.can_read_all_user_data", self.admin)
        self.client.force_authenticate(user=self.admin)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        userList = api_response.json()["data"]
        self.assertGreater(len(userList), 1)  # View all participants
        for u in userList:
            self.assertNotIn("username", u["attributes"].keys())

    def testUsersCanViewEmailsWithPermission(self):
        # User with specific 'can_view_usernames' permission can see usernames in user data
        self.emailpermissionuser = G(User, is_active=True, given_name="ResearcherEmail")
        assign_perm("accounts.can_read_usernames", self.emailpermissionuser)
        self.client.force_authenticate(user=self.emailpermissionuser)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        userList = api_response.json()["data"]
        self.assertGreater(len(userList), 0)  # View self
        for u in userList:
            self.assertIn("username", u["attributes"].keys())

    # Participant GET Detail Tests
    def testGetParticipantDetailUnauthenticated(self):
        # Must be authenticated to view participants
        api_response = self.client.get(
            self.user_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetResearcherDetail(self):
        # Researchers do not show up in user list, only participants
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            str(self.researcher.uuid) + "/", content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testParticipantCanViewOwnDetailEndpoint(self):
        # As a participant, can view yourself
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.user_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["given_name"], "Participant 1")

    def testGetParticipantDetailIncorrectPermissions(self):
        # Can_view_study permissions not sufficient for viewing participants
        assign_perm("studies.can_view_study", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.user_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testGetParticipantDetailCanViewStudyResponsesPermissions(self):
        # As a researcher, need can_view_study_responses permissions to view participant detail
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.user_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["given_name"], "Participant 1")

    # POST User Tests
    def testPostUser(self):
        # Cannot POST to users
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.post(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # PATCH User Tests
    def testUpdateUser(self):
        # Cannot Update User
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.patch(
            self.user_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # DELETE User Tests
    def testDeleteUser(self):
        # Cannot Delete User
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.delete(
            self.user_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
