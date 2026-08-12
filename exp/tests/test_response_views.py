import csv
import datetime
import io
import json
import re
import uuid
import zipfile
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.http import urlencode
from django_dynamic_fixture import G

from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from accounts.models import Child, DemographicData, User
from accounts.utils import hash_id
from exp.views.responses import (
    StudyResponseSetResearcherFields,
    get_frame_data,
)
from exp.views.responses_data import RESPONSE_COLUMNS
from studies.models import ConsentRuling, Lab, Response, Study, StudyType, Video
from studies.queries import (
    get_response_type_counts_external,
    get_summary_statistics_external,
)


class Force2FAClient(Client):
    @property
    def session(self):
        _session = super().session
        _session[TWO_FACTOR_AUTH_SESSION_KEY] = True
        return _session


# Run celery tasks right away, but don't catch errors from them. The relevant tasks for
# this case involve S3/GCP access which we're not testing.
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
@override_settings(CELERY_TASK_EAGER_PROPAGATES=False)
class ResponseViewsTestCase(TestCase):
    def setUp(self):
        self.client = Force2FAClient()

        n_participants = 5
        children_per_participant = 3

        self.study_admin = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 1"
        )
        self.study_reader = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 2"
        )
        self.study_previewer = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 4"
        )
        self.other_researcher = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 3"
        )
        self.participants = [
            G(User, is_active=True, given_name="Mom") for i in range(n_participants)
        ]

        self.lab = G(Lab, name="MIT")
        self.study = G(
            Study,
            creator=self.study_admin,
            shared_preview=False,
            name="Test Study",
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )
        # Note: currently not mocking Study.image field, because I couldn't get any of the
        # approaches outlined at https://stackoverflow.com/questions/26298821/django-testing-model-with-imagefield
        # working.
        self.study_shared_preview = G(
            Study,
            creator=self.study_admin,
            shared_preview=True,
            name="Test Study",
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )

        self.study.admin_group.user_set.add(self.study_admin)
        self.study.researcher_group.user_set.add(self.study_reader)
        self.study.preview_group.user_set.add(self.study_previewer)

        self.study_reader_child = G(
            Child,
            user=self.study_reader,
            given_name="Study reader child",
            birthday=datetime.date.today() - datetime.timedelta(30),
        )
        self.other_researcher_child = G(
            Child,
            user=self.other_researcher,
            given_name="Other researcher child",
            birthday=datetime.date.today() - datetime.timedelta(60),
        )

        self.children_for_participants = []
        self.demo_snapshots_for_participants = []
        self.responses = []
        self.preview_responses = []
        for part in self.participants:
            these_children = [
                G(
                    Child,
                    user=part,
                    given_name="Child" + str(i),
                    existing_conditions=Child.existing_conditions.multiple_birth,
                    birthday=datetime.date.today() - datetime.timedelta(60),
                )
                for i in range(children_per_participant)
            ]
            self.children_for_participants.append(these_children)
            demo_snapshot = G(DemographicData, user=part, density="urban")
            self.demo_snapshots_for_participants.append(demo_snapshot)
            self.responses += [
                G(
                    Response,
                    child=child,
                    study=self.study,
                    study_type=self.study.study_type,
                    completed=False,
                    completed_consent_frame=True,
                    sequence=["0-video-config", "1-video-setup", "2-my-consent-frame"],
                    exp_data={
                        "0-video-config": {"frameType": "DEFAULT"},
                        "1-video-setup": {"frameType": "DEFAULT"},
                        "2-my-consent-frame": {"frameType": "CONSENT"},
                    },
                    demographic_snapshot=demo_snapshot,
                )
                for child in these_children
            ]
            self.preview_responses += [
                G(
                    Response,
                    child=child,
                    study=self.study,
                    study_type=self.study.study_type,
                    completed=False,
                    is_preview=True,
                    completed_consent_frame=True,
                    sequence=["0-video-config", "1-video-setup", "2-my-consent-frame"],
                    exp_data={
                        "0-video-config": {"frameType": "DEFAULT"},
                        "1-video-setup": {"frameType": "DEFAULT"},
                        "2-my-consent-frame": {"frameType": "CONSENT"},
                    },
                    demographic_snapshot=demo_snapshot,
                )
                for child in these_children
            ]

        # Confirm consent for all responses

        self.n_previews = children_per_participant * n_participants
        self.consent_rulings = [
            G(
                ConsentRuling,
                response=response,
                action="accepted",
                arbiter=self.study_reader,
            )
            for response in self.responses + self.preview_responses
        ]

        self.all_response_urls = [
            reverse("exp:study-responses-all", kwargs={"pk": self.study.pk}),
            reverse(
                "exp:study-responses-children-summary-csv", kwargs={"pk": self.study.pk}
            ),
            reverse(
                "exp:study-responses-children-summary-dict-csv",
                kwargs={"pk": self.study.pk},
            ),
            reverse(
                "exp:study-hashed-id-collision-check", kwargs={"pk": self.study.pk}
            ),
            reverse(
                "exp:study-responses-download-frame-data-dict-csv",
                kwargs={"pk": self.study.pk},
            ),
            reverse(
                "exp:study-responses-download-frame-data-zip-csv",
                kwargs={"pk": self.study.pk},
            ),
            reverse(
                "exp:study-responses-download-frame-data-zip-psychds",
                kwargs={"pk": self.study.pk},
            ),
            reverse("exp:study-demographics", kwargs={"pk": self.study.pk}),
            reverse(
                "exp:study-demographics-download-json", kwargs={"pk": self.study.pk}
            ),
            reverse(
                "exp:study-demographics-download-csv", kwargs={"pk": self.study.pk}
            ),
            reverse(
                "exp:study-demographics-download-dict-csv", kwargs={"pk": self.study.pk}
            ),
            reverse("exp:study-responses-list", kwargs={"pk": self.study.pk}),
            reverse(
                "exp:study-responses-consent-manager", kwargs={"pk": self.study.pk}
            ),
            reverse("exp:study-responses-download-json", kwargs={"pk": self.study.pk}),
            reverse("exp:study-responses-download-csv", kwargs={"pk": self.study.pk}),
            reverse(
                "exp:study-responses-download-summary-dict-csv",
                kwargs={"pk": self.study.pk},
            ),
            reverse("exp:study-attachments", kwargs={"pk": self.study.pk}),
        ]
        # For testing researcher-editable response fields: researcher_session_status, researcher_payment_status, researcher_star, is_tallied
        self.editable_fields = StudyResponseSetResearcherFields.EDITABLE_FIELDS
        default_values = [
            "",
            "",
            False,
            False,
        ]  # These correspond to session status, payment status, star, and tallied response
        new_values = ["follow_up", "to_pay", True, True]
        self.fields_default_values = {
            self.editable_fields[i]: default_values[i]
            for i in range(len(self.editable_fields))
        }
        self.fields_new_values = {
            self.editable_fields[i]: new_values[i]
            for i in range(len(self.editable_fields))
        }

    def test_cannot_see_any_responses_views_unauthenticated(self):
        for url in self.all_response_urls:
            page = self.client.get(url)
            self.assertNotEqual(
                page.status_code,
                200,
                "Unauthenticated user not redirected from responses: " + url,
            )

    def test_cannot_see_any_responses_views_as_participant(self):
        self.client.force_login(self.participants[0])
        for url in self.all_response_urls:
            page = self.client.get(url)
            self.assertEqual(
                page.status_code,
                403,
                "Unassociated participant not forbidden to access responses: " + url,
            )

    def test_cannot_see_any_responses_views_as_unassociated_researcher(self):
        self.client.force_login(self.other_researcher)
        for url in self.all_response_urls:
            page = self.client.get(url)
            self.assertEqual(
                page.status_code,
                403,
                "Unassociated researcher not forbidden to access responses: " + url,
            )

    def test_can_see_response_views_as_study_researcher(self):
        self.client.force_login(self.study_reader)
        for url in self.all_response_urls:
            page = self.client.get(url)
            self.assertIn(
                page.status_code, [200, 302], "Unexpected status code for " + url
            )

    def test_can_see_video_attachments_as_study_researcher(self):
        self.client.force_login(self.study_reader)
        # Add a video for each response
        self.videos = [
            G(
                Video,
                frame_id="2-my-consent-frame",
                full_name=f"videoStream_{self.study.uuid}_2-my-consent-frame_{resp.uuid}_1594823856933_{resp.pk}",
                pipe_name=f"7WHkjNhHt741R4lpMsDzTGBgCqBfkC{resp.pk}.mp4",
                study=self.study,
                response=resp,
                is_consent_footage=True,
            )
            for resp in self.responses
        ]
        page = self.client.get(
            reverse("exp:study-attachments", kwargs={"pk": self.study.pk})
        )
        self.assertIn(
            page.status_code,
            [200, 302],
            "Unexpected status code for video attachments page",
        )

    def test_can_see_response_views_as_study_admin(self):
        self.client.force_login(self.study_admin)
        for url in self.all_response_urls:
            page = self.client.get(url)
            self.assertIn(
                page.status_code, [200, 302], "Unexpected status code for " + url
            )

    def test_cannot_delete_preview_data_as_unassociated_researcher(self):
        self.client.force_login(self.other_researcher)
        url = reverse(
            "exp:study-delete-preview-responses", kwargs={"pk": self.study.pk}
        )
        response = self.client.post(url, {})
        self.assertEqual(
            response.status_code,
            403,
            "Unassociated researcher able to delete preview data!",
        )
        # Check that there's still preview data
        self.assertEqual(
            self.study.responses.filter(is_preview=True).count(), self.n_previews
        )

    def test_delete_preview_data(self):
        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-delete-preview-responses", kwargs={"pk": self.study.pk}
        )
        self.assertEqual(
            self.study.responses.filter(is_preview=True).count(), self.n_previews
        )
        self.client.post(url, {})
        self.assertEqual(self.study.responses.filter(is_preview=True).count(), 0)

    def test_unassociated_researcher_cannot_edit_modifiable_fields_in_response(self):
        self.client.force_login(self.other_researcher)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )
        for resp in self.responses:
            for field in self.editable_fields:
                self.assertEqual(
                    getattr(resp, field), self.fields_default_values[field]
                )
                data = {
                    "responseId": resp.id,
                    "field": field,
                    "value": self.fields_new_values[field],
                }
                response = self.client.post(
                    url, json.dumps(data), content_type="application/json"
                )
                self.assertEqual(response.status_code, 403)
                self.assertIn("Forbidden", response.content.decode("utf-8"))
                self.assertEqual(
                    getattr(Response.objects.get(id=resp.id), field),
                    self.fields_default_values[field],
                )

    def test_previewer_researcher_cannot_edit_modifiable_fields_in_response(self):
        self.client.force_login(self.study_previewer)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )
        for resp in self.responses:
            for field in self.editable_fields:
                self.assertEqual(
                    getattr(resp, field), self.fields_default_values[field]
                )
                data = {
                    "responseId": resp.id,
                    "field": field,
                    "value": self.fields_new_values[field],
                }
                response = self.client.post(
                    url, json.dumps(data), content_type="application/json"
                )
                self.assertEqual(response.status_code, 403)
                self.assertIn("Forbidden", response.content.decode("utf-8"))
                self.assertEqual(
                    getattr(Response.objects.get(id=resp.id), field),
                    self.fields_default_values[field],
                )

    def test_edit_modifiable_fields_in_response(self):
        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )
        for resp in self.responses:
            for field in self.editable_fields:
                # is_tallied writes go to is_tallied_researcher_override; use effective_is_tallied to read back
                actual_default = (
                    resp.effective_is_tallied
                    if field == "is_tallied"
                    else getattr(resp, field)
                )
                self.assertEqual(actual_default, self.fields_default_values[field])
                data = {
                    "responseId": resp.id,
                    "field": field,
                    "value": self.fields_new_values[field],
                }
                response = self.client.post(
                    url, json.dumps(data), content_type="application/json"
                )
                self.assertEqual(response.status_code, 200)
                success_str = f"Response {resp.id} field {field} updated to {self.fields_new_values[field]}"
                self.assertIn(success_str, response.json().get("success"))
                updated_resp = Response.objects.get(id=resp.id)
                actual_new = (
                    updated_resp.effective_is_tallied
                    if field == "is_tallied"
                    else getattr(updated_resp, field)
                )
                self.assertEqual(actual_new, self.fields_new_values[field])
                # Reset the response object to default values
                if field == "is_tallied":
                    updated_resp.is_tallied_researcher_override = None
                else:
                    setattr(updated_resp, field, self.fields_default_values[field])
                updated_resp.save()


