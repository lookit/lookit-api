from unittest import skip

from django.conf import settings
from django.test import TestCase
from django_dynamic_fixture import G

from accounts.models import Child, User
from studies.models import Response, Study, Video


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
    @skip(
        "Should now test this in a new test of from_pipe_payload, as is_consent_footage isn't set upon response save"
    )
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
