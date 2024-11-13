import datetime
import uuid
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Child, User
from attachment_helpers import get_url
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


class Force2FAClient(Client):
    """For convenience when testing researcher views, let's just pretend everyone is two-factor auth'd."""

    @property
    def session(self):
        _session = super().session
        _session[TWO_FACTOR_AUTH_SESSION_KEY] = True
        return _session


class RecordingMethodJsPsychTestCase(TestCase):
    def test_jspysch(self):
        user, study, child = get_user(StudyType.get_jspsych())
        context = {"study": study, "view": TestView(child.uuid)}
        response = get_jspsych_response(context)
        self.assertEqual(response.recording_method, "jspsych")

    def test_jspsych_view(self):
        user, study, child = get_user(StudyType.get_jspsych())
        url = reverse(
            "web:jspsych-experiment",
            kwargs={"uuid": study.uuid, "child_id": child.uuid},
        )
        self.client.force_login(user)
        response = self.client.get(url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["response"].recording_method, "jspsych")

    def test_jspsych_researcher_preview(self):
        cache.clear()
        user, study, child = get_researcher(StudyType.get_jspsych())
        url = reverse(
            "exp:preview-jspsych",
            kwargs={"uuid": study.uuid, "child_id": child.uuid},
        )
        self.client = Force2FAClient()
        self.client.force_login(user)
        response = self.client.get(url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context_data["response"].recording_method, "jspsych")


class RecordingMethodExternalTestCase(TestCase):
    def test_external(self):
        user, study, child = get_user(StudyType.get_external())
        response = create_external_response(study, child.uuid)
        self.assertIsNone(response.recording_method)

    def test_external_view(self):
        user, study, child = get_user(StudyType.get_external())
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
        user, study, child = get_user(study_type)
        response = Response.objects.create(
            study_type=study_type, child=child, study=study
        )
        self.assertEqual(response.recording_method, "pipe")


class GetUrlTestCase(TestCase):
    def test_efp_pipe_bucket(self):
        pipe = True
        jspsych = False
        header = False
        url = urlparse(get_url("some video key", pipe, jspsych, header))
        self.assertEqual(url.hostname.split(".")[0], settings.BUCKET_NAME)

    def test_efp_recordrtc_bucket(self):
        pipe = False
        jspsych = False
        header = False
        url = urlparse(get_url("some video key", pipe, jspsych, header))
        self.assertEqual(url.hostname.split(".")[0], settings.S3_BUCKET_NAME)

    def test_jspsych_bucket(self):
        pipe = False
        jspsych = True
        header = False
        url = urlparse(get_url("some video key", pipe, jspsych, header))
        self.assertEqual(url.path.split("/")[1], settings.JSPSYCH_S3_BUCKET)

    def test_attachment(self):
        pipe = True
        jspsych = False
        header = True
        url = urlparse(get_url("some video key", pipe, jspsych, header))
        query = parse_qs(url.query)
        self.assertEqual(query["response-content-disposition"], ["attachment"])
