import json
import uuid

from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm

from accounts.models import Child, DemographicData, User
from studies.models import ConsentRuling, Feedback, Response, Study, Video


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
        self.study = G(Study, creator=self.study_admin, shared_preview=False)
        self.study_shared_preview = G(
            Study, creator=self.study_admin, shared_preview=True
        )

        self.study.study_admin_group.user_set.add(self.study_admin)
        self.study.study_read_group.user_set.add(self.study_reader)
        [
            assign_perm("accounts.can_view_experimenter", researcher)
            for researcher in [
                self.study_admin,
                self.study_reader,
                self.other_researcher,
            ]
        ]

        self.study_reader_child = G(
            Child, user=self.study_reader, given_name="Study reader child"
        )
        self.other_researcher_child = G(
            Child, user=self.other_researcher, given_name="Other researcher child"
        )

        self.children_for_participants = []
        self.demo_snapshots_for_participants = []
        self.responses = []
        self.preview_responses = []
        for part in self.participants:
            these_children = [
                G(Child, user=part, given_name="Child" + str(i))
                for i in range(children_per_participant)
            ]
            self.children_for_participants.append(these_children)
            self.demo_snapshots_for_participants.append(
                G(DemographicData, user=part, density="urban")
            )
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
                )
                for child in these_children
            ]

        # Confirm consent for all responses

        self.n_previews = children_per_participant * n_participants
        self.consent_rulings = [
            G(ConsentRuling, study=self.study, response=response, action="accepted")
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
        url = reverse("exp:preview-detail", kwargs={"path": self.study.uuid})
        page = self.client.get(url)
        self.assertEqual(
            page.status_code,
            200,
            "Researcher with study read access cannot access: " + url,
        )

    def testCanSeeStudyPreviewAsOtherResearcherIfShared(self):
        self.client.force_login(self.other_researcher)
        url = reverse(
            "exp:preview-detail", kwargs={"path": self.study_shared_preview.uuid}
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
            "exp:preview-detail", kwargs={"path": self.study_shared_preview.uuid}
        )
        page = self.client.get(url)
        self.assertEqual(
            page.status_code, 403, "Study preview is accessible by participant: " + url
        )

    def testCannotSeeStudyPreviewAsOtherResearcherIfNotShared(self):
        self.client.force_login(self.other_researcher)
        url = reverse("exp:preview-detail", kwargs={"path": self.study.uuid})
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


class ResponseSaveHandlingTestCase(TestCase):
    def setUp(self):
        self.researcher = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 1"
        )
        self.participant = G(User, is_active=True, given_name="Participant 1")
        self.participant.save()
        self.child = G(Child, user=self.participant, given_name="Sally")
        self.study = G(Study, creator=self.researcher)
        self.response_after_consent_frame = G(
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
        self.setup_video = G(
            Video,
            study=self.study,
            response=self.response_after_consent_frame,
            is_consent_footage=False,
            frame_id="1-video-setup",
        )
        self.consent_video = G(
            Video,
            study=self.study,
            response=self.response_after_consent_frame,
            is_consent_footage=False,
            frame_id="2-my-consent-frame",
        )
        self.consent_video_2 = G(
            Video,
            study=self.study,
            response=self.response_after_consent_frame,
            is_consent_footage=False,
            frame_id="2-my-consent-frame",
        )

        self.response_after_default_frame = G(
            Response,
            child=self.child,
            study=self.study,
            completed=False,
            completed_consent_frame=True,
            sequence=[
                "0-video-config",
                "1-video-setup",
                "2-my-consent-frame",
                "3-test-trial",
            ],
            exp_data={
                "0-video-config": {"frameType": "DEFAULT"},
                "1-video-setup": {"frameType": "DEFAULT"},
                "2-my-consent-frame": {"frameType": "CONSENT"},
                "3-test-trial": {"frameType": "DEFAULT"},
            },
        )
        self.consent_video_previously_completed = G(
            Video,
            study=self.study,
            response=self.response_after_default_frame,
            is_consent_footage=False,
            frame_id="2-my-consent-frame",
        )
        self.test_video_just_completed = G(
            Video,
            study=self.study,
            response=self.response_after_default_frame,
            is_consent_footage=False,
            frame_id="3-test-trial",
        )

        self.withdrawn_response_after_exit_frame = G(
            Response,
            child=self.child,
            study=self.study,
            completed=False,
            completed_consent_frame=True,
            sequence=[
                "0-video-config",
                "1-video-setup",
                "2-my-consent-frame",
                "3-final-survey",
            ],
            exp_data={
                "0-video-config": {"frameType": "DEFAULT"},
                "1-video-setup": {"frameType": "DEFAULT"},
                "2-my-consent-frame": {"frameType": "CONSENT"},
                "3-final-survey": {"frameType": "EXIT", "withdrawal": True},
            },
        )
        self.withdrawn_video_1 = G(
            Video,
            study=self.study,
            response=self.withdrawn_response_after_exit_frame,
            is_consent_footage=False,
            frame_id="0-video-config",
        )
        self.withdrawn_video_2 = G(
            Video,
            study=self.study,
            response=self.withdrawn_response_after_exit_frame,
            is_consent_footage=False,
            frame_id="1-video-setup",
        )
        self.withdrawn_video_consent = G(
            Video,
            study=self.study,
            response=self.withdrawn_response_after_exit_frame,
            is_consent_footage=False,
            frame_id="2-my-consent-frame",
        )

    # Test labeling of current consent type frame video(s) as consent
    def testMarkConsentTypeVideoAsConsent(self):
        self.response_after_consent_frame.save()  # to run post-save hook
        consent_video = Video.objects.get(pk=self.consent_video.pk)
        consent_video_2 = Video.objects.get(pk=self.consent_video_2.pk)
        setup_video = Video.objects.get(pk=self.setup_video.pk)
        self.assertTrue(consent_video.is_consent_footage)
        self.assertTrue(consent_video_2.is_consent_footage)
        self.assertFalse(setup_video.is_consent_footage)

    # Test non-labeling of video as consent if current frame is not consent type
    def testDoNotMarkConsentUnlessCurrentFrameIsConsent(self):
        self.response_after_default_frame.save()  # to run post-save hook
        consent_video_previously_completed = Video.objects.get(
            pk=self.consent_video_previously_completed.pk
        )
        test_video_just_completed = Video.objects.get(
            pk=self.test_video_just_completed.pk
        )
        self.assertFalse(consent_video_previously_completed.is_consent_footage)
        self.assertFalse(test_video_just_completed.is_consent_footage)

    # Test that withdrawn videos are removed from database following save of exit frame with withdrawal flag
    def testRemoveWithdrawnVideos(self):
        settings.CELERY_TASK_ALWAYS_EAGER = True  # Don't test removal from S3
        self.assertEqual(len(self.withdrawn_response_after_exit_frame.videos.all()), 3)
        self.withdrawn_response_after_exit_frame.save()  # to run post-save hook
        self.assertEqual(len(self.withdrawn_response_after_exit_frame.videos.all()), 0)
