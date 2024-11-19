import datetime
import uuid
from datetime import date
from unittest.mock import patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import Child, User
from attachment_helpers import S3_CLIENT, get_url
from studies.models import Lab, Response, Study, StudyType
from web.views import create_external_response, get_jspsych_response

TWO_FACTOR_AUTH_SESSION_KEY = "using_2FA"


class TestView:
    def __init__(self, child_id):
        self.kwargs = {"child_id": child_id}


def get_researcher(study_type):
    researcher = User.objects.create(
        is_active=True, is_researcher=True, username=str(uuid.uuid4())
    )
    researcher_child = Child.objects.create(
        birthday=datetime.date.today(), user=researcher
    )
    lab = Lab.objects.get(name="Sandbox lab")
    researcher_study = Study.objects.create(
        study_type=study_type,
        name="researcher external study",
        image=SimpleUploadedFile(
            "fake_image.png", b"fake-stuff", content_type="image/png"
        ),
        metadata={"url": "https://lookit.mit.edu", "scheduled": True},
        public=False,
        shared_preview=True,
        lab=lab,
    )
    researcher_study.state = "active"
    researcher_study.save()
    return (researcher, researcher_study, researcher_child)


def get_user(study_type):
    user = User.objects.create(is_active=True, username=str(uuid.uuid4()))
    child = Child.objects.create(birthday=datetime.date.today(), user=user)
    lab = Lab.objects.get(name="Sandbox lab")
    study = Study.objects.create(
        study_type=study_type,
        name="external study",
        image=SimpleUploadedFile(
            "fake_image.png", b"fake-stuff", content_type="image/png"
        ),
        metadata={"url": "", "scheduled": True},
        public=False,
        lab=lab,
    )
    study.state = "active"
    study.save()

    return (user, study, child)


def make_boto_client(mock):
    mock().get_federation_token.return_value = {
        "Credentials": {
            "AccessKeyId": "",
            "SecretAccessKey": "",
            "SessionToken": "",
            "Expiration": date.today(),
        }
    }


class Force2FAClient(Client):
    """For convenience when testing researcher views, let's just pretend everyone is two-factor auth'd."""

    @property
    def session(self):
        _session = super().session
        _session[TWO_FACTOR_AUTH_SESSION_KEY] = True
        return _session


class RecordingMethodJsPsychTestCase(TestCase):
    @patch("boto3.client")
    def test_jspysch(self, mock_client):
        make_boto_client(mock_client)
        _, study, child = get_user(StudyType.get_jspsych())
        context = {"study": study, "view": TestView(child.uuid)}
        response = get_jspsych_response(context)
        self.assertEqual(response.recording_method, "jspsych")

    @patch("boto3.client")
    def test_jspsych_view(self, mock_client):
        make_boto_client(mock_client)
        user, study, child = get_user(StudyType.get_jspsych())
        url = reverse(
            "web:jspsych-experiment",
            kwargs={"uuid": study.uuid, "child_id": child.uuid},
        )
        self.client.force_login(user)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["response"].recording_method, "jspsych")

    @patch("boto3.client")
    def test_jspsych_researcher_preview(self, mock_client):
        make_boto_client(mock_client)
        user, study, child = get_researcher(StudyType.get_jspsych())
        url = reverse(
            "exp:preview-jspsych",
            kwargs={"uuid": study.uuid, "child_id": child.uuid},
        )
        self.client = Force2FAClient()
        self.client.force_login(user)
        response = self.client.get(url, follow=True)

        self.assertEqual(response.redirect_chain, [])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context_data["response"].recording_method, "jspsych")


class RecordingMethodExternalTestCase(TestCase):
    def test_external(self):
        _, study, child = get_user(StudyType.get_external())
        response = create_external_response(study, child.uuid)
        self.assertIsNone(response.recording_method)

    def test_external_view(self):
        _, study, child = get_user(StudyType.get_external())
        url = reverse("web:study-detail", kwargs={"uuid": study.uuid})
        response = self.client.post(url, {"child_id": child.uuid})
        response_uuid = response.url.split("response=")[1]
        self.assertIsNone(Response.objects.get(uuid=response_uuid).recording_method)

    def test_external_researcher_preview(self):
        researcher, researcher_study, researcher_child = get_researcher(
            StudyType.get_external()
        )
        self.client = Force2FAClient()
        self.client.force_login(researcher)
        url = reverse("exp:preview-detail", kwargs={"uuid": researcher_study.uuid})
        response = self.client.post(url, {"child_id": researcher_child.uuid})
        response_uuid = response.url.split("response=")[1]
        self.assertIsNone(Response.objects.get(uuid=response_uuid).recording_method)


class RecordingMethodEFPTestCase(TestCase):
    def test_efp(self):
        study_type = StudyType.get_ember_frame_player()
        _, study, child = get_user(study_type)
        response = Response.objects.create(
            study_type=study_type, child=child, study=study
        )
        self.assertEqual(response.recording_method, "pipe")


class GetUrlTestCase(TestCase):
    @override_settings(BUCKET_NAME=uuid.uuid4)
    @patch.object(S3_CLIENT, "generate_presigned_url")
    def test_efp_pipe_bucket(self, mock_url):
        pipe = True
        jspsych = False
        header = False
        test_url = "some url"
        mock_url.return_value = test_url
        self.assertEqual(get_url("some video key", pipe, jspsych, header), test_url)
        _, kwargs = mock_url.call_args
        self.assertEqual(kwargs["Params"]["Bucket"], settings.BUCKET_NAME)
        self.assertTrue(settings.BUCKET_NAME)

    @override_settings(S3_BUCKET_NAME=uuid.uuid4)
    @patch.object(S3_CLIENT, "generate_presigned_url")
    def test_efp_recordrtc_bucket(self, mock_url):
        pipe = False
        jspsych = False
        header = False
        test_url = "some url"
        mock_url.return_value = test_url
        self.assertEqual(get_url("some video key", pipe, jspsych, header), test_url)
        _, kwargs = mock_url.call_args
        self.assertEqual(kwargs["Params"]["Bucket"], settings.S3_BUCKET_NAME)
        self.assertTrue(settings.S3_BUCKET_NAME)

    @override_settings(JSPSYCH_S3_BUCKET=uuid.uuid4)
    @patch.object(S3_CLIENT, "generate_presigned_url")
    def test_jspsych_bucket(self, mock_url):
        pipe = False
        jspsych = True
        header = False
        test_url = "some url"
        mock_url.return_value = test_url
        self.assertEqual(get_url("some video key", pipe, jspsych, header), test_url)
        _, kwargs = mock_url.call_args
        self.assertEqual(kwargs["Params"]["Bucket"], settings.JSPSYCH_S3_BUCKET)
        self.assertTrue(settings.JSPSYCH_S3_BUCKET)

    @patch.object(S3_CLIENT, "generate_presigned_url")
    def test_attachment(self, mock_url):
        test_url = "some url"
        pipe = True
        jspsych = False
        header = True
        mock_url.return_value = test_url
        self.assertEqual(get_url("some video key", pipe, jspsych, header), test_url)
        _, kwargs = mock_url.call_args
        self.assertEqual(kwargs["Params"]["ResponseContentDisposition"], "attachment")
