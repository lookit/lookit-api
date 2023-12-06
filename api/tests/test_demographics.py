from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import Child, DemographicData, User
from studies.models import ConsentRuling, Lab, Response, Study, StudyType
from studies.permissions import LabPermission, StudyPermission


class DemographicsTestCase(APITestCase):
    def setUp(self):
        self.researcher = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 1"
        )
        self.superuser = G(User, is_active=True, is_researcher=True, is_superuser=True)
        self.participant_with_consented_response = G(
            User, is_active=True, given_name="Participant 1"
        )
        self.demographics_with_consented_response = G(
            DemographicData,
            user=self.participant_with_consented_response,
            additional_comments="Additional comments 1",
        )
        self.child_with_consent = G(
            Child, user=self.participant_with_consented_response, given_name="Sally"
        )
        self.participant_without_consented_response = G(
            User, is_active=True, given_name="Participant 2"
        )
        self.demographics_without_consented_response = G(
            DemographicData,
            user=self.participant_without_consented_response,
            additional_comments="Additional comments 2",
        )
        self.child_without_consent = G(
            Child, user=self.participant_without_consented_response, given_name="Sally"
        )

        self.lab = G(Lab, name="MIT")
        self.lab.researchers.add(self.researcher)
        self.lab.save()
        self.study = G(
            Study,
            creator=self.researcher,
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )
        self.response_with_consent = G(
            Response,
            child=self.child_with_consent,
            study=self.study,
            demographic_snapshot=self.demographics_with_consented_response,
            completed_consent_frame=True,
        )
        self.positive_consent_ruling = G(
            ConsentRuling, response=self.response_with_consent, action="accepted"
        )
        self.response_without_consent = G(
            Response,
            child=self.child_without_consent,
            study=self.study,
            demographic_snapshot=self.demographics_without_consented_response,
            completed_consent_frame=True,
        )
        self.negative_consent_ruling = G(
            ConsentRuling, response=self.response_without_consent, action="rejected"
        )
        self.url = "/api/v1/demographics/"
        self.demo_data_consented_url = f"/api/v1/demographics/{str(self.demographics_with_consented_response.uuid)}/"
        self.demo_data_unconsented_url = f"/api/v1/demographics/{str(self.demographics_without_consented_response.uuid)}/"
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
        self.participant_with_consented_response.is_active = False
        self.participant_with_consented_response.save()
        # Give researcher perms that would otherwise allow viewing
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
        self.assertEqual(api_response.data["links"]["meta"]["count"], 0)

    def testParticipantCanViewOwnDemographicData(self):
        # As a participant, can view your own demographic data regardless of consent coding status
        self.client.force_authenticate(user=self.participant_without_consented_response)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            api_response.data["results"][0]["additional_comments"],
            "Additional comments 2",
        )

    def testGetDemographicsIncorrectPermissions(self):
        # None of these perms or groups should be sufficient for viewing demographics
        assign_perm(
            StudyPermission.READ_STUDY_DETAILS.prefixed_codename,
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

    def testGetDemographicsListWithCanViewStudyResponsesPermissions(self):
        # As a researcher, need read_study__responses permissions to view demographics
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
        self.assertEqual(
            api_response.data["results"][0]["additional_comments"],
            "Additional comments 1",
        )

    def testGetDemographicsListWithLabwideCanViewStudyResponsesPermissions(self):
        # As a researcher, need read_study__responses permissions to view demographics.
        # Lab-wide perms are ok. Can only view demo data from participants who've consented
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
        # Can only view demographics from consented participants - should not see both!
        self.assertEqual(api_response.data["links"]["meta"]["count"], 1)
        self.assertEqual(
            api_response.data["results"][0]["additional_comments"],
            "Additional comments 1",
        )

    def testSuperusersCanViewAllDemographics(self):
        # Superusers can see all demographics of active participants
        self.demographics2 = G(
            DemographicData,
            user=self.researcher,
            additional_comments="English",
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
            self.demo_data_consented_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetInactiveUserDemographicData(self):
        # An inactive user's demographic data can't be retrieved
        self.participant_with_consented_response.is_active = False
        self.participant_with_consented_response.save()
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.demo_data_consented_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testParticipantCanViewOwnDemographicData(self):
        # As a participant, can view own demographic data, regardless of consent coding status
        self.client.force_authenticate(user=self.participant_without_consented_response)
        api_response = self.client.get(
            self.demo_data_unconsented_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            api_response.data["additional_comments"], "Additional comments 2"
        )

    def testGetDemographicDataIncorrectPermissions(self):
        # None of these perms or groups should be sufficient for viewing demographics
        assign_perm(
            StudyPermission.READ_STUDY_DETAILS.prefixed_codename,
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
            self.demo_data_consented_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testGetDemographicDataWithCanViewStudyResponsesPermissions(self):
        # As a researcher, need read_study__responses permissions to view demo data
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.demo_data_consented_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            api_response.data["additional_comments"], "Additional comments 1"
        )

    def testGetDemographicDataWithLabwideCanViewStudyResponsesPermissions(self):
        # As a researcher, need read_study__responses permissions to view demo data
        assign_perm(
            LabPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study.lab,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.demo_data_consented_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            api_response.data["additional_comments"], "Additional comments 1"
        )

    def testGetUnconsentedDemographicDataWithCanViewStudyResponsesPermissions(self):
        # As a researcher, can't view demo data only associated with unconsented responses
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.demo_data_unconsented_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    # POST Demo Data Tests
    def testPostDemoData(self):
        # Cannot POST to Demo Data (regardless of perms)
        self.client.force_authenticate(user=self.superuser)
        api_response = self.client.post(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # PATCH Demo Data Tests
    def testUpdateDemoData(self):
        # Cannot Update Demo Data (regardless of perms)
        self.client.force_authenticate(user=self.superuser)
        api_response = self.client.patch(
            self.demo_data_consented_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # DELETE Demo Data Tests
    def testDeleteDemoData(self):
        # Cannot Delete Demo Data (regardless of perms)
        self.client.force_authenticate(user=self.superuser)
        api_response = self.client.delete(
            self.demo_data_consented_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
