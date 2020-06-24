from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import HttpResponseRedirect
from django.shortcuts import reverse
from django.utils.text import slugify
from django.views import generic

from accounts.models import Message, User
from accounts.utils import hash_id
from exp.views.mixins import SingleObjectParsimoniousQueryMixin
from studies.models import Study
from studies.permissions import StudyPermission


class StudyParticipantContactView(
    UserPassesTestMixin, SingleObjectParsimoniousQueryMixin, generic.DetailView
):
    """
    StudyParticipantContactView lets you contact study participants.
    """

    model = Study
    raise_exception = True
    template_name = "studies/study_participant_contact.html"

    def can_contact_participants(self):
        user = self.request.user
        study = self.get_object()
        return user.is_researcher and user.has_study_perms(
            StudyPermission.CONTACT_STUDY_PARTICIPANTS, study
        )

    test_func = can_contact_participants

    def participant_hash(self, participant):
        return hash_id(participant["uuid"], self.object.uuid, self.object.salt)

    def participant_slug(self, participant):
        return (
            self.participant_hash(participant)
            + "-"
            + slugify(participant["nickname"] or "anonymous")
        )

    def slug_from_user_object(self, user):
        study = self.object
        user_hash_id = hash_id(user.uuid, study.uuid, study.salt)
        user_slug = slugify(user.nickname or "anonymous")
        return f"{user_hash_id}-{user_slug}"

    def get_context_data(self, **kwargs):
        """Gets the required data for emailing participants."""
        ctx = super().get_context_data(**kwargs)
        study = ctx["study"]
        participants = (
            study.participants.order_by(
                "-email_next_session"
            )  # Just to get the grouping in the right order
            .all()
            .values(
                "email_next_session",
                "uuid",
                "username",
                "nickname",
                "password",
                "email_new_studies",
                "email_study_updates",
                "email_response_questions",
            )
        )
        for par in participants:
            par["hashed_id"] = self.participant_hash(par)
            par["slug"] = self.participant_slug(par)
        ctx["participants"] = participants

        previous_messages = (
            Message.objects.filter(related_study=self.object)
            .select_related("sender")
            .prefetch_related("recipients")
        )
        # Since we only need a few values for display/sorting, but they include both
        # properties of related fields and an annotated recipient list, just create
        # explicitly
        ctx["previous_messages"] = [
            {
                "sender": {
                    "uuid": message.sender.uuid,
                    "full_name": message.sender.get_full_name(),
                },
                "subject": message.subject,
                "recipients": [
                    {
                        "uuid": recipient.uuid,
                        "nickname": recipient.nickname,
                        "slug": self.slug_from_user_object(recipient),
                    }
                    for recipient in message.recipients.all()
                ],
                "date_created": message.date_created,
                "body": message.body,
            }
            for message in previous_messages
        ]

        ctx["researchers"] = self.get_researchers()
        return ctx

    def post(self, request, *args, **kwargs):
        """Handles saving message and sending email.

        TODO: enable mail merge with tokens.
        """
        study = self.get_object()

        # TODO: implement checks on these being in the list of study participants &
        # appropriate for this message type
        participant_uuids = request.POST.getlist("recipients")
        subject = request.POST["subject"]
        body = request.POST["body"]

        outgoing_message = Message.objects.create(
            sender=request.user, subject=subject, body=body, related_study=study
        )

        # TODO: Check into the performance of .iterator() with some real load testing
        outgoing_message.recipients.add(
            *User.objects.filter(uuid__in=participant_uuids).iterator()
        )

        outgoing_message.send_as_email()

        messages.success(self.request, f'Message "{subject}" sent!')
        return HttpResponseRedirect(
            reverse("exp:study-participant-contact", kwargs=dict(pk=study.pk))
        )

    def get_researchers(self):
        """Pulls researchers that can contact participants."""
        study = self.get_object()
        return study.users_with_study_perms(StudyPermission.CONTACT_STUDY_PARTICIPANTS)
