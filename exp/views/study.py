import datetime
import json
import operator
from collections import Counter, defaultdict
from functools import reduce
from typing import NamedTuple
import csv
import io
import zipfile

from django.contrib import messages
from django.contrib.auth.mixins import (
    PermissionRequiredMixin as DjangoPermissionRequiredMixin,
)
from django.core.mail import BadHeaderError
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, Prefetch
from django.db.models.functions import Lower
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, reverse
from django.utils import timezone
from django.views import generic
from guardian.mixins import PermissionRequiredMixin
from guardian.shortcuts import get_objects_for_user, get_perms
from revproxy.views import ProxyView

import attachment_helpers
from accounts.models import Child, Message, Organization, User
from exp.mixins.paginator_mixin import PaginatorMixin
from exp.mixins.study_responses_mixin import StudyResponsesMixin
from exp.views.mixins import ExperimenterLoginRequiredMixin, StudyTypeMixin
from project import settings
from studies.fields import (
    CONDITIONS,
    GESTATIONAL_AGE_ENUM_MAP,
    LANGUAGES,
    popcnt_bitfield,
)
from studies.forms import StudyEditForm, StudyForm
from studies.helpers import send_mail
from studies.models import ACCEPTED, Feedback, Response, Study, StudyLog, StudyType
from studies.queries import (
    get_annotated_responses_qs,
    get_consent_statistics,
    get_responses_with_current_rulings_and_videos,
    get_study_list_qs,
)
from studies.tasks import build_zipfile_of_videos, ember_build_and_gcp_deploy
from studies.workflow import (
    STATE_UI_SIGNALS,
    STATUS_HELP_TEXT,
    TRANSITION_HELP_TEXT,
    TRANSITION_LABELS,
)


class DiscoverabilityKey(NamedTuple):
    """Key to a small truth table for help text."""

    active: bool
    public: bool


STUDY_LISTING_A_TAG = (
    f'<a href="{settings.BASE_URL}/studies/">the study listing page</a>'
)


DISCOVERABILITY_HELP_TEXT = {
    (
        True,
        True,
    ): "Public. Your study is active and public. Participants can access it at your study link, "
    f"and it can be found listed in {STUDY_LISTING_A_TAG}.",
    (
        True,
        False,
    ): "Private. Your study is active, but not public. Participants may access it at your study link, "
    f"however will not be listed in {STUDY_LISTING_A_TAG}.",
    (
        False,
        True,
    ): "Public. Your study is not currently active, but it is public. When it is active, participants will be able to access it at your study link, "
    f"and it will be found listed in {STUDY_LISTING_A_TAG}. ",
    (
        False,
        False,
    ): "Private. Your study is not currently active, and is not public. When it is active, participants will be able to access it at your study link, "
    f"but it will not be listed in {STUDY_LISTING_A_TAG}. ",
}


LANGUAGES_MAP = {code: lang for code, lang in LANGUAGES}
CONDITIONS_MAP = {snake_cased: title_cased for snake_cased, title_cased in CONDITIONS}


def get_discoverability_text(study):
    """Helper function for getting discoverability text."""
    discoverability_key = DiscoverabilityKey(
        active=study.state == "active", public=study.public
    )
    return DISCOVERABILITY_HELP_TEXT.get(discoverability_key)


class StudyCreateView(
    ExperimenterLoginRequiredMixin,
    DjangoPermissionRequiredMixin,
    generic.CreateView,
    StudyTypeMixin,
):
    """
	StudyCreateView allows a user to create a study and then redirects
	them to the detail view for that study.
	"""

    model = Study
    permission_required = "studies.can_create_study"
    raise_exception = True
    form_class = StudyForm

    def form_valid(self, form):
        """
		Add the logged-in user as the study creator and the user's organization as the
		study's organization. If the form is valid, save the associated study and
		redirect to the supplied URL
		"""
        user = self.request.user
        form.instance.metadata = self.extract_type_metadata()
        form.instance.creator = user
        form.instance.organization = user.organization
        self.object = form.save()
        self.add_creator_to_study_admin_group()
        # Adds success message that study has been created.
        messages.success(self.request, f"{self.object.name} created.")
        return HttpResponseRedirect(self.get_success_url())

    def add_creator_to_study_admin_group(self):
        """
		Add the study's creator to the study admin group.
		"""
        study_admin_group = self.object.study_admin_group
        study_admin_group.user_set.add(self.request.user)
        return study_admin_group

    def get_success_url(self):
        return reverse("exp:study-detail", kwargs=dict(pk=self.object.id))

    def get_context_data(self, **kwargs):
        """
		Adds study types to get_context_data
		"""
        context = super().get_context_data(**kwargs)
        context["types"] = [
            study_type["metadata"]["fields"]
            for study_type in StudyType.objects.all().values_list(
                "configuration", flat=True
            )
        ]
        return context

    def get_initial(self):
        """
		Returns initial data to use for the create study form - make default
		structure field data an empty dict
		"""
        initial = super().get_initial()
        initial["structure"] = json.dumps(Study._meta.get_field("structure").default)
        return initial


class StudyListView(
    ExperimenterLoginRequiredMixin,
    DjangoPermissionRequiredMixin,
    generic.ListView,
    PaginatorMixin,
):
    """
	StudyListView shows a list of studies that a user has permission to.
	"""

    model = Study
    permission_required = "accounts.can_view_experimenter"
    raise_exception = True
    template_name = "studies/study_list.html"

    def get_queryset(self, *args, **kwargs):
        """
		Returns paginated list of items for the StudyListView - handles filtering on state, match,
		and sort.
		"""
        request = self.request.GET

        queryset = get_study_list_qs(self.request.user)

        # TODO: Starting date and ending date as subqueries, then delete the model methods.

        state = request.get("state")
        if state and state != "all":
            if state == "myStudies":
                queryset = queryset.filter(creator=self.request.user)
            else:
                queryset = queryset.filter(state=state)

        match = request.get("match")
        if match:
            queryset = queryset.filter(
                reduce(
                    operator.or_,
                    (
                        Q(name__icontains=term) | Q(short_description__icontains=term)
                        for term in match.split()
                    ),
                )
            )

        sort = request.get("sort", "")
        if "name" in sort:
            queryset = queryset.order_by(
                Lower("name").desc() if "-" in sort else Lower("name").asc()
            )
        elif "beginDate" in sort:
            # TODO optimize using subquery
            queryset = sorted(
                queryset,
                key=lambda t: t.begin_date or timezone.now(),
                reverse=True if "-" in sort else False,
            )
        elif "endDate" in sort:
            # TODO optimize using subquery
            queryset = sorted(
                queryset,
                key=lambda t: t.end_date or timezone.now(),
                reverse=True if "-" in sort else False,
            )
        else:
            queryset = queryset.order_by(Lower("name"))

        return self.paginated_queryset(queryset, request.get("page"), 10)

    def get_context_data(self, **kwargs):
        """
		Gets the context for the StudyListView and supplements with the state, match, and sort query params.
		"""
        context = super().get_context_data(**kwargs)
        context["state"] = self.request.GET.get("state", "all")
        context["match"] = self.request.GET.get("match", "")
        context["sort"] = self.request.GET.get("sort", "name")
        context["page"] = self.request.GET.get("page", "1")
        context["can_create_study"] = self.request.user.has_perm(
            "studies.can_create_study"
        )
        return context


