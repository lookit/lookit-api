import datetime
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm

from accounts.models import Child, User
from studies.helpers import ResponseEligibility
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

    def test_exit_frame_properties_with_non_dict_value_does_not_raise(self):
        """Accessing exit-frame-derived response properties (withdrawn, privacy, databrary)
        should not raise when exp_data contains non-dict values."""
        response = G(
            Response,
            child=self.child,
            study=self.study,
            completed=False,
            completed_consent_frame=True,
            sequence=["0-video-config", "1-exit-frame"],
            exp_data={
                "0-video-config": {"frameType": "DEFAULT"},
                "1-exit-frame": "unexpected string",
            },
        )
        _ = response.withdrawn
        _ = response.privacy
        _ = response.databrary

    def test_non_dict_exp_data_value_does_not_raise(self):
        """Saving an EFP response where the current frame's exp_data value is not a dict
        should not raise an error."""
        response = G(
            Response,
            child=self.child,
            study=self.study,
            completed=False,
            completed_consent_frame=True,
            sequence=["0-video-config", "1-non-dict-frame"],
            exp_data={
                "0-video-config": {"frameType": "DEFAULT"},
                "1-non-dict-frame": "unexpected string",
            },
        )
        response.save()

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


class JspsychResponseSaveHandlingTestCase(TestCase):
    def setUp(self):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        jspsych = StudyType.get_jspsych()
        user = G(User)
        child = G(Child, birthday=datetime.date(1911, 11, 11), user=user)
        study = G(Study, study_type=jspsych)
        frame_id = "0-survey"
        self.response = G(
            Response,
            child=child,
            study=study,
            study_type=jspsych,
            sequence=[frame_id],
        )
        G(
            Video,
            response=self.response,
            study=study,
            s3_timestamp=timezone.now(),
            frame_id=frame_id,
        )

    def tearDown(self):
        settings.CELERY_TASK_ALWAYS_EAGER = False

    def test_exit_withdraw_videos(self):
        self.response.exp_data = [
            {"chs_type": "exit", "response": {"withdrawal": True}}
        ]
        self.assertEqual(len(self.response.videos.all()), 1)
        self.response.save()
        self.assertEqual(len(self.response.videos.all()), 0)

    def test_exit_not_withdraw_videos(self):
        self.response.exp_data = [
            {"chs_type": "exit", "response": {"withdrawal": False}}
        ]
        self.assertEqual(len(self.response.videos.all()), 1)

        self.response.save()

        self.assertEqual(len(self.response.videos.all()), 1)

    def test_consent_video(self):
        self.response.exp_data = [{"chs_type": "consent", "response": {}}]
        self.assertEqual(len(self.response.videos.all()), 1)
        self.assertFalse(self.response.videos.first().is_consent_footage)
        self.response.save()
        self.assertTrue(self.response.videos.first().is_consent_footage)

    def test_non_dict_element_does_not_raise(self):
        """Saving a jsPsych response where an exp_data element is not a dict
        should not raise an error."""
        self.response.exp_data = [{"chs_type": "consent", "response": {}}, "not-a-dict"]
        self.response.sequence = ["0-consent", "1-bad"]
        self.response.save()

    def test_non_dict_only_element_does_not_raise(self):
        """Saving a jsPsych response where the sole exp_data element is not a dict
        should not raise an error."""
        self.response.exp_data = ["not-a-dict"]
        self.response.sequence = ["0-bad"]
        self.response.save()

    def test_exit_frame_properties_with_non_dict_element_does_not_raise(self):
        """Accessing exit-frame-derived response properties (withdrawn, privacy, databrary)
        should not raise when exp_data contains non-dict elements."""
        self.response.exp_data = [
            {"chs_type": "exit", "response": {"withdrawal": True}},
            "not-a-dict",
        ]
        _ = self.response.withdrawn
        _ = self.response.privacy
        _ = self.response.databrary


