from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import Child, User
from studies.models import ConsentRuling, Lab, Response, Study, StudyType
from studies.permissions import LabPermission, StudyPermission


class StudiesTestCase(APITestCase):
    def setUp(self):
        self.researcher = G(
            User,
            is_active=True,
            is_researcher=True,
            given_name="Jane",
            family_name="Smith",
        )
        self.researcher_outside_lab = G(
            User,
            is_active=True,
            is_researcher=True,
            given_name="Jane",
            family_name="Smith",
        )
        self.participant = G(User, is_active=True)
        self.child = G(Child, user=self.participant)
        self.lab = G(Lab, name="MIT")
        self.lab.researchers.add(self.researcher)
        self.lab.save()
        self.study = G(
            Study,
            lab=self.lab,
            creator=self.researcher,
            name="Test Name",
            short_description="Short description",
            purpose="Longer description",
            criteria="Five years or older",
            duration="Twenty minutes",
            contact_info="my email",
            max_age_years=2,
            min_age_years=4,
            image="asd",
            shared_preview=False,
            state="created",
            study_type=StudyType.get_ember_frame_player(),
        )
        self.study.save()

        self.response = G(
            Response,
            child=self.child,
            study=self.study,
            exp_data={"first": "response"},
            completed_consent_frame=True,
            study_type=self.study.study_type,
        )

        self.positive_consent_ruling = G(
            ConsentRuling,
            response=self.response,
            action="accepted",
            arbiter=self.researcher,
        )

        self.study_list_url = reverse("api:study-list", kwargs={"version": "v1"})
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
        assign_perm(
            StudyPermission.READ_STUDY_DETAILS.prefixed_codename,
            self.researcher,
            self.study,
        )
        api_response = self.client.get(
            self.study_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["name"], self.study.name)

    def testViewStudyWithLabwideCanViewPermission(self):
        self.client.force_authenticate(user=self.researcher)
        assign_perm(
            LabPermission.READ_STUDY_DETAILS.prefixed_codename,
            self.researcher,
            self.study.lab,
        )
        api_response = self.client.get(
            self.study_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["name"], self.study.name)

    def testViewSharedStudyWithoutCanViewPermission(self):
        self.client.force_authenticate(user=self.researcher_outside_lab)
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
        assign_perm(
            StudyPermission.READ_STUDY_DETAILS.prefixed_codename,
            self.researcher,
            self.study,
        )
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
        assign_perm(
            StudyPermission.WRITE_STUDY_DETAILS.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.post(
            self.study_list_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # PATCH Study
    def testUpdateStudy(self):
        assign_perm(
            StudyPermission.WRITE_STUDY_DETAILS.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.study.admin_group.user_set.add(self.researcher)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.patch(
            self.study_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # DELETE Study
    def testDeleteStudy(self):
        assign_perm(
            StudyPermission.WRITE_STUDY_DETAILS.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.study.admin_group.user_set.add(self.researcher)
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.delete(
            self.study_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def testStudyResponses(self):
        # Accessing study responses restricts queryset to responses of that particular study
        self.study2 = G(
            Study,
            creator=self.researcher,
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )
        self.response2 = self.response = G(
            Response,
            child=self.child,
            study=self.study2,
            exp_data={"second": "response"},
            completed_consent_frame=True,
            study_type=self.study2.study_type,
        )

        self.client.force_authenticate(user=self.researcher)
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study2,
        )
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
        self.study2 = G(
            Study,
            creator=self.researcher,
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )
        self.response2 = G(
            Response,
            child=G(Child, user=self.researcher),
            study=self.study2,
            exp_data={"second": "response"},
            completed_consent_frame=True,
            study_type=self.study2.study_type,
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