class StudyDetailView(
    ExperimenterLoginRequiredMixin,
    PermissionRequiredMixin,
    generic.DetailView,
    PaginatorMixin,
):
    """
	StudyDetailView shows information about a study. Can view basic metadata about a study, can view
	study logs, and can change a study's state.
	"""

    template_name = "studies/study_detail.html"
    model = Study
    permission_required = "studies.can_view_study"
    raise_exception = True

    def post(self, *args, **kwargs):
        """
		Post method can update the trigger if the state of the study has changed.  If "clone" study
		button is pressed, clones study and redirects to the clone.
		"""
        self.manage_researcher_permissions()

        if "trigger" in self.request.POST:
            try:
                update_trigger(self)
            except Exception as e:
                messages.error(self.request, f"TRANSITION ERROR: {e}")
                return HttpResponseRedirect(
                    reverse("exp:study-detail", kwargs=dict(pk=self.get_object().pk))
                )

        if "build" in self.request.POST:
            ember_build_and_gcp_deploy.delay(
                self.get_object().uuid, self.request.user.uuid, preview=False
            )
            messages.success(
                self.request,
                f"Scheduled Study {self.get_object().name} for build. You will be emailed when it's completed.",
            )

        if self.request.POST.get("clone_study"):
            clone = self.get_object().clone()
            clone.creator = self.request.user
            clone.organization = self.request.user.organization
            clone.study_type = self.get_object().study_type
            clone.built = False
            clone.previewed = False
            clone.save()
            # Adds success message when study is cloned
            messages.success(self.request, f"{self.get_object().name} copied.")
            self.add_creator_to_study_admin_group(clone)
            return HttpResponseRedirect(
                reverse("exp:study-detail", kwargs=dict(pk=clone.pk))
            )

        return HttpResponseRedirect(
            reverse("exp:study-detail", kwargs=dict(pk=self.get_object().pk))
        )

    def manage_researcher_permissions(self):
        """
		Handles adding, updating, and deleting researcher from study. Users are
		added to study read group by default.
		"""
        study = self.get_object()
        study_read_group = study.study_read_group
        study_admin_group = study.study_admin_group
        add_user = self.request.POST.get("add_user")
        remove_user = self.request.POST.get("remove_user")
        update_user = None

        # Early exit if the user doesn't have proper permissions.
        if not self.request.user.groups.filter(name=study_admin_group.name).exists():
            messages.error(
                self.request,
                f"You don't have proper permissions to add researchers to {study.name}.",
            )
            return

        if self.request.POST.get("name") == "update_user":
            update_user = self.request.POST.get("pk")
            permissions = self.request.POST.get("value")
        if add_user:
            # Adds user to study read by default
            add_user_object = User.objects.get(pk=add_user)
            study_read_group.user_set.add(add_user_object)
            messages.success(
                self.request,
                f"{add_user_object.get_short_name()} given {study.name} Read Permissions.",
                extra_tags="user_added",
            )
            self.send_study_email(add_user_object, "read")
        if remove_user:
            # Removes user from both study read and study admin groups
            remove = User.objects.get(pk=remove_user)
            if self.adequate_study_admins(study_admin_group, remove):
                study_read_group.user_set.remove(remove)
                study_admin_group.user_set.remove(remove)
                messages.success(
                    self.request,
                    f"{remove.get_short_name()} removed from {study.name}.",
                    extra_tags="user_removed",
                )
            else:
                messages.error(
                    self.request,
                    "Could not delete this researcher. There must be at least one study admin.",
                    extra_tags="user_removed",
                )
        if update_user:
            update = User.objects.get(pk=update_user)
            if permissions == "study_admin":
                # if admin, removes user from study read and adds to study admin
                study_read_group.user_set.remove(update)
                study_admin_group.user_set.add(update)
                self.send_study_email(update, "admin")
            if permissions == "study_read":
                # if read, removes user from study admin and adds to study read
                if self.adequate_study_admins(study_admin_group, update):
                    study_read_group.user_set.add(update)
                    study_admin_group.user_set.remove(update)
                    self.send_study_email(update, "read")
        return

    def send_study_email(self, user, permission):
        study = self.get_object()
        context = {
            "permission": permission,
            "study_name": study.name,
            "study_id": study.id,
            "org_name": user.organization.name,
            "researcher_name": user.get_short_name(),
        }
        send_mail.delay(
            "notify_researcher_of_study_permissions",
            f" Invitation to collaborate on {self.get_object().name}",
            user.username,
            from_address=settings.EMAIL_FROM_ADDRESS,
            **context,
        )

    def add_creator_to_study_admin_group(self, clone):
        """
		Add the study's creator to the clone's study admin group.
		"""
        study_admin_group = clone.study_admin_group
        study_admin_group.user_set.add(self.request.user)
        return study_admin_group

    @property
    def study_logs(self):
        """ Returns a page object with 10 study logs"""
        logs_list = self.object.logs.select_related("user").order_by("-created_at")
        page = self.request.GET.get("page")
        return self.paginated_queryset(logs_list, page, 10)

    def get_context_data(self, **kwargs):
        """
		Adds several items to the context dictionary - the study, applicable triggers for the study,
		paginated study logs, and a tooltip that is dependent on the study's current state
		"""
        context = super(StudyDetailView, self).get_context_data(**kwargs)

        study = context["study"]
        admin_group = study.study_admin_group

        context["triggers"] = get_permitted_triggers(
            self, self.object.machine.get_triggers(self.object.state)
        )
        context["logs"] = self.study_logs
        state = context["state"] = self.object.state
        context["status_tooltip"] = STATUS_HELP_TEXT.get(state, state)
        context["current_researchers"] = self.get_study_researchers()
        context["users_result"] = self.search_researchers()
        context["build_ui_tag"] = "success" if study.built else "warning"
        context["preview_ui_tag"] = "success" if study.previewed else "warning"
        context["state_ui_tag"] = STATE_UI_SIGNALS.get(study.state, "info")
        context["search_query"] = self.request.GET.get("match")
        context["name"] = self.request.GET.get("match", None)
        context["multiple_admins"] = (
            len(User.objects.filter(groups__name=admin_group.name)) > 1
        )
        context["study_admins"] = User.objects.filter(
            groups__name=admin_group.name
        ).values_list("id", flat=True)
        context["discoverability_text"] = get_discoverability_text(study)
        context["transition_help"] = json.dumps(TRANSITION_HELP_TEXT)
        context["triggers_with_labels"] = [
            {"name": trigger, "label": TRANSITION_LABELS[trigger]}
            for trigger in context["triggers"]
        ]
        return context

    def get_study_researchers(self):
        """	 Pulls researchers that belong to Study Admin and Study Read groups - Not showing Org Admin and Org Read in this list (even though they technically
		can view the project.) """
        study = self.object
        return (
            User.objects.filter(
                Q(groups__name=study.study_admin_group.name)
                | Q(groups__name=study.study_read_group.name)
            )
            .distinct()
            .order_by(Lower("family_name").asc())
        )

    def search_researchers(self):
        """ Searches user first, last, and middle names for search query. Does not display researchers that are already on project """
        search_query = self.request.GET.get("match", None)
        researchers_result = None
        if search_query:
            current_researcher_ids = self.get_study_researchers().values_list(
                "id", flat=True
            )
            user_queryset = User.objects.filter(
                organization=self.get_object().organization, is_active=True
            )
            researchers_result = (
                user_queryset.filter(
                    reduce(
                        operator.or_,
                        (
                            Q(family_name__icontains=term)
                            | Q(given_name__icontains=term)
                            | Q(middle_name__icontains=term)
                            for term in search_query.split()
                        ),
                    )
                )
                .exclude(id__in=current_researcher_ids)
                .distinct()
                .order_by(Lower("family_name").asc())
            )
            researchers_result = self.build_researchers_paginator(researchers_result)
        return researchers_result

    def adequate_study_admins(self, admin_group, researcher):
        # Returns true if researchers's permissions can be edited, or researcher deleted,
        # with the constraint of there being at least one study admin at all times
        admins = User.objects.filter(groups__name=admin_group.name)
        return len(admins) - (researcher in admins) > 0

    def build_researchers_paginator(self, researchers_result):
        """
		Builds paginated search results for researchers
		"""
        page = self.request.GET.get("page")
        return self.paginated_queryset(researchers_result, page, 5)


