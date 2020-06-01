import datetime
import io
import json
import operator
import zipfile
from collections import Counter, defaultdict
from functools import reduce
from typing import NamedTuple

from django.contrib import messages
from django.contrib.auth.mixins import (
    PermissionRequiredMixin as DjangoPermissionRequiredMixin,
)
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Prefetch, Q
from django.db.models.functions import Lower
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, reverse
from django.utils.text import slugify
from django.views import generic
from django.views.generic.detail import SingleObjectMixin
from guardian.mixins import PermissionRequiredMixin as ObjectPermissionRequiredMixin
from guardian.shortcuts import get_objects_for_user, get_perms
from revproxy.views import ProxyView

import attachment_helpers
from accounts.models import Child, Message, User
from accounts.utils import (
    hash_child_id,
    hash_demographic_id,
    hash_id,
    hash_participant_id,
)
from exp.mixins.paginator_mixin import PaginatorMixin
from exp.utils import (
    RESPONSE_PAGE_SIZE,
    csv_dict_output_and_writer,
    flatten_dict,
    round_age,
    round_ages_from_birthdays,
    study_name_for_files,
)
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
from studies.models import Feedback, Lab, Study, StudyType
from studies.permissions import LabPermission, StudyPermission
from studies.queries import (
    get_annotated_responses_qs,
    get_consent_statistics,
    get_responses_with_current_rulings_and_videos,
    get_study_list_qs,
)
from studies.tasks import (
    build_framedata_dict,
    build_zipfile_of_videos,
    ember_build_and_gcp_deploy,
)
from studies.workflow import (
    STATE_UI_SIGNALS,
    STATUS_HELP_TEXT,
    TRANSITION_HELP_TEXT,
    TRANSITION_LABELS,
)
from web.views import StudyDetailView as ParticipantStudyDetailView


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


KEY_DISPLAY_NAMES = {
    "player_repo_url": "Experiment runner code URL",
    "last_known_player_sha": "Experiment runner version (commit SHA)",
}


class SingleObjectParsimoniousQueryMixin(SingleObjectMixin):

    object: Study

    def get_object(self, queryset=None):
        """Override get_object() to be smarter.

        This is to allow us to get the study for use the predicate function
        of UserPassesTestMixin without making `SingleObjectMixin.get` (called
        within the context of `View.dispatch`) issue a second expensive query.
        """
        if getattr(self, "object", None) is None:
            # Only call get_object() when self.object isn't present.
            self.object = super().get_object()
        return self.object


class StudyCreateView(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    StudyTypeMixin,
    generic.CreateView,
):
    """
    StudyCreateView allows a user to create a study and then redirects
    them to the detail view for that study.
    """

    model = Study
    # permission_required = "studies.can_create_study"
    raise_exception = True
    form_class = StudyForm

    def user_can_make_studies_for_lab(self):
        user = self.request.user
        lab = user.lab

        if lab:
            # has_perm will check for superuser by default.
            return user.has_perm(
                LabPermission.CREATE_LAB_ASSOCIATED_STUDY.codename, obj=lab
            )
        else:
            # This should effectively delegate to the correct handler, by way
            # of View.dispatch()
            return False

    # Make PyCharm happy - otherwise we'd just override get_test_func()
    test_func = user_can_make_studies_for_lab

    def form_valid(self, form):
        """
        Add the logged-in user as the study creator and the user's organization as the
        study's organization. If the form is valid, save the associated study and
        redirect to the supplied URL
        """
        user = self.request.user
        target_study_type_id = self.request.POST["study_type"]
        target_study_type = StudyType.objects.get(id=target_study_type_id)
        form.instance.metadata = self.extract_type_metadata(target_study_type)
        form.instance.creator = user
        form.instance.lab = user.lab
        # Add user to admin group for study.
        new_study = self.object = form.save()
        new_study.admin_group.add(user)
        new_study.save()
        # Adds success message that study has been created.
        messages.success(self.request, f"{self.object.name} created.")
        return HttpResponseRedirect(self.get_success_url())

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
        context["key_display_names"] = KEY_DISPLAY_NAMES
        return context

    def get_initial(self):
        """
        Returns initial data to use for the create study form - make default
        structure field data an empty dict
        """
        initial = super().get_initial()
        initial["structure"] = json.dumps(Study._meta.get_field("structure").default)
        return initial