class ResponseDataDownloadTestCase(TestCase):
    def _decode_response(self, response):
        """Read content from either a streaming or regular response."""
        if hasattr(response, "streaming_content"):
            return b"".join(response.streaming_content).decode("utf-8")
        return response.content.decode("utf-8")

    def setUp(self):
        self.client = Force2FAClient()

        n_participants = 3
        children_per_participant = 2

        self.study_reader = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 2"
        )
        self.study_previewer = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 3"
        )

        self.lab = G(Lab, name="MIT")
        self.study = G(
            Study,
            creator=self.study_reader,
            shared_preview=False,
            name="Test Study",
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )
        self.other_study = G(
            Study,
            creator=self.study_reader,
            shared_preview=False,
            name="Test Study 2",
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )

        self.study.researcher_group.user_set.add(self.study_reader)
        self.study.design_group.user_set.add(self.study_previewer)
        self.other_study.researcher_group.user_set.add(self.study_reader)
        self.other_study.design_group.user_set.add(self.study_previewer)

        self.children_for_participants = []
        self.demo_snapshots_for_participants = []
        self.responses = []
        self.preview_responses = []
        self.participant_names = ["Alice", "Bob", "Carol"]
        self.participants = [
            G(User, is_active=True, nickname=self.participant_names[i])
            for i in range(n_participants)
        ]
        for part in self.participants:
            these_children = [
                G(
                    Child,
                    user=part,
                    given_name="ChildGivenName" + str(i),
                    existing_conditions=Child.existing_conditions.multiple_birth,
                    birthday=datetime.date.today() - datetime.timedelta(60),
                )
                for i in range(children_per_participant)
            ]
            self.children_for_participants.append(these_children)
            demo_snapshot = G(DemographicData, user=part, density="urban")
            self.demo_snapshots_for_participants.append(demo_snapshot)
            # Include one incomplete response for each participant
            self.responses += [
                G(
                    Response,
                    child=child,
                    study=self.study,
                    study_type=self.study.study_type,
                    completed=False,
                    completed_consent_frame=True,
                    sequence=["0-video-config", "1-video-setup", "2-my-consent-frame"],
                    exp_data={
                        "0-video-config": {"frameType": "DEFAULT"},
                        "1-video-setup": {"frameType": "DEFAULT"},
                        "2-my-consent-frame": {"frameType": "CONSENT"},
                    },
                    demographic_snapshot=demo_snapshot,
                )
                for child in these_children
            ]
            # And one complete response
            self.responses += [
                G(
                    Response,
                    child=child,
                    study=self.study,
                    study_type=self.study.study_type,
                    completed=False,
                    completed_consent_frame=True,
                    sequence=["0-video-config", "1-video-setup", "2-my-consent-frame"],
                    exp_data={
                        "0-video-config": {"frameType": "DEFAULT"},
                        "1-video-setup": {"frameType": "DEFAULT"},
                        "2-my-consent-frame": {"frameType": "CONSENT"},
                        "3-my-exit-frame": {"frameType": "EXIT"},
                    },
                    demographic_snapshot=demo_snapshot,
                )
                for child in these_children
            ]
            # And one preview
            self.preview_responses += [
                G(
                    Response,
                    child=child,
                    study=self.study,
                    study_type=self.study.study_type,
                    completed=False,
                    is_preview=True,
                    completed_consent_frame=True,
                    sequence=["0-video-config", "1-video-setup", "2-my-consent-frame"],
                    exp_data={
                        "0-video-config": {"frameType": "DEFAULT"},
                        "1-video-setup": {"frameType": "DEFAULT"},
                        "2-my-consent-frame": {"frameType": "CONSENT"},
                    },
                    demographic_snapshot=demo_snapshot,
                )
                for child in these_children
            ]

        # Add real but not preview response from an additional participant
        self.non_preview_participant = G(
            User, is_active=True, nickname="non-preview-participant"
        )
        self.non_preview_child = G(
            Child,
            user=self.non_preview_participant,
            given_name="non-preview-child",
            birthday=datetime.date.today() - datetime.timedelta(366),
        )
        self.non_preview_demo = G(
            DemographicData,
            user=self.non_preview_participant,
            additional_comments="comments",
        )
        self.non_preview_resp = G(
            Response,
            child=self.non_preview_child,
            study=self.study,
            study_type=self.study.study_type,
            completed=False,
            completed_consent_frame=True,
            sequence=["0-video-config", "1-video-setup", "2-my-consent-frame"],
            exp_data={
                "0-video-config": {"frameType": "DEFAULT"},
                "1-video-setup": {"frameType": "DEFAULT"},
                "2-my-consent-frame": {
                    "frameType": "CONSENT",
                    "someField": "non-preview-data",
                },
            },
            demographic_snapshot=self.non_preview_demo,
        )

        # Add a response to a different study which shouldn't be included in self.study responses
        self.other_study_response = G(
            Response,
            child=self.children_for_participants[0][0],
            study=self.other_study,
            study_type=self.other_study.study_type,
            completed=True,
            completed_consent_frame=True,
            sequence=["0-video-config", "1-video-setup", "2-my-consent-frame"],
            exp_data={
                "0-video-config": {"frameType": "DEFAULT"},
                "1-video-setup": {"frameType": "DEFAULT"},
                "2-my-consent-frame": {
                    "frameType": "CONSENT",
                    "someField": "different-study",
                },
            },
            demographic_snapshot=self.demo_snapshots_for_participants[0],
        )

        # Confirm consent for all responses above
        self.consent_rulings = [
            G(
                ConsentRuling,
                response=response,
                action="accepted",
                arbiter=self.study_reader,
            )
            for response in self.responses
            + self.preview_responses
            + [self.non_preview_resp, self.other_study_response]
        ]

        # Add unconsented response from additional participant
        self.poison_string = (
            "no-one-should-see-this"  # phrase that shouldn't be in any downloads
        )
        self.unconsented_participant = G(
            User, is_active=True, nickname=self.poison_string
        )
        self.unconsented_child = G(
            Child,
            user=self.unconsented_participant,
            given_name=self.poison_string,
            birthday=datetime.date.today() - datetime.timedelta(366),
        )
        self.unconsented_demo = G(
            DemographicData,
            user=self.unconsented_participant,
            additional_comments="comments",
        )
        self.unconsented_resp = G(
            Response,
            child=self.non_preview_child,
            study=self.study,
            study_type=self.study.study_type,
            completed=False,
            completed_consent_frame=True,
            sequence=["0-video-config", "1-video-setup", "2-my-consent-frame"],
            exp_data={
                "0-video-config": {"frameType": "DEFAULT"},
                "1-video-setup": {"frameType": "DEFAULT"},
                "2-my-consent-frame": {
                    "frameType": "CONSENT",
                    "data": self.poison_string,
                },
            },
            demographic_snapshot=self.unconsented_demo,
        )

        # How many responses do we expect?
        self.n_previews = children_per_participant * n_participants
        self.n_responses = children_per_participant * n_participants * 2 + 1

        self.n_preview_children = children_per_participant * n_participants
        self.n_total_children = children_per_participant * n_participants + 1

        self.n_preview_participants = n_participants
        self.n_total_participants = n_participants + 1

        # Build a few complementary sets of options for fields to include in downloads
        self.age_optionset_1 = ["child__age_rounded"]
        self.child_optionset_1 = [
            "child__global_id",
            "child__gender",
            "child__condition_list",
            "participant__nickname",
        ]
        self.optionset_1 = self.age_optionset_1 + self.child_optionset_1
        self.child_labels_json_1 = [
            "global_id",
            "gender",
            "condition_list",
            "age_rounded",
        ]
        self.participant_labels_json_1 = ["nickname"]
        self.age_optionset_2 = ["child__age_in_days", "child__birthday"]
        self.child_optionset_2 = [
            "child__name",
            "child__age_at_birth",
            "child__language_list",
            "child__additional_information",
            "participant__global_id",
        ]
        self.optionset_2 = self.age_optionset_2 + self.child_optionset_2
        self.child_labels_json_2 = [
            "age_in_days",
            "birthday",
            "name",
            "age_at_birth",
            "language_list",
            "additional_information",
        ]
        self.participant_labels_json_2 = ["global_id"]
        self.response_summary_url = reverse(
            "exp:study-responses-download-csv", kwargs={"pk": self.study.pk}
        )
        self.response_summary_json_url = reverse(
            "exp:study-responses-download-json", kwargs={"pk": self.study.pk}
        )
        # For testing presence of researcher-editable fields/values
        self.editable_fields = StudyResponseSetResearcherFields.EDITABLE_FIELDS
        default_values = [
            "",
            "",
            False,
            False,
        ]  # These correspond to session status, payment status, star, and tallied response
        self.fields_default_values = {
            self.editable_fields[i]: default_values[i]
            for i in range(len(self.editable_fields))
        }

    def test_get_appropriate_fields_in_csv_downloads_set1(self):
        self.client.force_login(self.study_reader)
        query_string = urlencode({"data_options": self.optionset_1}, doseq=True)
        response = self.client.get(f"{self.response_summary_url}?{query_string}")
        content = self._decode_response(response)
        csv_reader = csv.reader(io.StringIO(content), quoting=csv.QUOTE_ALL)
        csv_body = list(csv_reader)
        csv_headers = csv_body.pop(0)
        # Check that we have the expected number of responses
        self.assertEqual(
            len(csv_body),
            self.n_responses + self.n_previews,
            "Unexpected number of response rows in CSV download",
        )
        # Check that the appropriate specifically-requested headers ARE present
        for header in self.optionset_1:
            self.assertIn(
                header,
                csv_headers,
                f"Downloaded summary CSV file is missing header {header}",
            )
        # Check that the remaining headers ARE NOT present
        for header in self.optionset_2:
            self.assertNotIn(
                header,
                csv_headers,
                f"Downloaded summary CSV file has header it shouldn't: {header}",
            )
        # Check that some *data* is present as expect: parent, but not child names
        for parent_name in self.participant_names:
            self.assertIn(
                parent_name,
                content,
                "Parent given name was missing from CSV when selected as download field",
            )
        self.assertNotIn(
            "ChildGivenName",
            content,
            "Child given name was included in CSV when not selected as download field",
        )
        self.assertNotIn(
            datetime.datetime.strftime(
                self.children_for_participants[0][0].birthday, "%Y-%m-%d"
            ),
            content,
            "Child birthdate was included in CSV when not selected as download field",
        )
        self.assertNotIn(
            self.poison_string,
            content,
            "Data from unconsented response included in download!",
        )
        # Check that the filename is appropriately titled - because parent name is present
        self.assertRegex(
            response.get("Content-Disposition"),
            r"^attachment; filename=\"(.*)-identifiable\.csv\"",
        )

    def test_get_appropriate_fields_in_json_downloads(self):
        self.client.force_login(self.study_reader)
        query_string = urlencode({"data_options": self.optionset_1}, doseq=True)
        response = self.client.get(f"{self.response_summary_json_url}?{query_string}")
        content = b"".join(response.streaming_content).decode("utf-8")
        data = json.loads(content)

        # Check that we have the expected number of responses
        self.assertEqual(
            len(data),
            self.n_responses + self.n_previews,
            "Unexpected number of response rows in JSON download",
        )
        # Check that the appropriate specifically-requested headers ARE present
        for header in self.child_labels_json_1:
            self.assertNotEqual(data[0]["child"][header], "")
        for header in self.participant_labels_json_1:
            self.assertNotEqual(data[0]["participant"][header], "")
        # # Check that the remaining headers ARE NOT present
        for header in self.child_labels_json_2:
            self.assertNotIn(header, data[0]["child"])
        for header in self.participant_labels_json_2:
            self.assertNotIn(header, data[0]["participant"].keys())
        # Check that some *data* is present as expect: parent, but not child names
        for row in data:
            self.assertIn(
                row["participant"]["nickname"],
                self.participant_names + [self.non_preview_participant.nickname],
            )
        self.assertNotIn(
            "ChildGivenName",
            content,
            "Child given name was included in JSON when not selected as download field",
        )
        self.assertNotIn(
            datetime.datetime.strftime(
                self.children_for_participants[0][0].birthday, "%Y-%m-%d"
            ),
            content,
            "Child birthdate was included in JSON when not selected as download field",
        )
        self.assertNotIn(
            self.poison_string,
            content,
            "Data from unconsented response included in download!",
        )
        # Check that the filename is appropriately titled - because parent name is present
        self.assertRegex(
            response.get("Content-Disposition"),
            r"^attachment; filename=\"(.*)-identifiable\.json\"",
            "JSON file not named with -identifiable suffix as expected based on fields included",
        )

    def test_get_appropriate_fields_in_csv_downloads_set2(self):
        self.client.force_login(self.study_reader)
        query_string = urlencode({"data_options": self.optionset_2}, doseq=True)
        response = self.client.get(f"{self.response_summary_url}?{query_string}")
        content = self._decode_response(response)
        csv_reader = csv.reader(io.StringIO(content), quoting=csv.QUOTE_ALL)
        csv_body = list(csv_reader)
        csv_headers = csv_body.pop(0)
        # Check that we have the expected number of responses
        self.assertEqual(
            len(csv_body),
            self.n_responses + self.n_previews,
            "Unexpected number of response rows in CSV download",
        )
        # Check that the appropriate specifically-requested headers ARE present
        for header in self.optionset_2:
            self.assertIn(
                header,
                csv_headers,
                f"Downloaded summary CSV file is missing header {header}",
            )
        # Check that the remaining headers ARE NOT present
        for header in self.optionset_1:
            self.assertNotIn(
                header,
                csv_headers,
                f"Downloaded summary CSV file has header it shouldn't: {header}",
            )
        # Check that some *data* is present as expect: parent, but not child names
        for parent_name in self.participant_names:
            self.assertNotIn(
                parent_name,
                content,
                "Parent given name was included in CSV when not selected as download field",
            )
        self.assertIn(
            "ChildGivenName",
            content,
            "Child given name was missing from CSV when selected as download field",
        )
        self.assertIn(
            datetime.datetime.strftime(
                self.children_for_participants[0][0].birthday, "%Y-%m-%d"
            ),
            content,
            "Child birthday was not included in CSV when selected as download field",
        )
        # Check that the filename is appropriately titled - because child name is present
        self.assertRegex(
            response.get("Content-Disposition"),
            r"^attachment; filename=\"(.*)-identifiable\.csv\"",
        )

    def test_get_exit_survey_fields_in_summary_csv(self):
        self.client.force_login(self.study_reader)
        # Add a few single responses where we expect specific fields
        withdrawn_response = G(
            Response,
            child=self.children_for_participants[0][0],
            study=self.study,
            study_type=self.study.study_type,
            completed=False,
            completed_consent_frame=True,
            sequence=["0-video-config", "1-video-setup", "2-my-consent-frame"],
            exp_data={
                "0-video-config": {"frameType": "DEFAULT"},
                "1-video-setup": {"frameType": "DEFAULT"},
                "2-my-consent-frame": {"frameType": "CONSENT"},
                # Include an additional exit survey frame just to make sure this doesn't break anything
                # - the last one is what should count
                "3-my-exit-survey": {
                    "frameType": "EXIT",
                    "withdrawal": False,
                    "databraryShare": "yes",
                    "useOfMedia": "",
                    "birthDate": datetime.datetime.strftime(
                        self.children_for_participants[0][0].birthday
                        + datetime.timedelta(17),
                        "%Y-%m-%dT%H:%M:%S.%fZ",
                    ),
                    "feedback": "this was fun but my older child was reciting top secret prime numbers",
                },
                "4-my-exit-survey": {
                    "frameType": "EXIT",
                    "withdrawal": True,
                    "databraryShare": "yes",
                    "useOfMedia": "private",
                    "birthDate": datetime.datetime.strftime(
                        self.children_for_participants[0][0].birthday
                        + datetime.timedelta(17),
                        "%Y-%m-%dT%H:%M:%S.%fZ",
                    ),
                    "feedback": "this was fun but my older child was reciting top secret prime numbers",
                },
            },
            demographic_snapshot=self.demo_snapshots_for_participants[0],
        )

        incomplete_response = G(
            Response,
            child=self.children_for_participants[0][0],
            study=self.study,
            study_type=self.study.study_type,
            completed=False,
            completed_consent_frame=True,
            sequence=["0-video-config", "1-video-setup", "2-my-consent-frame"],
            exp_data={
                "0-video-config": {"frameType": "DEFAULT"},
                "1-video-setup": {"frameType": "DEFAULT"},
                "2-my-consent-frame": {"frameType": "CONSENT"},
                "3-my-exit-survey": {
                    "frameType": "DEFAULT",
                    "withdrawal": True,
                    "databraryShare": "yes",
                    "useOfMedia": "private",
                    "birthDate": datetime.datetime.strftime(
                        self.children_for_participants[0][0].birthday
                        + datetime.timedelta(17),
                        "%Y-%m-%dT%H:%M:%S.%fZ",
                    ),
                    "feedback": "this was fun but my older child was reciting top secret prime numbers",
                },
            },
            demographic_snapshot=self.demo_snapshots_for_participants[0],
        )

        [
            G(
                ConsentRuling,
                response=response,
                action="accepted",
                arbiter=self.study_reader,
            )
            for response in [withdrawn_response, incomplete_response]
        ]

        csv_response = self.client.get(self.response_summary_url)
        content = self._decode_response(csv_response)
        csv_reader = csv.reader(io.StringIO(content), quoting=csv.QUOTE_ALL)
        csv_body = list(csv_reader)
        csv_headers = csv_body.pop(0)

        exit_survey_headers = [
            "response__uuid",
            "response__withdrawn",
            "response__parent_feedback",
            "response__video_privacy",
            "response__databrary",
            "response__birthdate_difference",
        ]
        exit_survey_headers_columns = {}

        for header in exit_survey_headers:
            self.assertIn(
                header,
                csv_headers,
                f"Exit survey header {header} missing from summary CSV file",
            )
            exit_survey_headers_columns[header] = csv_headers.index(header)

        # Now check that the actual values are correct in a few cases. Add two to existing
        # known responses for ones added in this test.
        self.assertEqual(self.n_responses + self.n_previews + 2, len(csv_body))

        withdrawn_response_line = [
            line
            for line in csv_body
            if line[exit_survey_headers_columns["response__uuid"]]
            == str(withdrawn_response.uuid)
        ][0]
        self.assertEqual(
            withdrawn_response_line[exit_survey_headers_columns["response__withdrawn"]],
            "True",
            "Withdrawn response was not marked as response in CSV summary!",
        )
        self.assertEqual(
            withdrawn_response_line[
                exit_survey_headers_columns["response__parent_feedback"]
            ],
            "this was fun but my older child was reciting top secret prime numbers",
            "Parent feedback was not correctly inserted in CSV summary",
        )
        self.assertEqual(
            withdrawn_response_line[
                exit_survey_headers_columns["response__video_privacy"]
            ],
            "private",
            "Video privacy level was not correctly inserted in CSV summary",
        )
        self.assertEqual(
            withdrawn_response_line[exit_survey_headers_columns["response__databrary"]],
            "yes",
            "Databrary consent was not correctly inserted in CSV summary",
        )
        self.assertEqual(
            withdrawn_response_line[
                exit_survey_headers_columns["response__birthdate_difference"]
            ],
            "17",
            "Birthdate difference was not correctly inserted in CSV summary",
        )

        incomplete_response_line = [
            line
            for line in csv_body
            if line[exit_survey_headers_columns["response__uuid"]]
            == str(incomplete_response.uuid)
        ][0]
        self.assertEqual(
            incomplete_response_line[
                exit_survey_headers_columns["response__withdrawn"]
            ],
            "False",
            "Incomplete response was not marked as non-withdrawn",
        )
        self.assertEqual(
            incomplete_response_line[
                exit_survey_headers_columns["response__parent_feedback"]
            ],
            "",
        )
        self.assertEqual(
            incomplete_response_line[
                exit_survey_headers_columns["response__video_privacy"]
            ],
            "",
        )
        self.assertEqual(
            incomplete_response_line[
                exit_survey_headers_columns["response__databrary"]
            ],
            "",
        )

    def test_get_exit_survey_fields_in_summary_json(self):
        self.client.force_login(self.study_reader)
        # Add a single response where we expect specific fields
        withdrawn_response = G(
            Response,
            child=self.children_for_participants[0][0],
            study=self.study,
            study_type=self.study.study_type,
            completed=False,
            completed_consent_frame=True,
            sequence=["0-video-config", "1-video-setup", "2-my-consent-frame"],
            exp_data={
                "0-video-config": {"frameType": "DEFAULT"},
                "1-video-setup": {"frameType": "DEFAULT"},
                "2-my-consent-frame": {"frameType": "CONSENT"},
                "3-my-exit-survey": {
                    "frameType": "EXIT",
                    "withdrawal": True,
                    "databraryShare": "yes",
                    "useOfMedia": "private",
                    "birthDate": datetime.datetime.strftime(
                        self.children_for_participants[0][0].birthday
                        + datetime.timedelta(17),
                        "%Y-%m-%dT%H:%M:%S.%fZ",
                    ),
                    "feedback": "this was fun but my older child was reciting top secret prime numbers",
                },
            },
            demographic_snapshot=self.demo_snapshots_for_participants[0],
        )

        G(
            ConsentRuling,
            response=withdrawn_response,
            action="accepted",
            arbiter=self.study_reader,
        )

        json_response = self.client.get(self.response_summary_json_url)
        content = b"".join(json_response.streaming_content).decode("utf-8")
        data = json.loads(content)

        exit_survey_headers = [
            "withdrawn",
            "parent_feedback",
            "video_privacy",
            "databrary",
            "birthdate_difference",
        ]
        this_response = [
            r for r in data if r["response"]["uuid"] == str(withdrawn_response.uuid)
        ][0]

        response_json_keys = this_response["response"].keys()

        for header in exit_survey_headers:
            self.assertIn(
                header,
                response_json_keys,
                f"Exit survey header {header} missing from summary JSON file",
            )

        # Now check that the actual values are correct in a few cases
        self.assertEqual(this_response["response"]["withdrawn"], True)
        self.assertEqual(
            this_response["response"]["parent_feedback"],
            "this was fun but my older child was reciting top secret prime numbers",
        )
        self.assertEqual(this_response["response"]["video_privacy"], "private")
        self.assertEqual(this_response["response"]["databrary"], "yes")
        self.assertEqual(this_response["response"]["birthdate_difference"], 17)
        self.assertEqual(this_response["consent"]["ruling"], "accepted")

    def test_get_researcher_editable_fields_in_csv_downloads(self):
        self.client.force_login(self.study_reader)
        query_string = urlencode({"data_options": self.optionset_1}, doseq=True)
        response = self.client.get(f"{self.response_summary_url}?{query_string}")
        content = self._decode_response(response)
        csv_reader = csv.reader(io.StringIO(content), quoting=csv.QUOTE_ALL)
        csv_body = list(csv_reader)
        csv_headers = csv_body.pop(0)
        researcher_editable_field_headers = [
            "response__" + field for field in self.editable_fields
        ]
        for field_header in researcher_editable_field_headers:
            self.assertIn(field_header, csv_headers)
        field_to_col = {h: i for i, h in enumerate(csv_headers)}
        for row in csv_body:
            for field in self.editable_fields:
                header = "response__" + field
                expected_csv = str(self.fields_default_values[field])
                self.assertEqual(row[field_to_col[header]], expected_csv)

    def test_get_researcher_editable_fields_in_json_downloads(self):
        self.client.force_login(self.study_reader)
        query_string = urlencode({"data_options": self.optionset_1}, doseq=True)
        response = self.client.get(f"{self.response_summary_json_url}?{query_string}")
        content = b"".join(response.streaming_content).decode("utf-8")
        data = json.loads(content)
        for row in data:
            for field in self.editable_fields:
                self.assertEqual(
                    row["response"][field],
                    self.fields_default_values[field],
                )

    def _set_conditions_on_first_response(self):
        """Give one response a mix of well-formed and malformed condition values."""
        # This modifies the setup data in place, but Django's TestCase wraps each test in a transaction and rolls
        # it back, so this mutation doesn't leak into other tests.
        resp = self.responses[0]
        resp.conditions = {
            "1-my-randomizer-frame": {"conditionNum": 0, "parameterSet": {"NAME": "A"}},
            "condition": "NA",
        }
        resp.save()
        return resp

    def test_malformed_conditions_in_csv_download(self):
        """A non-dict top-level conditions value shouldn't 500 the whole download."""
        resp = self._set_conditions_on_first_response()
        self.client.force_login(self.study_reader)
        query_string = urlencode({"data_options": self.optionset_1}, doseq=True)
        response = self.client.get(f"{self.response_summary_url}?{query_string}")
        self.assertEqual(response.status_code, 200)
        content = self._decode_response(response)
        csv_reader = csv.reader(io.StringIO(content), quoting=csv.QUOTE_ALL)
        csv_body = list(csv_reader)
        csv_headers = csv_body.pop(0)
        # Check that all responses are still present
        self.assertEqual(len(csv_body), self.n_responses + self.n_previews)
        field_to_col = {h: i for i, h in enumerate(csv_headers)}
        # Locate the poisoned response row (order is not guaranteed)
        row = next(
            row
            for row in csv_body
            if row[field_to_col["response__uuid"]] == str(resp.uuid)
        )
        # Collect the response__conditions.N.(...) fields for this response back into
        # one dict per condition entry. Ordering of the entries isn't guaranteed (JSON
        # field keys come back from the DB in arbitrary order), so compare unordered.
        condition_entries = {}
        for header, col in field_to_col.items():
            match = re.match(r"^response__conditions\.(\d+)\.(.+)$", header)
            if match and row[col] != "":
                index, field = match.groups()
                condition_entries.setdefault(index, {})[field] = row[col]
        self.assertCountEqual(
            condition_entries.values(),
            [
                {
                    "frameName": "1-my-randomizer-frame",
                    "conditionNum": "0",
                    "parameterSet.NAME": "A",
                },
                # The malformed value is kept under a "value" field
                {"frameName": "condition", "value": "NA"},
            ],
        )

    def test_malformed_conditions_in_json_download(self):
        """A non-dict top-level conditions value shouldn't 500 the whole download."""
        resp = self._set_conditions_on_first_response()
        self.client.force_login(self.study_reader)
        query_string = urlencode({"data_options": self.optionset_1}, doseq=True)
        response = self.client.get(f"{self.response_summary_json_url}?{query_string}")
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content).decode("utf-8")
        data = json.loads(content)
        # Check that all responses are still present
        self.assertEqual(len(data), self.n_responses + self.n_previews)
        # Locate the poisoned response row (order is not guaranteed)
        this_response = next(
            row for row in data if row["response"]["uuid"] == str(resp.uuid)
        )
        # Entry order isn't guaranteed (JSON field keys come back from the DB in
        # arbitrary order), so compare unordered.
        self.assertCountEqual(
            this_response["response"]["conditions"],
            [
                {
                    "frameName": "1-my-randomizer-frame",
                    "conditionNum": 0,
                    "parameterSet": {"NAME": "A"},
                },
                {"frameName": "condition", "value": "NA"},
            ],
        )

    def test_get_appropriate_children_in_child_csv_as_previewer(self):
        self.client.force_login(self.study_previewer)
        csv_response = self.client.get(
            reverse(
                "exp:study-responses-children-summary-csv", kwargs={"pk": self.study.pk}
            )
        )
        content = self._decode_response(csv_response)
        csv_reader = csv.reader(io.StringIO(content), quoting=csv.QUOTE_ALL)
        csv_body = list(csv_reader)
        csv_body.pop(0)
        self.assertEqual(len(csv_body), self.n_preview_children)
        self.assertNotIn(
            self.poison_string,
            content,
            "Data from unconsented response included in child file download!",
        )
        self.assertNotIn(
            "non-preview-child",
            content,
            "Data from child who provided only non-preview response available to previewer!",
        )

    def test_get_appropriate_children_in_child_csv_as_researcher(self):
        self.client.force_login(self.study_reader)
        csv_response = self.client.get(
            reverse(
                "exp:study-responses-children-summary-csv", kwargs={"pk": self.study.pk}
            )
        )
        content = self._decode_response(csv_response)
        csv_reader = csv.reader(io.StringIO(content), quoting=csv.QUOTE_ALL)
        csv_body = list(csv_reader)
        csv_body.pop(0)
        self.assertEqual(len(csv_body), self.n_total_children)
        self.assertNotIn(
            self.poison_string,
            content,
            "Data from unconsented response included in child file download!",
        )

    def test_get_study_demographics_view_as_researcher(self):
        # Check indicated number of responses is correct for all-response permissions
        self.client.force_login(self.study_reader)
        response = self.client.get(
            reverse("exp:study-demographics", kwargs={"pk": self.study.pk})
        )
        content = self._decode_response(response)
        self.assertIn(
            f"{self.n_previews + self.n_responses} snapshot",
            content,
            "Incorrect number of responses indicated on study demographics view for researcher",
        )

    def test_get_study_demographics_view_as_previewer(self):
        # Check indicated number of responses is correct for preview-data-only permissions
        self.client.force_login(self.study_previewer)
        response = self.client.get(
            reverse("exp:study-demographics", kwargs={"pk": self.study.pk})
        )
        content = self._decode_response(response)
        self.assertIn(
            f"{self.n_previews} snapshot",
            content,
            "Incorrect number of responses indicated on study demographics view for previewer",
        )
        self.assertIn(
            "(Based on your permissions, only snapshots from preview responses are included.)",
            content,
            "Missing expected signaling to user that only preview data is shown on demographics view",
        )

    def test_get_appropriate_participants_in_demographic_csv_as_researcher(self):
        self.client.force_login(self.study_reader)
        csv_response = self.client.get(
            reverse("exp:study-demographics-download-csv", kwargs={"pk": self.study.pk})
        )
        content = self._decode_response(csv_response)
        csv_reader = csv.reader(io.StringIO(content), quoting=csv.QUOTE_ALL)
        csv_body = list(csv_reader)
        csv_headers = csv_body.pop(0)

        participant_id_col = csv_headers.index("participant__hashed_id")
        participant_ids = [line[participant_id_col] for line in csv_body]
        unique_participant_ids = list(set(participant_ids))
        self.assertEqual(len(csv_body), self.n_previews + self.n_responses)
        self.assertEqual(len(unique_participant_ids), self.n_total_participants)

        self.assertNotIn(
            self.poison_string,
            content,
            "Data from unconsented response included in demographic file download!",
        )
        self.assertIn(
            "comments",
            content,
            "Data from participant who provided consented non-preview response not available to researcher",
        )

    def test_get_appropriate_participants_in_demographic_csv_as_previewer(self):
        self.client.force_login(self.study_previewer)
        csv_response = self.client.get(
            reverse("exp:study-demographics-download-csv", kwargs={"pk": self.study.pk})
        )
        content = self._decode_response(csv_response)
        csv_reader = csv.reader(io.StringIO(content), quoting=csv.QUOTE_ALL)
        csv_body = list(csv_reader)
        csv_headers = csv_body.pop(0)

        participant_id_col = csv_headers.index("participant__hashed_id")
        participant_ids = [line[participant_id_col] for line in csv_body]
        unique_participant_ids = list(set(participant_ids))
        self.assertEqual(len(csv_body), self.n_previews)
        self.assertEqual(len(unique_participant_ids), self.n_preview_participants)

        self.assertNotIn(
            self.poison_string,
            content,
            "Data from unconsented response included in demographic file download!",
        )
        self.assertNotIn(
            "non-preview-participant",
            content,
            "Data from participant who provided only non-preview response available to previewer!",
        )

    def test_get_appropriate_fields_in_demographic_csv(self):
        self.client.force_login(self.study_reader)
        demographic_csv_url = reverse(
            "exp:study-demographics-download-csv", kwargs={"pk": self.study.pk}
        )

        # With participant__global_id selected, should be in header and participant uuid included in file
        query_string = urlencode(
            {"demo_options": ["participant__global_id"]}, doseq=True
        )
        csv_response = self.client.get(f"{demographic_csv_url}?{query_string}")
        content = self._decode_response(csv_response)
        csv_reader = csv.reader(io.StringIO(content), quoting=csv.QUOTE_ALL)
        csv_body = list(csv_reader)
        csv_headers = csv_body.pop(0)
        self.assertIn("participant__global_id", csv_headers)
        self.assertIn(str(self.participants[0].uuid), content)

        # Without participant__global_id selected, should not be in header and data should not be included
        query_string = urlencode({"demo_options": []}, doseq=True)
        csv_response = self.client.get(f"{demographic_csv_url}?{query_string}")
        content = self._decode_response(csv_response)
        csv_reader = csv.reader(io.StringIO(content), quoting=csv.QUOTE_ALL)
        csv_body = list(csv_reader)
        csv_headers = csv_body.pop(0)
        self.assertNotIn("participant__global_id", csv_headers)
        self.assertNotIn(str(self.participants[0].uuid), content)

    def test_get_appropriate_fields_in_demographic_json(self):
        self.client.force_login(self.study_reader)
        demographic_json_url = reverse(
            "exp:study-demographics-download-json", kwargs={"pk": self.study.pk}
        )

        # With participant__global_id selected, this info is included
        query_string = urlencode(
            {"demo_options": ["participant__global_id"]}, doseq=True
        )
        response = self.client.get(f"{demographic_json_url}?{query_string}")
        content = self._decode_response(response)
        data = json.loads(content)
        for demo in data:
            self.assertIn("global_id", demo["participant"])
            self.assertEqual(
                demo["participant"]["global_id"],
                str(
                    Response.objects.get(uuid=demo["response"]["uuid"]).child.user.uuid
                ),
            )

        # Without participant__global_id selected, this info is absent
        query_string = urlencode({"demo_options": []}, doseq=True)
        response = self.client.get(f"{demographic_json_url}?{query_string}")
        content = self._decode_response(response)
        data = json.loads(content)
        for demo in data:
            self.assertNotIn("global_id", demo["participant"])
            self.assertNotIn(
                str(
                    Response.objects.get(uuid=demo["response"]["uuid"]).child.user.uuid
                ),
                content,
            )

    def test_get_appropriate_individual_responses_as_researcher(self):
        self.client.force_login(self.study_reader)
        n_matches = 0

        response = self.client.get(
            f"{reverse('exp:study-responses-list', kwargs={'pk': self.study.pk})}"
        )
        content = self._decode_response(response)
        matches = re.finditer('data-response-uuid="(.*)"', content)
        for m in matches:
            n_matches += 1
            this_response_uuid = m.group(1)
            response = Response.objects.get(uuid=this_response_uuid)
            self.assertEqual(response.study.pk, self.study.pk)
            self.assertTrue(response.has_valid_consent)

            # Also check values are displayed in table
            hashed_child_id = hash_id(
                response.child.uuid,
                self.study.uuid,
                self.study.salt,
                self.study.hash_digits,
            )
            self.assertIn(f"<td>{hashed_child_id}</td>", content)
            self.assertIn(f"<td>{str(this_response_uuid)[:8]}", content)
            response_date = response.date_created
            # Generate start of date representation matching Django template tag usage
            formatted_date = response_date.strftime("%-m/%-d/%Y %-I:%M %p")
            self.assertIn(f"{formatted_date}", content)
        self.assertNotIn(self.poison_string, content)

        self.assertEqual(n_matches, self.n_responses + self.n_previews)

    def test_get_appropriate_individual_responses_as_previewer(self):
        self.client.force_login(self.study_previewer)
        response = self.client.get(
            reverse("exp:study-responses-list", kwargs={"pk": self.study.pk})
        )
        content = self._decode_response(response)

        matches = re.finditer('data-response-uuid="(.*)"', content)
        n_matches = 0
        for m in matches:
            n_matches += 1
            this_response_uuid = m.group(1)
            response = Response.objects.get(uuid=this_response_uuid)
            self.assertEqual(response.study.pk, self.study.pk)
            self.assertTrue(response.has_valid_consent)
            self.assertTrue(response.is_preview)

        # Assumes n_previews fit on one page
        self.assertEqual(n_matches, self.n_previews)

    def _get_psychds_zip(self, query_string=""):
        url = reverse(
            "exp:study-responses-download-frame-data-zip-psychds",
            kwargs={"pk": self.study.pk},
        )
        response = self.client.get(f"{url}?{query_string}" if query_string else url)
        zip_bytes = b"".join(response.streaming_content)
        return response, zip_bytes

    def test_psychds_download_returns_zip(self):
        self.client.force_login(self.study_reader)
        response, zip_bytes = self._get_psychds_zip()
        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.get("Content-Disposition"),
            r'^attachment; filename=".*--psychds\.zip"',
        )
        # Verify content is a valid zip file
        zipfile.ZipFile(io.BytesIO(zip_bytes))

    def test_psychds_download_zip_structure(self):
        self.client.force_login(self.study_reader)
        _, zip_bytes = self._get_psychds_zip()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
        self.assertIn("dataset_description.json", names)
        self.assertIn("README.md", names)
        self.assertIn(".psychds-ignore", names)
        self.assertTrue(
            any(n.startswith("data/framedata-per-response/") for n in names)
        )
        self.assertTrue(any(n.startswith("data/overview/") for n in names))
        self.assertTrue(
            any(n.startswith("data/raw/") and n.endswith(".json") for n in names)
        )

    def test_psychds_download_dataset_description_has_variables_measured(self):
        self.client.force_login(self.study_reader)
        _, zip_bytes = self._get_psychds_zip()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            metadata = json.loads(zf.read("dataset_description.json"))
        self.assertIn("variableMeasured", metadata)
        self.assertIsInstance(metadata["variableMeasured"], list)
        self.assertGreater(len(metadata["variableMeasured"]), 0)

    def test_psychds_download_frame_data_file_per_response(self):
        self.client.force_login(self.study_reader)
        _, zip_bytes = self._get_psychds_zip()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            framedata_csv_files = [
                n
                for n in zf.namelist()
                if n.startswith("data/framedata-per-response/") and n.endswith(".csv")
            ]
        self.assertEqual(
            len(framedata_csv_files),
            self.n_responses + self.n_previews,
            "Expected one frame data CSV file per consented response",
        )

    def test_psychds_download_all_responses_json_count(self):
        self.client.force_login(self.study_reader)
        _, zip_bytes = self._get_psychds_zip()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            all_responses_json = [
                n
                for n in zf.namelist()
                if n.startswith("data/raw/") and n.endswith(".json")
            ]
            self.assertEqual(len(all_responses_json), 1)
            all_responses = json.loads(zf.read(all_responses_json[0]))
        self.assertEqual(
            len(all_responses),
            self.n_responses + self.n_previews,
            "Unexpected number of responses in all_responses JSON",
        )

    def test_psychds_download_excludes_unconsented_responses(self):
        self.client.force_login(self.study_reader)
        _, zip_bytes = self._get_psychds_zip()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                content = zf.read(name).decode("utf-8", errors="replace")
                self.assertNotIn(
                    self.poison_string,
                    content,
                    f"Data from unconsented response found in {name}",
                )


