import csv
import datetime
import io
import json
import re

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.http import urlencode
from django_dynamic_fixture import G

from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from accounts.models import Child, DemographicData, User
from accounts.utils import hash_id
from exp.views.responses import StudyResponseSetResearcherFields
from studies.models import ConsentRuling, Lab, Response, Study, StudyType, Video


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
        # For testing researcher-editable response fields: researcher_session_status, researcher_payment_status, researcher_star
        self.editable_fields = StudyResponseSetResearcherFields.EDITABLE_FIELDS
        default_values = [
            "",
            "",
            False,
        ]  # These correspond to session status, payment status, and star
        new_values = ["follow_up", "to_pay", True]
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
                self.assertEqual(response.status_code, 200)
                success_str = f"Response {resp.id} field {field} updated to {self.fields_new_values[field]}"
                self.assertIn(success_str, response.json().get("success"))
                updated_resp = Response.objects.get(id=resp.id)
                self.assertEqual(
                    getattr(updated_resp, field),
                    self.fields_new_values[field],
                )
                # Reset the response object to default values
                setattr(updated_resp, field, self.fields_default_values[field])
                updated_resp.save()


class ResponseDataDownloadTestCase(TestCase):
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
        ]  # These correspond to session status, payment status, and star
        self.fields_default_values = {
            self.editable_fields[i]: default_values[i]
            for i in range(len(self.editable_fields))
        }

    def test_get_appropriate_fields_in_csv_downloads_set1(self):
        self.client.force_login(self.study_reader)
        query_string = urlencode({"data_options": self.optionset_1}, doseq=True)
        response = self.client.get(f"{self.response_summary_url}?{query_string}")
        content = response.content.decode("utf-8")
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
        content = response.content.decode("utf-8")
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
        content = csv_response.content.decode("utf-8")
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
        content = response.content.decode("utf-8")
        csv_reader = csv.reader(io.StringIO(content), quoting=csv.QUOTE_ALL)
        csv_body = list(csv_reader)
        csv_headers = csv_body.pop(0)
        self.assertEqual(True, True)
        researcher_editable_field_headers = [
            "response__" + field for field in self.editable_fields
        ]
        for field in researcher_editable_field_headers:
            self.assertIn(field, csv_headers)

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

    def test_get_appropriate_children_in_child_csv_as_previewer(self):
        self.client.force_login(self.study_previewer)
        csv_response = self.client.get(
            reverse(
                "exp:study-responses-children-summary-csv", kwargs={"pk": self.study.pk}
            )
        )
        content = csv_response.content.decode("utf-8")
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
        content = csv_response.content.decode("utf-8")
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
        content = response.content.decode("utf-8")
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
        content = response.content.decode("utf-8")
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
        content = csv_response.content.decode("utf-8")
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
        content = csv_response.content.decode("utf-8")
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
        content = csv_response.content.decode("utf-8")
        csv_reader = csv.reader(io.StringIO(content), quoting=csv.QUOTE_ALL)
        csv_body = list(csv_reader)
        csv_headers = csv_body.pop(0)
        self.assertIn("participant__global_id", csv_headers)
        self.assertIn(str(self.participants[0].uuid), content)

        # Without participant__global_id selected, should not be in header and data should not be included
        query_string = urlencode({"demo_options": []}, doseq=True)
        csv_response = self.client.get(f"{demographic_csv_url}?{query_string}")
        content = csv_response.content.decode("utf-8")
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
        content = response.content.decode("utf-8")
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
        content = response.content.decode("utf-8")
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
        content = response.content.decode("utf-8")
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
        content = response.content.decode("utf-8")

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
        # For testing researcher-editable response fields: researcher_session_status, researcher_payment_status, researcher_star
        self.editable_fields = StudyResponseSetResearcherFields.EDITABLE_FIELDS
        default_values = [
            "",
            "",
            False,
        ]  # These correspond to session status, payment status, and star
        new_values = ["follow_up", "to_pay", True]
        invalid_values = ["some_other_string", 42, "true"]
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
        # These correspond to the fields: session status, payment status, star
        err_strings = [
            "Invalid request: Session Status must be one of ",
            "Invalid request: Payment Status must be one of ",
            "Invalid request: Star field must be a boolean value.",
        ]
        fields_err_strings = {
            self.editable_fields[i]: err_strings[i]
            for i in range(len(self.editable_fields))
        }
        for field in self.editable_fields:
            self.assertEqual(
                getattr(self.response, field), self.fields_default_values[field]
            )
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