class StudyUpdateView(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    PaginatorMixin,
    StudyTypeMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.UpdateView,
):
    """
    StudyUpdateView allows user to edit study metadata, add researchers to study, update researcher permissions, and delete researchers from study.
    Also allows you to update the study status.
    """

    template_name = "studies/study_edit.html"
    form_class = StudyEditForm
    model = Study
    # permission_required = "studies.can_edit_study"
    raise_exception = True

    def user_can_edit_study(self):
        """Test predicate for the study editing view."""
        user = self.request.user
        # If we end up using method, this will be useful.
        # method = self.request.method
        study = self.get_object()

        return user.has_study_perms(StudyPermission.WRITE_STUDY_DETAILS, study)

    # Make PyCharm happy - otherwise we'd just override
    # UserPassesTestMixin.get_test_func()
    test_func = user_can_edit_study

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
        Handles updating study metadata like name, short_description, etc.
        """
        study = self.get_object()

        target_study_type_id = self.request.POST["study_type"]
        target_study_type = StudyType.objects.get(id=target_study_type_id)

        metadata, meta_errors = self.validate_and_fetch_metadata(
            study_type=target_study_type
        )

        if meta_errors:
            messages.error(
                self.request,
                f"WARNING: Experiment runner version not saved: {meta_errors}",
            )
        else:
            # Check that study type hasn't changed.
            if not (
                study.study_type_id == target_study_type_id
                and metadata == study.metadata
            ):
                # Invalidate the previous build
                study.built = False
                # May still be building, but we're now good to allow another build
                study.is_building = False
            study.metadata = metadata
            study.study_type_id = target_study_type_id
            study.save()

            return super().post(request, *args, **kwargs)

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

        context["study_types"] = StudyType.objects.all()
        context["study_metadata"] = self.object.metadata
        context["key_display_names"] = KEY_DISPLAY_NAMES
        context["types"] = [
            exp_type.configuration["metadata"]["fields"]
            for exp_type in context["study_types"]
        ]
        context["save_confirmation"] = self.object.state in [
            "approved",
            "active",
            "paused",
            "deactivated",
        ]
        return context

    def get_success_url(self):
        return reverse("exp:study-edit", kwargs={"pk": self.object.id})


class StudyListView(
    ExperimenterLoginRequiredMixin,
    # DjangoPermissionRequiredMixin,
    PaginatorMixin,
    generic.ListView,
):
    """
    StudyListView shows a list of studies that a user has permission to.
    """

    model = Study
    # permission_required = "accounts.can_view_experimenter"
    raise_exception = True
    template_name = "studies/study_list.html"

    def get_queryset(self, *args, **kwargs):
        """
        Returns paginated list of items for the StudyListView - handles filtering on state, match,
        and sort.
        """
        user = self.request.user
        query_dict = self.request.GET

        queryset = get_study_list_qs(user, query_dict)

        return self.paginated_queryset(queryset, query_dict.get("page"), 10)

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
    UserPassesTestMixin,
    PaginatorMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.DetailView,
):
    """
    StudyDetailView shows information about a study. Can view basic metadata about a study, can view
    study logs, and can change a study's state.
    """

    template_name = "studies/study_detail.html"
    model = Study
    # permission_required = "studies.can_view_study"
    raise_exception = True

    def user_can_see_or_edit_study_details(self):
        """Checks based on method, with fallback to umbrella lab perms.

        Returns:
            A boolean indicating whether or not the user should be able to see
            this view.
        """
        user = self.request.user
        method = self.request.method
        study = self.object = self.get_object()

        if method == "GET":
            return user.has_study_perms(StudyPermission.READ_STUDY_DETAILS, study)
        elif method == "POST":
            return user.has_study_perms(StudyPermission.MANAGE_STUDY_RESEARCHERS, study)
            # What to do about study cloning
        else:
            # If we're not one of the two allowed methods this should be caught
            # earlier
            return False

    # Make PyCharm happy - otherwise we'd just override
    # UserPassesTestMixin.get_test_func()
    test_func = user_can_see_or_edit_study_details

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

        if self.request.POST.get("clone_study"):
            clone = self.get_object().clone()
            clone.creator = self.request.user
            # clone.organization = self.request.user.organization
            clone.lab = self.request.user.lab
            clone.study_type = self.get_object().study_type
            clone.built = False
            clone.is_building = False
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
        change_requester = self.request.user
        study = self.get_object()
        study_researcher_group = study.researcher_group
        study_admin_group = study.admin_group
        id_of_user_to_add = self.request.POST.get("add_user")
        id_of_user_to_remove = self.request.POST.get("remove_user")

        # Early exit if the user doesn't have proper permissions.
        # We should not need this because the test function will check for us whether
        # or not this user is legal for the POST request based on object perms.
        # if not self.request.user.groups.filter(name=study_admin_group.name).exists():
        #     messages.error(
        #         self.request,
        #         f"You don't have proper permissions to add researchers to {study.name}.",
        #     )
        #     return

        if self.request.POST.get("name") == "update_user":
            id_of_user_to_update = self.request.POST.get("pk")
            name_of_role_to_enable = self.request.POST.get("value")
            if id_of_user_to_update:
                user_to_update = User.objects.get(pk=id_of_user_to_update)
                if name_of_role_to_enable == "study_admin":
                    # if admin, removes user from study read and adds to study admin
                    user_to_update.groups.add(study_admin_group)
                    user_to_update.groups.remove(study_researcher_group)
                    self.send_study_email(user_to_update, "admin")
                if name_of_role_to_enable == "study_read":
                    # if read, removes user from study admin and adds to study read
                    # Must have more than one admin to make this change.
                    if study_admin_group.user_set.count() > 1:
                        user_to_update.groups.add(study_researcher_group)
                        user_to_update.groups.remove(study_admin_group)
                        self.send_study_email(user_to_update, "read")
        if id_of_user_to_add:
            # Adds user to study read by default
            user_to_add = User.objects.get(pk=id_of_user_to_add)
            user_to_add.groups.add(study_researcher_group)
            messages.success(
                self.request,
                f"{user_to_add.get_short_name()} given {study.name} Read Permissions.",
                extra_tags="user_added",
            )
            self.send_study_email(user_to_add, "read")
        if id_of_user_to_remove:
            # Removes user from both study read and study admin groups
            user_to_remove = User.objects.get(pk=id_of_user_to_remove)
            if study_admin_group.user_set.count() > 1:
                user_to_remove.groups.remove(study_researcher_group)
                user_to_remove.groups.remove(study_admin_group)
                messages.success(
                    self.request,
                    f"{user_to_remove.get_short_name()} removed from {study.name}.",
                    extra_tags="user_removed",
                )
            else:
                messages.error(
                    self.request,
                    "Could not delete this researcher. There must be at least one study admin.",
                    extra_tags="user_removed",
                )

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
        user = self.request.user
        study_admin_group = clone.admin_group
        user.groups.add(study_admin_group)
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
        admin_group = study.admin_group

        context["triggers"] = get_permitted_triggers(
            self, self.object.machine.get_triggers(self.object.state)
        )
        context["logs"] = self.study_logs
        state = context["state"] = self.object.state
        context["status_tooltip"] = STATUS_HELP_TEXT.get(state, state)
        context["current_researchers"] = self.get_study_researchers()
        context["users_result"] = self.search_researchers()
        context["build_ui_tag"] = "success" if study.built else "warning"
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
        """Pulls researchers that belong to Study Admin and Study Read groups.

        Not showing Org Admin and Org Read in this list (even though they technically can view the project)
        """
        study = self.get_object()
        study_admins = study.admin_group.user_set.all()
        study_researchers = study.researcher_group.user_set.all()
        return (study_admins | study_researchers).order_by(Lower("family_name").asc())

    def search_researchers(self):
        """Searches user first, last, and middle names for search query.
        Does not display researchers that are already on project.
        """
        search_query = self.request.GET.get("match", None)

        if search_query:
            current_researcher_ids = self.get_study_researchers().values_list(
                "id", flat=True
            )
            user_queryset = User.objects.filter(
                lab=self.get_object().lab, is_active=True
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

            return self.build_researchers_paginator(researchers_result)

    def build_researchers_paginator(self, researchers_result):
        """Builds paginated search results for researchers."""
        page = self.request.GET.get("page")
        return self.paginated_queryset(researchers_result, page, 5)


class StudyParticipantContactView(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.DetailView,
):
    """
    StudyParticipantContactView lets you contact study participants.
    """

    model = Study
    # permission_required = "studies.can_edit_study"
    raise_exception = True
    template_name = "studies/study_participant_contact.html"

    def can_contact_participants(self):
        user = self.request.user
        study = self.get_object()
        user.has_study_perms(StudyPermission.CONTACT_STUDY_PARTICIPANTS, study)

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
            study.participants.select_related("organization")
            .order_by(
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
        """Pulls researchers that belong to Study Admin and Study Read groups.
        Currently same as StudyDetailView.get_study_researchers"""
        study = self.get_object()
        return User.objects.filter(
            Q(groups__name=study.study_admin_group.name)
            | Q(groups__name=study.study_read_group.name)
        )


class StudyResponsesList(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    PaginatorMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.DetailView,
):
    """
    View to acquire a list of study responses.
    """

    template_name = "studies/study_responses.html"
    queryset = Study.objects.all()
    # permission_required = "studies.can_view_study_responses"
    raise_exception = True

    def user_can_see_study_responses(self):
        user = self.request.user
        study = self.get_object()
        method = self.request.method

        if method == "GET":
            return user.has_study_perms(StudyPermission.READ_STUDY_RESPONSE_DATA, study)
        elif method == "POST":
            return user.has_study_perms(StudyPermission.EDIT_STUDY_FEEDBACK, study)

    test_func = user_can_see_study_responses

    def post(self, request, *args, **kwargs):
        """Currently, handles feedback form."""
        form_data = self.request.POST
        user = self.request.user

        # first, check the case for video download
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
            orderby = "-child__id" if reverse else "child__id"
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
        context["response_data"] = build_responses_json(
            paginated_responses, minimal_optional_headers
        )
        context["csv_data"] = [
            build_summary_csv([resp], minimal_optional_headers)
            for resp in paginated_responses
        ]

        context["frame_data"] = [
            build_single_response_framedata_csv(resp) for resp in paginated_responses
        ]
        context["response_data_full"] = build_responses_json(
            paginated_responses, ALL_OPTIONAL_HEADER_KEYS
        )
        context["csv_data_full"] = [
            build_summary_csv([resp], ALL_OPTIONAL_HEADER_KEYS)
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


class StudyResponsesConsentManager(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.DetailView,
):
    """Manage videos from here."""

    template_name = "studies/study_responses_consent_ruling.html"
    queryset = Study.objects.all()
    # permission_required = "studies.can_view_study_responses"
    raise_exception = True

    def user_can_encode_consent(self):
        user = self.request.user
        study = self.get_object()
        return user.has_study_perms(StudyPermission.CODE_STUDY_CONSENT, study)

    test_func = user_can_encode_consent

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

        paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            # two jobs - generate statistics and populate k/v store.
            for response in page_of_responses:

                response_json = response_key_value_store[str(response["uuid"])] = {}

                response["uuid"] = str(response.pop("uuid"))
                response_json["videos"] = response.pop("videos")

                response_json["details"] = {
                    "general": {
                        "uuid": response["uuid"],
                        "global_event_timings": json.dumps(
                            response.pop("global_event_timings")
                        ),
                        "sequence": json.dumps(response.pop("sequence")),
                        "completed": json.dumps(response.pop("completed")),
                        "date_created": str(response["date_created"]),
                    },
                    "participant": {
                        "hashed_id": hash_participant_id(response),
                        "uuid": str(response.pop("child__user__uuid")),
                        "nickname": response.pop("child__user__nickname"),
                    },
                    "child": {
                        "hashed_id": hash_child_id(response),
                        "uuid": str(response.pop("child__uuid")),
                        "name": response.pop("child__given_name"),
                        "birthday": str(response.pop("child__birthday")),
                        "gender": response.pop("child__gender"),
                        "additional_information": response.pop(
                            "child__additional_information"
                        ),
                    },
                }

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


# Definitions of optional columns that can be included in downloads in the individual
# responses and all responses views.
AGE_DATA_OPTIONS = [
    {
        "id": "rounded",
        "name": "Rounded age",
        "column": "child_age_rounded",
        "default": True,
    },
    {"id": "exact", "name": "Age in days", "column": "child_age_in_days"},
    {"id": "birthday", "name": "Birthdate", "column": "child_birthday"},
]
CHILD_DATA_OPTIONS = [
    {"id": "name", "name": "Child name", "column": "child_name"},
    {
        "id": "globalchild",
        "name": "Child global ID",
        "column": "child_global_id",
        "default": False,
    },
    {"id": "gender", "name": "Child gender", "column": "child_gender", "default": True},
    {"id": "gestage", "name": "Child gestational age", "column": "child_age_at_birth"},
    {
        "id": "conditions",
        "name": "Child conditions",
        "column": "child_characteristics",
        "default": True,
    },
    {
        "id": "languages",
        "name": "Child languages",
        "column": "child_languages",
        "default": True,
    },
    {
        "id": "addl",
        "name": "Child additional info",
        "column": "child_additional_information",
    },
    {"id": "parent", "name": "Parent name", "column": "participant_nickname"},
    {
        "id": "globalparent",
        "name": "Parent global ID",
        "column": "participant_global_id",
        "default": False,
    },
]
ALL_OPTIONAL_HEADER_KEYS = [
    option["id"] for option in AGE_DATA_OPTIONS + CHILD_DATA_OPTIONS
]

# ------- Helper functions for response downloads ----------------------------------------


def get_response_headers(optional_headers_selected_ids, all_headers_available):
    standard_headers = get_response_headers_and_row_data()["headers"]
    optional_headers = [
        option["column"] for option in AGE_DATA_OPTIONS + CHILD_DATA_OPTIONS
    ]
    selected_headers = [
        option["column"]
        for option in AGE_DATA_OPTIONS + CHILD_DATA_OPTIONS
        if option["id"] in optional_headers_selected_ids
    ]
    standard_headers_selected_only = [
        header
        for header in standard_headers
        if header not in optional_headers or header in selected_headers
    ]
    ordered_headers = standard_headers_selected_only + sorted(
        list(all_headers_available - set(standard_headers))
    )
    return ordered_headers


def build_responses_json(responses, optional_headers=None):
    """
    Builds the JSON response data for the researcher to download
    """
    # Note: this uses the actual response object rather than a dict returned by
    # values() because we use several properties (which cannot be retrieved by
    # values()), e.g. withdrawn and child__language_list.
    json_responses = []
    if optional_headers == None:
        optional_headers = []
    paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
    for page_num in paginator.page_range:
        page_of_responses = paginator.page(page_num)
        for resp in page_of_responses:
            age_in_days = (resp.date_created.date() - resp.child.birthday).days
            json_responses.append(
                {
                    "response": {
                        "id": resp.id,
                        "uuid": str(resp.uuid),
                        "sequence": resp.sequence,
                        "conditions": resp.conditions,
                        "exp_data": resp.exp_data,
                        "global_event_timings": resp.global_event_timings,
                        "completed": resp.completed,
                        "date_created": resp.date_created,
                        "withdrawn": resp.withdrawn,
                        "is_preview": resp.is_preview,
                    },
                    "study": {"uuid": str(resp.study.uuid)},
                    "participant": {
                        "global_id": str(resp.child.user.uuid)
                        if "globalparent" in optional_headers
                        else "",
                        "hashed_id": hash_id(
                            resp.child.user.uuid,
                            resp.study.uuid,
                            resp.study.salt,
                            resp.study.hash_digits,
                        ),
                        "nickname": resp.child.user.nickname
                        if "parent" in optional_headers
                        else "",
                    },
                    "child": {
                        "global_id": str(resp.child.uuid)
                        if "globalchild" in optional_headers
                        else "",
                        "hashed_id": hash_id(
                            resp.child.uuid,
                            resp.study.uuid,
                            resp.study.salt,
                            resp.study.hash_digits,
                        ),
                        "name": resp.child.given_name
                        if "name" in optional_headers
                        else "",
                        "birthday": resp.child.birthday
                        if "birthday" in optional_headers
                        else "",
                        "age_in_days": age_in_days
                        if "exact" in optional_headers
                        else "",
                        "age_rounded": str(round_age(int(age_in_days)))
                        if "rounded" in optional_headers
                        else "",
                        "gender": resp.child.gender
                        if "gender" in optional_headers
                        else "",
                        "language_list": resp.child.language_list
                        if "languages" in optional_headers
                        else "",
                        "condition_list": resp.child.condition_list
                        if "conditions" in optional_headers
                        else "",
                        "age_at_birth": resp.child.age_at_birth
                        if "gestage" in optional_headers
                        else "",
                        "additional_information": resp.child.additional_information
                        if "addl" in optional_headers
                        else "",
                    },
                    "consent": resp.current_consent_details,
                }
            )
    return json_responses


def get_response_headers_and_row_data(resp=None):
    # Note: this uses the actual response object rather than a dict returned by
    # values() because we use several properties (which cannot be retrieved by
    # values()):
    #
    # "withdrawn"
    # "most_recent_ruling",
    # "most_recent_ruling_arbiter",
    # "most_recent_ruling_date",
    # "most_recent_ruling_comment",
    # "child__language_list",
    # "child__condition_list"
    #
    # Iterating over the responses to fetch these properties would defeat the point
    # so we just use the object.

    age_in_days = (resp.date_created.date() - resp.child.birthday).days if resp else ""

    all_row_data = [
        ("response_id", resp.id if resp else "", "Short ID for this response"),
        (
            "response_uuid",
            str(resp.uuid) if resp else "",
            "Unique identifier for response. Can be used to match data to video filenames.",
        ),
        (
            "response_date_created",
            str(resp.date_created) if resp else "",
            "Timestamp for when participant began session, in format e.g. 2019-11-07 17:13:38.702958+00:00",
        ),
        (
            "response_completed",
            resp.completed if resp else "",
            "Whether the participant submitted the exit survey; depending on study criteria, this may not align with whether the session is considered complete. E.g., participant may have left early but submitted exit survey, or may have completed all test trials but not exit survey.",
        ),
        (
            "response_withdrawn",
            resp.withdrawn if resp else "",
            "Whether the participant withdrew permission for viewing/use of study video beyond consent video. If true, video will not be available and must not be used.",
        ),
        (
            "response_is_preview",
            resp.is_preview if resp else "",
            "Whether this response was generated by a researcher previewing the experiment. Preview data should not be used in any actual analyses.",
        ),
        (
            "response_consent_ruling",
            resp.most_recent_ruling if resp else "",
            "Most recent consent video ruling: one of 'accepted' (consent has been reviewed and judged to indidate informed consent), 'rejected' (consent has been reviewed and judged not to indicate informed consent -- e.g., video missing or parent did not read statement), or 'pending' (no current judgement, e.g. has not been reviewed yet or waiting on parent email response')",
        ),
        (
            "response_consent_arbiter",
            resp.most_recent_ruling_arbiter if resp else "",
            "Name associated with researcher account that made the most recent consent ruling",
        ),
        (
            "response_consent_time",
            resp.most_recent_ruling_date if resp else "",
            "Timestamp of most recent consent ruling, format e.g. 2019-12-09 20:40",
        ),
        (
            "response_consent_comment",
            resp.most_recent_ruling_comment if resp else "",
            "Comment associated with most recent consent ruling (may be used to track e.g. any cases where consent was confirmed by email)",
        ),
        (
            "study_uuid",
            str(resp.study.uuid) if resp else "",
            "Unique identifier of study associated with this response. Same for all responses to a given Lookit study.",
        ),
        (
            "participant_global_id",
            str(resp.child.user.uuid) if resp else "",
            "Unique identifier for family account associated with this response. Will be the same for multiple responses from a child and for siblings, and across different studies. MUST BE REDACTED FOR PUBLICATION because this allows identification of families across different published studies, which may have unintended privacy consequences. Researchers can use this ID to match participants across studies (subject to their own IRB review), but would need to generate their own random participant IDs for publication in that case. Use participant_hashed_id as a publication-safe alternative if only analyzing data from one Lookit study.",
        ),
        (
            "participant_hashed_id",
            hash_id(
                resp.child.user.uuid,
                resp.study.uuid,
                resp.study.salt,
                resp.study.hash_digits,
            )
            if resp
            else "",
            "Identifier for family account associated with this response. Will be the same for multiple responses from a child and for siblings, but is unique to this study. This may be published directly.",
        ),
        (
            "participant_nickname",
            resp.child.user.nickname if resp else "",
            "Nickname associated with the family account for this response - generally the mom or dad's name. Must be redacted for publication.",
        ),
        (
            "child_global_id",
            str(resp.child.uuid) if resp else "",
            "Primary unique identifier for the child associated with this response. Will be the same for multiple responses from one child, even across different Lookit studies. MUST BE REDACTED FOR PUBLICATION because this allows identification of children across different published studies, which may have unintended privacy consequences. Researchers can use this ID to match participants across studies (subject to their own IRB review), but would need to generate their own random participant IDs for publication in that case. Use child_hashed_id as a publication-safe alternative if only analyzing data from one Lookit study.",
        ),
        (
            "child_hashed_id",
            hash_id(
                resp.child.uuid,
                resp.study.uuid,
                resp.study.salt,
                resp.study.hash_digits,
            )
            if resp
            else "",
            "Identifier for child associated with this response. Will be the same for multiple responses from a child, but is unique to this study. This may be published directly.",
        ),
        (
            "child_name",
            resp.child.given_name if resp else "",
            "Nickname for the child associated with this response. Not necessarily a real name (we encourage initials, nicknames, etc. if parents aren't comfortable providing a name) but must be redacted for publication of data.",
        ),
        (
            "child_birthday",
            resp.child.birthday if resp else "",
            "Birthdate of child associated with this response. Must be redacted for publication of data (switch to age at time of participation; either use rounded age, jitter the age, or redact timestamps of participation).",
        ),
        (
            "child_age_in_days",
            age_in_days,
            "Age in days at time of response of child associated with this response, exact. This can be used in conjunction with timestamps to calculate the child's birthdate, so must be jittered or redacted prior to publication unless no timestamp information is shared.",
        ),
        (
            "child_age_rounded",
            str(round_age(int(age_in_days))) if age_in_days else "",
            "Age in days at time of response of child associated with this response, rounded to the nearest 10 days if under 1 year old and to the nearest 30 days if over 1 year old. May be published; however, if you have more than a few sessions per participant it would be possible to infer the exact age in days (and therefore birthdate) with some effort. In this case you might consider directly jittering birthdates.",
        ),
        (
            "child_gender",
            resp.child.gender if resp else "",
            "Parent-identified gender of child, one of 'm' (male), 'f' (female), 'o' (other), or 'na' (prefer not to answer)",
        ),
        (
            "child_age_at_birth",
            resp.child.age_at_birth if resp else "",
            "Gestational age at birth in weeks. One of '40 or more weeks', '39 weeks' through '24 weeks', 'Under 24 weeks', or 'Not sure or prefer not to answer'",
        ),
        (
            "child_language_list",
            resp.child.language_list if resp else "",
            "List of languages spoken (using language codes in Lookit docs), separated by spaces",
        ),
        (
            "child_condition_list",
            resp.child.condition_list if resp else "",
            "List of child characteristics (using condition/characteristic codes in Lookit docs), separated by spaces",
        ),
        (
            "child_additional_information",
            resp.child.additional_information if resp else "",
            "Free response 'anything else you'd like us to know' field on child registration form for child associated with this response. Should be redacted or reviewed prior to publication as it may include names or other identifying information.",
        ),
        (
            "response_sequence",
            resp.sequence if resp else [],
            "Each response_sequence.N field (response_sequence.0, response_sequence.1, etc.) gives the ID of the Nth frame displayed during the session associated with this response. Responses may have different sequences due to randomization or if a participant leaves early.",
        ),
        (
            "response_conditions",
            [
                {**{"frameName": condFrame}, **conds}
                for (condFrame, conds) in resp.conditions.items()
            ]
            if resp
            else [],
            "RESEARCHERS: EXPAND THIS SECTION BASED ON YOUR INDIVIDUAL STUDY. Each set of response_conditions.N.(...) fields give information about condition assignment during a particular frame of this study. response_conditions.0.frameName is the frame ID (corresponding to a value in response_sequence) where the randomization occured. Additional fields such as response_conditions.0.conditionNum depend on the specific randomizer frames used in this study.",
        ),
    ]

    headers_ordered = [name for (name, val, desc) in all_row_data][0:-2]

    field_descriptions = {name: desc for (name, val, desc) in all_row_data}

    row_data_with_headers = flatten_dict(
        {name: val for (name, val, desc) in all_row_data}
    )

    return {
        "headers": headers_ordered,
        "descriptions": field_descriptions,
        "dict": row_data_with_headers,
    }


def get_frame_data(resp):

    if type(resp) is not dict:
        resp = {
            "child__uuid": resp.child.uuid,
            "study__uuid": resp.study.uuid,
            "study__salt": resp.study.salt,
            "study__hash_digits": resp.study.hash_digits,
            "uuid": resp.uuid,
            "exp_data": resp.exp_data,
            "global_event_timings": resp.global_event_timings,
        }

    frame_data_dicts = []
    child_hashed_id = hash_id(
        resp["child__uuid"],
        resp["study__uuid"],
        resp["study__salt"],
        resp["study__hash_digits"],
    )

    # First add all of the global event timings as events with frame_id "global"
    for (iEvent, event) in enumerate(resp["global_event_timings"]):
        for (key, value) in event.items():
            frame_data_dicts.append(
                {
                    "child_hashed_id": child_hashed_id,
                    "response_uuid": str(resp["uuid"]),
                    "frame_id": "global",
                    "key": key,
                    "event_number": str(iEvent),
                    "value": value,
                }
            )

            # Next add all data in exp_data
    event_prefix = "eventTimings."
    for (frame_id, frame_data) in resp["exp_data"].items():
        for (key, value) in flatten_dict(frame_data).items():
            # Process event data separately and include event_number within frame
            if key.startswith(event_prefix):
                key_pieces = key.split(".")
                frame_data_dicts.append(
                    {
                        "child_hashed_id": child_hashed_id,
                        "response_uuid": str(resp["uuid"]),
                        "frame_id": frame_id,
                        "key": ".".join(key_pieces[2:]),
                        "event_number": str(key_pieces[1]),
                        "value": value,
                    }
                )
                # omit frameType values from CSV
            elif key == "frameType":
                continue
                # Omit empty generatedProperties values from CSV
            elif key == "generatedProperties" and not (value):
                continue
                # For all other data, create a regular entry with frame_id and no event #
            else:
                frame_data_dicts.append(
                    {
                        "child_hashed_id": child_hashed_id,
                        "response_uuid": str(resp["uuid"]),
                        "frame_id": frame_id,
                        "key": key,
                        "event_number": "",
                        "value": value,
                    }
                )

    headers = [
        (
            "response_uuid",
            "Unique identifier for this response; can be matched to summary data and video filenames",
        ),
        (
            "child_hashed_id",
            "Hashed identifier for the child associated with this response; can be matched to summary data child_hashed_id. This random ID may be published directly; it is specific to this study. If you need to match children across multiple studies, use the child_global_id.",
        ),
        (
            "frame_id",
            "Identifier for the particular frame responsible for this data; matches up to an element in the response_sequence in the summary data file",
        ),
        (
            "event_number",
            "Index of the event responsible for this data, if this is an event. Indexes start from 0 within each frame (and within global data) within each response.",
        ),
        (
            "key",
            "Label for a piece of data collected during this frame - for example, 'formData.child_favorite_animal'",
        ),
        (
            "value",
            "Value of the data associated with this key (of the indexed event if applicable) - for example, 'giraffe'",
        ),
    ]

    return {
        "data": frame_data_dicts,
        "data_headers": [header for (header, description) in headers],
        "header_descriptions": headers,
    }


def build_framedata_dict_csv(writer, responses):

    response_paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
    unique_frame_ids = set()
    event_keys = set()
    unique_frame_keys_dict = {}

    for page_num in response_paginator.page_range:
        page_of_responses = response_paginator.page(page_num)
        for resp in page_of_responses:
            this_resp_data = get_frame_data(resp)["data"]
            these_ids = [
                d["frame_id"].partition("-")[2]
                for d in this_resp_data
                if not d["frame_id"] == "global"
            ]
            event_keys = event_keys | set(
                [d["key"] for d in this_resp_data if d["event_number"] != ""]
            )
            unique_frame_ids = unique_frame_ids | set(these_ids)
            for frame_id in these_ids:
                these_keys = set(
                    [
                        d["key"]
                        for d in this_resp_data
                        if d["frame_id"].partition("-")[2] == frame_id
                        and d["event_number"] == ""
                    ]
                )
                if frame_id in unique_frame_keys_dict:
                    unique_frame_keys_dict[frame_id] = (
                        unique_frame_keys_dict[frame_id] | these_keys
                    )
                else:
                    unique_frame_keys_dict[frame_id] = these_keys

    # Start with general descriptions of high-level headers (child_id, response_id, etc.)
    header_descriptions = get_frame_data(resp)["header_descriptions"]
    writer.writerows(
        [
            {"column": header, "description": description}
            for (header, description) in header_descriptions
        ]
    )
    writer.writerow(
        {
            "possible_frame_id": "global",
            "frame_description": "Data not associated with a particular frame",
        }
    )

    # Add placeholders to describe each frame type
    unique_frame_ids = sorted(list(unique_frame_ids))
    for frame_id in unique_frame_ids:
        writer.writerow(
            {
                "possible_frame_id": "*-" + frame_id,
                "frame_description": "RESEARCHER: INSERT FRAME DESCRIPTION",
            }
        )
        unique_frame_keys = sorted(list(unique_frame_keys_dict[frame_id]))
        for k in unique_frame_keys:
            writer.writerow(
                {
                    "possible_frame_id": "*-" + frame_id,
                    "possible_key": k,
                    "key_description": "RESEARCHER: INSERT DESCRIPTION OF WHAT THIS KEY MEANS IN THIS FRAME",
                }
            )

    event_keys = sorted(list(event_keys))
    event_key_stock_descriptions = {
        "eventType": "Descriptor for this event; determines what other data is available. Global event 'exitEarly' records cases where the participant attempted to exit the study early by closing the tab/window or pressing F1 or ctrl-X. RESEARCHER: INSERT DESCRIPTIONS OF PARTICULAR EVENTTYPES USED IN YOUR STUDY. (Note: you can find a list of events recorded by each frame in the frame documentation at https://lookit.github.io/ember-lookit-frameplayer, under the Events header.)",
        "exitType": "Used in the global event exitEarly. Only value stored at this point is 'browserNavigationAttempt'",
        "lastPageSeen": "Used in the global event exitEarly. Index of the frame the participant was on before exit attempt.",
        "pipeId": "Recorded by any event in a video-capture-equipped frame. Internal video ID used by Pipe service; only useful for troubleshooting in rare cases.",
        "streamTime": "Recorded by any event in a video-capture-equipped frame. Indicates time within webcam video (videoId) to nearest 0.1 second. If recording has not started yet, may be 0 or null.",
        "timestamp": "Recorded by all events. Timestamp of event in format e.g. 2019-11-07T17:14:43.626Z",
        "videoId": "Recorded by any event in a video-capture-equipped frame. Filename (without .mp4 extension) of video currently being recorded.",
    }
    for k in event_keys:
        writer.writerow(
            {
                "possible_frame_id": "any (event data)",
                "possible_key": k,
                "key_description": event_key_stock_descriptions.get(
                    k, "RESEARCHER: INSERT DESCRIPTION OF WHAT THIS EVENT KEY MEANS"
                ),
            }
        )


def build_summary_csv(responses, optional_headers_selected_ids):
    """
    Builds CSV file contents for overview of all responses
    """

    headers = set()
    session_list = []

    paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
    for page_num in paginator.page_range:
        page_of_responses = paginator.page(page_num)
        for resp in page_of_responses:
            row_data = get_response_headers_and_row_data(resp)["dict"]
            # Add any new headers from this session
            headers = headers | set(row_data.keys())
            session_list.append(row_data)

    header_list = get_response_headers(optional_headers_selected_ids, headers)
    output, writer = csv_dict_output_and_writer(header_list)
    writer.writerows(session_list)
    return output.getvalue()


def build_single_response_framedata_csv(response):
    """
    Builds CSV file contents for frame-level data from a single response.
    """

    this_resp_data = get_frame_data(response)
    output, writer = csv_dict_output_and_writer(this_resp_data["data_headers"])
    writer.writerows(this_resp_data["data"])

    return output.getvalue()


# ------- End helper functions for response downloads ------------------------------------


class StudyResponsesAll(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.DetailView,
):
    """
    StudyResponsesAll shows a variety of download options for response and child data.
    """

    template_name = "studies/study_responses_all.html"
    queryset = Study.objects.all()
    # permission_required = "studies.can_view_study_responses"
    raise_exception = True
    http_method_names = ["get", "post"]

    # Which headers from the response data summary should go in the child data downloads
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

    def user_can_see_study_responses(self):
        user = self.request.user
        study = self.get_object()
        # TODO: What about POST - deleting preview data?
        return user.has_study_perms(StudyPermission.READ_STUDY_RESPONSE_DATA, study)

    test_func = user_can_see_study_responses

    def get_response_values_for_framedata(self, study):
        return (
            study.consented_responses.order_by("id")
            .select_related("child", "study")
            .values(
                "uuid",
                "exp_data",
                "child__uuid",
                "study__uuid",
                "study__salt",
                "study__hash_digits",
                "global_event_timings",
            )
        )

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.
        """
        context = super().get_context_data(**kwargs)
        context["n_responses"] = context["study"].consented_responses.count()
        context["childoptions"] = CHILD_DATA_OPTIONS
        context["ageoptions"] = AGE_DATA_OPTIONS
        return context

    def post(self, request, *args, **kwargs):
        """
        Post method on all responses view handles the  'delete all preview data' button.
        """
        study = self.get_object()
        preview_responses = study.responses.filter(is_preview=True).prefetch_related(
            "videos", "responselog_set", "consent_rulings", "feedback"
        )
        paginator = Paginator(preview_responses, RESPONSE_PAGE_SIZE)
        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                # response logs, consent rulings, feedback, videos will all be deleted
                # via cascades - videos will be removed from S3 also on pre_delete hook
                resp.delete()
        return super().get(request, *args, **kwargs)


