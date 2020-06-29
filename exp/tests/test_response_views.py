import csv
import datetime
import io
import json

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.http import urlencode
from django_dynamic_fixture import G

from accounts.models import Child, DemographicData, User
from studies.models import ConsentRuling, Lab, Response, Study, StudyType


# Run celery tasks right away, but don't catch errors from them. The relevant tasks for
# this case involve S3/GCP access which we're not testing.
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
@override_settings(CELERY_TASK_EAGER_PROPAGATES=False)
class ResponseViewsTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        n_participants = 5
        children_per_participant = 3

        self.study_admin = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 1"
        )
        self.study_reader = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 2"
        )
        self.other_researcher = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 3"
        )
        self.participants = [
            G(User, is_active=True, given_name="Mom") for i in range(n_participants)
        ]
        self.study_type = G(StudyType, name="default", id=1)

        self.lab = G(Lab, name="MIT")
        self.study = G(
            Study,
            creator=self.study_admin,
            shared_preview=False,
            study_type=self.study_type,
            name="Test Study",
            lab=self.lab,
        )
        # Note: currently not mocking Study.image field, because I couldn't get any of the
        # approaches outlined at https://stackoverflow.com/questions/26298821/django-testing-model-with-imagefield
        # working.
        self.study_shared_preview = G(
            Study,
            creator=self.study_admin,
            shared_preview=True,
            study_type=self.study_type,
            name="Test Study",
            lab=self.lab,
        )

        self.study.admin_group.user_set.add(self.study_admin)
        self.study.researcher_group.user_set.add(self.study_reader)

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
                "exp:study-responses-download-frame-data-csv",
                kwargs={"pk": self.study.pk},
            ),
            reverse(
                "exp:study-responses-download-frame-data-dict-csv",
                kwargs={"pk": self.study.pk},
            ),
            reverse(
                "exp:study-responses-download-frame-data-zip-csv",
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

    def test_cannot_see_any_responses_views_unauthenticated(self):
        for url in self.all_response_urls:
            page = self.client.get(url)
            self.assertEqual(
                page.status_code,
                302,
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

    def test_can_see_response_views_as_study_admin(self):
        self.client.force_login(self.study_admin)
        for url in self.all_response_urls:
            page = self.client.get(url)
            self.assertIn(
                page.status_code, [200, 302], "Unexpected status code for " + url
            )

    def test_cannot_delete_preview_data_as_unassociated_researcher(self):
        self.client.force_login(self.other_researcher)
        url = reverse("exp:study-responses-all", kwargs={"pk": self.study.pk})
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
        url = reverse("exp:study-responses-all", kwargs={"pk": self.study.pk})
        self.assertEqual(
            self.study.responses.filter(is_preview=True).count(), self.n_previews
        )
        response = self.client.post(url, {})
        self.assertEqual(self.study.responses.filter(is_preview=True).count(), 0)


class ResponseDataDownloadTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        n_participants = 3
        children_per_participant = 2

        self.study_reader = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 2"
        )
        self.study_type = G(StudyType, name="default", id=1)
        self.lab = G(Lab, name="MIT")
        self.study = G(
            Study,
            creator=self.study_reader,
            shared_preview=False,
            study_type=self.study_type,
            name="Test Study",
            lab=self.lab,
        )

        self.study.researcher_group.user_set.add(self.study_reader)

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
        self.n_responses = children_per_participant * n_participants * 2
        self.consent_rulings = [
            G(
                ConsentRuling,
                response=response,
                action="accepted",
                arbiter=self.study_reader,
            )
            for response in self.responses + self.preview_responses
        ]

        # Build a few complementary sets of options for fields to include in downloads
        self.age_optionset_1 = ["rounded"]
        self.child_optionset_1 = ["globalchild", "gender", "conditions", "parent"]
        self.labels_1 = [
            "child_age_rounded",
            "child_global_id",
            "child_gender",
            "child_condition_list",
            "participant_nickname",
        ]
        self.child_labels_json_1 = [
            "global_id",
            "gender",
            "condition_list",
            "age_rounded",
        ]
        self.participant_labels_json_1 = ["nickname"]
        self.age_optionset_2 = ["exact", "birthday"]
        self.child_optionset_2 = [
            "name",
            "gestage",
            "languages",
            "addl",
            "globalparent",
        ]
        self.labels_2 = [
            "child_age_in_days",
            "child_birthday",
            "child_name",
            "child_age_at_birth",
            "child_language_list",
            "child_additional_information",
            "participant_global_id",
        ]
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

    def test_get_appropriate_fields_in_csv_downloads_set1(self):
        self.client.force_login(self.study_reader)
        query_string = urlencode(
            {
                "ageoptions": self.age_optionset_1,
                "childoptions": self.child_optionset_1,
            },
            doseq=True,
        )
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
        for header in self.labels_1:
            self.assertIn(
                header,
                csv_headers,
                f"Downloaded summary CSV file is missing header {header}",
            )
        # Check that the remaining headers ARE NOT present
        for header in self.labels_2:
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
        # Check that the filename is appropriately titled - because parent name is present
        self.assertRegex(
            response.get("Content-Disposition"),
            r"^attachment; filename=\"(.*)-identifiable\.csv\"",
        )

    def test_get_appropriate_fields_in_json_downloads(self):
        self.client.force_login(self.study_reader)
        query_string = urlencode(
            {
                "ageoptions": self.age_optionset_1,
                "childoptions": self.child_optionset_1,
            },
            doseq=True,
        )
        response = self.client.get(f"{self.response_summary_json_url}?{query_string}")
        content = response.content.decode("utf-8")
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
            self.assertEqual(data[0]["child"][header], "")
        for header in self.participant_labels_json_2:
            self.assertEqual(data[0]["participant"][header], "")
        # Check that some *data* is present as expect: parent, but not child names
        for row in data:
            self.assertIn(row["participant"]["nickname"], self.participant_names)
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
        # Check that the filename is appropriately titled - because parent name is present
        self.assertRegex(
            response.get("Content-Disposition"),
            r"^attachment; filename=\"(.*)-identifiable\.json\"",
            "JSON file not named with -identifiable suffix as expected based on fields included",
        )

    def test_get_appropriate_fields_in_csv_downloads_set2(self):
        self.client.force_login(self.study_reader)
        query_string = urlencode(
            {
                "ageoptions": self.age_optionset_2,
                "childoptions": self.child_optionset_2,
            },
            doseq=True,
        )
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
        for header in self.labels_2:
            self.assertIn(
                header,
                csv_headers,
                f"Downloaded summary CSV file is missing header {header}",
            )
        # Check that the remaining headers ARE NOT present
        for header in self.labels_1:
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
            "response_uuid",
            "response_withdrawn",
            "response_parent_feedback",
            "response_video_privacy",
            "response_databrary",
            "response_birthdate_difference",
        ]
        exit_survey_headers_columns = {}

        for header in exit_survey_headers:
            self.assertIn(
                header,
                csv_headers,
                f"Exit survey header {header} missing from summary CSV file",
            )
            exit_survey_headers_columns[header] = csv_headers.index(header)

        # Now check that the actual values are correct in a few cases
        self.assertEqual(self.n_responses + self.n_previews + 2, len(csv_body))

        withdrawn_response_line = [
            line
            for line in csv_body
            if line[exit_survey_headers_columns["response_uuid"]]
            == str(withdrawn_response.uuid)
        ][0]
        self.assertEqual(
            withdrawn_response_line[exit_survey_headers_columns["response_withdrawn"]],
            "True",
            "Withdrawn response was not marked as response in CSV summary!",
        )
        self.assertEqual(
            withdrawn_response_line[
                exit_survey_headers_columns["response_parent_feedback"]
            ],
            "this was fun but my older child was reciting top secret prime numbers",
            "Parent feedback was not correctly inserted in CSV summary",
        )
        self.assertEqual(
            withdrawn_response_line[
                exit_survey_headers_columns["response_video_privacy"]
            ],
            "private",
            "Video privacy level was not correctly inserted in CSV summary",
        )
        self.assertEqual(
            withdrawn_response_line[exit_survey_headers_columns["response_databrary"]],
            "yes",
            "Databrary consent was not correctly inserted in CSV summary",
        )
        self.assertEqual(
            withdrawn_response_line[
                exit_survey_headers_columns["response_birthdate_difference"]
            ],
            "17",
            "Birthdate difference was not correctly inserted in CSV summary",
        )

        incomplete_response_line = [
            line
            for line in csv_body
            if line[exit_survey_headers_columns["response_uuid"]]
            == str(incomplete_response.uuid)
        ][0]
        self.assertEqual(
            incomplete_response_line[exit_survey_headers_columns["response_withdrawn"]],
            "False",
            "Incomplete response was not marked as non-withdrawn",
        )
        self.assertEqual(
            incomplete_response_line[
                exit_survey_headers_columns["response_parent_feedback"]
            ],
            "",
        )
        self.assertEqual(
            incomplete_response_line[
                exit_survey_headers_columns["response_video_privacy"]
            ],
            "",
        )
        self.assertEqual(
            incomplete_response_line[exit_survey_headers_columns["response_databrary"]],
            "",
        )

    def test_get_exit_survey_fields_in_summary_json(self):
        self.client.force_login(self.study_reader)
        # Add a single response where we expect specific fields
        withdrawn_response = G(
            Response,
            child=self.children_for_participants[0][0],
            study=self.study,
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
        content = json_response.content.decode("utf-8")
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

    # TODO: add test for study-demographics-download-csv, checking for global ID inclusion
    # TODO: add test for study-responses-children-summary-csv
    # TODO: add test of study response downloads with large responses and with large
    #       number of responses
