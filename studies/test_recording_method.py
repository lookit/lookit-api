import datetime
import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Child, User
from studies.models import Lab, Response, Study, StudyType
from web.views import create_external_response, get_jspsych_response

TWO_FACTOR_AUTH_SESSION_KEY = "using_2FA"


class TestView:
    def __init__(self, child_id):
        self.kwargs = {"child_id": child_id}


def get_researcher():
    researcher = User.objects.create(
        is_active=True, is_researcher=True, username=str(uuid.uuid4())
    )
    researcher_child = Child.objects.create(
        birthday=datetime.date.today(), user=researcher
    )
    lab = Lab.objects.get(name="Sandbox lab")
    researcher_study = Study.objects.create(
        study_type=StudyType.get_external(),
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


def get_user():
    user = User.objects.create(is_active=True, username=str(uuid.uuid4()))
    child = Child.objects.create(birthday=datetime.date.today(), user=user)
    lab = Lab.objects.get(name="Sandbox lab")
    study = Study.objects.create(
        study_type=StudyType.get_external(),
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
        user, study, child = get_user()
        context = {"study": study, "view": TestView(child.uuid)}
        response = get_jspsych_response(context)
        self.assertEqual(response.recording_method, "jspsych")

    def test_jspsych_view(self):
        user, study, child = get_user()
        url = reverse(
            "web:jspsych-experiment",
            kwargs={"uuid": study.uuid, "child_id": child.uuid},
        )
        self.client.force_login(user)
        response = self.client.get(url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["response"].recording_method, "jspsych")

    def test_jspsych_researcher_preview(self):
        user, study, child = get_researcher()
        url = reverse(
            "exp:preview-jspsych",
            kwargs={"uuid": study.uuid, "child_id": child.uuid},
        )
        self.client = Force2FAClient()
        self.client.force_login(user)
        response = self.client.get(url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["response"].recording_method, "jspsych")


class RecordingMethodExternalTestCase(TestCase):
    def test_external(self):
        user, study, child = get_user()
        response = create_external_response(study, child.uuid)
        self.assertIsNone(response.recording_method)

    def test_external_view(self):
        user, study, child = get_user()
        url = reverse("web:study-detail", kwargs={"uuid": study.uuid})
        response = self.client.post(url, {"child_id": child.uuid})
        response_uuid = response.url.split("response=")[1]
        self.assertIsNone(Response.objects.get(uuid=response_uuid).recording_method)

    def test_external_researcher_preview(self):
        researcher, researcher_study, researcher_child = get_researcher()
        self.client = Force2FAClient()
        self.client.force_login(researcher)
        url = reverse("exp:preview-detail", kwargs={"uuid": researcher_study.uuid})
        response = self.client.post(url, {"child_id": researcher_child.uuid})
        response_uuid = response.url.split("response=")[1]
        self.assertIsNone(Response.objects.get(uuid=response_uuid).recording_method)