class StudyResponsesAllDownloadJSON(StudyResponsesAll):
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
            build_responses_json(responses, header_options), indent=4, default=str
        )
        filename = "{}_{}.json".format(
            study_name_for_files(study.name), "all-responses"
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
        cleaned_data = build_summary_csv(responses, header_options)
        IDENTIFIABLE_DATA_OPTIONS = [
            "exact",
            "birthday",
            "name",
            "addl",
            "parent",
            "globalchild",
            "globalparent",
        ]
        filename = "{}_{}.csv".format(
            study_name_for_files(study.name),
            "all-responses"
            + (
                "-identifiable"
                if any(
                    [option in IDENTIFIABLE_DATA_OPTIONS for option in header_options]
                )
                else ""
            ),
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponsesSummaryDictCSV(StudyResponsesAll):
    """
    Hitting this URL downloads a data dictionary for the study response summary in CSV format. Does not depend on actual response data.
    """

    def build_summary_dict_csv(self, optional_headers_selected_ids):
        """
        Builds CSV file contents for data dictionary corresponding to the overview CSV
        """

        descriptions = get_response_headers_and_row_data()["descriptions"]
        headerList = get_response_headers(
            optional_headers_selected_ids, descriptions.keys()
        )
        all_descriptions = [
            {"column": header, "description": descriptions[header]}
            for header in headerList
        ]
        output, writer = csv_dict_output_and_writer(["column", "description"])
        writer.writerows(all_descriptions)
        return output.getvalue()

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        header_options = self.request.GET.getlist(
            "ageoptions"
        ) + self.request.GET.getlist("childoptions")
        cleaned_data = self.build_summary_dict_csv(header_options)
        filename = "{}_{}.csv".format(
            study_name_for_files(study.name), "all-responses-dict"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyChildrenSummaryCSV(StudyResponsesAll):
    """
    Hitting this URL downloads a summary of all children who participated in CSV format.
    """

    def build_child_csv(self, responses):
        """
        Builds CSV file contents for overview of all child participants
        """

        child_list = []
        session_list = []

        paginator = Paginator(responses, RESPONSE_PAGE_SIZE)

        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                row_data = get_response_headers_and_row_data(resp)["dict"]
                if row_data["child_global_id"] not in child_list:
                    child_list.append(row_data["child_global_id"])
                    session_list.append(row_data)

        output, writer = csv_dict_output_and_writer(self.child_csv_headers)
        writer.writerows(session_list)
        return output.getvalue()

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.consented_responses.order_by("id")
        cleaned_data = self.build_child_csv(responses)
        filename = "{}_{}.csv".format(
            study_name_for_files(study.name), "all-children-identifiable"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyChildrenSummaryDictCSV(StudyResponsesAll):
    """
    Hitting this URL downloads a data dictionary in CSV format for the summary of children who participated. Does not depend on actual response data.
    """

    def build_child_dict_csv(self):
        """
        Builds CSV file contents for data dictionary for overview of all child participants
        """

        descriptions = get_response_headers_and_row_data()["descriptions"]
        all_descriptions = [
            {"column": header, "description": descriptions[header]}
            for header in self.child_csv_headers
        ]
        output, writer = csv_dict_output_and_writer(["column", "description"])
        writer.writerows(all_descriptions)
        return output.getvalue()

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        cleaned_data = self.build_child_dict_csv()
        filename = "{}_{}.csv".format(
            study_name_for_files(study.name), "all-children-dict"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponsesFrameDataCSV(StudyResponsesAll):
    """
    Hitting this URL downloads frame-level data from all study responses in CSV format
    """

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = self.get_response_values_for_framedata(study)
        paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
        headers = get_frame_data(responses[0])["data_headers"]
        output, writer = csv_dict_output_and_writer(headers)

        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                this_resp_data = get_frame_data(resp)
                writer.writerows(this_resp_data["data"])

        cleaned_data = output.getvalue()

        filename = "{}_{}.csv".format(study_name_for_files(study.name), "all-frames")
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponsesFrameDataIndividualCSV(StudyResponsesAll):
    """Hitting this URL downloads a ZIP file with frame data from one response per file in CSV format"""

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = self.get_response_values_for_framedata(study)
        paginator = Paginator(responses, RESPONSE_PAGE_SIZE)

        zipped_file = io.BytesIO()  # import io
        with zipfile.ZipFile(
            zipped_file, "w", zipfile.ZIP_DEFLATED
        ) as zipped:  # import zipfile

            for page_num in paginator.page_range:
                page_of_responses = paginator.page(page_num)
                for resp in page_of_responses:
                    data = build_single_response_framedata_csv(resp)
                    filename = "{}_{}_{}.csv".format(
                        study_name_for_files(study.name), resp["uuid"], "frames"
                    )
                    zipped.writestr(filename, data)

        zipped_file.seek(0)
        response = HttpResponse(zipped_file, content_type="application/octet-stream")
        response[
            "Content-Disposition"
        ] = 'attachment; filename="{}_framedata_per_session.zip"'.format(
            study_name_for_files(study.name)
        )
        return response


class StudyResponsesFrameDataDictCSV(StudyResponsesAll):
    """
    Hitting this URL queues creation of a template data dictionary for frame-level data in CSV format. The file is put on GCP and a link is emailed to the user.
    """

    def get(self, request, *args, **kwargs):

        study = self.get_object()
        responses = self.get_response_values_for_framedata(study)
        filename = "{}_{}_{}".format(
            study_name_for_files(study.name), study.uuid, "all-frames-dict"
        )

        build_framedata_dict.delay(filename, study.uuid, self.request.user.uuid)
        messages.success(
            request,
            f"A frame data dictionary for {self.get_object().name} is being generated. You will be emailed a link when it's completed.",
        )
        return HttpResponseRedirect(
            reverse("exp:study-responses-all", kwargs=dict(pk=self.get_object().pk))
        )


class StudyDemographics(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.DetailView,
):
    """
    StudyParticiapnts view shows participant demographic snapshots associated
    with each response to the study
    """

    template_name = "studies/study_demographics.html"
    queryset = Study.objects.all()
    # permission_required = "studies.can_view_study_responses"
    raise_exception = True

    def user_can_view_study_responses(self):
        user = self.request.user
        study = self.get_object()
        return user.has_study_perms(StudyPermission.READ_STUDY_RESPONSE_DATA, study)

    test_func = user_can_view_study_responses

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.  Study results
        are paginated.
        """
        context = super().get_context_data(**kwargs)
        context["n_responses"] = context["study"].consented_responses.count()
        return context

    def get_demographic_headers(self, optional_header_ids=None):
        if optional_header_ids == None:
            optional_header_ids = []
        optional_header_ids_to_columns = {"globalparent": "participant_global_id"}
        allHeaders = self.get_csv_demographic_row_and_headers()["headers"]
        selectedHeaders = [
            optional_header_ids_to_columns[id]
            for id in optional_header_ids
            if id in optional_header_ids_to_columns
        ]
        optionalHeaders = optional_header_ids_to_columns.values()
        return [
            h for h in allHeaders if h not in optionalHeaders or h in selectedHeaders
        ]

    def get_response_values_for_demographics(self, study):
        return (
            study.consented_responses.order_by("id")
            .select_related("child", "child__user", "study", "demographic_snapshot")
            .values(
                "uuid",
                "child__user__uuid",
                "study__uuid",
                "study__salt",
                "study__hash_digits",
                "demographic_snapshot__uuid",
                "demographic_snapshot__created_at",
                "demographic_snapshot__number_of_children",
                "demographic_snapshot__child_birthdays",
                "demographic_snapshot__languages_spoken_at_home",
                "demographic_snapshot__number_of_guardians",
                "demographic_snapshot__number_of_guardians_explanation",
                "demographic_snapshot__race_identification",
                "demographic_snapshot__age",
                "demographic_snapshot__gender",
                "demographic_snapshot__education_level",
                "demographic_snapshot__spouse_education_level",
                "demographic_snapshot__annual_income",
                "demographic_snapshot__number_of_books",
                "demographic_snapshot__additional_comments",
                "demographic_snapshot__country",
                "demographic_snapshot__state",
                "demographic_snapshot__density",
                "demographic_snapshot__lookit_referrer",
                "demographic_snapshot__extra",
            )
        )

    def build_demographic_json(self, responses, optional_headers=None):
        """
        Builds a JSON representation of demographic snapshots for download
        """
        json_responses = []
        if optional_headers == None:
            optional_headers = []
        paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                json_responses.append(
                    json.dumps(
                        {
                            "response": {"uuid": str(resp["uuid"])},
                            "participant": {
                                "global_id": str(resp["child__user__uuid"])
                                if "globalparent" in optional_headers
                                else "",
                                "hashed_id": hash_participant_id(resp),
                            },
                            "demographic_snapshot": {
                                "hashed_id": hash_demographic_id(resp),
                                "date_created": str(
                                    resp["demographic_snapshot__created_at"]
                                ),
                                "number_of_children": resp[
                                    "demographic_snapshot__number_of_children"
                                ],
                                "child_rounded_ages": round_ages_from_birthdays(
                                    resp["demographic_snapshot__child_birthdays"],
                                    resp["demographic_snapshot__created_at"],
                                ),
                                "languages_spoken_at_home": resp[
                                    "demographic_snapshot__languages_spoken_at_home"
                                ],
                                "number_of_guardians": resp[
                                    "demographic_snapshot__number_of_guardians"
                                ],
                                "number_of_guardians_explanation": resp[
                                    "demographic_snapshot__number_of_guardians_explanation"
                                ],
                                "race_identification": resp[
                                    "demographic_snapshot__race_identification"
                                ],
                                "age": resp["demographic_snapshot__age"],
                                "gender": resp["demographic_snapshot__gender"],
                                "education_level": resp[
                                    "demographic_snapshot__education_level"
                                ],
                                "spouse_education_level": resp[
                                    "demographic_snapshot__spouse_education_level"
                                ],
                                "annual_income": resp[
                                    "demographic_snapshot__annual_income"
                                ],
                                "number_of_books": resp[
                                    "demographic_snapshot__number_of_books"
                                ],
                                "additional_comments": resp[
                                    "demographic_snapshot__additional_comments"
                                ],
                                "country": resp["demographic_snapshot__country"],
                                "state": resp["demographic_snapshot__state"],
                                "density": resp["demographic_snapshot__density"],
                                "lookit_referrer": resp[
                                    "demographic_snapshot__lookit_referrer"
                                ],
                                "extra": resp["demographic_snapshot__extra"],
                            },
                        },
                        indent=4,
                    )
                )
        return json_responses

    def get_csv_demographic_row_and_headers(self, resp=None):
        """
        Returns dict with headers, row data dict, and description dict for csv participant data associated with a response
        """

        all_row_data = [
            (
                "response_uuid",
                str(resp["uuid"]) if resp else "",
                "Primary unique identifier for response. Can be used to match demographic data to response data and video filenames; must be redacted prior to publication if videos are also published.",
            ),
            (
                "participant_global_id",
                str(resp["child__user__uuid"]) if resp else "",
                "Unique identifier for family account associated with this response. Will be the same for multiple responses from a child and for siblings, and across different studies. MUST BE REDACTED FOR PUBLICATION because this allows identification of families across different published studies, which may have unintended privacy consequences. Researchers can use this ID to match participants across studies (subject to their own IRB review), but would need to generate their own random participant IDs for publication in that case. Use participant_hashed_id as a publication-safe alternative if only analyzing data from one Lookit study.",
            ),
            (
                "participant_hashed_id",
                hash_participant_id(resp) if resp else "",
                "Identifier for family account associated with this response. Will be the same for multiple responses from a child and for siblings, but is unique to this study. This may be published directly.",
            ),
            (
                "demographic_hashed_id",
                hash_demographic_id(resp) if resp else "",
                "Identifier for this demographic snapshot. Changes upon updates to the demographic form, so may vary within the same participant across responses.",
            ),
            (
                "demographic_date_created",
                str(resp["demographic_snapshot__created_at"]) if resp else "",
                "Timestamp of creation of the demographic snapshot associated with this response, in format e.g. 2019-10-02 21:39:03.713283+00:00",
            ),
            (
                "demographic_number_of_children",
                resp["demographic_snapshot__number_of_children"] if resp else "",
                "Response to 'How many children do you have?'; options 0-10 or >10 (More than 10)",
            ),
            (
                "demographic_child_rounded_ages",
                round_ages_from_birthdays(
                    resp["demographic_snapshot__child_birthdays"],
                    resp["demographic_snapshot__created_at"],
                )
                if resp
                else "",
                "List of rounded ages based on child birthdays entered in demographic form (not based on children registered). Ages are in days, rounded to nearest 10 for ages under 1 year and nearest 30 otherwise. In format e.g. [60, 390]",
            ),
            (
                "demographic_languages_spoken_at_home",
                resp["demographic_snapshot__languages_spoken_at_home"] if resp else "",
                "Freeform response to 'What language(s) does your family speak at home?'",
            ),
            (
                "demographic_number_of_guardians",
                resp["demographic_snapshot__number_of_guardians"] if resp else "",
                "Response to 'How many parents/guardians do your children live with?' - 1, 2, 3> [3 or more], varies",
            ),
            (
                "demographic_number_of_guardians_explanation",
                resp["demographic_snapshot__number_of_guardians_explanation"]
                if resp
                else "",
                "Freeform response to 'If the answer varies due to shared custody arrangements or travel, please enter the number of parents/guardians your children are usually living with or explain.'",
            ),
            (
                "demographic_race_identification",
                resp["demographic_snapshot__race_identification"] if resp else "",
                "Comma-separated list of all values checked for question 'What category(ies) does your family identify as?', from list:  White; Hispanic, Latino, or Spanish origin; Black or African American; Asian; American Indian or Alaska Native; Middle Eastern or North African; Native Hawaiian or Other Pacific Islander; Another race, ethnicity, or origin",
            ),
            (
                "demographic_age",
                resp["demographic_snapshot__age"] if resp else "",
                "Parent's response to question 'What is your age?'; options are <18, 18-21, 22-24, 25-29, 30-34, 35-39, 40-44, 45-49, 50s, 60s, >70",
            ),
            (
                "demographic_gender",
                resp["demographic_snapshot__gender"] if resp else "",
                "Parent's response to question 'What is your gender?'; options are m [male], f [female], o [other], na [prefer not to answer]",
            ),
            (
                "demographic_education_level",
                resp["demographic_snapshot__education_level"] if resp else "",
                "Parent's response to question 'What is the highest level of education you've completed?'; options are some [some or attending high school], hs [high school diploma or GED], col [some or attending college], assoc [2-year college degree], bach [4-year college degree], grad [some or attending graduate or professional school], prof [graduate or professional degree]",
            ),
            (
                "demographic_spouse_education_level",
                resp["demographic_snapshot__spouse_education_level"] if resp else "",
                "Parent's response to question 'What is the highest level of education your spouse has completed?'; options are some [some or attending high school], hs [high school diploma or GED], col [some or attending college], assoc [2-year college degree], bach [4-year college degree], grad [some or attending graduate or professional school], prof [graduate or professional degree], na [not applicable - no spouse or partner]",
            ),
            (
                "demographic_annual_income",
                resp["demographic_snapshot__annual_income"] if resp else "",
                "Parent's response to question 'What is your approximate family yearly income (in US dollars)?'; options are 0, 5000, 10000, 15000, 20000-19000 in increments of 10000, >200000, or na [prefer not to answer]",
            ),
            (
                "demographic_number_of_books",
                resp["demographic_snapshot__number_of_books"] if resp else "",
                "Parent's response to question 'About how many children's books are there in your home?'; integer",
            ),
            (
                "demographic_additional_comments",
                resp["demographic_snapshot__additional_comments"] if resp else "",
                "Parent's freeform response to question 'Anything else you'd like us to know?'",
            ),
            (
                "demographic_country",
                resp["demographic_snapshot__country"] if resp else "",
                "Parent's response to question 'What country do you live in?'; 2-letter country code",
            ),
            (
                "demographic_state",
                resp["demographic_snapshot__state"] if resp else "",
                "Parent's response to question 'What state do you live in?' if country is US; 2-letter state abbreviation",
            ),
            (
                "demographic_density",
                resp["demographic_snapshot__density"] if resp else "",
                "Parent's response to question 'How would you describe the area where you live?'; options are urban, suburban, rural",
            ),
            (
                "demographic_lookit_referrer",
                resp["demographic_snapshot__lookit_referrer"] if resp else "",
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

    def build_all_demographic_csv(self, responses, optional_header_ids=None):
        """
        Builds CSV file contents for all participant data
        """

        participant_list = []
        theseHeaders = self.get_demographic_headers(optional_header_ids)

        paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                row_data = self.get_csv_demographic_row_and_headers(resp)["dict"]
                # Add any new headers from this session
                participant_list.append(row_data)

        output, writer = csv_dict_output_and_writer(theseHeaders)
        writer.writerows(participant_list)
        return output.getvalue()

    def build_all_demographic_dict_csv(self, optional_header_ids=None):
        """
        Builds CSV file contents for all participant data dictionary
        """

        descriptions = self.get_csv_demographic_row_and_headers()["descriptions"]
        theseHeaders = self.get_demographic_headers(optional_header_ids)
        all_descriptions = [
            {"column": key, "description": val}
            for (key, val) in descriptions.items()
            if key in theseHeaders
        ]
        output, writer = csv_dict_output_and_writer(["column", "description"])
        writer.writerows(all_descriptions)
        return output.getvalue()


class StudyDemographicsDownloadJSON(StudyDemographics):
    """
    Hitting this URL downloads all participant demographics in JSON format.
    """

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = self.get_response_values_for_demographics(study)
        header_options = self.request.GET.getlist("demooptions")
        cleaned_data = ", ".join(self.build_demographic_json(responses, header_options))
        filename = "{}_{}.json".format(
            study_name_for_files(study.name), "all-demographic-snapshots"
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
        responses = self.get_response_values_for_demographics(study)
        header_options = self.request.GET.getlist("demooptions")
        cleaned_data = self.build_all_demographic_csv(responses, header_options)
        filename = "{}_{}.csv".format(
            study_name_for_files(study.name), "all-demographic-snapshots"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyDemographicsDownloadDictCSV(StudyDemographics):
    """
    Hitting this URL downloads a data dictionary for participant demographics in in CSV format. Does not depend on any actual data.
    """

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        header_options = self.request.GET.getlist("demooptions")
        cleaned_data = self.build_all_demographic_dict_csv(header_options)
        filename = "{}_{}.csv".format(
            study_name_for_files(study.name), "all-demographic-snapshots-dict"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyCollisionCheck(StudyResponsesAll):
    """
    Hitting this URL checks for collisions among all child and account hashed IDs, and returns a string describing any collisions (empty string if none).
    """

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = (
            study.consented_responses.order_by("id")
            .select_related("child", "child__user", "study")
            .values(
                "uuid",
                "child__uuid",
                "child__user__uuid",
                "study__uuid",
                "study__salt",
                "study__hash_digits",
            )
        )
        child_dict = {}
        account_dict = {}
        collision_text = ""
        # Note: could also just check number of unique global vs. hashed IDs in full dataset; only checking one-by-one for more informative output.

        paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                participant_hashed_id = hash_participant_id(resp)
                participant_global_id = resp["child__user__uuid"]
                child_hashed_id = hash_child_id(resp)
                child_global_id = resp["child__uuid"]

                if participant_hashed_id in account_dict:
                    if participant_global_id != account_dict[participant_hashed_id]:
                        collision_text += "Participant hashed ID {} ({}, {})\n".format(
                            participant_hashed_id,
                            account_dict[participant_hashed_id],
                            participant_global_id,
                        )
                else:
                    account_dict[participant_hashed_id] = participant_global_id

                if child_hashed_id in child_dict:
                    if child_global_id != child_dict[child_hashed_id]:
                        collision_text += "Child hashed ID {} ({}, {})<br>".format(
                            child_hashed_id,
                            child_dict[child_hashed_id],
                            child_global_id,
                        )
                else:
                    child_dict[child_hashed_id] = child_global_id
        return JsonResponse({"collisions": collision_text})


class StudyAttachments(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    PaginatorMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.DetailView,
):
    """
    StudyAttachments View shows video attachments for the study
    """

    template_name = "studies/study_attachments.html"
    queryset = Study.objects.prefetch_related("responses", "videos")
    # permission_required = "studies.can_view_study_responses"
    raise_exception = True

    def user_can_see_study_responses(self):
        user = self.request.user
        study = self.get_object()

        return user.has_study_perms(StudyPermission.READ_STUDY_RESPONSE_DATA, study)

    test_func = user_can_see_study_responses

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


class StudyBuildView(generic.detail.SingleObjectMixin, generic.RedirectView):
    """
    Checks to make sure an existing build isn't running, that the user has permissions
    to build, and then triggers a build.
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
        return_path = self.request.POST.get("return", "exp:study-edit")
        return reverse(return_path, kwargs={"pk": str(self.object.pk)})

    def post(self, request, *args, **kwargs):
        user = self.request.user
        study = self.object

        if user.has_study_perms(StudyPermission.WRITE_STUDY_DETAILS, study):

            if not study.is_building:
                study.is_building = True
                study.save(update_fields=["is_building"])
                ember_build_and_gcp_deploy.delay(study.uuid, request.user.uuid)
                messages.success(
                    request,
                    f"Scheduled experiment runner build for {self.object.name}. You will be emailed when it's completed. This may take up to 30 minutes.",
                )
            else:
                messages.warning(
                    request,
                    f"Experiment runner for {self.object.name} is already building. This may take up to 30 minutes. You will be emailed when it's completed.",
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
    ExperimenterLoginRequiredMixin, ObjectPermissionRequiredMixin, generic.TemplateView
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
        paginator = Paginator(annotated_responses, RESPONSE_PAGE_SIZE)
        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
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


class StudyPreviewDetailView(
    ExperimenterLoginRequiredMixin, UserPassesTestMixin, generic.DetailView
):

    queryset = Study.objects.all()
    http_method_names = ["get", "post"]
    # permission_required = "accounts.can_view_experimenter"
    raise_exception = True
    template_name = "../../web/templates/web/study-detail.html"

    def can_view_preview_data(self):
        user = self.request.user
        study = self.get_object()

        return user.has_study_perms(StudyPermission.READ_STUDY_PREVIEW_DATA, study)

    test_func = can_view_preview_data

    def get_object(self, queryset=None):
        """
        Needed because view expecting pk or slug, but url has UUID. Looks up
        study by uuid.
        """
        uuid = self.kwargs.get("uuid")
        return get_object_or_404(Study, uuid=uuid)

    def get_context_data(self, **kwargs):
        """If user is authenticated, add demographic, children, and response data.

        Note: mostly copied from StudyDetailView in web/ until we can find the right
            abstraction for all this.
        """
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context["has_demographic"] = self.request.user.latest_demographics
            context["children"] = self.request.user.children.filter(deleted=False)
            context["preview_mode"] = True

        return context

    def post(self, request, *args, **kwargs):
        """POST override to act as GET would in RedirectView.

        TODO: No more POST masquerading as GET, rewrite the template and both the
            web and experimenter views to be more reasonably sane.
        """
        child_id = self.request.POST.get("child_id")
        kwargs["child_id"] = child_id
        return HttpResponseRedirect(reverse("exp:preview-proxy", kwargs=kwargs))


class PreviewProxyView(ExperimenterLoginRequiredMixin, UserPassesTestMixin, ProxyView):
    """
    Proxy view to forward researcher to preview page in the Ember app
    """

    # So we are definitely not doing PREVIEW_EXPERIMENT_BASE_URL anymore
    upstream = settings.EXPERIMENT_BASE_URL

    def user_can_view_previews(self):
        request = self.request
        kwargs = self.kwargs
        user = request.user

        try:
            child = Child.objects.get(uuid=kwargs.get("child_id", None))
        except Child.DoesNotExist:
            return False

        try:
            study = Study.objects.get(uuid=kwargs.get("uuid", None))
        except Study.DoesNotExist:
            return False

        if child.user != request.user:
            # requesting user doesn't belong to that child
            return False

        if study.shared_preview or user.has_study_perms(
            StudyPermission.READ_STUDY_PREVIEW_DATA, study
        ):
            return True
        else:
            return False

    test_func = user_can_view_previews

    def dispatch(self, request, *args, **kwargs):
        """Override to fix argument signature mismatch w.r.t. ProxyView.

        Also, the redirect functionality in revproxy is broken so we have to patch
        path replacement manually. Great! Just wonderful.
        """

        _, _, _, study_uuid, _, _, _, *rest = request.path.split("/")
        path = f"{study_uuid}/{'/'.join(rest)}"
        if not rest:
            path += "index.html"
        # path = f"{kwargs['uuid']}/index.html"

        return super().dispatch(request, path)


def get_flattened_responses(response_qs, studies_for_child):
    """Get derived attributes for children.

    TODO: consider whether or not this work should be extracted out into a dataframe.
    """
    response_data = []
    paginator = Paginator(response_qs, RESPONSE_PAGE_SIZE)
    for page_num in paginator.page_range:
        page_of_responses = paginator.page(page_num)
        for resp in page_of_responses:
            participation_date = resp["date_created"]
            child_age_in_days = (
                resp["date_created"].date() - resp["child__birthday"]
            ).days
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
                if not (
                    user.lab == study.lab
                    and user.has_perm(
                        LabPermission.CHANGE_STUDY_STATUS.codename, user.lab
                    )
                ):
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
