import json
import uuid

from django.test import TestCase
from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import Child, User
from studies.models import Feedback, Response, Study, ConsentRuling


class ChildrenTestCase(APITestCase):
    def setUp(self):
        self.researcher = G(User, is_active=True, is_researcher=True)
        self.participant = G(User, is_active=True)
        self.child = G(Child, user=self.participant, given_name="Sally")
        self.study = G(Study, creator=self.researcher)
        self.response = G(Response, child=self.child, study=self.study, completed_consent_frame=True)
        self.positive_consent_ruling = G(
            ConsentRuling,
            study=self.study,
            response=self.response,
            action="accepted")
        self.url = reverse("child-list", kwargs={"version": "v1"})
        self.child_detail_url = (
            reverse("child-list", kwargs={"version": "v1"}) + str(self.child.uuid) + "/"
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
        # A participant can see their own children
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 1)

    def testGetChildrenListNoResearchers(self):
        # Researchers can see their children
        self.participant.is_researcher = True
        self.participant.save()
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 1)

    def testGetChildrenListCanViewStudyPermissions(self):
        # Cannot see children if only have can_view_study permissions
        assign_perm("studies.can_view_study", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 0)

    def testGetChildrenListCanViewStudyResponsesPermissions(self):
        # As a researcher, can only see children who've taken studies where you have
        # can_view_study_responses permissions
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
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
        self.assertGreater(api_response.data["links"]["meta"]["count"], 1)

    # Children GET Detail Tests
    def testGetChildDetailUnauthenticated(self):
        # Must be authenticated to view child
        api_response = self.client.get(
            self.child_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetChildDetailInactiveParticipant(self):
        # Can't see child of inactive participant
        self.participant.is_active = False
        self.participant.save()
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.child_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testGetOwnChildDetail(self):
        # A participant can see their own child
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.child_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["given_name"], "Sally")

    def testGetChildDetailResearcher(self):
        # A researcher can see their child
        self.participant.is_researcher = True
        self.participant.save()
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.child_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)

    def testGetChildDetailCanViewStudyPermissions(self):
        # Can't see a child with just can_view_study permissions
        assign_perm("studies.can_view_study", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.child_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testGetChildDetailCanViewStudyResponsesPermissions(self):
        # As a researcher, can only view a child if they've taken a study where you have
        # can_view_study_responses permissions
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.child_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["given_name"], "Sally")

    # Children POST Children Tests
    def testPostChild(self):
        # Cannot POST to children
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.post(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # Children PATCH Children Tests
    def testUpdateChild(self):
        # Cannot Update Child
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.patch(
            self.child_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # Children DELETE Children Tests
    def testDeleteChild(self):
        # Cannot Update Child
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.delete(
            self.child_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
