import json

import boto3
from django.core.exceptions import SuspiciousFileOperation
from django.test import Client, TestCase
from django.urls import reverse
from django_dynamic_fixture import G
from moto import mock_s3

from accounts.models import Child, User
from project import settings
from studies.models import Lab, Response, Study, StudyType, Video


class RenameVideoTestCase(TestCase):
    def setUp(self):
        self.researcher = G(User, is_active=True, is_researcher=True)
        self.participant = G(User, is_active=True)
        self.child = G(Child, user=self.participant, given_name="Sally")
        self.study_type = G(StudyType, name="default", id=1)
        self.lab = G(Lab, name="MIT")
        self.study = G(
            Study, creator=self.researcher, study_type=self.study_type, lab=self.lab
        )
        self.url = reverse("exp:rename-video")
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

        self.client = Client()
        self.non_consent_payload = {
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
                "payload": f"videoStream_{self.study.uuid}_3-test-trials_{self.response.uuid}_1599060715494_569",
            },
        }

        self.consent_payload = {
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
                "payload": f"videoStream_{self.study.uuid}_2-my-consent-frame_{self.response.uuid}_1599060715494_569",
            },
        }

    @mock_s3
    def test_create_non_consent_video_from_pipe_payload_with_valid_names(self):
        s3_client = boto3.client("s3")
        s3_client.create_bucket(Bucket=settings.BUCKET_NAME)
        s3_client.put_object(
            Bucket=settings.BUCKET_NAME,
            Key="oldfilename.mp4",
            Body=json.dumps({"fake": "videodata"}),
        )

        video = Video.from_pipe_payload(self.non_consent_payload)
        self.assertEqual(
            video.full_name, f"{self.non_consent_payload['data']['payload']}.mp4"
        )
        self.assertEqual(video.study, self.study)
        self.assertEqual(video.response, self.response)
        self.assertFalse(video.is_consent_footage)

    @mock_s3
    def test_create_consent_video_from_pipe_payload_with_valid_names(self):
        s3_client = boto3.client("s3")
        s3_client.create_bucket(Bucket=settings.BUCKET_NAME)
        s3_client.put_object(
            Bucket=settings.BUCKET_NAME,
            Key="oldfilename.mp4",
            Body=json.dumps({"fake": "videodata"}),
        )

        video = Video.from_pipe_payload(self.consent_payload)
        self.assertEqual(
            video.full_name, f"{self.consent_payload['data']['payload']}.mp4"
        )
        self.assertEqual(video.study, self.study)
        self.assertEqual(video.response, self.response)
        self.assertTrue(video.is_consent_footage)

    @mock_s3
    def test_rename_from_invalid_videoname(self):
        s3_client = boto3.client("s3")
        s3_client.create_bucket(Bucket=settings.BUCKET_NAME)
        s3_client.put_object(
            Bucket=settings.BUCKET_NAME,
            Key="oldfilename.mp4",
            Body=json.dumps({"fake": "videodata"}),
        )

        invalid_original_name_payload = {
            "version": "1.0",
            "event": "video_copied_s3",
            "data": {
                "s3UploadStatus": "upload success",
                "videoName": "old/filename",
                "type": "MP4",
                "size": 493534,
                "id": "123",
                "url": "https://bucketname.s3.amazonaws.com/oldfilename.mp4",
                "snapshotUrl": "https://bucketname.s3.amazonaws.com/oldfilename.jpg",
                "bucket": "bucketname",
                "region": "us-east-1",
                "acl": "public-read",
                "payload": f"videoStream_{self.study.uuid}_2-my-consent-frame_{self.response.uuid}_1599060715494_569",
            },
        }
        self.assertRaises(
            SuspiciousFileOperation,
            Video.from_pipe_payload,
            invalid_original_name_payload,
        )

    @mock_s3
    def test_rename_to_invalid_videoname(self):
        s3_client = boto3.client("s3")
        s3_client.create_bucket(Bucket=settings.BUCKET_NAME)
        s3_client.put_object(
            Bucket=settings.BUCKET_NAME,
            Key="oldfilename.mp4",
            Body=json.dumps({"fake": "videodata"}),
        )

        invalid_new_name_payload = {
            "version": "1.0",
            "event": "video_copied_s3",
            "data": {
                "s3UploadStatus": "upload success",
                "videoName": "old/filename",
                "type": "MP4",
                "size": 493534,
                "id": "123",
                "url": "https://bucketname.s3.amazonaws.com/oldfilename.mp4",
                "snapshotUrl": "https://bucketname.s3.amazonaws.com/oldfilename.jpg",
                "bucket": "bucketname",
                "region": "us-east-1",
                "acl": "public-read",
                "payload": f"videoStream_{self.study.uuid}_2_my-consent-frame_{self.response.uuid}_1599060715494_569",
            },
        }
        self.assertRaises(
            SuspiciousFileOperation, Video.from_pipe_payload, invalid_new_name_payload
        )

    @mock_s3
    def test_rename_to_videoname_for_missing_response(self):
        s3_client = boto3.client("s3")
        s3_client.create_bucket(Bucket=settings.BUCKET_NAME)
        s3_client.put_object(
            Bucket=settings.BUCKET_NAME,
            Key="oldfilename.mp4",
            Body=json.dumps({"fake": "videodata"}),
        )
        self.response.delete()
        self.assertRaises(
            Response.DoesNotExist, Video.from_pipe_payload, self.consent_payload
        )


# TODO: test webhook authentication
