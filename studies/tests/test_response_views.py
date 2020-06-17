import datetime

from django.test import Client, TestCase
from django.urls import reverse
from django_dynamic_fixture import G

from accounts.models import Child, DemographicData, User
from studies.models import ConsentRuling, Lab, Response, Study, StudyType


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
        ]

    def testCannotSeeAnyResponsesViewsAsParticipant(self):
        self.client.force_login(self.participants[0])
        for url in self.all_response_urls:
            page = self.client.get(url)
            self.assertEqual(
                page.status_code,
                403,
                "Unassociated participant not forbidden to access responses: " + url,
            )

    def testCannotSeeAnyResponsesViewsAsUnassociatedResearcher(self):
        self.client.force_login(self.other_researcher)
        for url in self.all_response_urls:
            page = self.client.get(url)
            self.assertEqual(
                page.status_code,
                403,
                "Unassociated researcher not forbidden to access responses: " + url,
            )

    def testCanSeeResponseViewsAsStudyResearcher(self):
        self.client.force_login(self.study_reader)
        for url in self.all_response_urls:
            page = self.client.get(url)
            self.assertIn(
                page.status_code, [200, 302], "Unexpected status code for " + url
            )

    def testCanSeeResponseViewsAsStudyAdmin(self):
        self.client.force_login(self.study_admin)
        for url in self.all_response_urls:
            page = self.client.get(url)
            self.assertIn(
                page.status_code, [200, 302], "Unexpected status code for " + url
            )

    def testCanSeeStudyPreviewAsStudyRead(self):
        self.client.force_login(self.study_reader)
        url = reverse("exp:preview-detail", kwargs={"uuid": self.study.uuid})
        page = self.client.get(url)
        self.assertEqual(
            page.status_code,
            200,
            "Researcher with study read access cannot access: " + url,
        )

    def testCanSeeStudyPreviewAsOtherResearcherIfShared(self):
        self.client.force_login(self.other_researcher)
        url = reverse(
            "exp:preview-detail", kwargs={"uuid": self.study_shared_preview.uuid}
        )
        page = self.client.get(url)
        self.assertEqual(
            page.status_code,
            200,
            "Study preview is shared but unassociated researcher cannot access: " + url,
        )

    def testCannotSeeStudyPreviewAsParticipant(self):
        self.client.force_login(self.participants[0])
        url = reverse(
            "exp:preview-detail", kwargs={"uuid": self.study_shared_preview.uuid}
        )
        page = self.client.get(url)
        self.assertEqual(
            page.status_code, 403, "Study preview is accessible by participant: " + url
        )

    def testCannotSeeStudyPreviewAsOtherResearcherIfNotShared(self):
        self.client.force_login(self.other_researcher)
        url = reverse("exp:preview-detail", kwargs={"uuid": self.study.uuid})
        page = self.client.get(url)
        self.assertEqual(
            page.status_code,
            403,
            "Study preview is not shared but unassociated researcher can access: "
            + url,
        )

    def testCannotDeletePreviewDataAsUnassociatedResearcher(self):
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

    def testDeletePreviewData(self):
        self.client.force_login(self.study_admin)
        url = reverse("exp:study-responses-all", kwargs={"pk": self.study.pk})
        self.assertEqual(
            self.study.responses.filter(is_preview=True).count(), self.n_previews
        )
        response = self.client.post(url, {})
        self.assertEqual(self.study.responses.filter(is_preview=True).count(), 0)
