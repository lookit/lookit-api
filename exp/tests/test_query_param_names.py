from urllib.parse import parse_qs, urlparse

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms.models import model_to_dict
from django.test import Client, TestCase
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework.test import APIClient

from accounts.models import Child, User
from exp.tests import test_study_forms
from studies.forms import StudyCreateForm, StudyEditForm
from studies.models import Response, Study, StudyType, validate_query_param_names
from web.views import get_external_url


def query_of(url):
    return parse_qs(urlparse(url).query)


class QueryParamNamesValidatorTestCase(TestCase):
    def test_valid_values(self):
        for value in [
            None,
            {},
            {"child": "CHILD"},
            {"response": "entry.264543955"},
            {"child": "child_id-1", "response": "resp~2"},
        ]:
            validate_query_param_names(value)

    def test_malformed_values(self):
        for value in [
            "CHILD",
            ["child"],
            {"kid": "CHILD"},
            {"child": 5},
            {"child": None},
            {"child": ""},
            {"child": "has space"},
            {"child": "a&b"},
            {"child": "x" * 101},
            {"child": "same", "response": "same"},
            {"child": "response"},
        ]:
            with self.assertRaises(ValidationError, msg=value):
                validate_query_param_names(value)


class QueryParamNamesFormTestCase(TestCase):
    setUp = test_study_forms.StudyFormTestCase.setUp

    def form_data(self, **names):
        data = model_to_dict(self.study)
        data["preview_summary"] = "Summary"
        data["contact_name"] = "Test PI"
        data["contact_email"] = "test@example.com"
        data.update(names)
        return data

    def save_edit(self, **names):
        form = StudyEditForm(
            data=self.form_data(**names), instance=self.study, user=self.study_designer
        )
        self.assertTrue(form.is_valid(), form.errors)
        return form.save()

    def create(self, **names):
        data = self.form_data(**names)
        data["lab"] = self.main_lab.id
        image = SimpleUploadedFile(
            "image.png",
            open("exp/tests/static/study_image.png", "rb").read(),
            content_type="image/png",
        )
        form = StudyCreateForm(data=data, files={"image": image}, user=self.study_admin)
        self.assertTrue(form.is_valid(), form.errors)
        form.instance.creator = self.study_admin
        return form.save()

    def test_create_with_defaults(self):
        study = self.create()
        self.assertIsNone(study.query_param_names)
        self.assertEqual(
            study.get_query_param_names(), {"child": "child", "response": "response"}
        )

    def test_create_with_custom_names(self):
        cases = [
            ({"child_param_name": "CHILD"}, {"child": "CHILD"}),
            ({"response_param_name": "entry.123"}, {"response": "entry.123"}),
            (
                {"child_param_name": "CHILD", "response_param_name": "RESPONSE"},
                {"child": "CHILD", "response": "RESPONSE"},
            ),
        ]
        for form_names, stored in cases:
            self.assertEqual(self.create(**form_names).query_param_names, stored)

    def test_entering_the_default_name_stores_nothing(self):
        study = self.create(child_param_name="child", response_param_name="response")
        self.assertIsNone(study.query_param_names)

    def test_edit_default_to_custom_and_back(self):
        self.assertEqual(
            self.save_edit(child_param_name="CHILD").query_param_names,
            {"child": "CHILD"},
        )
        form = StudyEditForm(instance=self.study, user=self.study_designer)
        self.assertEqual(form.initial["child_param_name"], "CHILD")
        self.assertIsNone(self.save_edit(child_param_name="").query_param_names)

    def test_editing_names_keeps_approved_study_approved(self):
        # Contact info matching the form data, so only the names change.
        Study.objects.filter(pk=self.study.pk).update(
            state="approved", contact_info="Test PI (contact: test@example.com)"
        )
        self.study.refresh_from_db()
        study = self.save_edit(child_param_name="CHILD", response_param_name="RESP")
        study.refresh_from_db()
        self.assertEqual(study.state, "approved")
        self.assertEqual(
            study.query_param_names, {"child": "CHILD", "response": "RESP"}
        )

    def test_invalid_names_rejected(self):
        for names, field in [
            ({"child_param_name": "has space"}, "child_param_name"),
            ({"response_param_name": "a&b"}, "response_param_name"),
            (
                {"child_param_name": "x", "response_param_name": "x"},
                "response_param_name",
            ),
            ({"child_param_name": "response"}, "response_param_name"),
        ]:
            form = StudyEditForm(
                data=self.form_data(**names),
                instance=self.study,
                user=self.study_designer,
            )
            self.assertFalse(form.is_valid(), names)
            self.assertIn(field, form.errors, names)


class ExternalStudyUrlTestCase(TestCase):
    def setUp(self):
        self.study = G(
            Study,
            metadata={"url": "https://example.com/book?source=chs"},
            study_type=StudyType.get_external(),
        )
        self.response = G(Response, child=G(Child), study=self.study)

    def test_default_names(self):
        query = query_of(get_external_url(self.study, self.response))
        self.assertEqual(query["response"], [str(self.response.uuid)])
        self.assertIn("child", query)
        self.assertEqual(query["source"], ["chs"])

    def test_custom_names(self):
        self.study.query_param_names = {"child": "CHILD", "response": "entry.123"}
        query = query_of(get_external_url(self.study, self.response))
        self.assertEqual(query["entry.123"], [str(self.response.uuid)])
        self.assertIn("CHILD", query)
        self.assertNotIn("child", query)
        self.assertNotIn("response", query)


class ExitUrlTestCase(TestCase):
    def setUp(self):
        self.study = G(
            Study,
            exit_url="https://example.com/done?source=chs",
            study_type=StudyType.get_ember_frame_player(),
        )
        Study.objects.filter(pk=self.study.pk).update(state="active")
        self.client = APIClient()
        self.client.force_authenticate(user=G(User, is_active=True))

    def api_exit_url(self):
        url = reverse("api:study-list", kwargs={"version": "v2"})
        return self.client.get(f"{url}{self.study.uuid}/").data["exit_url"]

    def test_api_sends_real_exit_url_by_default(self):
        self.assertEqual(self.api_exit_url(), "https://example.com/done?source=chs")

    def test_api_sends_redirect_for_custom_names(self):
        Study.objects.filter(pk=self.study.pk).update(
            query_param_names={"child": "CHILD"}
        )
        self.assertEqual(
            self.api_exit_url(),
            "http://testserver"
            + reverse("web:study-exit", kwargs={"uuid": self.study.uuid}),
        )

    def test_redirect_renames_params(self):
        Study.objects.filter(pk=self.study.pk).update(
            query_param_names={"child": "CHILD", "response": "entry.123"}
        )
        response = Client().get(
            reverse("web:study-exit", kwargs={"uuid": self.study.uuid}),
            {"child": "abc123", "response": "resp-uuid"},
        )
        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertTrue(location.startswith("https://example.com/done?"))
        self.assertEqual(
            query_of(location),
            {"source": ["chs"], "CHILD": ["abc123"], "entry.123": ["resp-uuid"]},
        )
