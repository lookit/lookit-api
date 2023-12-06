import logging
import urllib.parse
from unittest import skip

from django.test import TestCase
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import Child, User
from studies.models import Lab, Response, Study, StudyType, Video


class RenameVideoTestCase(APITestCase):
    def setUp(self):
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
