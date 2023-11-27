import json

from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import Child, DemographicData, User
from studies.models import ConsentRuling, Lab, Response, Study, StudyType
from studies.permissions import LabPermission, StudyPermission


class ResponseTestCase(APITestCase):
    def setUp(self):
        self.researcher = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 1"
        )
        self.participant = G(User, is_active=True, given_name="Participant 1")
        self.superuser = G(User, is_active=True, is_researcher=True, is_superuser=True)
        self.demographics = G(DemographicData, user=self.participant)
        self.participant.save()

        self.child = G(Child, user=self.participant, given_name="Sally")
        self.child_of_researcher = G(Child, user=self.researcher, given_name="Grace")

        self.lab = G(Lab, name="MIT")
        self.study = G(
            Study,
            creator=self.researcher,
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )
        self.response = G(Response, child=self.child, study=self.study, completed=False)
        self.consented_response = G(
            Response,
            child=self.child,
            study=self.study,
            completed=False,
            completed_consent_frame=True,
        )
        self.positive_consent_ruling = G(
            ConsentRuling, response=self.consented_response, action="accepted"
        )
        self.url = reverse("api:response-list", kwargs={"version": "v1"})
        self.response_detail_url = f"{self.url}{self.response.uuid}/"
        self.consented_response_detail_url = (
            f"{self.url}{self.consented_response.uuid}/"
        )
        self.client = APIClient()

        self.data = {
            "data": {
                "attributes": {
                    "global_event_timings": [],
                    "exp_data": {"first_frame": {}, "second_frame": {}},
                    "sequence": [],
                    "completed": False,
                    "completed_consent_frame": False,
                },
                "relationships": {
                    "child": {"data": {"type": "children", "id": str(self.child.uuid)}},
                    "study": {"data": {"type": "studies", "id": str(self.study.uuid)}},
                },
                "type": "responses",
            }
        }
        self.patch_data = {
            "data": {
                "attributes": {
                    "global_event_timings": [],
                    "exp_data": {"first_frame": {}, "second_frame": {}},
                    "sequence": ["first_frame", "second_frame"],
                    "completed": True,
                    "completed_consent_frame": True,
                },
                "type": "responses",
                "id": str(self.response.uuid),
            }
        }

    # Response List test
    def testGetResponseListUnauthenticated(self):
        #  Must be authenticated to view participants
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetResponseOrderingReverseDateModified(self):
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.client.force_authenticate(user=self.researcher)
        self.response2 = G(
            Response,
            child=self.child,
            study=self.study,
            completed=False,
            completed_consent_frame=True,
        )
        self.positive_consent_ruling2 = G(
            ConsentRuling, response=self.response2, action="accepted"
        )
        self.response3 = G(
            Response,
            child=self.child,
            study=self.study,
            completed=False,
            completed_consent_frame=True,
        )
        self.positive_consent_ruling3 = G(
            ConsentRuling, response=self.response3, action="accepted"
        )
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 3)
        self.assertIn(str(self.response3.uuid), api_response.data["results"][0]["url"])
        self.assertIn(str(self.response2.uuid), api_response.data["results"][1]["url"])
        self.assertIn(
            str(self.consented_response.uuid), api_response.data["results"][2]["url"]
        )

    def testGetResponsesListByOwnChildren(self):
        # Participant can view their own responses
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)

        # Should get both the consented and unconsented.
        self.assertEqual(api_response.data["links"]["meta"]["count"], 2)

    def testGetResponsesListViewStudyPermissions(self):
        # Can view study permissions insufficient to view responses
        assign_perm(
            StudyPermission.READ_STUDY_DETAILS.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            StudyPermission.WRITE_STUDY_DETAILS.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.lab.admin_group.user_set.add(self.researcher)
        self.lab.save()
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["links"]["meta"]["count"], 0)

    def testGetResponsesListViewStudyResponsesPermissions(self):
        # With can_view_study_responses permissions, can view study responses
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

    def testGetResponsesListLabwideViewStudyResponsesPermissions(self):
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

    # Response Detail tests
    def testGetResponseDetailUnauthenticated(self):
        # Can't view response detail unless authenticated
        api_response = self.client.get(
            self.consented_response_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetResponseDetailByOwnChildren(self):
        # Participant can view their own response detail regardless of consent coding
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.get(
            self.response_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)

    def testGetResponseDetailViewStudyPermissions(self):
        # Can view study permissions insufficient to view responses
        assign_perm(
            StudyPermission.READ_STUDY_DETAILS.prefixed_codename,
            self.researcher,
            self.study,
        )
        assign_perm(
            StudyPermission.WRITE_STUDY_DETAILS.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.lab.admin_group.user_set.add(self.researcher)
        self.lab.save()
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.consented_response_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testGetResponseDetailViewStudyResponsesPermissions(self):
        # With can_view_study_responses permissions, can view study response detail,
        # but still can't view non-consented response
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.client.force_authenticate(user=self.researcher)
        api_response = self.client.get(
            self.response_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)

    def testGetResponseDetailViewStudyResponsesPermissionsAfterConsent(self):
        # With can_view_study_responses permissions, can view study response detail
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study,
        )
        self.client.force_authenticate(user=self.researcher)

        api_response = self.client.get(
            self.consented_response_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["completed"], False)
        self.assertEqual(api_response.data["completed_consent_frame"], True)

    def testGetResponseDetailLabwideViewStudyResponsesPermissionsAfterConsent(self):
        # With can_view_study_responses permissions, can view study response detail
        assign_perm(
            LabPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            self.researcher,
            self.study.lab,
        )
        self.client.force_authenticate(user=self.researcher)

        api_response = self.client.get(
            self.consented_response_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["completed"], False)
        self.assertEqual(api_response.data["completed_consent_frame"], True)

    # POST Responses tests
    def testPostResponse(self):
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.post(
            self.url, json.dumps(self.data), content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(api_response.data["completed"], False)
        self.assertEqual(Response.objects.count(), 3)

    def testPostResponseWithNotYourChild(self):
        self.client.force_authenticate(user=self.participant)
        self.data["data"]["relationships"]["child"]["data"]["id"] = str(
            self.child_of_researcher.uuid
        )
        api_response = self.client.post(
            self.url, json.dumps(self.data), content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_403_FORBIDDEN)

    def testPostResponseNeedDataHeader(self):
        self.client.force_authenticate(user=self.participant)
        data = {}
        api_response = self.client.post(
            self.url, json.dumps(data), content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(api_response.data[0]["detail"].code, "parse_error")
        self.assertEqual(api_response.data[0]["source"]["pointer"], "/data")

    def testPostResponseNeedResponsesType(self):
        self.client.force_authenticate(user=self.participant)
        self.data["data"]["type"] = "bad"
        api_response = self.client.post(
            self.url, json.dumps(self.data), content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_409_CONFLICT)

    def testPostResponseNeedChildRelationship(self):
        self.client.force_authenticate(user=self.participant)
        self.data["data"]["relationships"] = {
            "study": {"data": {"type": "studies", "id": str(self.study.uuid)}}
        }
        api_response = self.client.post(
            self.url, json.dumps(self.data), content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(api_response.data[0]["detail"].code, "required")
        self.assertEqual(
            api_response.data[0]["source"]["pointer"], "/data/attributes/child"
        )

    def testPostResponseNeedStudyRelationship(self):
        self.client.force_authenticate(user=self.participant)
        self.data["data"]["relationships"] = {
            "child": {"data": {"type": "children", "id": str(self.child.uuid)}}
        }
        api_response = self.client.post(
            self.url, json.dumps(self.data), content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(api_response.data[0]["detail"].code, "required")
        self.assertEqual(
            api_response.data[0]["source"]["pointer"], "/data/attributes/study"
        )

    def testPostResponseWithEmptyAttributes(self):
        self.client.force_authenticate(user=self.participant)
        self.data["data"]["attributes"] = {}
        api_response = self.client.post(
            self.url, json.dumps(self.data), content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_201_CREATED)

    # PATCH responses
    def testPatchResponseAttributes(self):
        self.client.force_authenticate(user=self.participant)
        api_response = self.client.patch(
            self.response_detail_url,
            json.dumps(self.patch_data),
            content_type="application/vnd.api+json",
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data["sequence"], ["first_frame", "second_frame"])

    def testPatchResponseAttributesTopLevelKeysUnderscoredOnly(self):
        self.client.force_authenticate(user=self.participant)

        data = {
            "data": {
                "id": str(self.response.uuid),
                "attributes": {
                    "conditions": {
                        "8-pref-phys-videos": {
                            "startType": 5,
                            "showStay": 8,
                            "whichObjects": [8, 5, 6, 8],
                        }
                    },
                    "global_event_timings": [],
                    "exp_data": {
                        "0-0-video-config": {
                            "eventTimings": [
                                {
                                    "eventType": "nextFrame",
                                    "timestamp": "2017-10-31T20:09:47.479Z",
                                }
                            ]
                        },
                        "1-1-video-consent": {
                            "videoId": "e729321f-418f-4728-992c-9364623dbe9b_1-video-consent_bdebd15b-adc7-4377-b2f6-e9f3de70dd19",
                            "eventTimings": [
                                {
                                    "eventType": "hasCamAccess",
                                    "timestamp": "2017-10-31T20:09:48.096Z",
                                    "hasCamAccess": "True",
                                    "videoId": "e729321f-418f-4728-992c-9364623dbe9b_1-video-consent_bdebd15b-adc7-4377-b2f6-e9f3de70dd19",
                                    "streamTime": "None",
                                },
                                {
                                    "eventType": "videoStreamConnection",
                                    "timestamp": "2017-10-31T20:09:50.534Z",
                                    "status": "NetConnection.Connect.Success",
                                    "videoId": "e729321f-418f-4728-992c-9364623dbe9b_1-video-consent_bdebd15b-adc7-4377-b2f6-e9f3de70dd19",
                                    "streamTime": "None",
                                },
                                {
                                    "eventType": "stoppingCapture",
                                    "timestamp": "2017-10-31T20:09:53.051Z",
                                    "videoId": "e729321f-418f-4728-992c-9364623dbe9b_1-video-consent_bdebd15b-adc7-4377-b2f6-e9f3de70dd19",
                                    "streamTime": 2.459,
                                },
                                {
                                    "eventType": "nextFrame",
                                    "timestamp": "2017-10-31T20:09:53.651Z",
                                    "videoId": "e729321f-418f-4728-992c-9364623dbe9b_1-video-consent_bdebd15b-adc7-4377-b2f6-e9f3de70dd19",
                                    "streamTime": "None",
                                },
                            ],
                        },
                        "2-2-instructions": {
                            "confirmationCode": "6YdLL",
                            "eventTimings": [
                                {
                                    "eventType": "nextFrame",
                                    "timestamp": "2017-10-31T20:09:56.472Z",
                                }
                            ],
                        },
                        "5-5-mood-survey": {
                            "rested": "1",
                            "healthy": "1",
                            "childHappy": "1",
                            "active": "1",
                            "energetic": "1",
                            "ontopofstuff": "1",
                            "parentHappy": "1",
                            "napWakeUp": "11:00",
                            "usualNapSchedule": "no",
                            "lastEat": "6:00",
                            "doingBefore": "s",
                            "eventTimings": [
                                {
                                    "eventType": "nextFrame",
                                    "timestamp": "2017-10-31T20:10:17.269Z",
                                }
                            ],
                        },
                    },
                    "sequence": [
                        "0-0-video-config",
                        "1-1-video-consent",
                        "2-2-instructions",
                        "5-5-mood-survey",
                    ],
                    "completed": "False",
                    "completed_consent_frame": "true",
                },
                "type": "responses",
            }
        }

        api_response = self.client.patch(
            self.response_detail_url,
            json.dumps(data),
            content_type="application/vnd.api+json",
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            api_response.data["sequence"],
            [
                "0-0-video-config",
                "1-1-video-consent",
                "2-2-instructions",
                "5-5-mood-survey",
            ],
        )
        self.assertEqual(
            api_response.data["exp_data"]["0-0-video-config"],
            {
                "eventTimings": [
                    {"eventType": "nextFrame", "timestamp": "2017-10-31T20:09:47.479Z"}
                ]
            },
        )
        self.assertEqual(
            api_response.data["exp_data"]["5-5-mood-survey"],
            {
                "rested": "1",
                "healthy": "1",
                "childHappy": "1",
                "active": "1",
                "energetic": "1",
                "ontopofstuff": "1",
                "parentHappy": "1",
                "napWakeUp": "11:00",
                "usualNapSchedule": "no",
                "lastEat": "6:00",
                "doingBefore": "s",
                "eventTimings": [
                    {"eventType": "nextFrame", "timestamp": "2017-10-31T20:10:17.269Z"}
                ],
            },
        )

    # Delete responses
    def testDeleteResponse(self):
        self.client.force_authenticate(user=self.superuser)
        api_response = self.client.delete(
            self.response_detail_url, content_type="application/vnd.api+json"
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