class ResponseViewResearcherUpdateFieldsTestCase(TestCase):
    def setUp(self):
        self.client = Force2FAClient()

        self.study_admin = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 1"
        )
        self.other_researcher = G(
            User, is_active=True, is_researcher=True, given_name="Other researcher"
        )
        self.lab = G(Lab, name="MIT")
        self.study = G(
            Study,
            creator=self.study_admin,
            shared_preview=False,
            name="Test Study 1",
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )
        self.study.admin_group.user_set.add(self.study_admin)

        self.other_study = G(
            Study,
            creator=self.other_researcher,
            shared_preview=False,
            name="Other study",
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )

        self.participant = G(User, is_active=True, given_name="Parent")
        self.child = G(
            Child,
            user=self.participant,
            given_name="Child 1",
            existing_conditions=Child.existing_conditions.multiple_birth,
            birthday=datetime.date.today() - datetime.timedelta(60),
        )
        self.demo_snapshot = G(DemographicData, user=self.participant, density="urban")
        self.response = G(
            Response,
            child=self.child,
            study=self.study,
            study_type=self.study.study_type,
            completed=True,
            completed_consent_frame=True,
            sequence=["0-video-config", "1-video-setup", "2-my-consent-frame"],
            exp_data={
                "0-video-config": {"frameType": "DEFAULT"},
                "1-video-setup": {"frameType": "DEFAULT"},
                "2-my-consent-frame": {"frameType": "CONSENT"},
                "3-my-exit-frame": {"frameType": "EXIT"},
            },
            demographic_snapshot=self.demo_snapshot,
        )
        self.consent_ruling = G(
            ConsentRuling,
            response=self.response,
            action="accepted",
            arbiter=self.study_admin,
        )
        self.other_response = G(
            Response,
            child=self.child,
            study=self.other_study,
            study_type=self.other_study.study_type,
            completed=True,
            completed_consent_frame=True,
            sequence=["0-video-config", "1-video-setup", "2-my-consent-frame"],
            exp_data={
                "0-video-config": {"frameType": "DEFAULT"},
                "1-video-setup": {"frameType": "DEFAULT"},
                "2-my-consent-frame": {"frameType": "CONSENT"},
                "3-my-exit-frame": {"frameType": "EXIT"},
            },
            demographic_snapshot=self.demo_snapshot,
        )
        self.other_consent_ruling = G(
            ConsentRuling,
            response=self.other_response,
            action="accepted",
            arbiter=self.other_researcher,
        )
        # For testing researcher-editable response fields: researcher_session_status, researcher_payment_status, researcher_star, is_tallied
        self.editable_fields = StudyResponseSetResearcherFields.EDITABLE_FIELDS
        default_values = [
            "",
            "",
            False,
            False,
        ]  # These correspond to session status, payment status, star, and tallied response
        new_values = ["follow_up", "to_pay", True, True]
        invalid_values = ["some_other_string", 42, "true", "not_a_bool"]
        self.fields_default_values = {
            self.editable_fields[i]: default_values[i]
            for i in range(len(self.editable_fields))
        }
        self.fields_new_values = {
            self.editable_fields[i]: new_values[i]
            for i in range(len(self.editable_fields))
        }
        self.fields_invalid_values = {
            self.editable_fields[i]: invalid_values[i]
            for i in range(len(self.editable_fields))
        }

    def test_update_fails_with_missing_data(self):
        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )
        invalid_data_list = [
            {},
            {"responseId": self.response.id},
            {"field": self.editable_fields[0]},
            {"value": self.fields_new_values[self.editable_fields[0]]},
            {
                "responseId": self.response.id,
                "field": self.editable_fields[0],
            },
            {
                "responseId": self.response.id,
                "value": self.fields_new_values[self.editable_fields[0]],
            },
            {
                "field": self.editable_fields[0],
                "value": self.fields_new_values[self.editable_fields[0]],
            },
        ]
        for data in invalid_data_list:
            post_response = self.client.post(
                url, json.dumps(data), content_type="application/json"
            )
            self.assertEqual(post_response.status_code, 400)
            error_str = (
                "Invalid request: One or more of the required arguments is missing."
            )
            self.assertIn(error_str, post_response.json().get("error"))

    def test_update_fails_with_invalid_values(self):
        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )
        # These correspond to the fields: session status, payment status, star, tallied response
        err_strings = [
            "Invalid request: Session Status must be one of ",
            "Invalid request: Payment Status must be one of ",
            "Invalid request: Star field must be a boolean value.",
            "Invalid request: Tallied Response must be a boolean value.",
        ]
        fields_err_strings = {
            self.editable_fields[i]: err_strings[i]
            for i in range(len(self.editable_fields))
        }
        for field in self.editable_fields:
            actual = (
                self.response.effective_is_tallied
                if field == "is_tallied"
                else getattr(self.response, field)
            )
            self.assertEqual(actual, self.fields_default_values[field])
            data_invalid = {
                "responseId": self.response.id,
                "field": field,
                "value": self.fields_invalid_values[field],
            }
            post_response = self.client.post(
                url, json.dumps(data_invalid), content_type="application/json"
            )
            self.assertEqual(post_response.status_code, 400)
            self.assertIn(fields_err_strings[field], post_response.json().get("error"))

    def test_update_fails_with_invalid_fields(self):
        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )
        # Test that researchers can't modify any other Response fields (with somewhat-reasonable values)
        fields = Response._meta.get_fields()
        other_fields = [
            field.name
            for field in fields
            if field.name not in self.editable_fields and field.concrete
        ]
        other_fields_types = {
            field.name: field.get_internal_type()
            for field in fields
            if field.name not in self.editable_fields and field.concrete
        }
        valid_values = {
            "DateTimeField": str(datetime.datetime(2025, 3, 15, 12, 0, 0)),
            "JSONField": "{'foo': 'bar'}",
            "BooleanField": True,
            "CharField": "bad data!",
            "ArrayField": ["uh-oh"],
            "AutoField": 999999,
            "UUIDField": str(self.response.uuid),
            "ForeignKey": 1,
        }
        for field in other_fields:
            data_invalid_field = {
                "responseId": self.response.id,
                "field": field,
                "value": valid_values[other_fields_types[field]],
            }
            post_response = self.client.post(
                url, json.dumps(data_invalid_field), content_type="application/json"
            )
            self.assertEqual(post_response.status_code, 400)
            self.assertIn(
                f"""Invalid request: Invalid field {field}""",
                post_response.json().get("error"),
            )

    def test_update_fails_when_response_does_not_exist(self):
        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )
        non_existent_id = 999999
        data_response_invalid = {
            "responseId": non_existent_id,
            "field": self.editable_fields[0],
            "value": self.fields_new_values[self.editable_fields[0]],
        }
        post_response = self.client.post(
            url, json.dumps(data_response_invalid), content_type="application/json"
        )
        self.assertEqual(post_response.status_code, 400)
        error_str = (
            f"""Invalid request: Response object {non_existent_id} does not exist"""
        )
        self.assertIn(error_str, post_response.json().get("error"))

    def test_update_fails_when_response_not_from_this_study(self):
        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )
        data_resp_id_not_from_study = {
            "responseId": self.other_response.id,
            "field": self.editable_fields[0],
            "value": self.fields_new_values[self.editable_fields[0]],
        }
        post_response = self.client.post(
            url,
            json.dumps(data_resp_id_not_from_study),
            content_type="application/json",
        )
        self.assertEqual(post_response.status_code, 400)
        error_str = f"""Invalid request: Response object {self.other_response.id} is not from this study."""
        self.assertIn(error_str, post_response.json().get("error"))

    def test_update_with_blank_value_is_successful(self):
        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )
        data_with_blank = {
            "responseId": self.response.id,
            "field": self.editable_fields[0],
            "value": "",
        }
        post_response = self.client.post(
            url, json.dumps(data_with_blank), content_type="application/json"
        )
        success_str = f"Response {self.response.id} field {self.editable_fields[0]} updated to {''}"
        self.assertIn(success_str, post_response.json().get("success"))

    def test_update_with_false_value_is_successful(self):
        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )
        data_with_blank = {
            "responseId": self.response.id,
            "field": self.editable_fields[2],
            "value": False,
        }
        post_response = self.client.post(
            url, json.dumps(data_with_blank), content_type="application/json"
        )
        success_str = f"Response {self.response.id} field {self.editable_fields[2]} updated to {False}"
        self.assertIn(success_str, post_response.json().get("success"))

    def test_is_tallied_via_view_writes_to_override_not_system_field(self):
        """Posting is_tallied=True writes is_tallied_researcher_override, leaving is_tallied unchanged."""
        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )
        # Force system is_tallied to False in DB to contrast with the override
        Response.objects.filter(pk=self.response.pk).update(is_tallied=False)
        self.response.refresh_from_db()
        self.assertFalse(self.response.is_tallied)

        data = {"responseId": self.response.id, "field": "is_tallied", "value": True}
        resp = self.client.post(url, json.dumps(data), content_type="application/json")
        self.assertEqual(resp.status_code, 200)

        updated = Response.objects.get(pk=self.response.pk)
        self.assertFalse(updated.is_tallied)  # system field unchanged
        self.assertTrue(updated.is_tallied_researcher_override)  # override set
        self.assertTrue(updated.effective_is_tallied)

    def test_is_tallied_researcher_override_can_be_changed_multiple_times(self):
        """Researcher can toggle is_tallied (override) repeatedly via the view."""
        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )

        for value in [True, False, True, False]:
            data = {
                "responseId": self.response.id,
                "field": "is_tallied",
                "value": value,
            }
            resp = self.client.post(
                url, json.dumps(data), content_type="application/json"
            )
            self.assertEqual(resp.status_code, 200)
            updated = Response.objects.get(pk=self.response.pk)
            self.assertEqual(updated.is_tallied_researcher_override, value)
            self.assertEqual(updated.effective_is_tallied, value)

    def test_is_tallied_researcher_override_field_cannot_be_set_directly_via_view(self):
        """is_tallied_researcher_override is not in EDITABLE_FIELDS, so direct edits are rejected."""
        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )
        data = {
            "responseId": self.response.id,
            "field": "is_tallied_researcher_override",
            "value": True,
        }
        resp = self.client.post(url, json.dumps(data), content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn(
            "Invalid request: Invalid field is_tallied_researcher_override",
            resp.json()["error"],
        )

    @patch("studies.models.send_mail")
    def test_set_tallied_true_pauses_active_study_and_returns_reached_max_message(
        self, mock_send_mail
    ):
        """POSTing is_tallied=True pauses an active study when max_responses is reached and returns the message."""
        self.study.max_responses = 1
        self.study.state = "active"
        self.study.save()

        # Make the response not effectively tallied so the count starts at 0
        Response.objects.filter(pk=self.response.pk).update(
            is_tallied=False, is_tallied_researcher_override=None
        )
        self.response.refresh_from_db()
        self.assertFalse(self.response.effective_is_tallied)
        self.assertFalse(self.study.has_reached_max_responses)

        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )
        data = {"responseId": self.response.id, "field": "is_tallied", "value": True}
        resp = self.client.post(url, json.dumps(data), content_type="application/json")

        self.assertEqual(resp.status_code, 200)
        self.study.refresh_from_db()
        self.assertEqual(self.study.state, "paused")
        self.assertIn("reached the response limit", resp.json().get("message", ""))
        self.assertIn("1/1", resp.json()["message"])
        self.assertIn("counts", resp.json())
        counts = resp.json()["counts"]
        self.assertEqual(counts["tallied"], 1)
        self.assertEqual(counts["total"], 1)

    def test_set_tallied_false_when_was_at_max_returns_dropped_below_message(self):
        """POSTing is_tallied=False when the study was at max_responses returns a 'dropped below' message."""
        self.study.max_responses = 1
        self.study.state = "paused"
        self.study.save()

        # Ensure the response is effectively tallied so tallied_count=1 = max
        Response.objects.filter(pk=self.response.pk).update(
            is_tallied=True, is_tallied_researcher_override=None
        )
        self.response.refresh_from_db()
        self.assertTrue(self.response.effective_is_tallied)
        self.assertTrue(self.study.has_reached_max_responses)

        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )
        data = {"responseId": self.response.id, "field": "is_tallied", "value": False}
        resp = self.client.post(url, json.dumps(data), content_type="application/json")

        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            "dropped back below the response limit", resp.json().get("message", "")
        )
        self.assertIn("0/1", resp.json()["message"])
        self.assertIn("counts", resp.json())
        counts = resp.json()["counts"]
        self.assertEqual(counts["tallied"], 0)
        self.assertEqual(counts["total"], 1)
        self.study.refresh_from_db()
        self.assertEqual(self.study.state, "paused")  # Still paused, no auto-unpause

    def test_set_tallied_false_does_not_unpause_study_below_max(self):
        """Setting is_tallied=False keeps the study paused even after dropping below max_responses."""
        self.study.max_responses = 1
        self.study.state = "paused"
        self.study.save()
        Response.objects.filter(pk=self.response.pk).update(
            is_tallied=True, is_tallied_researcher_override=None
        )

        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )
        data = {"responseId": self.response.id, "field": "is_tallied", "value": False}
        self.client.post(url, json.dumps(data), content_type="application/json")

        self.study.refresh_from_db()
        self.assertFalse(self.study.has_reached_max_responses)
        self.assertEqual(self.study.state, "paused")

    def test_set_tallied_no_message_when_not_crossing_max_threshold(self):
        """No message is returned when the tallied status change does not cross the max_responses threshold."""
        self.study.max_responses = 5
        self.study.save()
        Response.objects.filter(pk=self.response.pk).update(
            is_tallied=True, is_tallied_researcher_override=None
        )

        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": self.study.pk}
        )
        # Set to False: count goes from 1 to 0, still below max=5
        data = {"responseId": self.response.id, "field": "is_tallied", "value": False}
        resp = self.client.post(url, json.dumps(data), content_type="application/json")

        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("message", resp.json())
        self.assertIn("counts", resp.json())

    def test_set_tallied_on_external_study_returns_external_counts(self):
        """For external studies, counts returned after setting is_tallied use external keys (no tallied_approved/tallied_pending)."""
        external_study = G(
            Study,
            creator=self.study_admin,
            shared_preview=False,
            name="External Test Study",
            lab=self.lab,
            study_type=StudyType.get_external(),
        )
        external_study.admin_group.user_set.add(self.study_admin)
        external_response = G(
            Response,
            child=self.child,
            study=external_study,
            study_type=external_study.study_type,
            completed=True,
        )
        # External responses may be auto-tallied via signal; force to untallied to test the transition
        Response.objects.filter(pk=external_response.pk).update(
            is_tallied=False, is_tallied_researcher_override=None
        )
        external_response.refresh_from_db()
        self.assertFalse(external_response.effective_is_tallied)

        self.client.force_login(self.study_admin)
        url = reverse(
            "exp:study-responses-researcher-update", kwargs={"pk": external_study.pk}
        )
        data = {
            "responseId": external_response.id,
            "field": "is_tallied",
            "value": True,
        }
        resp = self.client.post(url, json.dumps(data), content_type="application/json")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("counts", resp.json())
        counts = resp.json()["counts"]
        self.assertEqual(counts["tallied"], 1)
        self.assertEqual(counts["untallied"], 0)
        self.assertEqual(counts["preview"], 0)
        self.assertEqual(counts["total"], 1)
        self.assertNotIn("tallied_approved", counts)
        self.assertNotIn("tallied_pending", counts)


