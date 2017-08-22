# import json
# import uuid
# from django.test import TestCase
# from rest_framework.test import APITestCase
# from rest_framework.test import APIClient
# from rest_framework import status
# from django.urls import reverse
#
# from guardian.shortcuts import assign_perm
# from studies.models import Response, Study, Feedback
# from accounts.models import Child, User
# from django_dynamic_fixture import G
#
#
# class StudiesTestCase(APITestCase):
#     def setUp(self):
#         self.researcher = G(User, is_active=True, is_researcher=True)
#         self.participant = G(User, is_active=True)
#         self.child = G(Child, user=self.participant)
#         self.study = G(Study, creator=self.researcher,
#             name="Test Name",
#             short_description="Short description",
#             long_description="Longer description",
#             criteria="Five years or older",
#             duration="Five minutes",
#             contact_info="my email",
#             max_age="four",
#             min_age="two",
#             image="asd",
#             exit_url="www.cos.io"
#             )
#         self.study.save()
#
#         self.response = G(Response, child=self.child, study=self.study)
#         self.url = reverse('study-list',  kwargs={'version':'v1'})
#         self.client = APIClient()
#
#     # Studies GET LIST Tests
#     def testGetStudyListUnauthenticated(self):
#         api_response = self.client.get(self.url, content_type="application/vnd.api+json")
#         self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)
#
#     def testGetStudyListAdminAuthenticated(self):
#         # Must have can_edit_study permissions on a study to view
#         api_response = self.client.get(self.url, content_type="application/vnd.api+json")
#         assign_perm('studies.can_edit_study', self.researcher, self.study)
#         self.client.force_authenticate(user=self.researcher)
#
#         api_response = self.client.get(self.url, content_type="application/vnd.api+json")
#         self.assertEqual(api_response.status_code, status.HTTP_200_OK)
#         self.assertEqual(api_response.data['links']['meta']['count'], 1)
#
#     def testGetStudyListAsReadAuthenticated(self):
#         # Need can_edit_study permissions to view study through API
#         api_response = self.client.get(self.url, content_type="application/vnd.api+json")
#         assign_perm('studies.can_view_study', self.researcher, self.study)
#         self.client.force_authenticate(user=self.researcher)
#
#         api_response = self.client.get(self.url, content_type="application/vnd.api+json")
#         self.assertEqual(api_response.status_code, status.HTTP_200_OK)
#         self.assertEqual(api_response.data['links']['meta']['count'], 0)
#
#     def testGetStudyListAsParticipant(self):
#         # Participants can't view most studies
#         api_response = self.client.get(self.url, content_type="application/vnd.api+json")
#         self.client.force_authenticate(user=self.participant)
#
#         api_response = self.client.get(self.url, content_type="application/vnd.api+json")
#         self.assertEqual(api_response.status_code, status.HTTP_200_OK)
#         self.assertEqual(api_response.data['links']['meta']['count'], 0)
#
#     def testGetPublicStudiesAsParticipantOnly(self):
#         # Studies must be public and active to view by participant
#         self.study.public = True
#         api_response = self.client.get(self.url, content_type="application/vnd.api+json")
#         self.client.force_authenticate(user=self.participant)
#
#         api_response = self.client.get(self.url, content_type="application/vnd.api+json")
#         self.assertEqual(api_response.status_code, status.HTTP_200_OK)
#         self.assertEqual(api_response.data['links']['meta']['count'], 0)
#
#     def testGetActiveStudiesAsParticipantOnly(self):
#         # Studies must be public and active to view by participant
#         self.study.active = True
#         api_response = self.client.get(self.url, content_type="application/vnd.api+json")
#         self.client.force_authenticate(user=self.participant)
#
#         api_response = self.client.get(self.url, content_type="application/vnd.api+json")
#         self.assertEqual(api_response.status_code, status.HTTP_200_OK)
#         self.assertEqual(api_response.data['links']['meta']['count'], 0)
#
#     def testGetPublicAndActiveStudiesAsParticipant(self):
#         # Studies must be public and active to view by participant
#         self.study.public = True
#         self.study.save()
#         self.study.state = 'active'
#         self.study.save()
#
#         api_response = self.client.get(self.url, content_type="application/vnd.api+json")
#         self.client.force_authenticate(user=self.participant)
#
#         api_response = self.client.get(self.url, content_type="application/vnd.api+json")
#         self.assertEqual(api_response.status_code, status.HTTP_200_OK)
#         self.assertEqual(api_response.data['links']['meta']['count'], 1)
