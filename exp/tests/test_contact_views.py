import datetime
from unittest.mock import patch

from django.contrib.sites.models import Site
from django.test import Client, TestCase
from django.urls import reverse
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm

from accounts.backends import TWO_FACTOR_AUTH_SESSION_KEY
from accounts.models import Child, Message, User
from studies.models import Lab, Response, Study, StudyType
from studies.permissions import StudyPermission


class Force2FAClient(Client):
    @property
    def session(self):
        _session = super().session
        _session[TWO_FACTOR_AUTH_SESSION_KEY] = True
        return _session


class ContactViewTestCase(TestCase):
    def setUp(self):
        self.client = Force2FAClient()

        # Create researcher who will have permission to contact participants
        self.researcher_with_perm = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 2"
        )

        # Create researcher without permission to contact participants
        self.researcher_without_perm = G(
            User, is_active=True, is_researcher=True, given_name="Researcher 2"
        )

        # Create main study
        self.lab = G(Lab, name="MIT")
        self.study = G(
            Study,
            creator=self.researcher_without_perm,
            name="Main Study",
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )

        # Create one other study to ensure participants in this study aren't also included for contact
        self.other_study = G(
            Study,
            creator=self.researcher_without_perm,
            name="Other Study",
            lab=self.lab,
            study_type=StudyType.get_ember_frame_player(),
        )

        # Assign permissions
        assign_perm(
            StudyPermission.CONTACT_STUDY_PARTICIPANTS.prefixed_codename,
            self.researcher_with_perm,
            self.study,
        )
        self.study.analysis_group.user_set.add(self.researcher_without_perm)

        # Create participants
        n_participants = 5
        self.participants = [
            G(User, is_active=True, nickname=f"Mommy{i}theGreat")
            for i in range(n_participants)
        ]

        # Create one child per participant
        self.children = [
            G(
                Child,
                user=self.participants[i],
                given_name=f"Childof{i}",
                birthday=datetime.date.today() - datetime.timedelta(365),
            )
            for i in range(n_participants)
        ]

        # Create responses to study with completed consent frame for first 3 children
        # Note NO responses have consent confirmed - we do want to be able to contact participants prior to confirming consent
        [
            G(
                Response,
                child=self.children[i],
                study=self.study,
                completed=False,
                completed_consent_frame=True,
            )
            for i in range(3)
        ]

        # Create one response without completed consent frame (participant 3) - should also be able to contact this one
        G(
            Response,
            child=self.children[3],
            study=self.study,
            completed=False,
            completed_consent_frame=False,
        )

        # Create one responses to other study (participant 4)
        G(
            Response,
            child=self.children[4],
            study=self.other_study,
            completed=False,
            completed_consent_frame=True,
        )

        # Create some existing messages to participant 0

        # One announcement message - no sender
        self.announcement_message = G(
            Message,
            sender=None,
            subject="New study announcement",
            related_study=self.study,
        )
        self.announcement_message.recipients.add(self.participants[0])
        self.announcement_message.children_of_interest.add(self.children[0])

        # Messages from researchers
        n_senders = 5
        self.senders = [
            G(User, is_active=True, is_researcher=True, given_name=f"Researcher{i}")
            for i in range(n_senders)
        ]

        # Messages about this study - should see these messages and see senders 0, 1, 2 (3 is deleted)
        for i_message in range(4):
            message = G(
                Message,
                sender=self.senders[i_message],
                subject=f"Question {i_message} about your response",
                related_study=self.study,
            )
            message.recipients.add(self.participants[0])

        # Remove one of these researchers
        self.senders[3].delete()

        # Message about other study - should not see this or sender 4.
        message = G(
            Message,
            sender=self.senders[4],
            subject=f"Question 4 about your response",
            related_study=self.other_study,
        )
        message.recipients.add(self.participants[0])

        self.contact_url = reverse(
            "exp:study-participant-contact", kwargs={"pk": self.study.pk}
        )

        # Site fixture enabling login
        self.fake_site = G(Site, id=1)

    def test_cannot_get_contact_view_unauthenticated(self):
        response = self.client.get(self.contact_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1], (reverse("login"), 302))

    def test_cannot_get_contact_view_as_participant(self):
        self.client.force_login(self.participants[0])
        response = self.client.get(self.contact_url)
        self.assertEqual(
            response.status_code,
            403,
            "Participant not forbidden to access contact view",
        )

    def test_cannot_get_contact_view_without_perm(self):
        self.client.force_login(self.researcher_without_perm)
        response = self.client.get(self.contact_url)
        self.assertEqual(
            response.status_code,
            403,
            "Researcher without perm not forbidden to access contact view",
        )

    def test_can_get_contact_view_with_perm(self):
        self.client.force_login(self.researcher_with_perm)
        response = self.client.get(self.contact_url)
        self.assertEqual(
            response.status_code,
            200,
            "Researcher with perm not able to access contact view",
        )

    def test_appropriate_participants_available_to_contact(self):
        self.client.force_login(self.researcher_with_perm)
        response = self.client.get(self.contact_url)
        participant_names = {
            part["nickname"] for part in response.context["participants"]
        }
        expected_participant_names = {part.nickname for part in self.participants[0:4]}
        self.assertEqual(participant_names, expected_participant_names)

    def test_appropriate_senders_available_to_filter(self):
        self.client.force_login(self.researcher_with_perm)
        response = self.client.get(self.contact_url)
        sender_uuids = {sender["uuid"] for sender in response.context["senders"]}
        expected_sender_uuids = {sender.uuid for sender in self.senders[0:3]}
        expected_sender_uuids.add(
            None
        )  # Include None because we have a deleted sender & an announcement email
        self.assertEqual(sender_uuids, expected_sender_uuids)

    def test_appropriate_previous_messages_available(self):
        self.client.force_login(self.researcher_with_perm)
        response = self.client.get(self.contact_url)
        message_subjects = {
            message["subject"] for message in response.context["previous_messages"]
        }
        expected_message_subjects = {
            f"Question {i} about your response" for i in range(4)
        }.union({"New study announcement"})
        self.assertEqual(message_subjects, expected_message_subjects)
        content = response.content.decode("utf-8")

        for message_subject in expected_message_subjects:
            self.assertIn(message_subject, content)
        self.assertNotIn("Question 4 about your response", content)

        for sender_id in range(3):
            self.assertIn(
                f"Researcher{sender_id}",
                content,
                "Previous sender's name missing from rendered contact view",
            )
        self.assertNotIn(
            "Researcher3", content, "Deleted researcher's name in rendered contact view"
        )
        self.assertNotIn(
            "Researcher4", content, "Extra researcher's name in rendered contact view"
        )

    @patch("studies.helpers.send_mail.delay")
    def test_can_post_message_to_participants(self, mock_send_mail):
        self.client.force_login(self.researcher_with_perm)
        response = self.client.post(
            self.contact_url,
            {
                "subject": "test email",
                "body": "some content",
                "recipients": [p.uuid for p in self.participants[0:3]],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        # Ensure message sent to participants 0, 1, 2
        mock_send_mail.assert_called_once()
        self.assertEqual(
            mock_send_mail.call_args.args,
            ("custom_email", "test email", ["lookit.robot@some.domain"]),
        )
        self.assertEqual(
            mock_send_mail.call_args.kwargs["bcc"],
            [p.username for p in self.participants[0:3]],
        )
        self.assertEqual(
            mock_send_mail.call_args.kwargs["from_email"], self.study.lab.contact_email
        )

        # And that appropriate message object created
        self.assertTrue(Message.objects.filter(subject="test email").exists())
        new_message = Message.objects.get(subject="test email")
        self.assertEqual(new_message.body, "some content")
        self.assertEqual(
            {participant for participant in new_message.recipients.all()},
            set(self.participants[0:3]),
        )

    @patch("studies.helpers.send_mail.delay")
    def test_message_not_posted_to_non_participant(self, mock_send_mail):
        self.client.force_login(self.researcher_with_perm)
        response = self.client.post(
            self.contact_url,
            {
                "subject": "test email",
                "body": "some content",
                "recipients": [p.uuid for p in self.participants[3:5]],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        # Ensure message sent only to participant 3, not participant 4 (who did not participate in this study)
        mock_send_mail.assert_called_once()
        self.assertEqual(
            mock_send_mail.call_args.args,
            ("custom_email", "test email", [self.participants[3].username]),
        )
        self.assertEqual(mock_send_mail.call_args.kwargs["bcc"], [])
        self.assertEqual(
            mock_send_mail.call_args.kwargs["from_email"], self.study.lab.contact_email
        )

        # And that appropriate message object created
        self.assertTrue(Message.objects.filter(subject="test email").exists())
        new_message = Message.objects.get(subject="test email")
        self.assertEqual(
            {participant for participant in new_message.recipients.all()},
            {self.participants[3]},
        )
