from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import Child, User
from studies.models import ConsentRuling, Lab, Response, Study, StudyType
from studies.permissions import LabPermission, StudyPermission


class ChildrenTestCase(APITestCase):
    def setUp(self):
        self.researcher = G(User, is_active=True, is_researcher=True)
        self.participant = G(User, is_active=True)
        self.child_with_consented_response = G(
            Child, user=self.participant, given_name="Sally"
        )
        self.child_without_consented_response = G(
            Child, user=self.participant, given_name="Jane"
        )
        self.lab = G(Lab, name="ECCL")
        self.lab.researchers.add(self.researcher)
        self.lab.save()
        self.study = G(
            Study,
            creator=self.researcher,
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )
        self.response_consented = G(
            Response,
            child=self.child_with_consented_response,
            study=self.study,
            completed_consent_frame=True,
        )
        self.positive_consent_ruling = G(
            ConsentRuling, response=self.response_consented, action="accepted"
        )
        self.response_unconsented = G(
            Response,
            child=self.child_without_consented_response,
            study=self.study,
            completed_consent_frame=True,
        )
        self.negative_consent_ruling = G(
            ConsentRuling, response=self.response_unconsented, action="rejected"
        )
        self.url = reverse("api:child-list", kwargs={"version": "v1"})
        self.child_with_consent_detail_url = (
            f"{self.url}{self.child_with_consented_response.uuid}/"
        )
        self.child_without_consent_detail_url = (
            f"{self.url}{self.child_without_consented_response.uuid}/"
        )
        self.client = APIClient()

    # Children GET LIST Tests
    def testGetChildrenListUnauthenticated(self):
        # Must be authenticated to view children
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetChildrenListInactiveParticipant(self):
        # Can only see children of active participants
        self.participant.is_active = False
        self.participant.save()
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 0)

    def testGetChildrenListSeeOwnChildren(self):
        # A participant can see their own children (regardless of consent coding status)
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 2)

    def testGetChildrenListNoResearchers(self):
        # Researchers can see their children (regardless of consent coding status)
        self.participant.is_researcher = True
        self.participant.save()
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 2)

    def testGetChildrenListCanViewStudyPermissions(self):
        # Cannot see children unless have READ_STUDY_RESPONSE_DATA perms on study or associated lab. Add a variety
        # of other study-specific perms & add to design group, none of these should grant access.
        assign_perm(
            StudyPermission.READ_STUDY_PREVIEW_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            StudyPermission.CODE_STUDY_CONSENT.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            StudyPermission.CONTACT_STUDY_PARTICIPANTS.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.study.design_group.user_set.add(self.researcher)
        self.study.lab.admin_group.user_set.add(self.researcher)
        self.study.save()
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 0)

    def testGetChildrenListCanViewStudyResponsesPermissions(self):
        # As a researcher, can only see children who've taken studies where you have
        # read response data permissions, and can only see children with consented responses
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

    def testGetChildrenListLabwideCanViewStudyResponsesPermissions(self):
        # As a researcher, can only see children who've taken studies where you have
        # read response data permissions, and can only see children with consented responses.
        # Lab-wide perms work as well as study-specific
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

    def testSuperusersViewAllChildren(self):
        # Superusers can see all children of active participants
        self.superuser = G(User, is_active=True, is_researcher=True, is_superuser=True)
        self.child2 = G(Child, user=self.researcher, given_name="Jack")
        self.client.force_authenticate(user=self.superuser)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertGreater(api_response.data["links"]["meta"]["count"], 2)

    # Children GET Detail Tests
    def testGetChildDetailUnauthenticated(self):
        # Must be authenticated to view child
        api_response = self.client.get(
            self.child_with_consent_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetChildDetailInactiveParticipant(self):
        # Can't see child of inactive participant
        self.participant.is_active = False
        self.participant.save()
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.child_with_consent_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testGetOwnChildDetail(self):
        # A participant can see their own child, regardless of consent coding status
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.child_without_consent_detail_url,
            content_type="application/vnd.api+json",
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["given_name"], "Jane")

    def testGetChildDetailResearcher(self):
        # A researcher can see their child, regardless of consent coding status
        self.participant.is_researcher = True
        self.participant.save()
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.child_with_consent_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)

    def testGetChildDetailCanViewStudyPermissions(self):
        # None of the following perms or groups should grant access
        assign_perm(
            StudyPermission.READ_STUDY_PREVIEW_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            StudyPermission.CODE_STUDY_CONSENT.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            StudyPermission.CONTACT_STUDY_PARTICIPANTS.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.study.design_group.user_set.add(self.researcher)
        self.study.lab.admin_group.user_set.add(self.researcher)
        self.study.save()
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.child_with_consent_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testGetChildDetailCanViewStudyResponsesPermissions(self):
        # As a researcher, can only view a child if they've taken a study where you have
        # read_study__responses permissions and consent has been approved
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.child_with_consent_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["given_name"], "Sally")

    def testGetChildDetailLabwideCanViewStudyResponsesPermissions(self):
        # As a researcher, can only view a child if they've taken a study where you have
        # read_study__responses permissions and consent has been approved
        assign_perm(
            LabPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study.lab,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.child_with_consent_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["given_name"], "Sally")

    def testGetChildDetailNoConsentCanViewStudyResponsesPermissions(self):
        # As a researcher, can only view a child if they've taken a study where you have
        # can_view_study_responses permissions and consent has been approved
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            LabPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study.lab,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.child_without_consent_detail_url,
            content_type="application/vnd.api+json",
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    # Children POST Children Tests
    def testPostChild(self):
        # Cannot POST to children, regardless of perms.
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.study.admin_group.user_set.add(self.researcher)
        self.study.lab.admin_group.user_set.add(self.researcher)
        self.study.save()
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.post(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # Children PATCH Children Tests
    def testUpdateChild(self):
        # Cannot Update Child
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.study.admin_group.user_set.add(self.researcher)
        self.study.lab.admin_group.user_set.add(self.researcher)
        self.study.save()
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.patch(
            self.child_with_consent_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # Children DELETE Children Tests
    def testDeleteChild(self):
        # Cannot Update Child
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.study.admin_group.user_set.add(self.researcher)
        self.study.lab.admin_group.user_set.add(self.researcher)
        self.study.save()
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.delete(
            self.child_with_consent_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
