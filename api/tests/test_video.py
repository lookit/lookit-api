import hashlib
import hmac
import json
import random
import string
from datetime import datetime

import pytz
from django.urls import reverse
from rest_framework import status

from project.settings import AWS_LAMBDA_SECRET_ACCESS_KEY
from studies.models import Video

from .test_responses import ResponseTestCase


class VideoTestCase(ResponseTestCase):
    # helper functions
    def dict_to_json_bytes(self, dict_data):
        """Helper function to convert a Python dictionary to JSON bytes string."""
        return bytes(json.dumps(dict_data, separators=(",", ":")), "UTF-8")

    def calculate_signature(self):
        """Calculate signature using current value of data_to_hash."""
        key = bytes(AWS_LAMBDA_SECRET_ACCESS_KEY, "UTF-8")
        self.signature = hmac.new(
            key, self.video_data_to_hash, hashlib.sha256
        ).hexdigest()

    def create_data_to_hash(self):
        """Set the data_to_hash value based on the current video_data."""
        self.video_data_to_hash = self.dict_to_json_bytes(
            self.video_data["data"]["attributes"]
        )

    def delete_video_by_name(self, name):
        Video.objects.get(full_name=name).delete()

    def setUp(self):
        # set up the Response test case first so that we have some response/study/child data to work with
        super().setUp()
        # set up all info needed to make POST requests
        self.video_url = reverse("api:video-list", kwargs={"version": "v1"})
        study_str = str(self.study.uuid)
        resp_str = str(self.response.uuid)
        ts_str = "".join(random.choices(string.digits, k=13))
        rand_digit_str = "".join(random.choices(string.digits, k=3))
        self.video_name = f"videoStream_{study_str}_0-video-consent_{resp_str}_{ts_str}_{rand_digit_str}.mp4"
        pipe_name = (
            "".join(random.choices(string.ascii_letters + string.digits, k=31)) + ".mp4"
        )
        pipe_id = "".join(random.choices(string.digits, k=8))
        utc_tz = pytz.timezone("UTC")
        date_obj = datetime.now().astimezone(utc_tz)
        date_str = date_obj.strftime("%Y-%m-%d %H:%M:%S.%f")
        self.video_data = {
            "data": {
                "attributes": {
                    "pipe_name": pipe_name,
                    "pipe_numeric_id": pipe_id,
                    "frame_id": "0-video-consent",
                    "full_name": self.video_name,
                    "s3_timestamp": date_str,
                    "is_consent_footage": True,
                    "pk": None,
                },
                "type": "videos",
                "relationships": {
                    "response": {"data": {"type": "responses", "id": resp_str}},
                    "study": {"data": {"type": "studies", "id": study_str}},
                },
            }
        }
        self.video_data_json = self.dict_to_json_bytes(self.video_data)
        self.create_data_to_hash()
        self.calculate_signature()
        self.headers = {"X_AWS_LAMBDA_HMAC_SIG": self.signature}

    # POST Responses tests
    def sendPostResponse(self):
        return self.client.post(
            self.video_url,
            self.video_data_json,
            content_type="application/vnd.api+json",
            headers=self.headers,
        )

    def testPostResponse(self):
        """Vaild POST request with video data should create new video object"""
        self.assertEqual(Video.objects.count(), 0)
        api_response = self.sendPostResponse()
        self.assertEqual(api_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(api_response.data["full_name"], self.video_name)
        self.assertEqual(api_response.data["is_consent_footage"], True)
        self.assertEqual(Video.objects.count(), 1)
        self.assertEqual(Video.objects.get().full_name, self.video_name)
        self.assertEqual(
            Video.objects.get().is_consent_footage,
            self.video_data["data"]["attributes"]["is_consent_footage"],
        )
        self.assertEqual(
            Video.objects.get().pipe_name,
            self.video_data["data"]["attributes"]["pipe_name"],
        )
        self.assertEqual(
            Video.objects.get().pipe_numeric_id,
            int(self.video_data["data"]["attributes"]["pipe_numeric_id"]),
        )
        timestamp_from_db = Video.objects.get().s3_timestamp.strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )
        utc_tz = pytz.timezone("UTC")
        timestamp_sent = (
            datetime.strptime(
                self.video_data["data"]["attributes"]["s3_timestamp"],
                "%Y-%m-%d %H:%M:%S.%f",
            )
            .astimezone(utc_tz)
            .strftime("%Y-%m-%d %H:%M:%S.%f")
        )
        self.assertEqual(timestamp_from_db, timestamp_sent)
        self.assertEqual(
            Video.objects.get().frame_id,
            self.video_data["data"]["attributes"]["frame_id"],
        )
        self.assertEqual(Video.objects.get().response_id, self.response.id)
        self.assertEqual(Video.objects.get().study_id, self.study.id)
        self.delete_video_by_name(self.video_name)
        self.assertEqual(Video.objects.count(), 0)

    def testPostResponseNeedSignature(self):
        """Request should fail if there's no signature in the header"""
        self.assertEqual(Video.objects.count(), 0)
        api_response = self.client.post(
            self.video_url,
            self.video_data_json,
            content_type="application/vnd.api+json",
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Video.objects.count(), 0)

    def testPostResponseNeedValidSignature(self):
        """Request should fail if the signature exists but doesn't match"""
        self.assertEqual(Video.objects.count(), 0)
        self.headers = {
            "X_AWS_LAMBDA_HMAC_SIG": "".join(
                random.choices(string.ascii_lowercase + string.digits, k=64)
            )
        }
        api_response = self.client.post(
            self.video_url,
            self.video_data_json,
            content_type="application/vnd.api+json",
            headers=self.headers,
        )
        self.assertEqual(api_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Video.objects.count(), 0)

    def testPostResponseNeedData(self):
        """POST request with empty data should fail"""
        self.assertEqual(Video.objects.count(), 0)
        self.video_data = {}
        self.video_data_json = self.dict_to_json_bytes(self.video_data)
        self.video_data_to_hash = self.dict_to_json_bytes(self.video_data)
        self.calculate_signature()
        self.headers = {"X_AWS_LAMBDA_HMAC_SIG": self.signature}
        api_response = self.client.post(
            self.video_url,
            self.video_data_json,
            content_type="application/vnd.api+json",
            headers=self.headers,
        )
        self.assertEqual(api_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(api_response.data[0]["detail"].code, "parse_error")
        self.assertEqual(api_response.data[0]["source"]["pointer"], "/data")
        self.assertEqual(Video.objects.count(), 0)

    def testPostResponseNeedVideoProperties(self):
        """POST request with incorrect resource type should fail"""
        self.assertEqual(Video.objects.count(), 0)
        self.video_data["data"]["type"] = "bad"
        self.video_data_json = self.dict_to_json_bytes(self.video_data)
        self.create_data_to_hash()
        self.calculate_signature()
        self.headers = {"X_AWS_LAMBDA_HMAC_SIG": self.signature}
        api_response = self.client.post(
            self.video_url,
            self.video_data_json,
            content_type="application/vnd.api+json",
            headers=self.headers,
        )
        self.assertEqual(api_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Video.objects.count(), 0)

    def testPostResponseWithMissingAttribute(self):
        """POST request with missing required data attribute should fail"""
        self.assertEqual(Video.objects.count(), 0)
        del self.video_data["data"]["attributes"]["full_name"]
        self.video_data_json = self.dict_to_json_bytes(self.video_data)
        self.create_data_to_hash()
        self.calculate_signature()
        self.headers = {"X_AWS_LAMBDA_HMAC_SIG": self.signature}
        api_response = self.client.post(
            self.video_url,
            self.video_data_json,
            content_type="application/vnd.api+json",
            headers=self.headers,
        )
        self.assertEqual(api_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Video.objects.count(), 0)

    # Non-POST requests should all fail - method not allowed
    def testGetResponse(self):
        """GET requests should fail"""
        api_response = self.client.get(
            self.video_url,
            content_type="application/vnd.api+json",
            headers=self.headers,
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def testPutResponse(self):
        """Put should fail even with a valid ID/PK and signature"""
        self.assertEqual(Video.objects.count(), 0)
        api_response = self.sendPostResponse()
        self.assertEqual(api_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Video.objects.count(), 1)
        video_pk = Video.objects.get().id
        self.video_data["data"]["attributes"]["pk"] = video_pk
        self.video_data["data"]["attributes"]["frame_id"] = "0-different-frame-name"
        self.video_data_json = self.dict_to_json_bytes(self.video_data)
        self.create_data_to_hash()
        self.calculate_signature()
        self.headers = {"X_AWS_LAMBDA_HMAC_SIG": self.signature}
        api_response_put = self.client.put(
            self.video_url,
            self.video_data_json,
            content_type="application/vnd.api+json",
            headers=self.headers,
        )
        self.assertEqual(
            api_response_put.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
        self.assertEqual(Video.objects.count(), 1)
        self.assertEqual(Video.objects.get().frame_id, "0-video-consent")
        self.delete_video_by_name(self.video_name)
        self.assertEqual(Video.objects.count(), 0)

    def testPatchResponse(self):
        """Patch should fail even with a valid ID/PK and signature"""
        self.assertEqual(Video.objects.count(), 0)
        api_response = self.sendPostResponse()
        self.assertEqual(api_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Video.objects.count(), 1)
        video_pk = Video.objects.get().id
        self.video_data["data"]["attributes"]["pk"] = video_pk
        self.video_data["data"]["attributes"]["frame_id"] = "0-different-frame-name"
        del self.video_data["data"]["attributes"]["s3_timestamp"]
        del self.video_data["data"]["relationships"]
        self.video_data_json = self.dict_to_json_bytes(self.video_data)
        self.create_data_to_hash()
        self.calculate_signature()
        self.headers = {"X_AWS_LAMBDA_HMAC_SIG": self.signature}
        api_response_patch = self.client.patch(
            self.video_url,
            self.video_data_json,
            content_type="application/vnd.api+json",
            headers=self.headers,
        )
        self.assertEqual(
            api_response_patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
        self.assertEqual(Video.objects.count(), 1)
        self.delete_video_by_name(self.video_name)
        self.assertEqual(Video.objects.count(), 0)

    def testDeleteResponse(self):
        """Delete should fail even with a valid ID/PK and signature"""
        self.assertEqual(Video.objects.count(), 0)
        api_response = self.sendPostResponse()
        self.assertEqual(api_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Video.objects.count(), 1)
        api_response_no_pk = self.client.delete(
            self.video_url,
            content_type="application/vnd.api+json",
            headers=self.headers,
        )
        self.assertEqual(
            api_response_no_pk.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
        self.assertEqual(Video.objects.count(), 1)
        video_pk = Video.objects.get().id
        video_url_with_pk = self.video_url + str(video_pk)
        api_response_with_pk = self.client.delete(
            video_url_with_pk,
            self.video_data_json,
            content_type="application/vnd.api+json",
            headers=self.headers,
            follow=True,
        )
        self.assertEqual(
            api_response_with_pk.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
        self.assertEqual(Video.objects.count(), 1)
        self.delete_video_by_name(self.video_name)
        self.assertEqual(Video.objects.count(), 0)

    def testHeadResponse(self):
        self.assertEqual(Video.objects.count(), 0)
        api_response = self.client.head(
            self.video_url,
            content_type="application/vnd.api+json",
            headers=self.headers,
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(Video.objects.count(), 0)

    def testOptionsResponse(self):
        """OPTIONS requests should fail"""
        api_response_no_data = self.client.options(
            self.video_url,
            content_type="application/vnd.api+json",
            headers=self.headers,
        )
        self.assertEqual(
            api_response_no_data.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
        api_response_data = self.client.options(
            self.video_url,
            self.video_data,
            content_type="application/vnd.api+json",
            headers=self.headers,
        )
        self.assertEqual(
            api_response_data.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def testTraceResponse(self):
        """TRACE requests should fail"""
        self.assertEqual(Video.objects.count(), 0)
        api_response = self.client.trace(
            self.video_url,
            content_type="application/vnd.api+json",
            headers=self.headers,
        )
        self.assertEqual(api_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(Video.objects.count(), 0)
