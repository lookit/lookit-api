from datetime import date, timedelta

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django_dynamic_fixture import G
from more_itertools import quantify

from accounts.models import Child, Message, User
from studies.models import Lab, Response, Study
from studies.tasks import (
    MessageTarget,
    acquire_announcement_email_targets,
    potential_message_targets,
)

TARGET_EMAIL_TEMPLATE = """Dear Charlie,

We're writing to invite you and your children Moe and Curly to participate in the study "The Most Fake Study Ever" on Lookit! This study is run by the ECCL at MIT.

More details about the study...

Who: Children who have stopped believing in Santa in the past 6 months.

What happens: How fast can your child hand-compute integrals?

Why: We are interested in seeing how fast your child can hand-compute integrals.

Compensation: You child will receive exactly $1 for each integral computed.

You and your child can participate any time you want by going to "The Most Fake Study Ever" on Lookit ({base_url}/studies/{study_uuid}/). If you have any questions, please reply to this email to reach the ECCL at faker@fakelab.com.

Thanks for contributing to the science of how kids learn - we hope to see you soon!

-- the Lookit team
"""


class TestAnnouncementEmailFunctionality(TestCase):

    maxDiff = 2000  # In case we need to check the email body contents

    def setUp(self):
        # TODO: the check_modification_of_approved_study signal will change the
        #     study state to "rejected" if certain fields are changed, including
        #     "image". This is annoying for tests - do we actually need that logic?

        five_months_ago = date.today() - timedelta(days=30 * 5)
        one_year_ago = date.today() - timedelta(days=365)
        four_years_ago = date.today() - timedelta(days=365 * 4)

        self.fake_lab = G(
            Lab, name="ECCL", institution="MIT", contact_email="faker@fakelab.com"
        )
        self.study_one = G(
            Study,
            name="A Study that should never show up",
            image=SimpleUploadedFile(
                "fake_image.png", b"fake-stuff", content_type="image/png"
            ),  # we could also pass fill_nullable_fields=True
            criteria_expression="NOT dyslexia",
            public=True,
            built=True,
            lab=self.fake_lab,
            # Age range between 11 months and 2 years - born a year ago should be fine.
            min_age_years=0,
            min_age_months=11,
            min_age_days=0,
            max_age_years=2,
            max_age_months=0,
            max_age_days=0,
        )
        self.study_one.state = "active"
        self.study_one.save()
        self.study_two = G(
            Study,
            name="The Most Fake Study Ever",
            image=SimpleUploadedFile(
                "fake_image.png", b"fake-stuff-2", content_type="image/png"
            ),  # we could also pass fill_nullable_fields=True
            criteria_expression="NOT hearing_impairment",
            criteria="Children who have stopped believing in Santa in the past 6 months.",
            public=True,
            built=True,
            lab=self.fake_lab,
            # Age range between 11 months and 2 years - born a year ago should be fine.
            min_age_years=0,
            min_age_months=11,
            min_age_days=0,
            max_age_years=2,
            max_age_months=0,
            max_age_days=0,
            short_description="How fast can your child hand-compute integrals?",
            long_description="We are interested in seeing how fast your child can hand-compute integrals.",
            compensation_description="You child will receive exactly $1 for each integral computed.",
        )
        self.study_two.state = "active"
        self.study_two.save()

        # Study three is public, but paused
        self.study_three = G(
            Study,
            name="A Paused study",
            image=SimpleUploadedFile(
                "fake_image.png", b"fake-stuff", content_type="image/png"
            ),  # we could also pass fill_nullable_fields=True
            criteria_expression="",
            public=True,
            built=True,
            lab=self.fake_lab,
            # Age range between 11 months and 2 years - born a year ago should be fine.
            min_age_years=0,
            min_age_months=11,
            min_age_days=0,
            max_age_years=2,
            max_age_months=0,
            max_age_days=0,
        )
        self.study_three.state = "paused"
        self.study_three.save()

        # Study four is active, but not public
        self.study_four = G(
            Study,
            name="A Paused study",
            image=SimpleUploadedFile(
                "fake_image.png", b"fake-stuff", content_type="image/png"
            ),  # we could also pass fill_nullable_fields=True
            criteria_expression="",
            public=False,
            built=True,
            lab=self.fake_lab,
            # Age range between 11 months and 2 years - born a year ago should be fine.
            min_age_years=0,
            min_age_months=11,
            min_age_days=0,
            max_age_years=2,
            max_age_months=0,
            max_age_days=0,
        )
        self.study_four.state = "active"
        self.study_four.save()

        self.participant_one = G(User, is_active=True)
        self.child_one = G(
            Child, given_name="Larry", user=self.participant_one, birthday=one_year_ago
        )
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

        # (Eventually) excluded children - too old, too young, and unable to participate in studies
        # due to specific existing conditions.

        self.older_child = G(
            Child,
            given_name="Billy",
            user=self.participant_one,
            birthday=four_years_ago,
        )

        self.younger_child = G(
            Child,
            given_name="Joe",
            user=self.participant_one,
            birthday=five_months_ago,
        )

        self.disabled_child = G(
            Child,
            given_name="Bob",
            user=self.participant_one,
            birthday=one_year_ago,
            existing_conditions=int(
                Child.existing_conditions.hearing_impairment
                | Child.existing_conditions.dyslexia
            ),
        )

        # Older child with responses that would otherwise be eligible
        self.responses_for_older_child = [
            G(
                Response,
                study=self.study_one,
                child=self.older_child,
                completed_consent_frame=False,
            ),
            G(
                Response,
                study=self.study_two,
                child=self.older_child,
                completed_consent_frame=False,
            ),
        ]

        self.participant_two = G(User, nickname="Charlie", is_active=True)
        self.child_two = G(
            Child, given_name="Moe", user=self.participant_two, birthday=one_year_ago
        )
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

        self.child_three = G(
            Child, given_name="Curly", user=self.participant_two, birthday=one_year_ago,
        )
        # Child three has only done study #1 and has not reached the consent frame yet
        self.responses_for_child_three = [
            G(
                Response,
                study=self.study_one,
                child=self.child_three,
                completed_consent_frame=False,
            ),
        ]

        # Spongebob don't want none of yo emails ಠ_ಠ
        self.participant_three = G(
            User, nickname="Spongebob", is_active=True, email_new_studies=False
        )
        self.child_four = G(
            Child,
            given_name="Patrick",
            user=self.participant_three,
            birthday=one_year_ago,
        )
        # Child four would get notified for all studies, but doesn't because of user settings.

        # Add a single child with a long name to the database; not eligible for any studies
        G(
            Child,
            given_name="sixteencharacter" * 16,
            user=self.participant_one,
            birthday=date.today() + timedelta(days=365),
        )

    def test_potential_message_targets(self):
        targets = list(potential_message_targets())
        # Two targets for participant 1: three children for both studies. These
        # will be weeded out downstream, as they all fail to meet criteria in one way
        # or another.
        self.assertEqual(
            quantify(mt.user_id == self.participant_one.id for mt in targets), 6,
        )

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
        targets = list(acquire_announcement_email_targets())

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
            base_url=settings.BASE_URL, study_uuid=self.study_two.uuid
        )

        message_object: Message = Message.send_announcement_email(
            self.participant_two, self.study_two, [self.child_two, self.child_three]
        )
        self.assertMultiLineEqual(message_object.body, target_email_structure)
        self.assertEqual(
            message_object.subject,
            'Moe and Curly are invited to take part in "The Most Fake Study Ever" on Lookit!',
        )
        self.assertEqual(list(message_object.recipients.all()), [self.participant_two])
        self.assertEqual(
            list(message_object.children_of_interest.all()),
            [self.child_two, self.child_three],
        )
        self.assertEqual(message_object.related_study, self.study_two)
        self.assertIsNone(message_object.sender)

        # Test that the subject line changes with only one kid
        message_object: Message = Message.send_announcement_email(
            self.participant_two, self.study_two, [self.child_two]
        )
        self.assertEqual(
            message_object.subject,
            'Moe is invited to take part in "The Most Fake Study Ever" on Lookit!',
        )

        # Test proper formatting of child list in case of >2 kids
        message_object: Message = Message.send_announcement_email(
            self.participant_two,
            self.study_two,
            [self.child_one, self.child_two, self.child_three],
        )
        self.assertEqual(
            message_object.subject,
            'Larry, Moe, and Curly are invited to take part in "The Most Fake Study Ever" on Lookit!',
        )

    def test_study_excluded_from_targets_after_message(self):
        Message.send_announcement_email(
            self.participant_two, self.study_one, [self.child_three]
        )
        # New targets should have only study two targets
        targets = list(acquire_announcement_email_targets())

        # First level is the same - it's the same user...
        self.assertEqual(len(targets), 1)
        user, study_child_mapping = targets[0]
        self.assertEqual(user, self.participant_two)

        # ... But no study one this time.
        self.assertDictEqual(
            study_child_mapping, {self.study_two: [self.child_two, self.child_three]},
        )

    def test_announcement_email_to_child_with_long_name(self):
        # Family with a child with a long name
        long_name_family = G(User, nickname="Mama", is_active=True)
        long_name_child = G(
            Child,
            given_name="sixteencharacter" * 16,
            user=long_name_family,
            birthday=date.today() - timedelta(days=365),
        )
        short_name_child = G(
            Child,
            given_name="Bob",
            user=long_name_family,
            birthday=date.today() - timedelta(days=365),
        )

        message_object = Message.send_announcement_email(
            long_name_family, self.study_one, [long_name_child, short_name_child],
        )
        self.assertEqual(
            message_object.subject,
            'Your children are invited to take part in "The Most Fake Study Ever" on Lookit!',
        )

    def test_announcement_email_about_study_with_long_name(self):
        # Study with a long name
        long_name_study = G(
            Study,
            name="A long study name " * 16,
            image=SimpleUploadedFile(
                "fake_image.png", b"fake-stuff-2", content_type="image/png"
            ),
            criteria_expression="",
            criteria="for toddlers",
            public=True,
            built=True,
            lab=self.fake_lab,
            # Age range between 11 months and 2 years - born a year ago should be fine.
            min_age_years=0,
            min_age_months=11,
            min_age_days=0,
            max_age_years=2,
            max_age_months=0,
            max_age_days=0,
            short_description="How fast can your child hand-compute integrals?",
            long_description="We are interested in seeing how fast your child can hand-compute integrals.",
            compensation_description="You child will receive exactly $1 for each integral computed.",
        )
        long_name_study.state = "active"
        long_name_study.save()
        message_object = Message.send_announcement_email(
            self.participant_two, long_name_study, [self.child_two]
        )
        self.assertEqual(
            message_object.subject,
            "Bob is invited to take part in a new study on Lookit!",
        )
