from pprint import pprint

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django_dynamic_fixture import G

from accounts.models import Child, Message, User
from studies.models import Lab, Response, Study
from studies.tasks import (
    MessageTarget,
    _deserialized,
    _grouped_by_user,
    _segmented_by_study,
    _validated,
    potential_message_targets,
)

TARGET_EMAIL_TEMPLATE = """Dear Charlie,

We're writing to invite you and your children to participate in the study "The Most Fake Study Ever" that MIT is running on Lookit!

Who:
- Moe
- Curly

What happens: How fast can your child hand-compute integrals?

Why: We are interested in seeing how fast your child can hand-compute integrals.

Compensation: You child will receive exactly $1 for each integral computed.

You and your child can participate any time you want by going to "The Most Fake Study Ever" on Lookit ({base_url}/exp/studies/{study_id}/). If you have any questions, please reply to this email or contact the study PI.

We hope to see you soon, and thanks for contributing to the science of how kids learn and grow!

-- The Lookit team
"""


class TestAnnouncementEmailFunctionality(TestCase):

    maxDiff = 2000  # In case we need to check the email body contents

    def setUp(self):
        # TODO: the check_modification_of_approved_study signal will change the
        #     study state to "rejected" if certain fields are changed, including
        #     "image". This is annoying for tests - do we actually need that logic?
        self.fake_lab = G(Lab, name="MIT", contact_email="faker@fakelab.com")
        self.study_one = G(
            Study,
            image=SimpleUploadedFile(
                "fake_image.png", b"fake-stuff", content_type="image/png"
            ),  # we could also pass fill_nullable_fields=True
            criteria_expression="",
            public=True,
            built=True,
            lab=self.fake_lab,
        )
        self.study_one.state = "active"
        self.study_one.save()
        self.study_two = G(
            Study,
            name="The Most Fake Study Ever",
            image=SimpleUploadedFile(
                "fake_image.png", b"fake-stuff-2", content_type="image/png"
            ),  # we could also pass fill_nullable_fields=True
            criteria_expression="",
            public=True,
            built=True,
            lab=self.fake_lab,
            short_description="How fast can your child hand-compute integrals?",
            long_description="We are interested in seeing how fast your child can hand-compute integrals.",
            compensation_description="You child will receive exactly $1 for each integral computed.",
        )
        self.study_two.state = "active"
        self.study_two.save()

        self.participant_one = G(User, is_active=True)
        self.child_one = G(Child, given_name="Larry", user=self.participant_one)
        # Child one has a response that has reached the consent frame for each study
        self.responses_for_child_one = [
            G(
                Response,
                study=self.study_one,
                child=self.child_one,
                completed_consent_frame=True,
            ),
            G(
                Response,
                study=self.study_two,
                child=self.child_one,
                completed_consent_frame=True,
            ),
        ]

        self.participant_two = G(User, nickname="Charlie", is_active=True)
        self.child_two = G(Child, given_name="Moe", user=self.participant_two)
        # Child two has reached the consent frame for only study #1
        self.responses_for_child_two = [
            G(
                Response,
                study=self.study_one,
                child=self.child_two,
                completed_consent_frame=True,
            ),
            G(
                Response,
                study=self.study_two,
                child=self.child_two,
                completed_consent_frame=False,
            ),
        ]

        self.child_three = G(Child, given_name="Curly", user=self.participant_two)
        # Child three has only done study #1 and has not reached the consent frame yet
        self.responses_for_child_three = [
            G(
                Response,
                study=self.study_one,
                child=self.child_three,
                completed_consent_frame=False,
            ),
        ]

    def test_potential_message_targets(self):
        targets = list(potential_message_targets())
        # No targets for participant #1, since their kid completed consent frame for both studies
        self.assertFalse(any(mt.user_id == self.participant_one.id for mt in targets))

        # Participant #2
        # Child 2 should only receive a single message for study 2, since they completed
        #    the consent frame for study 1
        self.assertNotIn(
            MessageTarget(
                user_id=self.participant_two.id,
                child_id=self.child_two.id,
                study_id=self.study_one.id,
            ),
            targets,
        )
        self.assertIn(
            MessageTarget(
                user_id=self.participant_two.id,
                child_id=self.child_two.id,
                study_id=self.study_two.id,
            ),
            targets,
        )
        # Child 3 should receive a message for both studies.
        self.assertIn(
            MessageTarget(
                user_id=self.participant_two.id,
                child_id=self.child_three.id,
                study_id=self.study_one.id,
            ),
            targets,
        )
        self.assertIn(
            MessageTarget(
                user_id=self.participant_two.id,
                child_id=self.child_three.id,
                study_id=self.study_two.id,
            ),
            targets,
        )

        # Sanity check - participant #2 isn't suddenly the parent of child #1...
        self.assertFalse(
            any(
                mt.user_id == self.participant_two.id
                and mt.child_id == self.child_one.id
                for mt in targets
            )
        )
        # Check other way around as well
        self.assertFalse(
            any(
                mt.user_id == self.participant_one.id
                and mt.child_id in (self.child_two.id, self.child_three.id)
                for mt in targets
            )
        )

    def test_target_creation_e2e(self):
        targets = list(
            _segmented_by_study(
                _validated(_deserialized(_grouped_by_user(potential_message_targets())))
            )
        )

        self.assertEqual(len(targets), 1)

        user, study_child_mapping = targets[0]

        self.assertEqual(user, self.participant_two)

        self.assertDictEqual(
            study_child_mapping,
            {
                self.study_one: [self.child_three],
                self.study_two: [self.child_two, self.child_three],
            },
        )

    def test_correct_message_structure(self):
        target_email_structure = TARGET_EMAIL_TEMPLATE.format(
            base_url=settings.BASE_URL, study_id=self.study_two.id
        )

        message_object: Message = Message.send_announcement_email(
            self.participant_two, self.study_two, [self.child_two, self.child_three]
        )
        self.assertMultiLineEqual(message_object.body, target_email_structure)
        self.assertEqual(
            message_object.subject,
            "New study available on Lookit: The Most Fake Study Ever",
        )
        self.assertEqual(list(message_object.recipients.all()), [self.participant_two])
        self.assertEqual(
            list(message_object.children_of_interest.all()),
            [self.child_two, self.child_three],
        )
        self.assertEqual(message_object.related_study, self.study_two)
        self.assertIsNone(message_object.sender)

    def test_study_excluded_from_targets_after_message(self):
        Message.send_announcement_email(
            self.participant_two, self.study_one, [self.child_three]
        )
        # New targets should have only study two targets
        targets = list(
            _segmented_by_study(
                _validated(_deserialized(_grouped_by_user(potential_message_targets())))
            )
        )

        # First level is the same - it's the same user...
        self.assertEqual(len(targets), 1)
        user, study_child_mapping = targets[0]
        self.assertEqual(user, self.participant_two)

        # ... But no study one this time.
        self.assertDictEqual(
            study_child_mapping, {self.study_two: [self.child_two, self.child_three]},
        )
