from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import Child, User
from studies.models import ConsentRuling, Lab, Response, Study, StudyType
from studies.permissions import LabPermission, StudyPermission


class UserTestCase(APITestCase):
    def setUp(self):
        self.researcher = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 1"
        )
        self.superuser = G(User, is_active=True, is_researcher=True, is_superuser=True)
        self.participant = G(User, is_active=True, given_name="Participant 1")
        self.participant2 = G(User, is_active=True, given_name="Participant 2")
        self.participant3 = G(User, is_active=True, given_name="Participant 3")
        self.child = G(Child, user=self.participant, given_name="Sally")
        self.lab = G(Lab, name="MIT")
        self.study = G(
            Study,
            creator=self.researcher,
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )
        self.response = G(
            Response, child=self.child, study=self.study, completed_consent_frame=True
        )
        self.positive_consent_ruling = G(
            ConsentRuling, response=self.response, action="accepted"
        )
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
        # none of these permissions sufficient for viewing participants
        assign_perm(
            StudyPermission.READ_STUDY_DETAILS.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            StudyPermission.CONTACT_STUDY_PARTICIPANTS.prefixed_codename,
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
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 1)

    def testGetParticipantListCanViewStudyResponsesPermissions(self):
        # As a researcher, need read_study__responses permissions to view participants
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
        self.assertEqual(api_response.data["links"]["meta"]["count"], 2)
        self.assertEqual(api_response.data["results"][0]["given_name"], "Researcher 1")
        self.assertEqual(api_response.data["results"][1]["given_name"], "Participant 1")

    def testSuperusersCanViewAllUsers(self):
        # Superusers can see all users
        self.client.force_authenticate(user=self.superuser)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertGreater(api_response.data["links"]["meta"]["count"], 1)

    def testAdminsCannotAutomaticallyViewEmails(self):
        # Lab admin permissions and even ability to read all user data are insufficient to see usernames
        self.lab.admin_group.user_set.add(self.researcher)
        self.lab.save()
        assign_perm("accounts.can_read_all_user_data", self.researcher)
        self.client.force_authenticate(user=self.researcher)
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
        # Researchers do not show up in user list, only participants. (Researcher would show up
        # if had a consented response though)
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
        # none of these permissions sufficient for viewing participants
        assign_perm(
            StudyPermission.READ_STUDY_DETAILS.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            StudyPermission.CONTACT_STUDY_PARTICIPANTS.prefixed_codename,
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
            self.user_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testGetParticipantDetailWithoutConsentedResponse(self):
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.client.force_authenticate(user=self.researcher)
        overrule_consent_ruling = G(
            ConsentRuling, response=self.response, action="rejected"
        )
        api_response = self.client.get(
            self.user_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testGetParticipantDetailCanViewStudyResponsesPermissions(self):
        # As a researcher, need can_view_study_responses permissions to view participant detail
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.user_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["given_name"], "Participant 1")

    def testGetParticipantDetailLabwideCanViewStudyResponsesPermissions(self):
        # Lab-wide perms work too
        assign_perm(
            LabPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study.lab,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.user_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["given_name"], "Participant 1")

    # POST User Tests
    def testPostUser(self):
        # Cannot POST to users
        self.client.force_authenticate(user=self.superuser)
        api_response = self.client.post(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # PATCH User Tests
    def testUpdateUser(self):
        # Cannot Update User
        self.client.force_authenticate(user=self.superuser)
        api_response = self.client.patch(
            self.user_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # DELETE User Tests
    def testDeleteUser(self):
        # Cannot Delete User
        self.client.force_authenticate(user=self.superuser)
        api_response = self.client.delete(
            self.user_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