class StudyParticipantEmailView(
    ExperimenterLoginRequiredMixin, PermissionRequiredMixin, generic.DetailView
):
    """
	StudyParticipantEmailView allows user to send a custom email to a participant.
	"""

    model = Study
    permission_required = "studies.can_edit_study"
    raise_exception = True
    template_name = "studies/study_participant_email.html"

    def get_context_data(self, **kwargs):
        """
		Adds email to the context_data dictionary
		"""
        context = super().get_context_data(**kwargs)
        context["sender"] = settings.EMAIL_FROM_ADDRESS
        context["email_next_session"] = self.get_study_participants(
            "email_next_session"
        )
        context["email_new_studies"] = self.get_study_participants("email_new_studies")
        context["email_study_updates"] = self.get_study_participants(
            "email_study_updates"
        )
        context["email_response_questions"] = self.get_study_participants(
            "email_response_questions"
        )
        return context

    def get_study_participants(self, email_field):
        """
		Restricts list to participants that have responded to this study as well as participants
		that have given their permission to be emailed personally
		"""
        return User.objects.filter(
            Q(children__response__study=self.get_object())
            & Q(**{f"{email_field}": True})
        ).distinct()

    def post(self, request, *args, **kwargs):
        """
		Post form for emailing participants.
		"""
        retval = super().get(request, *args, **kwargs)
        email_form = self.request.POST

        sender = email_form["sender"]
        subject = email_form["subject"]
        message = email_form["message"]
        recipients = list(
            User.objects.filter(pk__in=email_form.getlist("recipients")).values_list(
                "username", flat=True
            )
        )
        if sender != settings.EMAIL_FROM_ADDRESS and sender not in recipients:
            recipients += [sender]
        try:
            context = {"custom_message": message}
            send_mail.delay(
                "custom_email",
                subject,
                settings.EMAIL_FROM_ADDRESS,
                bcc=recipients,
                from_email=sender,
                **context,
            )
            messages.success(self.request, "Your message has been sent.")
            self.create_email_log(recipients, message, subject)
            return HttpResponseRedirect(self.get_success_url())
        except BadHeaderError:
            messages.error(self.request, "Invalid header found.")
        return HttpResponseRedirect(reverse("exp:study-participant-email"))

    def create_email_log(self, recipients, body, subject):
        return StudyLog.objects.create(
            extra={
                "researcher_id": self.request.user.id,
                "participant_ids": recipients,
                "body": body,
                "subject": subject,
            },
            action="email sent",
            study=self.get_object(),
            user=self.request.user,
        )

    def get_success_url(self):
        return reverse("exp:study-detail", kwargs={"pk": self.object.id})


class StudyParticipantContactView(
    ExperimenterLoginRequiredMixin, PermissionRequiredMixin, generic.DetailView
):
    """
	StudyParticipantContactView lets you contact study participants.
	"""

    model = Study
    permission_required = "studies.can_edit_study"
    raise_exception = True
    template_name = "studies/study_participant_contact.html"

    def get_context_data(self, **kwargs):
        """Gets the required data for emailing participants."""
        ctx = super().get_context_data(**kwargs)
        study = ctx["study"]
        ctx["participants"] = (
            study.participants.select_related("organization")
            .order_by(
                "-email_next_session"
            )  # Just to get the grouping in the right order
            .all()
        )
        ctx["previous_messages"] = (
            study.message_set.prefetch_related("recipients")
            .select_related("sender")
            .all()
        )
        ctx["researchers"] = self.get_researchers()
        return ctx

    def post(self, request, *args, **kwargs):
        """Handles saving message and sending email.

		TODO: enable mail merge with tokens.
		"""
        study = self.get_object()

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
        """Pulls researchers that belong to Study Admin and Study Read groups"""
        study = self.get_object()
        return User.objects.filter(organization=study.organization)


class StudyUpdateView(
    ExperimenterLoginRequiredMixin,
    PermissionRequiredMixin,
    generic.UpdateView,
    PaginatorMixin,
    StudyTypeMixin,
):
    """
	StudyUpdateView allows user to edit study metadata, add researchers to study, update researcher permissions, and delete researchers from study.
	Also allows you to update the study status.
	"""

    template_name = "studies/study_edit.html"
    form_class = StudyEditForm
    model = Study
    permission_required = "studies.can_edit_study"
    raise_exception = True

    def get_initial(self):
        """
		Returns the initial data to use for forms on this view.
		"""
        initial = super().get_initial()
        structure = self.object.structure
        if structure:
            # Ensures that json displayed in edit form is valid json w/ double quotes,
            # so incorrect json is not saved back into the db
            initial["structure"] = json.dumps(structure)
        return initial

    def post(self, request, *args, **kwargs):
        """
		Handles all post forms on page:
			1) study metadata like name, short_description, etc.
			2) researcher add
			3) researcher update
			4) researcher delete
			5) Changing study status / adding rejection comments
		"""
        study = self.get_object()

        if "trigger" in self.request.POST:
            update_trigger(self)

        if "short_description" in self.request.POST:  # Study metadata is being edited.
            return super().post(request, *args, **kwargs)

        if (
            "study_type" in self.request.POST
        ):  # Study type and metadata are being edited...
            # ... which means we must invalidate the build.
            study.built = False
            study.previewed = False
            metadata, meta_errors = self.validate_and_fetch_metadata()
            if meta_errors:
                messages.error(self.request, f"METADATA NOT SAVED: {meta_errors}")
            else:
                study.metadata = metadata
                study.study_type_id = StudyType.objects.filter(
                    id=self.request.POST.get("study_type")
                ).values_list("id", flat=True)[0]
                study.save()
                messages.success(self.request, f"{study.name} type and metadata saved.")

        return HttpResponseRedirect(reverse("exp:study-edit", kwargs=dict(pk=study.pk)))

    def form_valid(self, form):
        """
		Add success message that edits to study have been saved.
		"""
        ret = super().form_valid(form)
        messages.success(self.request, f"{self.get_object().name} study details saved.")
        return ret

    def get_context_data(self, **kwargs):
        """
		In addition to the study, adds several items to the context dictionary.
		"""
        context = super().get_context_data(**kwargs)
        study = context["study"]
        state = study.state
        admin_group = study.study_admin_group

        context["study_types"] = StudyType.objects.all()
        context["study_metadata"] = self.object.metadata
        context["types"] = [
            exp_type.configuration["metadata"]["fields"]
            for exp_type in context["study_types"]
        ]
        context["search_query"] = self.request.GET.get("match")
        context["status_tooltip"] = STATUS_HELP_TEXT.get(state, state)
        context["triggers"] = get_permitted_triggers(
            self, self.object.machine.get_triggers(state)
        )
        context["name"] = self.request.GET.get("match", None)
        context["save_confirmation"] = state in [
            "approved",
            "active",
            "paused",
            "deactivated",
        ]
        context["multiple_admins"] = (
            len(User.objects.filter(groups__name=admin_group.name)) > 1
        )
        context["study_admins"] = User.objects.filter(
            groups__name=admin_group.name
        ).values_list("id", flat=True)
        return context

    def get_success_url(self):
        return reverse("exp:study-edit", kwargs={"pk": self.object.id})