class IsTalliedComputeTestCase(TestCase):
    """Unit tests for Response.compute_is_tallied(), covering all combinations of
    is_preview, eligibility, study type, completed, completed_consent_frame, and consent ruling."""

    def setUp(self):
        participant = G(User, is_active=True)
        self.child = G(Child, user=participant)
        lab = G(Lab, name="Test Lab")
        self.internal_study = G(
            Study, lab=lab, study_type=StudyType.get_ember_frame_player()
        )
        self.external_study = G(Study, lab=lab, study_type=StudyType.get_external())

    def _resp(self, study, eligibility=None, **kwargs):
        """Create a Response, then inject eligibility directly in DB to bypass save() override."""
        resp = G(
            Response,
            child=self.child,
            study=study,
            study_type=study.study_type,
            **kwargs,
        )
        if eligibility is not None:
            Response.objects.filter(pk=resp.pk).update(eligibility=eligibility)
            resp = Response.objects.get(pk=resp.pk)
        return resp

    def test_preview_not_tallied_external(self):
        resp = self._resp(
            self.external_study,
            eligibility=[ResponseEligibility.ELIGIBLE],
            is_preview=True,
        )
        self.assertFalse(resp.compute_is_tallied())

    def test_preview_not_tallied_internal(self):
        resp = self._resp(
            self.internal_study,
            eligibility=[ResponseEligibility.ELIGIBLE],
            is_preview=True,
            completed=True,
            completed_consent_frame=True,
        )
        G(ConsentRuling, response=resp, action="accepted")
        self.assertFalse(resp.compute_is_tallied())

    def test_ineligible_too_young_not_tallied(self):
        resp = self._resp(
            self.external_study,
            is_preview=False,
            eligibility=[ResponseEligibility.INELIGIBLE_YOUNG],
        )
        self.assertFalse(resp.compute_is_tallied())

    def test_ineligible_too_old_not_tallied(self):
        resp = self._resp(
            self.external_study,
            is_preview=False,
            eligibility=[ResponseEligibility.INELIGIBLE_OLD],
        )
        self.assertFalse(resp.compute_is_tallied())

    def test_ineligible_criteria_not_tallied(self):
        resp = self._resp(
            self.external_study,
            is_preview=False,
            eligibility=[ResponseEligibility.INELIGIBLE_CRITERIA],
        )
        self.assertFalse(resp.compute_is_tallied())

    def test_ineligible_participation_not_tallied(self):
        resp = self._resp(
            self.external_study,
            is_preview=False,
            eligibility=[ResponseEligibility.INELIGIBLE_PARTICIPATION],
        )
        self.assertFalse(resp.compute_is_tallied())

    def test_empty_eligibility_treated_as_eligible_external(self):
        """Empty eligibility list is backwards-compatible — treated as Eligible."""
        resp = self._resp(self.external_study, is_preview=False, eligibility=[])
        self.assertTrue(resp.compute_is_tallied())

    def test_external_eligible_not_preview_is_tallied(self):
        resp = self._resp(
            self.external_study,
            is_preview=False,
            eligibility=[ResponseEligibility.ELIGIBLE],
        )
        self.assertTrue(resp.compute_is_tallied())

    def test_empty_eligibility_treated_as_eligible_internal(self):
        """Empty eligibility list is backwards-compatible — treated as Eligible."""
        resp = self._resp(
            self.internal_study,
            is_preview=False,
            eligibility=[],
            completed=True,
            completed_consent_frame=True,
        )
        G(ConsentRuling, response=resp, action="accepted")
        self.assertTrue(resp.compute_is_tallied())

    def test_internal_not_completed_not_tallied(self):
        resp = self._resp(
            self.internal_study,
            is_preview=False,
            eligibility=[ResponseEligibility.ELIGIBLE],
            completed=False,
            completed_consent_frame=True,
        )
        G(ConsentRuling, response=resp, action="accepted")
        self.assertFalse(resp.compute_is_tallied())

    def test_internal_no_consent_frame_not_tallied(self):
        resp = self._resp(
            self.internal_study,
            is_preview=False,
            eligibility=[ResponseEligibility.ELIGIBLE],
            completed=True,
            completed_consent_frame=False,
        )
        G(ConsentRuling, response=resp, action="accepted")
        self.assertFalse(resp.compute_is_tallied())

    def test_internal_consent_accepted_complete_is_tallied(self):
        resp = self._resp(
            self.internal_study,
            is_preview=False,
            eligibility=[ResponseEligibility.ELIGIBLE],
            completed=True,
            completed_consent_frame=True,
        )
        G(ConsentRuling, response=resp, action="accepted")
        self.assertTrue(resp.compute_is_tallied())

    def test_internal_consent_pending_complete_is_tallied(self):
        """Pending consent is not rejected, so the response is tallied."""
        resp = self._resp(
            self.internal_study,
            is_preview=False,
            eligibility=[ResponseEligibility.ELIGIBLE],
            completed=True,
            completed_consent_frame=True,
        )
        G(ConsentRuling, response=resp, action="pending")
        self.assertTrue(resp.compute_is_tallied())

    def test_internal_consent_rejected_not_tallied(self):
        resp = self._resp(
            self.internal_study,
            is_preview=False,
            eligibility=[ResponseEligibility.ELIGIBLE],
            completed=True,
            completed_consent_frame=True,
        )
        G(ConsentRuling, response=resp, action="rejected")
        self.assertFalse(resp.compute_is_tallied())

    def test_internal_no_consent_ruling_complete_is_tallied(self):
        """No ruling defaults to pending (not rejected), so a complete response is tallied."""
        resp = self._resp(
            self.internal_study,
            is_preview=False,
            eligibility=[ResponseEligibility.ELIGIBLE],
            completed=True,
            completed_consent_frame=True,
        )
        self.assertTrue(resp.compute_is_tallied())

    def test_internal_most_recent_ruling_accepted_then_rejected_not_tallied(self):
        """Most recent ruling takes precedence; accepted then rejected → not tallied."""
        resp = self._resp(
            self.internal_study,
            is_preview=False,
            eligibility=[ResponseEligibility.ELIGIBLE],
            completed=True,
            completed_consent_frame=True,
        )
        G(ConsentRuling, response=resp, action="accepted")
        G(ConsentRuling, response=resp, action="rejected")
        self.assertFalse(resp.compute_is_tallied())

    def test_internal_most_recent_ruling_rejected_then_accepted_is_tallied(self):
        """Reversing a rejection with a new accepted ruling → tallied."""
        resp = self._resp(
            self.internal_study,
            is_preview=False,
            eligibility=[ResponseEligibility.ELIGIBLE],
            completed=True,
            completed_consent_frame=True,
        )
        G(ConsentRuling, response=resp, action="rejected")
        G(ConsentRuling, response=resp, action="accepted")
        self.assertTrue(resp.compute_is_tallied())

    def test_ineligible_internal_complete_accepted_not_tallied(self):
        """Ineligibility trumps completion and accepted consent for internal studies."""
        resp = self._resp(
            self.internal_study,
            is_preview=False,
            eligibility=[ResponseEligibility.INELIGIBLE_YOUNG],
            completed=True,
            completed_consent_frame=True,
        )
        G(ConsentRuling, response=resp, action="accepted")
        self.assertFalse(resp.compute_is_tallied())


