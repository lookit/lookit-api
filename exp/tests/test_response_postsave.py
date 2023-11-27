from django.conf import settings
from django.test import TestCase
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm

from accounts.models import Child, User
from studies.models import ConsentRuling, Lab, Response, Study, StudyType, Video
from studies.permissions import StudyPermission


class ResponseSaveHandlingTestCase(TestCase):
    def setUp(self):
        self.researcher = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 1"
        )
        self.participant = G(User, is_active=True, given_name="Participant 1")
        self.participant.save()
        self.child = G(Child, user=self.participant, given_name="Sally")
        self.lab = G(Lab, name="MIT")
        self.study = G(
            Study,
            creator=self.researcher,
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )
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

    def test_responses_per_study_type(self):
        user = G(User)
        researcher = G(User, is_active=True, is_researcher=True, username="Researcher")
        child = G(Child, user=user)
        study = G(Study, study_type=StudyType.get_ember_frame_player())

        # Create frame player response
        frame_player_response = G(
            Response,
            study=study,
            child=child,
            study_type=study.study_type,
            completed_consent_frame=True,
        )
        G(ConsentRuling, response=frame_player_response, action="accepted")

        # Create external response
        study.study_type = StudyType.get_external()
        study.save()
        G(Response, study=study, child=child, study_type=study.study_type)

        # Give researcher perms
        assign_perm(
            StudyPermission.READ_STUDY_RESPONSE_DATA.prefixed_codename,
            researcher,
            study,
        )

        # There are two responses for this study
        self.assertEqual(Response.objects.filter(study=study).count(), 2)

        # The study is already set to external
        self.assertEqual(study.responses_for_researcher(researcher).count(), 1)
        self.assertTrue(
            study.responses_for_researcher(researcher).first().study_type.is_external
        )

        # Change study back to frame player
        study.study_type = StudyType.get_ember_frame_player()
        study.save()
        self.assertEqual(study.responses_for_researcher(researcher).count(), 1)
        self.assertTrue(
            study.responses_for_researcher(researcher)
            .first()
            .study_type.is_ember_frame_player
        )