class StudyResponsesList(StudyResponsesMixin, generic.DetailView, PaginatorMixin):
    """
	View to acquire a list of study responses.
	"""

    template_name = "studies/study_responses.html"
    queryset = Study.objects.all()

    def post(self, request, *args, **kwargs):
        """Currently, handles feedback form."""
        form_data = self.request.POST
        user = self.request.user

        # first, check the case for video download
        # TODO: get rid of the mixin with this original POST behavior?
        attachment_id = form_data.get("attachment")
        if attachment_id:
            download_url = self.get_object().videos.get(pk=attachment_id).download_url
            return redirect(download_url)

        feedback_id = form_data.get("feedback_id", None)
        comment = form_data.get("comment", "")

        if feedback_id:
            Feedback.objects.filter(id=feedback_id).update(comment=comment)
        else:
            response_id = int(form_data.get("response_id"))
            Feedback.objects.create(
                response_id=response_id, researcher=user, comment=comment
            )

        return HttpResponseRedirect(
            reverse("exp:study-responses-list", kwargs=dict(pk=self.get_object().pk))
        )

    def get_responses_orderby(self):
        """
		Determine sort field and order. Sorting on id actually sorts on user id, not response id.
		Sorting on status, actually sorts on 'completed' field, where we are alphabetizing
		"in progress" and "completed"
		"""
        orderby = self.request.GET.get("sort", "id")
        reverse = "-" in orderby
        if "id" in orderby:
            orderby = "-child__user__id" if reverse else "child__user__id"
        if "status" in orderby:
            orderby = "completed" if reverse else "-completed"
        return orderby

    def get_context_data(self, **kwargs):
        """
		In addition to the study, adds several items to the context dictionary.	 Study results
		are paginated.
		"""
        context = super().get_context_data(**kwargs)
        page = self.request.GET.get("page", None)
        orderby = self.get_responses_orderby()
        responses = (
            context["study"]
            .consented_responses.prefetch_related(
                "consent_rulings__arbiter",
                Prefetch(
                    "feedback",
                    queryset=Feedback.objects.select_related("researcher").order_by(
                        "-id"
                    ),
                ),
            )
            .order_by(orderby)
        )
        paginated_responses = context["responses"] = self.paginated_queryset(
            responses, page, 10
        )

        minimal_optional_headers = [
            "rounded",
            "gender",
            "languages",
            "conditions",
            "gestage",
        ]
        context["response_data"] = self.build_responses_json(
            paginated_responses, minimal_optional_headers
        )
        context["csv_data"] = [
            self.build_summary_csv([resp], minimal_optional_headers)
            for resp in paginated_responses
        ]
        context["frame_data"] = [
            self.build_framedata_csv([resp]) for resp in paginated_responses
        ]
        print(self.all_optional_header_keys)
        context["response_data_full"] = self.build_responses_json(
            paginated_responses, self.all_optional_header_keys
        )
        context["csv_data_full"] = [
            self.build_summary_csv([resp], self.all_optional_header_keys)
            for resp in paginated_responses
        ]
        return context

    def sort_attachments_by_response(self, responses):
        """
		Build a list of list of videos for each response
		"""
        study = self.get_object()
        attachments = attachment_helpers.get_study_attachments(study)
        all_attachments = []
        for response in responses:
            uuid = str(response.uuid)
            att_list = []
            for attachment in attachments:
                if uuid in attachment.key:
                    att_list.append(
                        {
                            "key": attachment.key,
                            "display": self.build_video_display_name(
                                str(study.uuid), uuid, attachment.key
                            ),
                        }
                    )
            all_attachments.append(att_list)
        return all_attachments

    def build_video_display_name(self, study_uuid, response_uuid, vid_name):
        """
		Strips study_uuid and response_uuid out of video responses titles for better display.
		"""
        return ". . ." + ". . .".join(
            vid_name.split(study_uuid + "_")[1].split("_" + response_uuid + "_")
        )


class StudyResponsesConsentManager(StudyResponsesMixin, generic.DetailView):
    """Manage videos from here."""

    template_name = "studies/study_responses_consent_ruling.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Need to prefetch our responses with consent-footage videos.
        study = context["study"]
        responses = get_responses_with_current_rulings_and_videos(study.id)

        context["loaded_responses"] = responses
        context["summary_statistics"] = get_consent_statistics(study.id)

        # Using a map for arbitrarily structured data - lists and objects that we can't just trivially shove onto
        # data-* properties in HTML
        response_key_value_store = {}

        # two jobs - generate statistics and populate k/v store.
        for response in responses:

            response_json = response_key_value_store[str(response["uuid"])] = {}

            response["uuid"] = str(response.pop("uuid"))
            response_json["videos"] = response.pop("videos")

            response_json["details"] = {
                "general": {
                    "id": response.pop("id"),
                    "uuid": response["uuid"],
                    "conditions": json.dumps(response.pop("conditions")),
                    "global_event_timings": json.dumps(
                        response.pop("global_event_timings")
                    ),
                    "sequence": json.dumps(response.pop("sequence")),
                    "completed": json.dumps(response.pop("completed")),
                    "withdrawn": response_is_withdrawn(response["exp_data"]),
                    "date_created": str(response["date_created"]),
                },
                "participant": {
                    "id": response.pop("child__user_id"),
                    "uuid": str(response.pop("child__user__uuid")),
                    "nickname": response.pop("child__user__nickname"),
                },
                "child": {
                    "id": response.pop("child_id"),
                    "uuid": str(response.pop("child__uuid")),
                    "name": response.pop("child__given_name"),
                    "birthday": str(response.pop("child__birthday")),
                    "gender": response.pop("child__gender"),
                    "age_at_birth": response.pop("child__gestational_age_at_birth"),
                    "additional_information": response.pop(
                        "child__additional_information"
                    ),
                },
            }

            exp_data = response.pop("exp_data")
            if response["current_ruling"] == ACCEPTED:
                response_json["details"]["exp_data"] = exp_data

                # TODO: Upgrade to Django 2.x and use json_script.
        context["response_key_value_store"] = json.dumps(response_key_value_store)

        return context

    def post(self, request, *args, **kwargs):
        """This is where consent is submitted."""
        form_data = self.request.POST
        user = self.request.user
        study = self.get_object()
        responses = study.responses

        comments = json.loads(form_data.get("comments"))

        # We now accept pending rulings to reverse old reject/approve decisions.
        for ruling in ("accepted", "rejected", "pending"):
            judged_responses = responses.filter(uuid__in=form_data.getlist(ruling))
            for response in judged_responses:
                response.consent_rulings.create(
                    action=ruling,
                    arbiter=user,
                    comments=comments.pop(str(response.uuid), None),
                )
                response.save()

                # if there are any comments left over, these will count as new rulings that are the same as the last.
        if comments:
            for resp_uuid, comment in comments.items():
                response = responses.get(uuid=resp_uuid)
                response.consent_rulings.create(
                    action=response.most_recent_ruling, arbiter=user, comments=comment
                )

        return HttpResponseRedirect(
            reverse(
                "exp:study-responses-consent-manager",
                kwargs=dict(pk=self.get_object().pk),
            )
        )


def response_is_withdrawn(exp_data):
    """Check if a response is withdrawn, using the experiment frame data.

	XXX: This is copied over from the model methods in studies/models.py

	TODO: See if we can delete the model method now that we're using .values() here.
	"""
    exit_frames = [f for f in exp_data.values() if f.get("frameType", None) == "EXIT"]
    return exit_frames[0].get("withdrawal", None) if exit_frames else None