def _make_eligible_setup():
    """Create a child, lab, and factory for studies guaranteed to produce ELIGIBLE responses.

    Uses an explicit child birthday (60 days old) and studies with a broad age range
    (0–18 years, no criteria expression) so that get_eligibility_for_response() always
    returns ELIGIBLE for responses created with this child+study pair.

    Returns (child, lab) — callers create studies separately using the returned lab.
    """
    participant = G(User, is_active=True)
    child = G(
        Child, user=participant, birthday=datetime.date.today() - datetime.timedelta(60)
    )
    lab = G(Lab)
    return child, lab


def _eligible_study(lab, study_type):
    return G(
        Study,
        lab=lab,
        study_type=study_type,
        min_age_years=0,
        min_age_months=0,
        min_age_days=0,
        max_age_years=18,
        max_age_months=0,
        max_age_days=0,
        criteria_expression="",
    )


class IsTalliedSignalTestCase(TestCase):
    """Tests that post_save signals keep is_tallied in sync with compute_is_tallied()."""

    def setUp(self):
        self.child, lab = _make_eligible_setup()
        self.internal_study = _eligible_study(lab, StudyType.get_ember_frame_player())
        self.external_study = _eligible_study(lab, StudyType.get_external())

    def test_is_tallied_true_on_create_external_eligible(self):
        resp = G(
            Response,
            child=self.child,
            study=self.external_study,
            study_type=self.external_study.study_type,
            is_preview=False,
        )
        resp.refresh_from_db()
        self.assertTrue(resp.is_tallied)

    def test_is_tallied_false_on_create_external_preview(self):
        resp = G(
            Response,
            child=self.child,
            study=self.external_study,
            study_type=self.external_study.study_type,
            is_preview=True,
        )
        resp.refresh_from_db()
        self.assertFalse(resp.is_tallied)

    def test_is_tallied_false_on_create_internal_not_completed(self):
        resp = G(
            Response,
            child=self.child,
            study=self.internal_study,
            study_type=self.internal_study.study_type,
            is_preview=False,
            completed=False,
            completed_consent_frame=True,
        )
        resp.refresh_from_db()
        self.assertFalse(resp.is_tallied)

    def test_is_tallied_true_on_create_internal_complete_no_ruling(self):
        """Complete internal response with no ruling defaults to pending (not rejected) → tallied."""
        resp = G(
            Response,
            child=self.child,
            study=self.internal_study,
            study_type=self.internal_study.study_type,
            is_preview=False,
            completed=True,
            completed_consent_frame=True,
        )
        resp.refresh_from_db()
        self.assertTrue(resp.is_tallied)

    def test_is_tallied_updates_when_response_completed(self):
        """Saving a response with completed=True causes the signal to recompute is_tallied."""
        resp = G(
            Response,
            child=self.child,
            study=self.internal_study,
            study_type=self.internal_study.study_type,
            is_preview=False,
            completed=False,
            completed_consent_frame=True,
        )
        G(ConsentRuling, response=resp, action="accepted")
        resp.refresh_from_db()
        self.assertFalse(resp.is_tallied)

        resp.completed = True
        resp.save()
        resp.refresh_from_db()
        self.assertTrue(resp.is_tallied)

    def test_is_tallied_skips_recompute_when_update_fields_is_is_tallied(self):
        """Signal guard: when update_fields == {'is_tallied'}, no recompute is done."""
        resp = G(
            Response,
            child=self.child,
            study=self.internal_study,
            study_type=self.internal_study.study_type,
            is_preview=False,
            completed=True,
            completed_consent_frame=True,
        )
        resp.refresh_from_db()
        self.assertTrue(resp.is_tallied)

        # Artificially set is_tallied=False in DB without triggering the signal
        Response.objects.filter(pk=resp.pk).update(is_tallied=False)
        resp.refresh_from_db()
        self.assertFalse(resp.is_tallied)

        # Saving with update_fields={"is_tallied"} should skip recompute
        resp.save(update_fields={"is_tallied"})
        resp.refresh_from_db()
        # Still False — recompute was skipped, so the artificially set value persists
        self.assertFalse(resp.is_tallied)

    def test_is_tallied_set_false_when_rejection_ruling_created(self):
        resp = G(
            Response,
            child=self.child,
            study=self.internal_study,
            study_type=self.internal_study.study_type,
            is_preview=False,
            completed=True,
            completed_consent_frame=True,
        )
        resp.refresh_from_db()
        self.assertTrue(resp.is_tallied)  # no ruling = pending = not rejected

        G(ConsentRuling, response=resp, action="rejected")
        resp.refresh_from_db()
        self.assertFalse(resp.is_tallied)

    def test_is_tallied_true_when_accepted_ruling_created(self):
        resp = G(
            Response,
            child=self.child,
            study=self.internal_study,
            study_type=self.internal_study.study_type,
            is_preview=False,
            completed=True,
            completed_consent_frame=True,
        )
        G(ConsentRuling, response=resp, action="accepted")
        resp.refresh_from_db()
        self.assertTrue(resp.is_tallied)

    def test_is_tallied_updates_when_ruling_changed_to_accepted(self):
        """Updating a ConsentRuling action to accepted triggers recompute on the Response."""
        resp = G(
            Response,
            child=self.child,
            study=self.internal_study,
            study_type=self.internal_study.study_type,
            is_preview=False,
            completed=True,
            completed_consent_frame=True,
        )
        ruling = G(ConsentRuling, response=resp, action="rejected")
        resp.refresh_from_db()
        self.assertFalse(resp.is_tallied)

        ruling.action = "accepted"
        ruling.save()
        resp.refresh_from_db()
        self.assertTrue(resp.is_tallied)

    def test_is_tallied_updates_when_ruling_changed_to_rejected(self):
        """Updating a ConsentRuling action to rejected triggers recompute on the Response."""
        resp = G(
            Response,
            child=self.child,
            study=self.internal_study,
            study_type=self.internal_study.study_type,
            is_preview=False,
            completed=True,
            completed_consent_frame=True,
        )
        ruling = G(ConsentRuling, response=resp, action="accepted")
        resp.refresh_from_db()
        self.assertTrue(resp.is_tallied)

        ruling.action = "rejected"
        ruling.save()
        resp.refresh_from_db()
        self.assertFalse(resp.is_tallied)

    @patch("studies.models.send_mail")
    def test_response_save_pauses_active_study_when_tallied_count_reaches_max(
        self, mock_send_mail
    ):
        """Saving a response that changes is_tallied to True pauses the study when max_responses is reached."""
        self.internal_study.max_responses = 1
        self.internal_study.state = "active"
        self.internal_study.save()

        resp = G(
            Response,
            child=self.child,
            study=self.internal_study,
            study_type=self.internal_study.study_type,
            is_preview=False,
            completed=False,
            completed_consent_frame=True,
        )
        resp.refresh_from_db()
        self.assertFalse(resp.is_tallied)
        self.internal_study.refresh_from_db()
        self.assertEqual(self.internal_study.state, "active")

        resp.completed = True
        resp.save()
        resp.refresh_from_db()
        self.assertTrue(resp.is_tallied)
        self.internal_study.refresh_from_db()
        self.assertEqual(self.internal_study.state, "paused")

    @patch("studies.models.send_mail")
    def test_consent_ruling_accepted_pauses_active_study_when_tallied_count_reaches_max(
        self, mock_send_mail
    ):
        """Accepting consent for a previously-rejected response pauses the study when max_responses is reached."""
        # Use a high max_responses so creating the response doesn't pause the study yet
        self.internal_study.max_responses = 99
        self.internal_study.state = "active"
        self.internal_study.save()

        resp = G(
            Response,
            child=self.child,
            study=self.internal_study,
            study_type=self.internal_study.study_type,
            is_preview=False,
            completed=True,
            completed_consent_frame=True,
        )
        G(ConsentRuling, response=resp, action="rejected")
        resp.refresh_from_db()
        self.assertFalse(resp.is_tallied)

        # Now lower max_responses to 1 so that an accepted ruling will trigger a pause
        self.internal_study.max_responses = 1
        self.internal_study.save()
        self.internal_study.refresh_from_db()
        self.assertEqual(self.internal_study.state, "active")

        G(ConsentRuling, response=resp, action="accepted")
        resp.refresh_from_db()
        self.assertTrue(resp.is_tallied)
        self.internal_study.refresh_from_db()
        self.assertEqual(self.internal_study.state, "paused")

    def test_consent_ruling_accepted_does_not_pause_when_is_tallied_unchanged(self):
        """Creating an accepted ruling for an already-tallied response does not trigger pausing."""
        self.internal_study.max_responses = 2
        self.internal_study.state = "active"
        self.internal_study.save()

        # No ruling = pending (not rejected) → tallied for a complete response
        resp = G(
            Response,
            child=self.child,
            study=self.internal_study,
            study_type=self.internal_study.study_type,
            is_preview=False,
            completed=True,
            completed_consent_frame=True,
        )
        resp.refresh_from_db()
        self.assertTrue(resp.is_tallied)
        self.internal_study.refresh_from_db()
        self.assertEqual(
            self.internal_study.state, "active"
        )  # count is still 1, which is less than the max (2)

        # Accepted ruling: is_tallied stays True (old=True, new=True) → no check_and_pause call
        G(ConsentRuling, response=resp, action="accepted")
        resp.refresh_from_db()
        self.assertTrue(resp.is_tallied)
        self.internal_study.refresh_from_db()
        self.assertEqual(self.internal_study.state, "active")

    @patch("studies.models.send_mail")
    def test_study_stays_paused_after_consent_rejection_drops_below_max(
        self, mock_send_mail
    ):
        """Rejecting consent drops is_tallied to False; the study stays paused without auto-unpausing."""
        self.internal_study.max_responses = 1
        self.internal_study.state = "active"
        self.internal_study.save()

        resp = G(
            Response,
            child=self.child,
            study=self.internal_study,
            study_type=self.internal_study.study_type,
            is_preview=False,
            completed=True,
            completed_consent_frame=True,
        )
        resp.refresh_from_db()
        self.assertTrue(resp.is_tallied)
        self.internal_study.refresh_from_db()
        self.assertEqual(
            self.internal_study.state, "paused"
        )  # auto-paused (1 >= max=1)

        G(ConsentRuling, response=resp, action="rejected")
        resp.refresh_from_db()
        self.assertFalse(resp.is_tallied)
        self.internal_study.refresh_from_db()
        self.assertFalse(self.internal_study.has_reached_max_responses)
        self.assertEqual(
            self.internal_study.state, "paused"
        )  # Still paused, no auto-unpause


