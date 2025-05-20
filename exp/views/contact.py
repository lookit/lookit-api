from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.forms import ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import reverse
from django.utils.text import slugify
from django.views import generic

from accounts.models import Message, User
from accounts.utils import hash_id
from exp.views.mixins import ResearcherLoginRequiredMixin, SingleObjectFetchProtocol
from studies import forms
from studies.models import Study
from studies.permissions import StudyPermission


class StudyParticipantContactView(
    ResearcherLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectFetchProtocol[Study],
    generic.DetailView,
    generic.FormView,
):
    """
    StudyParticipantContactView lets you contact study participants.
    """

    model = Study
    raise_exception = True
    template_name = "studies/study_participant_contact.html"
    form_class = forms.EmailParticipantsForm

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
                    "uuid": message.sender.uuid if message.sender else None,
                    "full_name": (
                        message.sender.get_full_name() if message.sender else "<None>"
                    ),
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

        # Populate options for 'sender' filter with existing senders' uuid & full name.
        # These may not line up with researchers who currently have perms to send email (e.g.,
        # when emails have been sent by an RA who has since left the lab), and in some cases
        # a sender may be null because the account has been deleted or because the message was sent
        # automatically by Lookit.

        sender_ids = previous_messages.values_list("sender", flat=True)
        senders = User.objects.filter(id__in=sender_ids).order_by("family_name")
        ctx["senders"] = (
            [
                {"uuid": sender.uuid, "full_name": sender.get_full_name}
                for sender in senders
            ]
            + [{"uuid": None, "full_name": "None"}]
            if None in sender_ids
            else []
        )

        return ctx

    def get_form(self, form_class=None):
        if form_class is None:
            form_class = self.get_form_class()

        study = self.object
        participants = (
            study.participants.order_by(
                "-email_next_session"
            )  # Just to get the grouping in the right order
            .all()
            .values(
                "nickname",
                "email_next_session",
                "uuid",
                "email_new_studies",
                "email_study_updates",
                "email_response_questions",
            )
        )

        # Populate the "choices" attribute for the SelectMultiple widget used for the "Recipients" form field.
        # Each choice must be a (value, label) tuple for the option element.
        # The data attributes are stored separately and used by the EmailRecipientSelectMultiple class to set the choice-specific data attributes that will be passed into the template.
        choices = []
        data_attrs = {}
        for p in participants:
            uuid_str = str(p["uuid"])
            p["slug"] = self.participant_slug(p)
            choices.append((uuid_str, p["slug"]))
            # The data attributes keys need to match the values expected by the JavaScript: no "email" prefix and hyphen as word separator
            data_attrs[uuid_str] = {
                "hashed-id": self.participant_hash(p),
                "slug": p["slug"],
                "next-session": p["email_next_session"],
                "new-studies": p["email_new_studies"],
                "study-updates": p["email_study_updates"],
                "response-questions": p["email_response_questions"],
                "transactional-message": True,
            }

        # Instantiate the form with the email dynamic recipients list and option-specific data attributes
        return form_class(
            **self.get_form_kwargs(),
            data_attrs=data_attrs,
            choices=choices,
        )

    def get_initial(self):
        initial = super().get_initial()
        recipient = self.request.GET.get("recipient", "")

        initial.update({"recipients": [recipient]})

        return initial

    def post(self, request, *args, **kwargs):
        """Handles saving message and sending email.

        TODO: enable mail merge with tokens.
        """
        study = self.get_object()

        # TODO: consider modeling message type and checking recipients have opted in
        participant_uuids = request.POST.getlist("recipients")
        subject = request.POST["subject"]
        body = request.POST["body"]

        outgoing_message = Message.objects.create(
            sender=request.user, subject=subject, body=body, related_study=study
        )

        # TODO: Check into the performance of .iterator() with some real load testing
        # Limit recipients to this study's participants
        outgoing_message.recipients.add(
            *study.participants.filter(uuid__in=participant_uuids).iterator()
        )

        outgoing_message.send_as_email()

        messages.success(self.request, f'Message "{subject}" sent!')
        return HttpResponseRedirect(
            reverse("exp:study-participant-contact", kwargs=dict(pk=study.pk))
        )

    def get(self, request, *args, **kwargs):
        recipient_uuid = request.GET.get("recipient")

        try:
            user = User.objects.get(uuid=recipient_uuid)

            if not user.email_response_questions:
                messages.warning(
                    request,
                    f"""User "{user.nickname or user.username}" has opted out of 
                    these types of emails.  If you wish to send another type of 
                    email, update the selection in the Recipients Filter and 
                    re-select the family ID.""",
                )
        except (ValidationError, User.DoesNotExist):
            pass

        return super().get(request, *args, **kwargs)
