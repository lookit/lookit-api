import base64
import hashlib
import hmac
import json
import logging
import math
import random
import time
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import Child, User
from studies.models import Lab, Response, Study, StudyType, Video


def create_test_video_name(study_uuid, frame_id, resp_uuid, consent):
    # Helper create a video name for the test video that meets the file name convention needed for processing
    prefix = "videoStream"
    if consent:
        prefix = f"consent-{prefix}"

    timestamp = str(int(time.time() * 1000))
    rand_digits = str(math.floor(random.random() * 1000))
    # No file extension
    return f"{prefix}_{str(study_uuid)}_{frame_id}_{str(resp_uuid)}_{timestamp}_{rand_digits}"


class RenameVideoTestCase(APITestCase):
    def setUp(self):
        # Start patcher to mock S3 resource object defined in studies.models, which is used in 'Video.from_pipe_payload'.
        # We can't use the patch decorator at the class level and pass it to setUp, so instead we'll set up the patch and call start here, and stop the patch in tearDown.
        self.s3_patcher = patch("studies.models.S3_RESOURCE.Object")
        self.mock_s3_object = self.s3_patcher.start()
        mock_obj = MagicMock()
        self.mock_s3_object.return_value = mock_obj
        mock_obj.copy_from.return_value = None
        mock_obj.delete.return_value = None

        self.researcher = G(User, is_active=True, is_researcher=True)
        self.participant = G(User, is_active=True)
        self.child = G(Child, user=self.participant, given_name="Sally")
        self.lab = G(Lab, name="MIT")
        self.study = G(
            Study,
            creator=self.researcher,
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )
        self.response = G(Response, child=self.child, study=self.study, completed=True)

        self.client = APIClient()
        self.secret = settings.PIPE_WEBHOOK_KEY
        self.url = reverse("exp:rename-video")
        # The Django test client's default domain is http://testserver
        self.full_url = f"http://testserver{self.url}"

        # Two videos associated with the response, one flagged as consent and one not
        self.new_video_filename = create_test_video_name(
            self.study.uuid, "frame-id", self.response.uuid, False
        )
        self.payload = {
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
                "payload": self.new_video_filename,
            },
        }
        self.new_video_filename_consent = create_test_video_name(
            self.study.uuid, "consent-frame-id", self.response.uuid, True
        )
        self.payload_consent = {
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
                "payload": self.new_video_filename_consent,
            },
        }

    def testRenameVideo(self):
        # Mimic the POST request construction from Pipe webhook
        payload_str = json.dumps(self.payload)
        message = self.full_url + payload_str
        signature = base64.b64encode(
            hmac.new(
                self.secret.encode("utf-8"),
                message.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("utf-8")
        post_data = {
            "payload": payload_str,
        }
        headers = {
            "HTTP_HOST": "testserver",
            "HTTP_X_PIPE_SIGNATURE": signature,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        api_response = self.client.post(self.url, data=post_data, **headers)
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertIn(
            f"oldfilename --> {self.new_video_filename}",
            api_response.content.decode("utf-8"),
        )

    def testRenameVideoConsent(self):
        # Mimic the POST request construction from Pipe webhook
        payload_str = json.dumps(self.payload_consent)
        message = self.full_url + payload_str
        signature = base64.b64encode(
            hmac.new(
                self.secret.encode("utf-8"),
                message.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("utf-8")
        post_data = {
            "payload": payload_str,
        }
        headers = {
            "HTTP_HOST": "testserver",
            "HTTP_X_PIPE_SIGNATURE": signature,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        api_response = self.client.post(self.url, data=post_data, **headers)
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        # the from_pipe_payload/check_and_parse_pipe_payload methods strip "consent-" from the video object full_name when creating the Video object, and the response logs this version of the filename
        video_filename = self.new_video_filename_consent[len("consent-") :]
        self.assertIn(
            f"oldfilename --> {video_filename}", api_response.content.decode("utf-8")
        )

    def tearDown(self):
        # Clean up the S3 patch
        self.s3_patcher.stop()


class CheckPipeProcessingTestCase(TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.lab = G(Lab, name="MIT", approved_to_test=True)
        self.study_creator = G(User, is_active=True, is_researcher=True)
        self.study = G(
            Study,
            creator=self.study_creator,
            shared_preview=False,
            name="Test Study",
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )
        self.participant = G(User, is_active=True, given_name="Mom")
        self.child = G(Child, user=self.participant, given_name="Molly")
        self.response = G(
            Response,
            child=self.child,
            study=self.study,
            completed=False,
            completed_consent_frame=True,
            sequence=["0-video-config", "1-video-setup", "2-my-consent-frame"],
            exp_data={
                "0-video-config": {"frameType": "DEFAULT"},
                "1-video-setup": {"frameType": "DEFAULT"},
                "2-my-consent-frame": {"frameType": "CONSENT"},
            },
        )

    def test_valid_payload_parses(self):
        initial_payload = f"videoStream_{self.study.uuid}_3-test-trial_{self.response.uuid}_10349395959_359"
        (
            marked_as_consent,
            payload,
            study,
            frame_id,
            response,
            timestamp,
        ) = Video.check_and_parse_pipe_payload(initial_payload)

        self.assertFalse(marked_as_consent)
        self.assertEqual(payload, initial_payload)
        self.assertEqual(study.id, self.study.id)
        self.assertEqual(response.id, self.response.id)
        self.assertEqual(frame_id, "3-test-trial")
        self.assertEqual(timestamp, "10349395959")

    def test_consent_flag_detected_in_payload(self):
        initial_payload = f"consent-videoStream_{self.study.uuid}_3-test-trial_{self.response.uuid}_10349395959_359"
        (
            marked_as_consent,
            payload,
            study,
            frame_id,
            response,
            timestamp,
        ) = Video.check_and_parse_pipe_payload(initial_payload)

        self.assertTrue(marked_as_consent)
        self.assertEqual(
            payload,
            f"videoStream_{self.study.uuid}_3-test-trial_{self.response.uuid}_10349395959_359",
        )
        self.assertEqual(study.id, self.study.id)
        self.assertEqual(response.id, self.response.id)
        self.assertEqual(frame_id, "3-test-trial")
        self.assertEqual(timestamp, "10349395959")

    def test_payload_referencing_fake_study_errors(self):
        initial_payload = f"videoStream_{self.response.uuid}_3-test-trial_{self.response.uuid}_10349395959_359"
        self.assertRaises(
            Study.DoesNotExist, Video.check_and_parse_pipe_payload, initial_payload
        )

    def test_payload_referencing_fake_response_errors(self):
        initial_payload = f"videoStream_{self.study.uuid}_3-test-trial_{self.study.uuid}_10349395959_359"
        self.assertRaises(
            Response.DoesNotExist, Video.check_and_parse_pipe_payload, initial_payload
        )

    def test_payload_too_many_underscores_errors(self):
        initial_payload = f"videoStream_{self.study.uuid}_3_test_trial_{self.response.uuid}_10349395959_359"
        self.assertRaises(
            ValueError, Video.check_and_parse_pipe_payload, initial_payload
        )

    def tearDown(self):
        logging.disable(logging.NOTSET)