class StudyResponsesAll(StudyResponsesMixin, generic.DetailView):
    """
	StudyResponsesAll shows all study responses in JSON and CSV format.
	Either format can be downloaded
	"""

    template_name = "studies/study_responses_all.html"
    queryset = Study.objects.all()

    def get_context_data(self, **kwargs):
        """
		In addition to the study, adds several items to the context dictionary.	 Study results
		are paginated.
		"""
        context = super().get_context_data(**kwargs)
        context["n_responses"] = context["study"].consented_responses.count()
        context["childoptions"] = self.child_data_options
        context["ageoptions"] = self.age_data_options
        return context

    def build_summary_dict_csv(self, responses, optional_headers_selected_ids):
        """
		Builds CSV file contents for data dictionary corresponding to the overview CSV
		"""

        descriptions = self.get_response_headers_and_row_data()["descriptions"]
        headerList = self.get_response_headers(
            optional_headers_selected_ids, descriptions.keys()
        )
        all_descriptions = [
            {"column": header, "description": descriptions[header]}
            for header in headerList
        ]
        output, writer = self.csv_dict_output_and_writer(["column", "description"])
        writer.writerows(all_descriptions)
        return output.getvalue()

    child_csv_headers = [
        "child_hashed_id",
        "child_global_id",
        "child_name",
        "child_birthday",
        "child_gender",
        "child_age_at_birth",
        "child_language_list",
        "child_condition_list",
        "child_additional_information",
        "participant_hashed_id",
        "participant_global_id",
        "participant_nickname",
    ]

    def build_child_csv(self, responses):
        """
		Builds CSV file contents for overview of all child participants
		"""

        child_list = []
        session_list = []

        for resp in responses:
            row_data = self.get_response_headers_and_row_data(resp)["dict"]
            if row_data["child_global_id"] not in child_list:
                child_list.append(row_data["child_global_id"])
                session_list.append(row_data)

        output, writer = self.csv_dict_output_and_writer(self.child_csv_headers)
        writer.writerows(session_list)
        return output.getvalue()

    def build_child_dict_csv(self):
        """
		Builds CSV file contents for data dictionary for overview of all child participants
		"""

        descriptions = self.get_response_headers_and_row_data()["descriptions"]
        all_descriptions = [
            {"column": header, "description": descriptions[header]}
            for header in self.child_csv_headers
        ]
        output, writer = self.csv_dict_output_and_writer(["column", "description"])
        writer.writerows(all_descriptions)
        return output.getvalue()