class EffectiveIsTalliedTestCase(TestCase):
    """Tests for the effective_is_tallied property and researcher override behavior."""

    def setUp(self):
        child, lab = _make_eligible_setup()
        internal_study = _eligible_study(lab, StudyType.get_ember_frame_player())

        self.tallied_response = G(
            Response,
            child=child,
            study=internal_study,
            study_type=internal_study.study_type,
            is_preview=False,
            completed=True,
            completed_consent_frame=True,
        )
        G(ConsentRuling, response=self.tallied_response, action="accepted")
        self.tallied_response.refresh_from_db()

        self.untallied_response = G(
            Response,
            child=child,
            study=internal_study,
            study_type=internal_study.study_type,
            is_preview=False,
            completed=False,
            completed_consent_frame=True,
        )
        self.untallied_response.refresh_from_db()

    def test_no_override_returns_system_true(self):
        self.assertIsNone(self.tallied_response.is_tallied_researcher_override)
        self.assertTrue(self.tallied_response.effective_is_tallied)

    def test_no_override_returns_system_false(self):
        self.assertIsNone(self.untallied_response.is_tallied_researcher_override)
        self.assertFalse(self.untallied_response.effective_is_tallied)

    def test_override_true_overrides_system_false(self):
        self.assertFalse(self.untallied_response.is_tallied)
        self.untallied_response.is_tallied_researcher_override = True
        self.assertTrue(self.untallied_response.effective_is_tallied)

    def test_override_false_overrides_system_true(self):
        self.assertTrue(self.tallied_response.is_tallied)
        self.tallied_response.is_tallied_researcher_override = False
        self.assertFalse(self.tallied_response.effective_is_tallied)

    def test_override_persists_after_save(self):
        """Researcher override is written to DB and survives a save/reload cycle."""
        self.untallied_response.is_tallied_researcher_override = True
        self.untallied_response.save()
        reloaded = Response.objects.get(pk=self.untallied_response.pk)
        self.assertTrue(reloaded.is_tallied_researcher_override)
        self.assertTrue(reloaded.effective_is_tallied)

    def test_override_cleared_to_none_restores_system_value(self):
        self.tallied_response.is_tallied_researcher_override = False
        self.assertFalse(self.tallied_response.effective_is_tallied)
        self.tallied_response.is_tallied_researcher_override = None
        self.assertTrue(self.tallied_response.effective_is_tallied)

    def test_override_can_be_toggled_multiple_times(self):
        for value in [True, False, True, False, None]:
            self.untallied_response.is_tallied_researcher_override = value
            expected = self.untallied_response.is_tallied if value is None else value
            self.assertEqual(self.untallied_response.effective_is_tallied, expected)