class GetFrameDataTestCase(TestCase):
    """Unit tests for the get_frame_data helper function."""

    BASE_RESP = {
        "child__uuid": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "study__uuid": uuid.UUID("00000000-0000-0000-0000-000000000002"),
        "study__salt": uuid.UUID("00000000-0000-0000-0000-000000000003"),
        "study__hash_digits": 6,
        "uuid": uuid.UUID("00000000-0000-0000-0000-000000000004"),
        "global_event_timings": [],
    }

    def _make_resp(self, exp_data):
        return {**self.BASE_RESP, "exp_data": exp_data}

    def test_non_dict_frame_value_produces_row(self):
        """A top-level exp_data value that is a string or int should produce a
        FrameDataRow with that frame_id, a blank key, and the raw value — rather
        than raising an error."""
        resp = self._make_resp(
            {
                "0-intro": {"frameType": "DEFAULT", "someKey": "someValue"},
                "top-level-string": "unexpected string",
                "top-level-int": 42,
            }
        )
        rows = get_frame_data(resp)

        frame_ids = [row.frame_id for row in rows]
        self.assertIn("top-level-string", frame_ids)
        self.assertIn("top-level-int", frame_ids)

        string_row = next(r for r in rows if r.frame_id == "top-level-string")
        self.assertEqual(string_row.key, "")
        self.assertEqual(string_row.value, "unexpected string")

        int_row = next(r for r in rows if r.frame_id == "top-level-int")
        self.assertEqual(int_row.key, "")
        self.assertEqual(int_row.value, 42)

    def test_jspsych_non_dict_list_element_produces_row(self):
        """For jsPsych responses, normalized_exp_data zips sequence with exp_data into a
        dict. A non-dict element in the list becomes a non-dict value in that dict. It
        should produce a row with a blank key and the raw value rather than raising."""
        # Simulate what normalized_exp_data returns for a jsPsych response where one
        # trial's data is a bare string.
        resp = self._make_resp(
            {
                "0-survey-likert": {
                    "trial_type": "survey-likert",
                    "response": {"q0": 3},
                },
                "1-bad-trial": "unexpected string",
            }
        )
        rows = get_frame_data(resp)

        frame_ids = [row.frame_id for row in rows]
        self.assertIn("1-bad-trial", frame_ids)

        bad_row = next(r for r in rows if r.frame_id == "1-bad-trial")
        self.assertEqual(bad_row.key, "")
        self.assertEqual(bad_row.value, "unexpected string")

    def test_normal_dict_frame_values_still_included(self):
        """Normal dict-valued frames should still produce rows as expected."""
        resp = self._make_resp(
            {"0-intro": {"frameType": "DEFAULT", "someKey": "someValue"}}
        )
        rows = get_frame_data(resp)

        frame_ids = [row.frame_id for row in rows]
        self.assertIn("0-intro", frame_ids)

        key_row = next(
            r for r in rows if r.frame_id == "0-intro" and r.key == "someKey"
        )
        self.assertEqual(key_row.value, "someValue")


