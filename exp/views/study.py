import datetime
import json
import operator
from functools import reduce
from typing import NamedTuple

from django.contrib import messages
from django.contrib.auth.mixins import (
    PermissionRequiredMixin as DjangoPermissionRequiredMixin,
)
from django.core.mail import BadHeaderError
from django.db.models import (
    Q,
    Case,
    Count,
    IntegerField,
    OuterRef,
    Prefetch,
    Subquery,
    When,
)
from django.db.models.functions import Lower
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, reverse
from django.utils import timezone
from django.views import generic
from guardian.mixins import PermissionRequiredMixin
from guardian.shortcuts import get_objects_for_user, get_perms
from revproxy.views import ProxyView

import attachment_helpers
from accounts.models import Message, User
from exp.mixins.paginator_mixin import PaginatorMixin
from exp.mixins.study_responses_mixin import StudyResponsesMixin
from exp.views.mixins import ExperimenterLoginRequiredMixin, StudyTypeMixin
from project import settings
from studies.forms import EligibleParticipantQueryModelForm, StudyEditForm, StudyForm
from studies.helpers import send_mail
from studies.models import (
    EligibleParticipantQueryModel,
    Response,
    Study,
    StudyLog,
    StudyType,
    get_annotated_responses_qs,
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

        annotated_responses_qs = get_annotated_responses_qs()

        queryset = (
            get_objects_for_user(self.request.user, "studies.can_view_study")
            .exclude(state="archived")
            .select_related("creator")
            .annotate(
                completed_responses_count=Subquery(
                    Response.objects.filter(
                        study=OuterRef("pk"),
                        completed_consent_frame=True,
                        completed=True,
                    )
                    .values("completed")
                    .order_by()
                    .annotate(count=Count("completed"))
                    .values("count")[:1],  # [:1] ensures that a queryset is returned
                    output_field=IntegerField(),
                ),
                incomplete_responses_count=Subquery(
                    Response.objects.filter(
                        study=OuterRef("pk"),
                        completed_consent_frame=True,
                        completed=False,
                    )
                    .values("completed")
                    .order_by()
                    .annotate(count=Count("completed"))
                    .values("count")[:1],  # [:1] ensures that a queryset is returned
                    output_field=IntegerField(),
                ),
                valid_consent_count=Subquery(
                    annotated_responses_qs.filter(
                        study=OuterRef("pk"), current_ruling="accepted"
                    )
                    .values("current_ruling")
                    .order_by(
                        "current_ruling"
                    )  # Need this for GROUP BY to work properly
                    .annotate(count=Count("current_ruling"))
                    .values("count")[:1],  # [:1] ensures that a queryset is returned
                    output_field=IntegerField(),
                ),
                pending_consent_count=Subquery(
                    annotated_responses_qs.filter(
                        study=OuterRef("pk"), current_ruling="pending"
                    )
                    .values("current_ruling")
                    .order_by("current_ruling")
                    .annotate(count=Count("current_ruling"))
                    .values("count")[:1],
                    output_field=IntegerField(),
                ),
                starting_date=Subquery(
                    StudyLog.objects.filter(study=OuterRef("pk"))
                    .order_by("-created_at")
                    .filter(action="active")
                    .values("created_at")[:1]
                ),
                ending_date=Subquery(
                    StudyLog.objects.filter(study=OuterRef("pk"))
                    .order_by("-created_at")
                    .filter(action="deactivated")
                    .values("created_at")[:1]
                ),
            )
        )

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
        """  Pulls researchers that belong to Study Admin and Study Read groups - Not showing Org Admin and Org Read in this list (even though they technically
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


class StudyParticipantEligibilityManager(
    ExperimenterLoginRequiredMixin, generic.UpdateView
):
    """Modifying study participant eligibility."""

    model = EligibleParticipantQueryModel
    form_class = EligibleParticipantQueryModelForm
    template_name = "studies/study_participant_eligibility.html"
    permission_required = "studies.can_edit_study"
    context_object_name = "eligible_participant_query_model"

    def get_object(self, queryset=None):
        """Override so that we have something approaching an AutoOneToOneField in terms of functionality."""
        query_model, created = self.get_queryset().get_or_create(
            pk=self.kwargs.get(self.pk_url_kwarg)
        )
        return query_model

    def get_success_url(self):
        return reverse(
            "exp:study-participant-eligibility", kwargs={"pk": self.object.study.id}
        )


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
        In addition to the study, adds several items to the context dictionary.  Study results
        are paginated.
        """
        context = super().get_context_data(**kwargs)
        page = self.request.GET.get("page", None)
        orderby = self.get_responses_orderby()
        responses = context["study"].consented_responses.order_by(orderby)
        paginated_responses = context["responses"] = self.paginated_queryset(
            responses, page, 10
        )
        context["response_data"] = self.build_responses(paginated_responses)
        context["csv_data"] = self.build_individual_csv(paginated_responses)
        return context

    def build_individual_csv(self, responses):
        """
        Builds CSV for individual responses and puts them in array
        """
        csv_responses = []
        for resp in responses:
            output, writer = self.csv_output_and_writer()
            writer.writerow(self.get_csv_headers())
            writer.writerow(self.csv_row_data(resp))
            csv_responses.append(output.getvalue())
        return csv_responses

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
        responses = study.responses_with_consent_videos
        context["loaded_responses"] = responses
        context["summary_statistics"] = statistics = {
            "accepted": {"responses": 0, "children": set()},
            "rejected": {"responses": 0, "children": set()},
            "pending": {"responses": 0, "children": set()},
            "total": {"responses": 0, "children": set()},
        }

        total_stats = statistics["total"]

        # Using a map for arbitrarily structured data - lists and objects that we can't just trivially shove onto
        # data-* properties in HTML
        response_key_value_store = {}

        # two jobs - generate statistics and populate k/v store.
        for response in responses:

            stat_for_status = statistics.get(response.most_recent_ruling)
            stat_for_status["responses"] += 1
            stat_for_status["children"].add(response.child)
            total_stats["responses"] += 1
            total_stats["children"].add(response.child)

            response_data = response_key_value_store[str(response.uuid)] = {}

            response_data["videos"] = [
                {"aws_url": video.download_url, "filename": video.filename}
                for video in response.videos.all()  # we did a prefetch, so all() is really is_consent_footage=True
            ]

            response_data["details"] = {
                "general": {
                    "id": response.id,
                    "uuid": str(response.uuid),
                    "sequence": response.sequence,
                    "conditions": json.dumps(response.conditions),
                    "global_event_timings": json.dumps(response.global_event_timings),
                    "completed": response.completed,
                    "withdrawn": response.withdrawn,
                },
                "participant": {
                    "id": response.child.user_id,
                    "uuid": str(response.child.user.uuid),
                    "nickname": response.child.user.nickname,
                },
                "child": {
                    "id": response.child.id,
                    "uuid": str(response.child.uuid),
                    "name": response.child.given_name,
                    "birthday": response.child.birthday,
                    "gender": response.child.gender,
                    "age_at_birth": response.child.age_at_birth,
                    "additional_information": response.child.additional_information,
                },
            }

            if response.has_valid_consent:
                response_data["details"]["exp_data"] = response.exp_data

        # TODO: Upgrade to Django 2.x and use json_script.
        context["response_key_value_store"] = json.dumps(
            response_key_value_store,
            default=lambda x: str(x) if isinstance(x, datetime.date) else x,
        )

        rejected = statistics["rejected"]
        rejected_child_set = rejected["children"]
        accepted_child_set = statistics["accepted"]["children"]
        rejected["count_without_accepted"] = len(
            rejected_child_set - accepted_child_set
        )

        for category, counts in statistics.items():
            counts["children"] = len(counts["children"])

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


class StudyResponsesAll(StudyResponsesMixin, generic.DetailView):
    """
    StudyResponsesAll shows all study responses in JSON and CSV format.
    Either format can be downloaded
    """

    template_name = "studies/study_responses_all.html"

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.  Study results
        are paginated.
        """
        context = super().get_context_data(**kwargs)
        context["n_responses"] = len(context["study"].consented_responses.all())
        return context

    def build_all_csv(self, responses):
        """
        Builds CSV file contents for all responses
        """
        output, writer = self.csv_output_and_writer()
        writer.writerow(self.get_csv_headers())
        for resp in responses:
            writer.writerow(self.csv_row_data(resp))
        return output.getvalue()


class StudyResponsesAllDownloadJSON(StudyResponsesMixin, generic.DetailView):
    """
    Hitting this URL downloads all study responses in JSON format.
    """

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.consented_responses.order_by("id")
        cleaned_data = json.dumps(
            self.build_responses(responses), indent=4, default=str
        )
        filename = "{}-{}.json".format(study.name, "all_responses")
        response = HttpResponse(cleaned_data, content_type="text/json")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponsesAllDownloadCSV(StudyResponsesAll):
    """
    Hitting this URL downloads all study responses in CSV format.
    """

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.consented_responses.order_by("id")
        cleaned_data = self.build_all_csv(responses)
        filename = "{}-{}.csv".format(study.name, "all_responses")
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyDemographics(StudyResponsesMixin, generic.DetailView):
    """
    StudyParticiapnts view shows participant demographic snapshots associated
    with each response to the study
    """

    template_name = "studies/study_demographics.html"

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.  Study results
        are paginated.
        """
        context = super().get_context_data(**kwargs)
        context["n_responses"] = len(context["study"].consented_responses.all())
        return context

    def build_all_participant_csv(self, responses):
        """
        Builds CSV file contents for all participant data
        """
        output, writer = self.csv_output_and_writer()
        writer.writerow(self.get_csv_participant_headers())
        for resp in responses:
            writer.writerow(self.build_csv_participant_row_data(resp))
        return output.getvalue()


class StudyDemographicsDownloadJSON(StudyResponsesMixin, generic.DetailView):
    """
    Hitting this URL downloads all participant demographics in JSON format.
    """

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.consented_responses.order_by("id")
        cleaned_data = ", ".join(self.build_participant_data(responses))
        filename = "{}-{}.json".format(study.name, "all_demographic_snapshots")
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
        cleaned_data = self.build_all_participant_csv(responses)
        filename = "{}-{}.csv".format(study.name, "all_demographic_snapshots")
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
        In addition to the study, adds several items to the context dictionary.  Study results
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


class PreviewProxyView(ProxyView, ExperimenterLoginRequiredMixin):
    """
    Proxy view to forward researcher to preview page in the Ember app
    """

    upstream = settings.PREVIEW_EXPERIMENT_BASE_URL

    def dispatch(self, request, path, *args, **kwargs):
        if request.path[-1] == "/":
            path = f"{path.split('/')[0]}/index.html"
        return super().dispatch(request, path)


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