class StudyResponsesAllDownloadJSON(StudyResponsesMixin, generic.DetailView):
    """
	Hitting this URL downloads all study responses in JSON format.
	"""

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.consented_responses.order_by("id")
        header_options = self.request.GET.getlist(
            "ageoptions"
        ) + self.request.GET.getlist("childoptions")
        cleaned_data = json.dumps(
            self.build_responses_json(responses, header_options), indent=4, default=str
        )
        filename = "{}_{}.json".format(
            self.study_name_for_files(study.name), "all-responses"
        )
        response = HttpResponse(cleaned_data, content_type="text/json")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponsesSummaryDownloadCSV(StudyResponsesAll):
    """
	Hitting this URL downloads a summary of all study responses in CSV format.
	"""

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        header_options = self.request.GET.getlist(
            "ageoptions"
        ) + self.request.GET.getlist("childoptions")
        responses = study.consented_responses.order_by("id")
        cleaned_data = self.build_summary_csv(responses, header_options)
        filename = "{}_{}.csv".format(
            self.study_name_for_files(study.name),
            "all-responses"
            + (
                "-identifiable"
                if any(
                    [
                        option in self.identifiable_data_options
                        for option in header_options
                    ]
                )
                else ""
            ),
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponsesSummaryDictCSV(StudyResponsesAll):
    """
	Hitting this URL downloads a data dictionary for the study response summary in CSV format.
	"""

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.consented_responses.order_by("id")
        header_options = self.request.GET.getlist(
            "ageoptions"
        ) + self.request.GET.getlist("childoptions")
        cleaned_data = self.build_summary_dict_csv(responses, header_options)
        filename = "{}_{}.csv".format(
            self.study_name_for_files(study.name), "all-responses-dict"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyChildrenSummaryCSV(StudyResponsesAll):
    """
	Hitting this URL downloads a summary of all children who participated in CSV format.
	"""

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.consented_responses.order_by("id")
        cleaned_data = self.build_child_csv(responses)
        filename = "{}_{}.csv".format(
            self.study_name_for_files(study.name), "all-children-identifiable"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyChildrenSummaryDictCSV(StudyResponsesAll):
    """
	Hitting this URL downloads a summary of all children who participated in CSV format.
	"""

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        cleaned_data = self.build_child_dict_csv()
        filename = "{}_{}.csv".format(
            self.study_name_for_files(study.name), "all-children-dict"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponsesFrameDataCSV(StudyResponsesMixin, generic.DetailView):
    """
	Hitting this URL downloads frame-level data from all study responses in CSV format
	"""

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.consented_responses.order_by("id")
        cleaned_data = self.build_framedata_csv(responses)
        filename = "{}_{}.csv".format(
            self.study_name_for_files(study.name), "all-frames"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponsesFrameDataIndividualCSV(StudyResponsesMixin, generic.DetailView):
    """Hitting this URL downloads a ZIP file with frame data from one response per file in CSV format"""

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.consented_responses.order_by("id")

        zipped_file = io.BytesIO()  # import io
        with zipfile.ZipFile(
            zipped_file, "w", zipfile.ZIP_DEFLATED
        ) as zipped:  # import zipfile

            for resp in responses:
                data = self.build_framedata_csv([resp])
                filename = "{}_{}_{}.csv".format(
                    self.study_name_for_files(study.name), resp.uuid, "frames"
                )
                zipped.writestr(filename, data)

        zipped_file.seek(0)
        response = HttpResponse(zipped_file, content_type="application/octet-stream")
        response[
            "Content-Disposition"
        ] = 'attachment; filename="{}_framedata_per_session.zip"'.format(
            self.study_name_for_files(study.name)
        )
        return response


class StudyResponsesFrameDataDictCSV(StudyResponsesMixin, generic.DetailView):
    """
	Hitting this URL downloads a template data dictionary for frame-level data in CSV format
	"""

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.consented_responses.order_by("id")
        cleaned_data = self.build_framedata_dict_csv(responses)
        filename = "{}_{}.csv".format(
            self.study_name_for_files(study.name), "all-frames-dict"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyDemographics(StudyResponsesMixin, generic.DetailView):
    """
	StudyParticiapnts view shows participant demographic snapshots associated
	with each response to the study
	"""

    template_name = "studies/study_demographics.html"
    queryset = Study.objects.all()

    def get_context_data(self, **kwargs):
        """
		In addition to the study, adds several items to the context dictionary.	 Study results
		are paginated.
		"""
        context = super().get_context_data(**kwargs)
        context["n_responses"] = context["study"].consented_responses.count()
        return context
        
    def get_demographic_headers(self, optional_header_ids=[]):
        optional_header_ids_to_columns = {"globalparent": "participant_uuid"}
        allHeaders = self.get_csv_demographic_row_and_headers()["headers"]
        selectedHeaders = [optional_header_ids_to_columns[id] for id in optional_header_ids if id in optional_header_ids_to_columns]
        optionalHeaders = optional_header_ids_to_columns.values()
        return [h for h in allHeaders if h not in optionalHeaders or h in selectedHeaders]


    def build_demographic_json(self, responses, optional_headers=[]):
        """
        Builds a JSON representation of demographic snapshots for download
        """
        json_responses = []
        for resp in responses:
            latest_dem = resp.demographic_snapshot
            json_responses.append(
                json.dumps(
                    {
                        "response": {"uuid": str(resp.uuid)},
                        "participant": {
                            "global_id": str(resp.child.user.uuid) if "globalparent" in optional_headers else "",
                            "hashed_id": self.hash_id(resp.child.user.uuid, resp.study.uuid, resp.study.salt)
                        },
                        "demographic_snapshot": {
                            "hashed_id": self.hash_id(latest_dem.uuid, resp.study.uuid, resp.study.salt),
                            "date_created": str(latest_dem.created_at),
                            "number_of_children": latest_dem.number_of_children,
                            "child_rounded_ages": self.round_ages_from_birthdays(
                                latest_dem.child_birthdays, latest_dem.created_at
                            ),
                            "languages_spoken_at_home": latest_dem.languages_spoken_at_home,
                            "number_of_guardians": latest_dem.number_of_guardians,
                            "number_of_guardians_explanation": latest_dem.number_of_guardians_explanation,
                            "race_identification": latest_dem.race_identification,
                            "age": latest_dem.age,
                            "gender": latest_dem.gender,
                            "education_level": latest_dem.gender,
                            "spouse_education_level": latest_dem.spouse_education_level,
                            "annual_income": latest_dem.annual_income,
                            "number_of_books": latest_dem.number_of_books,
                            "additional_comments": latest_dem.additional_comments,
                            "country": latest_dem.country.name,
                            "state": latest_dem.state,
                            "density": latest_dem.density,
                            "lookit_referrer": latest_dem.lookit_referrer,
                            "extra": latest_dem.extra,
                        },
                    },
                    indent=4,
                    default=self.convert_to_string,
                )
            )
        return json_responses

    def get_csv_demographic_row_and_headers(self, resp=[]):
        """
		Returns dict with headers, row data dict, and description dict for csv participant data associated with a response
		"""

        latest_dem = resp.demographic_snapshot if resp else ""

        all_row_data = [
            (
                "response_uuid",
                str(resp.uuid) if resp else "",
                "Primary unique identifier for response. Can be used to match demographic data to response data and video filenames; must be redacted prior to publication if videos are also published.",
            ),
            (
                "participant_global_id",
                str(resp.child.user.uuid) if resp else "",
                "Unique identifier for family account associated with this response. Will be the same for multiple responses from a child and for siblings, and across different studies. MUST BE REDACTED FOR PUBLICATION because this allows identification of families across different published studies, which may have unintended privacy consequences. Researchers can use this ID to match participants across studies (subject to their own IRB review), but would need to generate their own random participant IDs for publication in that case. Use participant_hashed_id as a publication-safe alternative if only analyzing data from one Lookit study."),
            (
                "participant_hashed_id",
                self.hash_id(resp.child.user.uuid, resp.study.uuid, resp.study.salt) if resp else "",
                "Identifier for family account associated with this response. Will be the same for multiple responses from a child and for siblings, but is unique to this study. This may be published directly.",
            ),
            (
                "demographic_hashed_id",
                self.hash_id(latest_dem.uuid, resp.study.uuid, resp.study.salt) if resp else "",
                "Identifier for this demographic snapshot. Changes upon updates to the demographic form, so may vary within the same participant across responses.",
            ),
            (
                "demographic_date_created",
                str(latest_dem.created_at) if latest_dem else "",
                "Timestamp of creation of the demographic snapshot associated with this response, in format e.g. 2019-10-02 21:39:03.713283+00:00",
            ),
            (
                "demographic_number_of_children",
                latest_dem.number_of_children if latest_dem else "",
                "Response to 'How many children do you have?'; options 0-10 or >10 (More than 10)",
            ),
            (
                "demographic_child_rounded_ages",
                self.round_ages_from_birthdays(
                    latest_dem.child_birthdays, latest_dem.created_at
                )
                if latest_dem
                else "",
                "List of rounded ages based on child birthdays entered in demographic form (not based on children registered). Ages are in days, rounded to nearest 10 for ages under 1 year and nearest 30 otherwise. In format e.g. [60, 390]",
            ),
            (
                "demographic_languages_spoken_at_home",
                latest_dem.languages_spoken_at_home if latest_dem else "",
                "Freeform response to 'What language(s) does your family speak at home?'",
            ),
            (
                "demographic_number_of_guardians",
                latest_dem.number_of_guardians if latest_dem else "",
                "Response to 'How many parents/guardians do your children live with?' - 1, 2, 3> [3 or more], varies",
            ),
            (
                "demographic_number_of_guardians_explanation",
                latest_dem.number_of_guardians_explanation if latest_dem else "",
                "Freeform response to 'If the answer varies due to shared custody arrangements or travel, please enter the number of parents/guardians your children are usually living with or explain.'",
            ),
            (
                "demographic_race_identification",
                latest_dem.race_identification if latest_dem else "",
                "Comma-separated list of all values checked for question 'What category(ies) does your family identify as?', from list:  White; Hispanic, Latino, or Spanish origin; Black or African American; Asian; American Indian or Alaska Native; Middle Eastern or North African; Native Hawaiian or Other Pacific Islander; Another race, ethnicity, or origin",
            ),
            (
                "demographic_age",
                latest_dem.age if latest_dem else "",
                "Parent's response to question 'What is your age?'; options are <18, 18-21, 22-24, 25-29, 30-34, 35-39, 40-44, 45-49, 50s, 60s, >70",
            ),
            (
                "demographic_gender",
                latest_dem.gender if latest_dem else "",
                "Parent's response to question 'What is your gender?'; options are m [male], f [female], o [other], na [prefer not to answer]",
            ),
            (
                "demographic_education_level",
                latest_dem.education_level if latest_dem else "",
                "Parent's response to question 'What is the highest level of education you've completed?'; options are some [some or attending high school], hs [high school diploma or GED], col [some or attending college], assoc [2-year college degree], bach [4-year college degree], grad [some or attending graduate or professional school], prof [graduate or professional degree]",
            ),
            (
                "demographic_spouse_education_level",
                latest_dem.spouse_education_level if latest_dem else "",
                "Parent's response to question 'What is the highest level of education your spouse has completed?'; options are some [some or attending high school], hs [high school diploma or GED], col [some or attending college], assoc [2-year college degree], bach [4-year college degree], grad [some or attending graduate or professional school], prof [graduate or professional degree], na [not applicable - no spouse or partner]",
            ),
            (
                "demographic_annual_income",
                latest_dem.annual_income if latest_dem else "",
                "Parent's response to question 'What is your approximate family yearly income (in US dollars)?'; options are 0, 5000, 10000, 15000, 20000-19000 in increments of 10000, >200000, or na [prefer not to answer]",
            ),
            (
                "demographic_number_of_books",
                latest_dem.number_of_books if latest_dem else "",
                "Parent's response to question 'About how many children's books are there in your home?'; integer",
            ),
            (
                "demographic_additional_comments",
                latest_dem.additional_comments if latest_dem else "",
                "Parent's freeform response to question 'Anything else you'd like us to know?'",
            ),
            (
                "demographic_country",
                latest_dem.country.name if latest_dem else "",
                "Parent's response to question 'What country do you live in?'; 2-letter country code",
            ),
            (
                "demographic_state",
                latest_dem.state if latest_dem else "",
                "Parent's response to question 'What state do you live in?' if country is US; 2-letter state abbreviation",
            ),
            (
                "demographic_density",
                latest_dem.density if latest_dem else "",
                "Parent's response to question 'How would you describe the area where you live?'; options are urban, suburban, rural",
            ),
            (
                "demographic_lookit_referrer",
                latest_dem.lookit_referrer if latest_dem else "",
                "Parent's freeform response to question 'How did you hear about Lookit?'",
            ),
        ]

        headers = [name for (name, val, desc) in all_row_data]
        row_data_with_headers = {name: val for (name, val, desc) in all_row_data}
        field_descriptions = {name: desc for (name, val, desc) in all_row_data}

        return {
            "headers": headers,
            "descriptions": field_descriptions,
            "dict": row_data_with_headers,
        }

    def build_all_demographic_csv(self, responses, optional_header_ids=[]):
        """
		Builds CSV file contents for all participant data
		"""

        participant_list = []
        theseHeaders = self.get_demographic_headers(optional_header_ids)
        
        for resp in responses:
            row_data = self.get_csv_demographic_row_and_headers(resp)["dict"]
            # Add any new headers from this session
            participant_list.append(row_data)

        output, writer = self.csv_dict_output_and_writer(theseHeaders)
        writer.writerows(participant_list)
        return output.getvalue()

    def build_all_demographic_dict_csv(self, responses, optional_header_ids=[]):
        """
		Builds CSV file contents for all participant data dictionary
		"""

        descriptions = self.get_csv_demographic_row_and_headers()["descriptions"]
        theseHeaders = self.get_demographic_headers(optional_header_ids)
        all_descriptions = [
            {"column": key, "description": val} for (key, val) in descriptions.items() if key in theseHeaders
        ]
        output, writer = self.csv_dict_output_and_writer(["column", "description"])
        writer.writerows(all_descriptions)
        return output.getvalue()


class StudyDemographicsDownloadJSON(StudyDemographics, generic.DetailView):
    """
	Hitting this URL downloads all participant demographics in JSON format.
	"""

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.consented_responses.order_by("id")
        header_options = self.request.GET.getlist("demooptions")
        cleaned_data = ", ".join(self.build_demographic_json(responses, header_options))
        filename = "{}_{}.json".format(
            self.study_name_for_files(study.name), "all-demographic-snapshots"
        )
        response = HttpResponse(cleaned_data, content_type="text/json")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyDemographicsDownloadCSV(StudyDemographics):
    """
	Hitting this URL downloads all participant demographics in CSV format.
	"""

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.consented_responses.order_by("id")
        header_options = self.request.GET.getlist("demooptions")
        cleaned_data = self.build_all_demographic_csv(responses, header_options)
        filename = "{}_{}.csv".format(
            self.study_name_for_files(study.name), "all-demographic-snapshots"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyDemographicsDownloadDictCSV(StudyDemographics):
    """
	Hitting this URL downloads a data dictionary for participant demographics in in CSV format.
	"""

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.consented_responses.order_by("id")
        header_options = self.request.GET.getlist("demooptions")
        cleaned_data = self.build_all_demographic_dict_csv(responses, header_options)
        filename = "{}_{}.csv".format(
            self.study_name_for_files(study.name), "all-demographic-snapshots-dict"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyAttachments(StudyResponsesMixin, generic.DetailView, PaginatorMixin):
    """
	StudyAttachments View shows video attachments for the study
	"""

    template_name = "studies/study_attachments.html"

    def get_context_data(self, **kwargs):
        """
		In addition to the study, adds several items to the context dictionary.	 Study results
		are paginated.
		"""
        context = super().get_context_data(**kwargs)
        orderby = self.request.GET.get("sort", "full_name")
        match = self.request.GET.get("match", "")
        videos = context["study"].videos_for_consented_responses
        if match:
            videos = videos.filter(full_name__icontains=match)
        if orderby:
            videos = videos.order_by(orderby)
        context["videos"] = videos
        context["match"] = match
        return context

    def post(self, request, *args, **kwargs):
        """
		Downloads study video
		"""
        attachment_url = self.request.POST.get("attachment")
        match = self.request.GET.get("match", "")
        orderby = self.request.GET.get("sort", "id") or "id"

        if attachment_url:
            return redirect(attachment_url)

        if self.request.POST.get("all-attachments"):
            build_zipfile_of_videos.delay(
                f"{self.get_object().uuid}_all_attachments",
                self.get_object().uuid,
                orderby,
                match,
                self.request.user.uuid,
            )
            messages.success(
                request,
                f"An archive of videos for {self.get_object().name} is being generated. You will be emailed a link when it's completed.",
            )

        if self.request.POST.get("all-consent-videos"):
            build_zipfile_of_videos.delay(
                f"{self.get_object().uuid}_all_consent",
                self.get_object().uuid,
                orderby,
                match,
                self.request.user.uuid,
                consent=True,
            )
            messages.success(
                request,
                f"An archive of consent videos for {self.get_object().name} is being generated. You will be emailed a link when it's completed.",
            )

        return HttpResponseRedirect(
            reverse("exp:study-attachments", kwargs=dict(pk=self.get_object().pk))
        )


class StudyPreviewBuildView(generic.detail.SingleObjectMixin, generic.RedirectView):
    """
	Checks to make sure an existing build isn't running, that the user has permissions
	to preview, and then triggers a preview build.
	"""

    http_method_names = ["post"]
    model = Study
    _object = None

    @property
    def object(self):
        if not self._object:
            self._object = self.get_object(queryset=self.get_queryset())
        return self._object

    def get_redirect_url(self, *args, **kwargs):
        return reverse("exp:study-edit", kwargs={"pk": str(self.object.pk)})

    def post(self, request, *args, **kwargs):
        study_permissions = get_perms(request.user, self.object)

        if study_permissions and "can_edit_study" in study_permissions:
            ember_build_and_gcp_deploy.delay(
                self.object.uuid, request.user.uuid, preview=True
            )
            messages.success(
                request,
                f"Scheduled Study {self.object.name} for preview. You will be emailed when it's completed.",
            )
        return super().post(request, *args, **kwargs)

    def get_object(self, queryset=None):
        """
		Returns the object the view is displaying.
		By default this requires `self.queryset` and a `pk` or `slug` argument
		in the URLconf, but subclasses can override this to return any object.
		"""
        # Use a custom queryset if provided; this is required for subclasses
        # like DateDetailView
        if queryset is None:
            queryset = self.get_queryset()
        uuid = self.kwargs.get("uuid")
        if uuid is not None:
            queryset = queryset.filter(uuid=uuid)

        if uuid is None:
            raise AttributeError(
                "View %s must be called with " "a uuid." % self.__class__.__name__
            )
        try:
            # Get the single item from the filtered queryset
            obj = queryset.get()
        except queryset.model.DoesNotExist:
            raise Http404(
                f"No {queryset.model._meta.verbose_name}s found matching the query"
            )

        return obj


class StudyParticipantAnalyticsView(
    ExperimenterLoginRequiredMixin, PermissionRequiredMixin, generic.TemplateView
):
    template_name = "studies/study_participant_analytics.html"
    model = Study
    permission_required = "accounts.can_view_analytics"
    raise_exception = True

    def get_context_data(self, **kwargs):
        """Context getter override."""
        ctx = super().get_context_data(**kwargs)

        if self.request.user.has_perm("studies.view_all_response_data_in_analytics"):
            # Recruitment manager
            studies_for_user = Study.objects.all()
            # Template tag needs a single object to check, so we need to flag based on queryset.
            ctx["can_view_all_responses"] = True
        else:
            # Researcher or other
            studies_for_user = get_objects_for_user(
                self.request.user, "studies.can_view_study"
            )

            # Responses for studies
        annotated_responses = (
            get_annotated_responses_qs()
            .filter(study__in=studies_for_user)
            .select_related("child", "child__user", "study", "demographic_snapshot")
        ).values(
            "uuid",
            "date_created",
            "current_ruling",
            "child_id",
            "child__uuid",
            "child__birthday",
            "child__gender",
            "child__gestational_age_at_birth",
            "child__languages_spoken",
            "study__name",
            "study_id",
            "child__user__uuid",
            "demographic_snapshot__number_of_children",
            "demographic_snapshot__race_identification",
            "demographic_snapshot__number_of_guardians",
            "demographic_snapshot__annual_income",
            "demographic_snapshot__age",
            "demographic_snapshot__education_level",
            "demographic_snapshot__gender",
            "demographic_snapshot__spouse_education_level",
            "demographic_snapshot__density",
            "demographic_snapshot__number_of_books",
            "demographic_snapshot__country",
            "demographic_snapshot__state",
            "demographic_snapshot__lookit_referrer",
            "demographic_snapshot__additional_comments",
        )

        # now, map studies for each child, and gather demographic data as well.
        studies_for_child = defaultdict(set)
        for resp in annotated_responses:
            studies_for_child[resp["child_id"]].add(resp["study__name"])

            # Include _all_ non-researcher users on Lookit
        registrations = User.objects.filter(is_researcher=False).values_list(
            "date_created", flat=True
        )

        ctx["all_studies"] = studies_for_user

        ctx["registration_data"] = json.dumps(
            list(registrations), cls=DjangoJSONEncoder
        )

        if self.request.user.has_perm("accounts.can_view_all_children_in_analytics"):
            children_queryset = Child.objects.filter(user__is_researcher=False)
            ctx["can_view_all_children"] = True
        else:
            children_queryset = Child.objects.filter(
                user__is_researcher=False,
                id__in=annotated_responses.values_list(
                    "child_id", flat=True
                ).distinct(),
            )
        children_pivot_data = unstack_children(children_queryset, studies_for_child)

        flattened_responses = get_flattened_responses(
            annotated_responses, studies_for_child
        )

        ctx["response_timeseries_data"] = json.dumps(flattened_responses, default=str)

        ctx["studies"], ctx["languages"], ctx["characteristics"], ctx["ages"] = [
            dict(counter) for counter in children_pivot_data
        ]
        return ctx


class PreviewProxyView(ProxyView, ExperimenterLoginRequiredMixin):
    """
	Proxy view to forward researcher to preview page in the Ember app
	"""

    upstream = settings.PREVIEW_EXPERIMENT_BASE_URL

    def dispatch(self, request, path, *args, **kwargs):
        if request.path[-1] == "/":
            path = f"{path.split('/')[0]}/index.html"
        return super().dispatch(request, path)


def get_flattened_responses(response_qs, studies_for_child):
    """Get derived attributes for children.

	TODO: consider whether or not this work should be extracted out into a dataframe.
	"""
    response_data = []
    for resp in response_qs:
        child_age_in_days = (resp["date_created"] - resp["child__birthday"]).days
        languages_spoken = popcnt_bitfield(
            int(resp["child__languages_spoken"]), "languages"
        )
        response_data.append(
            {
                "Response (unique identifier)": resp["uuid"],
                "Child (unique identifier)": resp["child__uuid"],
                "Child Age in Days": child_age_in_days,
                "Child Age in Months": int(child_age_in_days // 30),
                "Child Age in Years": int(child_age_in_days // 365),
                "Child Gender": resp["child__gender"],
                "Child Gestational Age at Birth": GESTATIONAL_AGE_ENUM_MAP.get(
                    resp["child__gestational_age_at_birth"], "Unknown"
                ),
                "Child # Languages Spoken": len(languages_spoken),
                "Child # Studies Participated": len(
                    studies_for_child[resp["child_id"]]
                ),
                "Study": resp["study__name"],
                "Study ID": resp["study_id"],  # TODO: change this to use UUID
                "Family (unique identifier)": resp["child__user__uuid"],
                "Family # of Children": resp[
                    "demographic_snapshot__number_of_children"
                ],
                "Family Race/Ethnicity": resp[
                    "demographic_snapshot__race_identification"
                ],
                "Family # of Guardians": resp[
                    "demographic_snapshot__number_of_guardians"
                ],
                "Family Annual Income": resp["demographic_snapshot__annual_income"],
                "Parent/Guardian Age": resp["demographic_snapshot__age"],
                "Parent/Guardian Education Level": resp[
                    "demographic_snapshot__education_level"
                ],
                "Parent/Guardian Gender": resp["demographic_snapshot__gender"],
                "Parent/Guardian Spouse Educational Level": resp[
                    "demographic_snapshot__spouse_education_level"
                ],
                "Living Density": resp["demographic_snapshot__density"],
                "Number of Books": resp["demographic_snapshot__number_of_books"],
                "Country": resp["demographic_snapshot__country"],
                "State": resp["demographic_snapshot__state"],
                "Time of Response": resp["date_created"].isoformat(),
                "Consent Ruling": resp["current_ruling"],
                "Lookit Referrer": resp["demographic_snapshot__lookit_referrer"],
                "Additional Comments": resp[
                    "demographic_snapshot__additional_comments"
                ],
            }
        )

    return response_data


def unstack_children(children_queryset, studies_for_child_map):
    """Unstack spoken languages, characteristics/conditions, and parent races/ethnicities"""
    languages = Counter()
    characteristics = Counter()
    studies = Counter()
    ages = Counter()
    for child in children_queryset:
        for study_name in studies_for_child_map[child.id]:
            studies[study_name] += 1
        for lang in child.languages_spoken:
            if lang[1]:
                languages[LANGUAGES_MAP[lang[0]]] += 1
        for cond in child.existing_conditions:
            if cond[1]:
                characteristics[CONDITIONS_MAP[cond[0]]] += 1

        child_age_days = (
            (datetime.date.today() - child.birthday).days if child.birthday else None
        )

        if child_age_days:  # In the rare case that we don't have a child age
            child_age_months = child_age_days // 30
            if child_age_months == 1:
                child_age = "1 month"
            elif child_age_months < 24:
                child_age = str(child_age_months) + " months"
            elif child_age_months == 24:
                child_age = "2 years"
            else:
                child_age = str(child_age_days // 365) + " years"
        else:
            child_age = None

        ages[child_age] += 1

    return studies, languages, characteristics, ages


# UTILITY FUNCTIONS
def get_permitted_triggers(view_instance, triggers):
    """Takes in the available triggers (next possible states) for a study and restricts that list
	based on the current user's permissions.
	The view_instance is the StudyDetailView or the StudyUpdateView.
	"""
    permitted_triggers = []
    user = view_instance.request.user
    study = view_instance.object
    study_permissions = get_perms(user, view_instance.object)

    admin_triggers = ["approve", "reject"]
    for trigger in triggers:
        # remove autogenerated triggers
        if trigger.startswith("to_"):
            continue

            # Trigger valid if 1) superuser 2) trigger is admin trigger and user is org admin
            # 3) trigger is found in user's study permissions
        if not user.is_superuser:
            if trigger in admin_triggers:
                if not (user.organization == study.organization and user.is_org_admin):
                    continue
            elif ("can_" + trigger + "_study") not in study_permissions:
                continue

        permitted_triggers.append(trigger)

    return permitted_triggers


def update_trigger(view_instance):
    """Transition to next state in study workflow.

	TODO: Comments text is a bit silly to have here - let's move it to the proper Edit
	View to be in the appropriate functional location once we do a refactor.

	:param view_instance: An instance of the django view.
	:type view_instance: StudyDetailView or StudyUpdateView
	"""
    trigger = view_instance.request.POST.get("trigger")
    object = view_instance.get_object()
    if trigger:
        if hasattr(object, trigger):
            # transition through workflow state
            getattr(object, trigger)(user=view_instance.request.user)
    if "comments-text" in view_instance.request.POST.keys():
        object.comments = view_instance.request.POST["comments-text"]
        object.save()
    displayed_state = object.state if object.state != "active" else "activated"
    messages.success(view_instance.request, f"Study {object.name} {displayed_state}.")
    return object