class ResponseConditionsColumnTestCase(TestCase):
    """Unit tests for the response__conditions column extractor."""

    def setUp(self):
        self.extract = next(
            col.extractor
            for col in RESPONSE_COLUMNS
            if col.id == "response__conditions"
        )

    def _extract(self, conditions):
        # Unsaved instance; the extractor only reads the conditions field.
        return self.extract(Response(conditions=conditions))

    def test_dict_conditions_are_merged_with_frame_name(self):
        self.assertEqual(
            self._extract(
                {
                    "1-my-randomizer-frame": {
                        "conditionNum": 0,
                        "parameterSet": {"NAME": "A"},
                    }
                }
            ),
            [
                {
                    "frameName": "1-my-randomizer-frame",
                    "conditionNum": 0,
                    "parameterSet": {"NAME": "A"},
                }
            ],
        )

    def test_non_dict_conditions_fall_back_to_value_field(self):
        """Malformed top-level values (string, number, list, None) should be stored
        under a "value" field rather than raising."""
        for conditions_value in ["NA", 42, ["a", "b"], None, True]:
            with self.subTest(conditions_value=conditions_value):
                self.assertEqual(
                    self._extract({"condition": conditions_value}),
                    [{"frameName": "condition", "value": conditions_value}],
                )

    def test_mix_of_dict_and_non_dict_conditions(self):
        self.assertEqual(
            self._extract(
                {
                    "1-my-randomizer-frame": {"conditionNum": 1},
                    "condition": "NA",
                }
            ),
            [
                {"frameName": "1-my-randomizer-frame", "conditionNum": 1},
                {"frameName": "condition", "value": "NA"},
            ],
        )

    def test_empty_conditions(self):
        self.assertEqual(self._extract({}), [])

    def test_dict_conditions_with_frame_name_key_are_not_overwritten(self):
        """An explicit frameName within the condition data wins, as before the fix."""
        self.assertEqual(
            self._extract({"1-my-randomizer-frame": {"frameName": "something-else"}}),
            [{"frameName": "something-else"}],
        )


