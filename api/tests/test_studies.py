import json
import uuid

from django.test import TestCase
from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import Child, User
from studies.models import ConsentRuling, Feedback, Response, Study


class StudiesTestCase(APITestCase):
    def setUp(self):
        self.researcher = G(User, is_active=True, is_researcher=True)
        self.participant = G(User, is_active=True)
        self.child = G(Child, user=self.participant)
        self.study = G(
            Study,
            creator=self.researcher,
            name="Test Name",
            short_description="Short description",
            long_description="Longer description",
            criteria="Five years or older",
            duration="Twenty minutes",
            contact_info="my email",
            max_age_years=2,
            min_age_years=4,
            image="asd",
            exit_url="www.cos.io",
            shared_preview=False,
            state="created",
        )
        self.study.save()

        self.response = G(
            Response,
            child=self.child,
            study=self.study,
            exp_data={"first": "response"},
            completed_consent_frame=True,
        )

        self.positive_consent_ruling = G(
            ConsentRuling, study=self.study, response=self.response, action="accepted"
        )

        self.study_list_url = reverse("study-list", kwargs={"version": "v1"})
        self.study_detail_url = self.study_list_url + str(self.study.uuid) + "/"
        self.study_responses_url = (
            self.study_list_url + str(self.study.uuid) + "/responses/"
        )
        self.client = APIClient()

    # Studies GET LIST Tests
    def testGetStudyListUnauthenticated(self):
        api_response = self.client.get(
            self.study_list_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testViewStudyWithCanViewPermission(self):
        self.client.force_authenticate(user=self.researcher)
        assign_perm("studies.can_view_study", self.researcher, self.study)
        api_response = self.client.get(
            self.study_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["name"], self.study.name)

    def testViewSharedStudyWithoutCanViewPermission(self):
        self.client.force_authenticate(user=self.researcher)
        self.study.shared_preview = True
        self.study.save()
        api_response = self.client.get(
            self.study_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["name"], self.study.name)

    def testGetStudyWithoutReadOrSharedPreview(self):
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.study_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testGetStudyListAsReadAuthenticated(self):
        # Need can_view_study permissions to view study through API
        assign_perm("studies.can_view_study", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.study_list_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 1)

    def testGetStudyListAsParticipant(self):
        # Participants can't view most studies (unless active & public)
        api_response = self.client.get(
            self.study_list_url, content_type="application/vnd.api+json"
        )
        self.client.force_authenticate(user=self.participant)

        api_response = self.client.get(
            self.study_list_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 0)

    def testGetPublicAndActiveStudiesAsParticipant(self):
        # Studies that are public and active can be viewed by participant in list
        self.study.state = "active"
        self.study.public = True
        self.study.save()

        api_response = self.client.get(
            self.study_list_url, content_type="application/vnd.api+json"
        )
        self.client.force_authenticate(user=self.participant)

        api_response = self.client.get(
            self.study_list_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 1)

    def testGetSpecificPrivateActiveStudyAsParticipant(self):
        # Any active studies can be viewed by participant
        self.study.state = "active"
        self.study.public = False
        self.study.save()
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.study_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["name"], self.study.name)

    # POST Study
    def testPostStudy(self):
        assign_perm("studies.can_edit_study", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.post(
            self.study_list_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # PATCH Study
    def testUpdateStudy(self):
        assign_perm("studies.can_edit_study", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.patch(
            self.study_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # DELETE Study
    def testDeleteStudy(self):
        assign_perm("studies.can_edit_study", self.researcher, self.study)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.delete(
            self.study_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def testStudyResponses(self):
        # Accessing study responses restricts queryset to responses of that particular study
        self.study2 = G(Study, creator=self.researcher)
        self.response2 = self.response = G(
            Response,
            child=self.child,
            study=self.study2,
            exp_data={"second": "response"},
            completed_consent_frame=True,
        )

        self.client.force_authenticate(user=self.researcher)
        assign_perm("studies.can_view_study_responses", self.researcher, self.study)
        assign_perm("studies.can_view_study_responses", self.researcher, self.study2)
        api_response = self.client.get(
            self.study_responses_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 1)
        self.assertEqual(
            api_response.data["results"][0]["exp_data"], {"first": "response"}
        )

    def testStudyResponsesAsParticipant(self):
        # Participants can only see the study responses they created
        self.study2 = G(Study, creator=self.researcher)
        self.response2 = G(
            Response,
            child=G(Child, user=self.researcher),
            study=self.study2,
            exp_data={"second": "response"},
            completed_consent_frame=True,
        )

        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.study_responses_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 1)
        self.assertEqual(
            api_response.data["results"][0]["exp_data"], {"first": "response"}
        )
