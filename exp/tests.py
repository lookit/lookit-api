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

from unittest import skip

import urllib.parse


class RenameVideoTestCase(APITestCase):
    def setUp(self):
        self.researcher = G(User, is_active=True, is_researcher=True)
        self.participant = G(User, is_active=True)
        self.child = G(Child, user=self.participant, given_name="Sally")
        self.study = G(Study, creator=self.researcher)
        self.url = reverse("exp:rename-video")
        self.client = APIClient()
        self.payload = {
            "payload": {
                "version": "1.0",
                "event": "video_copied_s3",
                "data": {
                    "s3UploadStatus": "upload success",
                    "videoName": "oldfilename",
                    "type": "MP4",
                    "size": 493534,
                    "id": "123",
                    "url": "https://bucketname.s3.amazonaws.com/oldfilename.mp4",
                    "snapshotUrl": "https://bucketname.s3.amazonaws.com/oldfilename.jpg",
                    "bucket": "bucketname",
                    "region": "us-east-1",
                    "acl": "public-read",
                    "payload": "newfilename",
                },
            }
        }

    # Video rename tests.
    @skip(
        "Authentication relies on current URL, should find a way to test smaller piece"
    )
    def testRenameVideo(self):
        api_response = self.client.post(
            self.url,
            urllib.parse.urlencode(self.payload),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