# TODO: test individual file downloads from response-list
#       * cannot get response from another study,
#       * cannot get real data if only preview perms
#       * cannot get unconsented data
#       check correct fields included, as for all-response downloads
# TODO: test can submit feedback only w correct perms and only for responses to this study
#       (path: "study-response-submit-feedback" (pk))
# TODO: test appropriate list of videos shows up in videos views (video from this study, no
#       video from another study, no non-preview video wo perms).
# TODO: Check can download/view video pk from appropriate set only.
#       (path: "study-response-video-download" (pk, video))


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
@override_settings(CELERY_TASK_EAGER_PROPAGATES=False)
class StudyResponsesConsentManagerMaxResponsesTestCase(TestCase):
    """Tests for max_responses behavior triggered via the consent manager view."""

    def setUp(self):
        self.client = Force2FAClient()
        self.researcher = G(User, is_active=True, is_researcher=True)
        participant = G(User, is_active=True)
        self.child = G(
            Child,
            user=participant,
            birthday=datetime.date.today() - datetime.timedelta(60),
        )
        self.lab = G(Lab, name="Test Lab")
        self.study = G(
            Study,
            creator=self.researcher,
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
            min_age_years=0,
            min_age_months=0,
            min_age_days=0,
            max_age_years=18,
            max_age_months=0,
            max_age_days=0,
            criteria_expression="",
            max_responses=2,
        )
        self.study.admin_group.user_set.add(self.researcher)

        for _ in range(2):
            G(
                Response,
                child=self.child,
                study=self.study,
                study_type=self.study.study_type,
                is_preview=False,
                completed=True,
                completed_consent_frame=True,
            )
        # Force both responses as tallied to ensure tallied_count=2=max_responses
        Response.objects.filter(study=self.study).update(is_tallied=True)
        self.tallied_response = Response.objects.filter(study=self.study).first()

    def test_consent_manager_shows_dropped_below_message_when_ruling_reduces_count(
        self,
    ):
        """Rejecting consent that drops tallied count below max_responses shows a 'dropped below' message."""
        self.client.force_login(self.researcher)
        self.assertTrue(self.study.has_reached_max_responses)

        url = reverse(
            "exp:study-responses-consent-manager", kwargs={"pk": self.study.pk}
        )
        data = {
            "comments": json.dumps({}),
            "rejected": str(self.tallied_response.uuid),
        }
        http_response = self.client.post(url, data, follow=True)

        message_texts = [str(m) for m in http_response.context["messages"]]
        self.assertTrue(
            any(
                "dropped back below the response limit" in text
                for text in message_texts
            )
        )
        self.study.refresh_from_db()
        self.assertFalse(self.study.has_reached_max_responses)

    def test_consent_manager_shows_reached_max_message_when_ruling_increases_count(
        self,
    ):
        """Accepting a rejected response that brings the tallied count to max_responses shows a 'reached max' warning."""
        # Reject one response so the study starts below max (count=1 < max=2)
        not_tallied_response = Response.objects.filter(study=self.study).last()
        G(ConsentRuling, response=not_tallied_response, action="rejected")
        not_tallied_response.refresh_from_db()
        self.assertFalse(not_tallied_response.is_tallied)

        # Set study to active so accepting the ruling will also trigger the auto-pause
        self.study.state = "active"
        self.study.save()
        self.assertFalse(
            self.study.has_reached_max_responses
        )  # count is 1, which is less than the max (2)

        self.client.force_login(self.researcher)
        url = reverse(
            "exp:study-responses-consent-manager", kwargs={"pk": self.study.pk}
        )
        data = {
            "comments": json.dumps({}),
            "accepted": str(not_tallied_response.uuid),
        }
        http_response = self.client.post(url, data, follow=True)

        message_texts = [str(m) for m in http_response.context["messages"]]
        self.assertTrue(
            any("reached the response limit" in text for text in message_texts)
        )
        self.study.refresh_from_db()
        self.assertTrue(self.study.has_reached_max_responses)
        self.assertEqual(self.study.state, "paused")


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
@override_settings(CELERY_TASK_EAGER_PROPAGATES=False)
class ResponseCountHelperFunctionTests(TestCase):
    """Unit tests for get_summary_statistics_external and get_response_type_counts_external."""

    def setUp(self):
        self.lab = G(Lab, name="Test Lab")
        self.researcher = G(User, is_active=True, is_researcher=True)
        self.participant = G(User, is_active=True, given_name="Parent")
        self.child = G(
            Child,
            user=self.participant,
            given_name="Child",
            birthday=datetime.date.today() - datetime.timedelta(60),
        )
        self.study = G(
            Study,
            creator=self.researcher,
            lab=self.lab,
            study_type=StudyType.get_external(),
            min_age_years=0,
            max_age_years=18,
            max_responses=20,
        )
        self.study.admin_group.user_set.add(self.researcher)

        # 2 tallied non-preview responses (is_tallied set True by signal for eligible external responses)
        for _ in range(2):
            G(
                Response,
                child=self.child,
                study=self.study,
                study_type=self.study.study_type,
                is_preview=False,
            )
        # 1 untallied non-preview response (researcher override to False)
        G(
            Response,
            child=self.child,
            study=self.study,
            study_type=self.study.study_type,
            is_preview=False,
            is_tallied_researcher_override=False,
        )
        # 1 preview response
        G(
            Response,
            child=self.child,
            study=self.study,
            study_type=self.study.study_type,
            is_preview=True,
        )
        # Totals: 2 tallied + 1 untallied + 1 preview = 4 responses

    def test_get_summary_statistics_external_accepted_equals_total(self):
        stats = get_summary_statistics_external(self.study, preview_only=False)
        self.assertEqual(stats["total_responses"], 4)

    def test_get_summary_statistics_external_preview_only_filters_to_previews(self):
        stats = get_summary_statistics_external(self.study, preview_only=True)
        self.assertEqual(stats["total_responses"], 1)

    def test_get_summary_statistics_external_consent_keys_are_absent(self):
        stats = get_summary_statistics_external(self.study, preview_only=False)
        self.assertNotIn("responses", stats)

    def test_get_response_type_counts_external_tallied_count(self):
        counts = get_response_type_counts_external(self.study)
        self.assertEqual(counts["tallied"], 2)

    def test_get_response_type_counts_external_untallied_count(self):
        counts = get_response_type_counts_external(self.study)
        self.assertEqual(counts["untallied"], 1)

    def test_get_response_type_counts_external_preview_count(self):
        counts = get_response_type_counts_external(self.study)
        self.assertEqual(counts["preview"], 1)

    def test_get_response_type_counts_external_totals(self):
        counts = get_response_type_counts_external(self.study)
        self.assertEqual(counts["total"], 4)

    def test_get_response_type_counts_external_consent_related_keys_are_none(self):
        counts = get_response_type_counts_external(self.study)
        for key in (
            "tallied_approved",
            "untallied_approved",
            "tallied_pending",
            "untallied_pending",
            "preview_approved",
            "preview_pending",
            "preview_rejected",
            "nonpreview_rejected",
            "total_pending",
            "total_rejected",
        ):
            with self.subTest(key=key):
                self.assertNotIn(key, counts)

    def test_get_response_type_counts_external_positive_override_counts_as_tallied(
        self,
    ):
        """A response with is_tallied_researcher_override=True should count as tallied."""
        G(
            Response,
            child=self.child,
            study=self.study,
            study_type=self.study.study_type,
            is_preview=False,
            is_tallied_researcher_override=True,
        )
        counts = get_response_type_counts_external(self.study)
        self.assertEqual(counts["tallied"], 3)
        self.assertEqual(counts["untallied"], 1)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
