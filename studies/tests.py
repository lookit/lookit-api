from datetime import date, timedelta

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils.safestring import mark_safe
from django_dynamic_fixture import G
from guardian.shortcuts import assign_perm
from more_itertools import quantify

from accounts.models import Child, Message, User
from studies.helpers import send_mail
from studies.models import Lab, Response, Study, StudyType, StudyTypeEnum
from studies.permissions import StudyPermission
from studies.tasks import (
    MessageTarget,
    acquire_potential_announcement_email_targets,
    limit_email_targets,
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
            purpose="We are interested in seeing how fast your child can hand-compute integrals.",
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
            name="A Private study",
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

        # Immediately excluded child - deleted. Will not be included in targets.
        self.deleted_child = G(
            Child, given_name="Deletey", user=self.participant_one, deleted=True
        )

        # Eventually excluded children - too old, too young, and unable to participate in studies
        # due to specific existing conditions.

        self.older_child = G(
            Child,
            given_name="Billy",
            user=self.participant_one,
            birthday=four_years_ago,
        )

        self.younger_child = G(
            Child, given_name="Joe", user=self.participant_one, birthday=five_months_ago
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
            Child, given_name="Curly", user=self.participant_two, birthday=one_year_ago
        )
        # Child three has only done study #1 and has not reached the consent frame yet
        self.responses_for_child_three = [
            G(
                Response,
                study=self.study_one,
                child=self.child_three,
                completed_consent_frame=False,
            )
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

    def test_potential_message_targets(self):
        targets = list(potential_message_targets())
        # Two targets for participant 1: three children for both studies. These
        # will be weeded out downstream, as they all fail to meet criteria in one way
        # or another.
        self.assertEqual(
            quantify(mt.user_id == self.participant_one.id for mt in targets), 6
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

    def test_potential_message_targets_deleted_children(self):
        user = User(is_active=True)
        user.save()

        child = Child(user=user)
        child.save()

        self.assertTrue(
            any(m.child_id == child.id for m in potential_message_targets())
        )

        child.deleted = True
        child.save()

        self.assertFalse(
            any(m.child_id == child.id for m in potential_message_targets())
        )

    def test_target_creation_e2e(self):
        targets = list(acquire_potential_announcement_email_targets())

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

    def test_target_emails_limited_to_max_per_study(self):

        # Add a study with 5 eligible children (ages 10-12, no overlap with existing studies) in different families
        school_age_study = G(
            Study,
            name="A study for preschoolers",
            image=SimpleUploadedFile(
                "fake_image.png", b"fake-stuff", content_type="image/png"
            ),  # we could also pass fill_nullable_fields=True
            criteria_expression="",
            public=True,
            built=True,
            lab=self.fake_lab,
            min_age_years=10,
            min_age_months=0,
            min_age_days=0,
            max_age_years=12,
            max_age_months=0,
            max_age_days=0,
        )
        school_age_study.state = "active"
        school_age_study.save()
        eleven_years_ago = date.today() - timedelta(days=365 * 11)
        for i in range(5):
            G(Child, user=G(User, is_active=True), birthday=eleven_years_ago)

        # Limit to max of one family getting email per study
        targets = list(
            limit_email_targets(acquire_potential_announcement_email_targets(), 1)
        )
        # One email should be to participant 2 about either study 1 or study 2.
        # Another email should be to one of our new participants about preschool_study.
        self.assertEqual(len(targets), 2)
        target_studies = [target[1] for target in targets]
        self.assertIn(school_age_study, target_studies)
        self.assertTrue(
            self.study_one in target_studies or self.study_two in target_studies
        )

        # Limit to max of 3 families getting email per study
        targets = list(
            limit_email_targets(acquire_potential_announcement_email_targets(), 3)
        )
        # Should still be just one email to participant 2 about study 1 or 2, but also 3 emails about preschool_study
        self.assertEqual(len(targets), 4)
        target_studies = [target[1] for target in targets]
        self.assertEqual(target_studies.count(school_age_study), 3)
        self.assertTrue(
            self.study_one in target_studies or self.study_two in target_studies
        )

        # Limit to max of 6 families getting email per study
        targets = list(
            limit_email_targets(acquire_potential_announcement_email_targets(), 6)
        )
        # Should still be just one email to participant 2 about study 1 or 2, but also 5 emails about preschool_study
        self.assertEqual(len(targets), 6)
        target_studies = [target[1] for target in targets]
        self.assertEqual(target_studies.count(school_age_study), 5)
        self.assertTrue(
            self.study_one in target_studies or self.study_two in target_studies
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
        targets = list(acquire_potential_announcement_email_targets())

        # First level is the same - it's the same user...
        self.assertEqual(len(targets), 1)
        user, study_child_mapping = targets[0]
        self.assertEqual(user, self.participant_two)

        # ... But no study one this time.
        self.assertDictEqual(
            study_child_mapping, {self.study_two: [self.child_two, self.child_three]}
        )

    def test_announcement_email_to_child_with_long_name(self):
        # Family with a child with a long name
        long_name_family = G(User, nickname="Mama", is_active=True)
        long_name_child = G(
            Child,
            given_name="A" * 255,
            user=long_name_family,
            birthday=date.today() - timedelta(days=365),
        )
        short_name_child = G(
            Child,
            given_name="Joe",
            user=long_name_family,
            birthday=date.today() - timedelta(days=365),
        )

        message_object = Message.send_announcement_email(
            long_name_family, self.study_two, [long_name_child, short_name_child]
        )
        self.assertEqual(
            message_object.subject,
            'Your children are invited to take part in "The Most Fake Study Ever" on Lookit!',
        )

    def test_announcement_email_about_study_with_long_name(self):
        # Study with a long name
        long_name_study = G(
            Study,
            name="A" * 255,
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
            purpose="We are interested in seeing how fast your child can hand-compute integrals.",
            compensation_description="You child will receive exactly $1 for each integral computed.",
        )
        long_name_study.state = "active"
        long_name_study.save()
        message_object = Message.send_announcement_email(
            self.participant_two, long_name_study, [self.child_two]
        )
        self.assertEqual(
            message_object.subject,
            "Your child is invited to take part in a new study on Lookit!",
        )


class TestSendMail(TestCase):
    def test_send_email_with_image(self):
        email = send_mail(
            "custom_email",
            "Test email",
            ["lookit-test-email@mit.edu"],
            bcc=[],
            from_email="lookit-bot@mit.edu",
            base_url="https://lookit-staging.mit.edu/",
            custom_message=mark_safe(
                '<p>line 1<br></p><p><img style="width: 24px;" src="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAASABIAAD/4QCURXhpZgAATU0AKgAAAAgABQESAAMAAAABAAEAAAEaAAUAAAABAAAASgEbAAUAAAABAAAAUgExAAIAAAAHAAAAWodpAAQAAAABAAAAYgAAAAAAAABIAAAAAQAAAEgAAAABUGljYXNhAAAAA6ABAAMAAAABAAEAAKACAAQAAAABAAAAGKADAAQAAAABAAAAEAAAAAD/7QA4UGhvdG9zaG9wIDMuMAA4QklNBAQAAAAAAAA4QklNBCUAAAAAABDUHYzZjwCyBOmACZjs+EJ+/8AAEQgAEAAYAwERAAIRAQMRAf/EAB8AAAEFAQEBAQEBAAAAAAAAAAABAgMEBQYHCAkKC//EALUQAAIBAwMCBAMFBQQEAAABfQECAwAEEQUSITFBBhNRYQcicRQygZGhCCNCscEVUtHwJDNicoIJChYXGBkaJSYnKCkqNDU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6g4SFhoeIiYqSk5SVlpeYmZqio6Slpqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2drh4uPk5ebn6Onq8fLz9PX29/j5+v/EAB8BAAMBAQEBAQEBAQEAAAAAAAABAgMEBQYHCAkKC//EALURAAIBAgQEAwQHBQQEAAECdwABAgMRBAUhMQYSQVEHYXETIjKBCBRCkaGxwQkjM1LwFWJy0QoWJDThJfEXGBkaJicoKSo1Njc4OTpDREVGR0hJSlNUVVZXWFlaY2RlZmdoaWpzdHV2d3h5eoKDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uLj5OXm5+jp6vLz9PX29/j5+v/bAEMACAYGCAoKCAgICAkICAkICQgICQkIDQgIBwkdGh8eHRocHCAkLicgIiwjHBwoNyksMDE0NDQfJzk9ODI8LjM0Mv/bAEMBCQkJDQoNFQ0NFTIhECEyMjIyMjIyMjInJzIyJiYnJycmMiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJv/dAAQAA//aAAwDAQACEQMRAD8AyvBEcEer2e6B5QNzK6hmUcHj09+avELTQ5sHZ6vf/gHsN/qejR3tjo7eU93qFs7QKjM2GwSpyOMHa35VnpojsVOTi59EeKeK7e5jv7+WFGeJpFR2iy56DOQPp+laU6kF7r3PPxeGqz96Pws//9Cj4RlJaWG0jjf/AEVRJdzv8iuc8HHIODWE60VNOb0+83hhn7K1Na+el2/8jQX+0ZLe3jh1Ww/tC0tLm2nkE7TeUN3yZOBtYAHjHrVzrUpJuK1/LyN6OFxFHldZe7p/296HC3muXf2nZ9nignKyM08nmzSGXJyQCcEcn25p+zjZSvc5p1pzm4yja2i9Ef/Z" data-filename="small.jpg"></p><p>line 2<br></p>'
            ),
        )
        self.assertEqual(email.subject, "Test email")
        self.assertEqual(email.to, ["lookit-test-email@mit.edu"])
        self.assertTrue(
            email.body.startswith(
                "line 1[IMAGE]line 2\n\nUpdate your email preferences here"
            ),
            "Email plain text does not have expected substitution of [IMAGE] for image tag",
        )
        self.assertEqual(
            len(email.attachments), 1, "Email does not have one attachment"
        )
        self.assertEqual(
            len(email.alternatives), 1, "Email does not have one HTML alternative"
        )
        self.assertEqual(
            email.alternatives[0],
            (
                '\n<p>line 1<br></p><p><img style="width: 24px;" src="cid:image-00001" data-filename="small.jpg"></p><p>line 2<br></p>\n\n\n<br>\n\n<a href="https://localhost:8000/account/email/"> Update your email preferences </a>\n',
                "text/html",
            ),
        )
        self.assertTrue(
            email.attachments[0]._payload.startswith(
                "/9j/4AAQSkZJRgABAQAASABIAAD/4QCURXhpZgAATU0AKgAAAAgABQESAAMAAAABAAEAAAEaAAUA"
            )
        )
        self.assertListEqual(
            email.attachments[0]._headers,
            [
                ("Content-Type", "image/jpeg"),
                ("MIME-Version", "1.0"),
                ("Content-Transfer-Encoding", "base64"),
                ("Content-ID", "image-00001"),
                ("Content-Disposition", "inline"),
                ("Filename", "image-00001.jpeg"),
            ],
            "Email image attachment does not have expected headers",
        )

    def test_empty_reply_to(self):
        reply_to = []
        email = send_mail(
            template_name="empty", subject="subject", to_addresses="to_addresses"
        )
        self.assertEquals(email.reply_to, reply_to)

    def test_one_reply_to(self):
        reply_to = ["email@mit.edu"]
        email = send_mail(
            template_name="empty",
            subject="subject",
            to_addresses="to_addresses",
            reply_to=reply_to,
        )
        self.assertEquals(email.reply_to, reply_to)

    def test_couple_reply_to(self):
        reply_to = ["email@mit.edu", "email@smith.edu"]
        email = send_mail(
            template_name="empty",
            subject="subject",
            to_addresses="to_addresses",
            reply_to=reply_to,
        )
        self.assertEquals(email.reply_to, reply_to)


class StudyTypeModelTestCase(TestCase):
    def test_default_pk(self):
        study_type = StudyType.objects.get(name=StudyTypeEnum.ember_frame_player.value)
        self.assertEqual(study_type.pk, StudyType.default_pk())

    def test_identify_study_type(self):
        self.assertTrue(
            StudyType.objects.get(
                name=StudyTypeEnum.ember_frame_player.value
            ).is_ember_frame_player
        )
        self.assertTrue(
            StudyType.objects.get(name=StudyTypeEnum.external.value).is_external
        )

    def test_get_ember_frame_player(self):
        self.assertTrue(StudyType.get_ember_frame_player().is_ember_frame_player)

    def test_get_external(self):
        self.assertTrue(StudyType.get_external().is_external)


class StudyModelTestCase(TestCase):
    def test_responses_for_researcher_external_studies(self):
        study = Study.objects.create(
            study_type=StudyType.get_external(),
        )
        user = User.objects.create(is_active=True, is_researcher=True)
        child = Child.objects.create(user=user)
        response = Response.objects.create(
            study=study,
            child=child,
            study_type=study.study_type,
            demographic_snapshot=user.latest_demographics,
        )

        self.assertNotIn(response, study.responses_for_researcher(user))

        assign_perm(StudyPermission.READ_STUDY_RESPONSE_DATA.codename, user, study)

        self.assertIn(response, study.responses_for_researcher(user))


class ExternalEmailTestCase(TestCase):
    def test_potential_message_targets_external(self):
        user = G(User, is_active=True)
        child = G(
            Child,
            user=user,
            birthday=date.today() - timedelta(days=365),
        )
        study = G(
            Study,
            name="External Study",
            study_type=StudyType.get_external(),
            image=SimpleUploadedFile("fake_image.png", b"", content_type="image/png"),
            public=True,
            max_age_years=2,
            criteria_expression="",
        )
        study.state = "active"
        study.save()

        message_target = MessageTarget(
            user_id=user.pk,
            child_id=child.pk,
            study_id=study.pk,
        )

        # Double check this is an external study
        self.assertTrue(study.study_type.is_external)

        # Check that user/child are potential message targets in new external study
        self.assertIn(message_target, potential_message_targets())

        # Add response from this child for this study
        G(
            Response,
            study=study,
            study_type=study.study_type,
            child=child,
        )

        # Check that the message target no longer has this child for this study
        self.assertNotIn(message_target, potential_message_targets())