@override_settings(CELERY_TASK_EAGER_PROPAGATES=False)
class ResponseCountContextDataTests(TestCase):
    """Tests for response count context data across 4 study type × max_responses conditions.

    For each combination (internal/external × with/without max_responses), verifies that
    summary_statistics and response_type_counts are correctly set in the view context.

    Internal study fixture (per study):
        - 2 tallied approved:  completed + consent accepted  → tallied_approved
        - 1 untallied approved: incomplete + consent accepted → untallied_approved
        - 1 tallied pending:    completed + no ruling         → tallied_pending
        - 1 preview approved: preview + consent accepted   → preview_approved
        Summary: accepted=4, pending=1, rejected=0

    External study fixture (per study):
        - 2 tallied: non-preview, no override  → tallied_approved
        - 1 untallied: non-preview, override=False → untallied_approved
        - 1 preview: is_preview=True         → preview
        Summary: accepted=total=4, pending=None, rejected=None
    """

    def _create_internal_responses(self, study):
        child = G(
            Child,
            user=self.participant,
            given_name="Child",
            birthday=datetime.date.today() - datetime.timedelta(60),
        )
        # 2 tallied approved (completed + accepted consent ruling)
        for _ in range(2):
            resp = G(
                Response,
                child=child,
                study=study,
                study_type=study.study_type,
                completed=True,
                completed_consent_frame=True,
                is_preview=False,
            )
            G(ConsentRuling, response=resp, action="accepted", arbiter=self.researcher)
        # 1 untallied approved (incomplete + accepted consent ruling)
        resp = G(
            Response,
            child=child,
            study=study,
            study_type=study.study_type,
            completed=False,
            completed_consent_frame=True,
            is_preview=False,
        )
        G(ConsentRuling, response=resp, action="accepted", arbiter=self.researcher)
        # 1 tallied pending (completed + no consent ruling → current_ruling=NULL)
        G(
            Response,
            child=child,
            study=study,
            study_type=study.study_type,
            completed=True,
            completed_consent_frame=True,
            is_preview=False,
        )
        # 1 preview approved (preview + accepted consent ruling)
        resp = G(
            Response,
            child=child,
            study=study,
            study_type=study.study_type,
            completed=False,
            completed_consent_frame=True,
            is_preview=True,
        )
        G(ConsentRuling, response=resp, action="accepted", arbiter=self.researcher)
        # 3 preview pending (preview + explicit pending consent ruling)
        for _ in range(3):
            resp = G(
                Response,
                child=child,
                study=study,
                study_type=study.study_type,
                completed=False,
                completed_consent_frame=True,
                is_preview=True,
            )
            G(ConsentRuling, response=resp, action="pending", arbiter=self.researcher)
        # 1 would-be-untallied rejected (ineligible + rejected consent ruling)
        resp = G(
            Response,
            child=child,
            study=study,
            study_type=study.study_type,
            completed=True,
            completed_consent_frame=True,
            is_preview=False,
            eligibility=["Ineligible_TooOld"],
        )
        G(ConsentRuling, response=resp, action="rejected", arbiter=self.researcher)
        # 1 would-be-tallied rejected (rejected consent ruling)
        resp = G(
            Response,
            child=child,
            study=study,
            study_type=study.study_type,
            completed=True,
            completed_consent_frame=True,
            is_preview=False,
        )
        G(ConsentRuling, response=resp, action="rejected", arbiter=self.researcher)

    def _create_external_responses(self, study):
        child = G(
            Child,
            user=self.participant,
            given_name="Child",
            birthday=datetime.date.today() - datetime.timedelta(60),
        )
        # 2 tallied (is_tallied set True by signal for eligible external non-preview responses)
        for _ in range(2):
            G(
                Response,
                child=child,
                study=study,
                study_type=study.study_type,
                is_preview=False,
            )
        # 1 untallied (researcher override to False)
        G(
            Response,
            child=child,
            study=study,
            study_type=study.study_type,
            is_preview=False,
            is_tallied_researcher_override=False,
        )
        # 1 preview
        G(
            Response,
            child=child,
            study=study,
            study_type=study.study_type,
            is_preview=True,
        )

    def setUp(self):
        self.client = Force2FAClient()
        self.lab = G(Lab, name="Test Lab")
        self.researcher = G(User, is_active=True, is_researcher=True)
        self.participant = G(User, is_active=True, given_name="Parent")

        self.internal_no_max = G(
            Study,
            creator=self.researcher,
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
            min_age_years=0,
            max_age_years=18,
            max_responses=None,
        )
        self.internal_with_max = G(
            Study,
            creator=self.researcher,
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
            min_age_years=0,
            max_age_years=18,
            max_responses=20,
        )
        self.external_no_max = G(
            Study,
            creator=self.researcher,
            lab=self.lab,
            study_type=StudyType.get_external(),
            min_age_years=0,
            max_age_years=18,
            max_responses=None,
        )
        self.external_with_max = G(
            Study,
            creator=self.researcher,
            lab=self.lab,
            study_type=StudyType.get_external(),
            min_age_years=0,
            max_age_years=18,
            max_responses=20,
        )

        for study in (
            self.internal_no_max,
            self.internal_with_max,
            self.external_no_max,
            self.external_with_max,
        ):
            study.admin_group.user_set.add(self.researcher)

        self._create_internal_responses(self.internal_no_max)
        self._create_internal_responses(self.internal_with_max)
        self._create_external_responses(self.external_no_max)
        self._create_external_responses(self.external_with_max)

    # StudyResponsesList view - individual responses page

    def _get_responses_list_context(self, study):
        self.client.force_login(self.researcher)
        url = reverse("exp:study-responses-list", kwargs={"pk": study.pk})
        return self.client.get(url).context

    def test_responses_list_internal_no_max_summary_statistics(self):
        # internal without max_responses, summary stats: responses: total/accepted/pending/rejected
        ctx = self._get_responses_list_context(self.internal_no_max)
        stats = ctx["summary_statistics"]["responses"]
        self.assertEqual(stats["accepted"], 4)
        self.assertEqual(stats["pending"], 4)
        self.assertEqual(stats["rejected"], 2)
        self.assertEqual(stats["total"], 10)  # accepted + pending + rejected
        self.assertNotIn("total_responses", ctx["summary_statistics"])
        self.assertNotIn("total_children", ctx["summary_statistics"])

    def test_responses_list_internal_no_max_response_type_counts(self):
        # internal without max_responses, response type counts:
        ctx = self._get_responses_list_context(self.internal_no_max)
        counts = ctx["response_type_counts"]
        # tallied
        self.assertEqual(counts["tallied_approved"], 2)
        self.assertEqual(counts["tallied_pending"], 1)
        self.assertEqual(counts["tallied"], 3)  # tallied_approved + tallied_pending
        # untallied
        self.assertEqual(counts["untallied_approved"], 1)
        self.assertEqual(counts["untallied_pending"], 0)
        self.assertEqual(
            counts["untallied"], 1
        )  # untallied_approved + untallied_pending
        # preview
        self.assertEqual(counts["preview_approved"], 1)
        self.assertEqual(counts["preview_pending"], 3)
        self.assertEqual(counts["preview"], 4)  # preview_approved + preview_pending
        # available
        self.assertEqual(
            counts["total_available"], 4
        )  # preview_approved + tallied_approved + untallied_approved
        # pending
        self.assertEqual(
            counts["total_pending"], 4
        )  # preview_pending + tallied_pending + untallied_pending
        # rejected
        self.assertEqual(counts["preview_rejected"], 0)
        self.assertEqual(counts["nonpreview_rejected"], 2)
        self.assertEqual(
            counts["total_rejected"], 2
        )  # preview_rejected + nonpreview_rejected
        # total
        self.assertEqual(
            counts["total"], 10
        )  # total_available + total_pending + total_rejected

    def test_responses_list_internal_with_max_summary_statistics(self):
        # internal with max_responses, summary stats: responses: total/accepted/pending/rejected
        ctx = self._get_responses_list_context(self.internal_with_max)
        stats = ctx["summary_statistics"]["responses"]
        self.assertEqual(stats["accepted"], 4)
        self.assertEqual(stats["pending"], 4)
        self.assertEqual(stats["rejected"], 2)
        self.assertEqual(stats["total"], 10)  # includes rejected
        self.assertNotIn("total_responses", ctx["summary_statistics"])
        self.assertNotIn("total_children", ctx["summary_statistics"])

    def test_responses_list_internal_with_max_response_type_counts(self):
        # internal with max_responses, response type counts:
        ctx = self._get_responses_list_context(self.internal_with_max)
        counts = ctx["response_type_counts"]
        # tallied
        self.assertEqual(counts["tallied_approved"], 2)
        self.assertEqual(counts["tallied_pending"], 1)
        self.assertEqual(counts["tallied"], 3)  # tallied_approved + tallied_pending
        # untallied
        self.assertEqual(counts["untallied_approved"], 1)
        self.assertEqual(counts["untallied_pending"], 0)
        self.assertEqual(
            counts["untallied"], 1
        )  # untallied_approved + untallied_pending
        # preview
        self.assertEqual(counts["preview_approved"], 1)
        self.assertEqual(counts["preview_pending"], 3)
        self.assertEqual(counts["preview"], 4)  # preview_approved + preview_pending
        # available
        self.assertEqual(
            counts["total_available"], 4
        )  # preview_approved + tallied_approved + untallied_approved
        # pending
        self.assertEqual(
            counts["total_pending"], 4
        )  # preview_pending + tallied_pending + untallied_pending
        # rejected
        self.assertEqual(counts["preview_rejected"], 0)
        self.assertEqual(counts["nonpreview_rejected"], 2)
        self.assertEqual(
            counts["total_rejected"], 2
        )  # preview_rejected + nonpreview_rejected
        # total
        self.assertEqual(
            counts["total"], 10
        )  # total_available + total_pending + total_rejected

    def test_responses_list_external_no_max_summary_statistics(self):
        # external without max_responses, summary stats: total responses, total children
        ctx = self._get_responses_list_context(self.external_no_max)
        self.assertEqual(ctx["summary_statistics"]["total_responses"], 4)
        self.assertEqual(ctx["summary_statistics"]["total_children"], 1)
        self.assertNotIn("pending", ctx["summary_statistics"])
        self.assertNotIn("rejected", ctx["summary_statistics"])
        self.assertNotIn("approved", ctx["summary_statistics"])

    def test_responses_list_external_no_max_response_type_counts(self):
        # external without max_responses, response type counts:
        ctx = self._get_responses_list_context(self.external_no_max)
        counts = ctx["response_type_counts"]
        self.assertEqual(counts["tallied"], 2)
        self.assertEqual(counts["untallied"], 1)
        self.assertEqual(counts["preview"], 1)
        self.assertEqual(counts["total"], 4)

    def test_responses_list_external_with_max_summary_statistics(self):
        # external with max_responses, summary stats: total_responses, total_children
        ctx = self._get_responses_list_context(self.external_with_max)
        stats = ctx["summary_statistics"]
        self.assertEqual(stats["total_responses"], 4)
        self.assertEqual(stats["total_children"], 1)
        self.assertNotIn("pending", stats)
        self.assertNotIn("rejected", stats)
        self.assertNotIn("approved", stats)

    def test_responses_list_external_with_max_response_type_counts(self):
        # external with max_responses, response type counts:
        ctx = self._get_responses_list_context(self.external_with_max)
        counts = ctx["response_type_counts"]
        self.assertEqual(counts["tallied"], 2)
        self.assertEqual(counts["untallied"], 1)
        self.assertEqual(counts["preview"], 1)
        self.assertNotIn("tallied_pending", counts)
        self.assertNotIn("total_rejected", counts)

    # StudyResponsesSummary view - response count summary page

    def _get_count_summary_context(self, study):
        self.client.force_login(self.researcher)
        url = reverse("exp:study-responses-count-summary", kwargs={"pk": study.pk})
        return self.client.get(url).context

    def test_count_summary_internal_response_type_counts(self):
        ctx = self._get_count_summary_context(self.internal_with_max)
        # internal with max, response type counts:
        counts = ctx["response_type_counts"]
        # tallied
        self.assertEqual(counts["tallied_approved"], 2)
        self.assertEqual(counts["tallied_pending"], 1)
        self.assertEqual(counts["tallied"], 3)  # tallied_approved + tallied_pending
        # untallied
        self.assertEqual(counts["untallied_approved"], 1)
        self.assertEqual(counts["untallied_pending"], 0)
        self.assertEqual(
            counts["untallied"], 1
        )  # untallied_approved + untallied_pending
        # preview
        self.assertEqual(counts["preview_approved"], 1)
        self.assertEqual(counts["preview_pending"], 3)
        self.assertEqual(counts["preview"], 4)  # preview_approved + preview_pending
        # available
        self.assertEqual(
            counts["total_available"], 4
        )  # preview_approved + tallied_approved + untallied_approved
        # pending
        self.assertEqual(
            counts["total_pending"], 4
        )  # preview_pending + tallied_pending + untallied_pending
        # rejected
        self.assertEqual(counts["preview_rejected"], 0)
        self.assertEqual(counts["nonpreview_rejected"], 2)
        self.assertEqual(
            counts["total_rejected"], 2
        )  # preview_rejected + nonpreview_rejected
        # total
        self.assertEqual(
            counts["total"], 10
        )  # total_available + total_pending + total_rejected

    def test_count_summary_external_response_type_counts(self):
        ctx = self._get_count_summary_context(self.external_with_max)
        # external with max, response type counts:
        counts = ctx["response_type_counts"]
        self.assertEqual(counts["tallied"], 2)
        self.assertEqual(counts["untallied"], 1)
        self.assertEqual(counts["preview"], 1)

    def test_count_summary_internal_summary_statistics(self):
        ctx = self._get_count_summary_context(self.internal_with_max)
        # internal with max responses, summary stats: responses: total/accepted/pending/rejected
        stats = ctx["summary_statistics"]["responses"]
        self.assertEqual(stats["accepted"], 4)
        self.assertEqual(stats["pending"], 4)
        self.assertEqual(stats["rejected"], 2)
        self.assertEqual(stats["total"], 10)  # includes rejected
        self.assertNotIn("total_responses", ctx["summary_statistics"])
        self.assertNotIn("total_children", ctx["summary_statistics"])

    def test_count_summary_external_summary_statistics(self):
        ctx = self._get_count_summary_context(self.external_with_max)
        # external with max responses, summary stats: total_responses, total_children
        self.assertEqual(ctx["summary_statistics"]["total_responses"], 4)
        self.assertEqual(ctx["summary_statistics"]["total_children"], 1)

    # StudyResponsesAll - all response download page

    def _get_responses_all_context(self, study):
        self.client.force_login(self.researcher)
        url = reverse("exp:study-responses-all", kwargs={"pk": study.pk})
        return self.client.get(url).context

    def test_responses_all_internal_response_type_counts(self):
        ctx = self._get_responses_all_context(self.internal_with_max)
        counts = ctx["response_type_counts"]
        # tallied
        self.assertEqual(counts["tallied_approved"], 2)
        self.assertEqual(counts["tallied_pending"], 1)
        self.assertEqual(counts["tallied"], 3)  # tallied_approved + tallied_pending
        # untallied
        self.assertEqual(counts["untallied_approved"], 1)
        self.assertEqual(counts["untallied_pending"], 0)
        self.assertEqual(
            counts["untallied"], 1
        )  # untallied_approved + untallied_pending
        # preview
        self.assertEqual(counts["preview_approved"], 1)
        self.assertEqual(counts["preview_pending"], 3)
        self.assertEqual(counts["preview"], 4)  # preview_approved + preview_pending
        # available
        self.assertEqual(
            counts["total_available"], 4
        )  # preview_approved + tallied_approved + untallied_approved
        # pending
        self.assertEqual(
            counts["total_pending"], 4
        )  # preview_pending + tallied_pending + untallied_pending
        # rejected
        self.assertEqual(counts["preview_rejected"], 0)
        self.assertEqual(counts["nonpreview_rejected"], 2)
        self.assertEqual(
            counts["total_rejected"], 2
        )  # preview_rejected + nonpreview_rejected
        # total
        self.assertEqual(
            counts["total"], 10
        )  # total_available + total_pending + total_rejected

    def test_responses_all_external_response_type_counts(self):
        ctx = self._get_responses_all_context(self.external_with_max)
        counts = ctx["response_type_counts"]
        self.assertEqual(counts["tallied"], 2)
        self.assertEqual(counts["untallied"], 1)
        self.assertEqual(counts["preview"], 1)

    # StudyDemographics view - demographics download page

    def _get_demographics_context(self, study):
        self.client.force_login(self.researcher)
        url = reverse("exp:study-demographics", kwargs={"pk": study.pk})
        return self.client.get(url).context

    def test_demographics_internal_response_type_counts(self):
        ctx = self._get_demographics_context(self.internal_with_max)
        counts = ctx["response_type_counts"]
        # tallied
        self.assertEqual(counts["tallied_approved"], 2)
        self.assertEqual(counts["tallied_pending"], 1)
        self.assertEqual(counts["tallied"], 3)  # tallied_approved + tallied_pending
        # untallied
        self.assertEqual(counts["untallied_approved"], 1)
        self.assertEqual(counts["untallied_pending"], 0)
        self.assertEqual(
            counts["untallied"], 1
        )  # untallied_approved + untallied_pending
        # preview
        self.assertEqual(counts["preview_approved"], 1)
        self.assertEqual(counts["preview_pending"], 3)
        self.assertEqual(counts["preview"], 4)  # preview_approved + preview_pending
        # available
        self.assertEqual(
            counts["total_available"], 4
        )  # preview_approved + tallied_approved + untallied_approved
        # pending
        self.assertEqual(
            counts["total_pending"], 4
        )  # preview_pending + tallied_pending + untallied_pending
        # rejected
        self.assertEqual(counts["preview_rejected"], 0)
        self.assertEqual(counts["nonpreview_rejected"], 2)
        self.assertEqual(
            counts["total_rejected"], 2
        )  # preview_rejected + nonpreview_rejected
        # total
        self.assertEqual(
            counts["total"], 10
        )  # total_available + total_pending + total_rejected

    def test_demographics_external_response_type_counts(self):
        ctx = self._get_demographics_context(self.external_with_max)
        counts = ctx["response_type_counts"]
        self.assertEqual(counts["tallied"], 2)
        self.assertEqual(counts["untallied"], 1)
        self.assertEqual(counts["preview"], 1)

    def test_demographics_internal_summary_statistics(self):
        ctx = self._get_demographics_context(self.internal_with_max)
        stats = ctx["summary_statistics"]["responses"]
        self.assertEqual(stats["accepted"], 4)
        self.assertEqual(stats["pending"], 4)
        self.assertEqual(stats["rejected"], 2)
        self.assertEqual(stats["total"], 10)  # includes rejected
        self.assertNotIn("total_responses", ctx["summary_statistics"])
        self.assertNotIn("total_children", ctx["summary_statistics"])

    def test_demographics_external_summary_statistics(self):
        ctx = self._get_demographics_context(self.external_with_max)
        self.assertEqual(ctx["summary_statistics"]["total_responses"], 4)
        self.assertEqual(ctx["summary_statistics"]["total_children"], 1)

    # StudyResponseSetResearcherFields AJAX endpoint

    def _post_is_tallied_update(self, study, response_obj, value):
        self.client.force_login(self.researcher)
        url = reverse("exp:study-responses-researcher-update", kwargs={"pk": study.pk})
        data = {"responseId": response_obj.id, "field": "is_tallied", "value": value}
        return self.client.post(url, json.dumps(data), content_type="application/json")

    def test_is_tallied_update_internal_returns_consent_based_counts(self):
        """Updating is_tallied on an internal study response returns consent-ruling-aware counts."""
        response_obj = self.internal_with_max.responses.filter(is_preview=False).first()
        resp = self._post_is_tallied_update(self.internal_with_max, response_obj, True)
        self.assertEqual(resp.status_code, 200)
        counts = resp.json()["counts"]
        # consent-related keys must be integers, not None
        self.assertIsNotNone(counts["tallied_pending"])
        self.assertIsNotNone(counts["total_rejected"])

    def test_is_tallied_update_external_returns_consent_free_counts(self):
        """Updating is_tallied on an external study response returns consent-free counts."""
        response_obj = self.external_with_max.responses.filter(is_preview=False).first()
        resp = self._post_is_tallied_update(self.external_with_max, response_obj, True)
        self.assertEqual(resp.status_code, 200)
        counts = resp.json()["counts"]
        # consent-related keys do not exist for external studies
        self.assertNotIn("tallied_pending", counts)
        self.assertNotIn("total_rejected", counts)
