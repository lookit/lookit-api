import json
import operator
from functools import reduce
from typing import NamedTuple

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Q
from django.db.models.functions import Lower
from django.http import Http404, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, reverse
from django.utils.text import slugify
from django.views import generic
from revproxy.views import ProxyView

from accounts.models import Child, Message, User
from accounts.utils import hash_id
from exp.mixins.paginator_mixin import PaginatorMixin
from exp.views.mixins import (
    ExperimenterLoginRequiredMixin,
    SingleObjectParsimoniousQueryMixin,
    StudyTypeMixin,
)
from project import settings
from studies.forms import StudyCreateForm, StudyEditForm
from studies.helpers import send_mail
from studies.models import Study, StudyType
from studies.permissions import StudyPermission
from studies.queries import get_study_list_qs
from studies.tasks import ember_build_and_gcp_deploy
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


KEY_DISPLAY_NAMES = {
    "player_repo_url": "Experiment runner code URL",
    "last_known_player_sha": "Experiment runner version (commit SHA)",
}


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
    raise_exception = True
    form_class = StudyCreateForm

    def user_can_make_study(self):
        # If returning False,
        # should effectively delegate to the correct handler by way of
        # View.dispatch()
        return self.request.user.can_create_study()

    # Make PyCharm happy - otherwise we'd just override get_test_func()
    test_func = user_can_make_study

    def form_valid(self, form):
        """
        Add the logged-in user as the study creator. If the form is valid,
        save the associated study and redirect to the supplied URL
        """
        user = self.request.user
        target_study_type_id = self.request.POST["study_type"]
        target_study_type = StudyType.objects.get(id=target_study_type_id)
        form.instance.metadata = self.extract_type_metadata(target_study_type)
        form.instance.creator = user
        # Add user to admin group for study.
        new_study = self.object = form.save()
        new_study.admin_group.add(user)  # TODO does this actually work?
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
        initial["structure"] = json.dumps(Study._meta.get_field("structure").default())
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs


class StudyUpdateView(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
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
    raise_exception = True

    def user_can_edit_study(self):
        """Test predicate for the study editing view."""
        user = self.request.user
        # If we end up using method, this will be useful.
        # method = self.request.method
        study = self.get_object()

        return user.has_study_perms(StudyPermission.WRITE_STUDY_DETAILS, study)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

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
    raise_exception = True
    template_name = "studies/study_list.html"

    def get_queryset(self, *args, **kwargs):
        """
        Returns paginated list of items for the StudyListView - handles filtering on state, match,
        and sort.
        """
        user = self.request.user
        query_dict = self.request.GET

        queryset = get_study_list_qs(user, query_dict)  # READ_STUDY_DETAILS permission

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
        context["can_create_study"] = self.request.user.can_create_study()
        return context


class StudyDetailView(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    PaginatorMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.DetailView,
):
    """
    StudyDetailView shows information about a study. Can view basic metadata about a study,
    view study logs, manage study researchers, and change a study's state.
    """

    template_name = "studies/study_detail.html"
    model = Study
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
            if (
                "add_user" in self.request.POST
                or "remove_user" in self.request.POST
                or self.request.POST.get("name") == "update_user"
            ):
                return user.has_study_perms(
                    StudyPermission.MANAGE_STUDY_RESEARCHERS, study
                )
            if "trigger" in self.request.POST:
                return user.has_study_perms(StudyPermission.CHANGE_STUDY_STATUS, study)
            if "clone_study" in self.request.POST:
                return user.can_create_study()
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
        # Manage researchers case
        if (
            "add_user" in self.request.POST
            or "remove_user" in self.request.POST
            or self.request.POST.get("name") == "update_user"
        ):

            try:
                self.manage_researcher_permissions()
            except AssertionError:
                return HttpResponseForbidden()
        # Change study status case
        if "trigger" in self.request.POST:
            try:
                update_trigger(self)
            except Exception as e:
                messages.error(self.request, f"TRANSITION ERROR: {e}")
                return HttpResponseRedirect(
                    reverse("exp:study-detail", kwargs=dict(pk=self.get_object().pk))
                )
        # Clone study case
        if self.request.POST.get("clone_study"):
            clone = self.get_object().clone()
            clone.creator = self.request.user
            clone.lab = self.request.user.labs.first()
            clone.study_type = self.get_object().study_type
            clone.built = False
            clone.is_building = False
            clone.save()
            # Adds success message when study is cloned
            messages.success(self.request, f"{self.get_object().name} copied.")
            self.add_creator_to_study_admin_group(clone)
            return HttpResponseRedirect(
                reverse("exp:study-edit", kwargs=dict(pk=clone.pk))
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
        study_admin_group = study.admin_group
        id_of_user_to_add = self.request.POST.get("add_user")
        id_of_user_to_remove = self.request.POST.get("remove_user")

        roles_to_groups = {
            "study_preview": study.preview_group,
            "study_design": study.design_group,
            "study_analysis": study.analysis_group,
            "study_submission_processor": study.submission_processor_group,
            "study_researcher": study.researcher_group,
            "study_manager": study.manager_group,
            "study_admin": study.admin_group,
        }

        if self.request.POST.get("name") == "update_user":
            id_of_user_to_update = self.request.POST.get("pk")
            name_of_role_to_enable = self.request.POST.get("value")

            if id_of_user_to_update:
                user_to_update = User.objects.get(pk=id_of_user_to_update)
                if name_of_role_to_enable in roles_to_groups:
                    # Enforce not changing a current admin unless there's another admin
                    if study_admin_group in user_to_update.groups.all():
                        if study_admin_group.user_set.count() <= 1:
                            messages.error(
                                self.request,
                                "Could not change permissions for this researcher. There must be at least one study admin.",
                                extra_tags="user_removed",
                            )
                        assert study_admin_group.user_set.count() > 1
                    for gr in study.all_study_groups():
                        gr.user_set.remove(user_to_update)
                    user_to_update.groups.add(roles_to_groups[name_of_role_to_enable])
                    self.send_study_email(
                        user_to_update, name_of_role_to_enable
                    )  # TODO: format role name for email
        if id_of_user_to_add:
            # Adds user to study read by default
            user_to_add = User.objects.get(pk=id_of_user_to_add)
            user_to_add.groups.add(study.preview_group)
            messages.success(
                self.request,
                f"{user_to_add.get_short_name()} given {study.name} Preview Permissions.",
                extra_tags="user_added",
            )
            self.send_study_email(user_to_add, "study_preview")
        if id_of_user_to_remove:
            # Removes user from both study read and study admin groups
            user_to_remove = User.objects.get(pk=id_of_user_to_remove)
            if (
                study_admin_group in user_to_remove.groups.all()
                and study_admin_group.user_set.count() <= 1
            ):
                messages.error(
                    self.request,
                    "Could not delete this researcher. There must be at least one study admin.",
                    extra_tags="user_removed",
                )
                return
            for gr in study.all_study_groups():
                gr.user_set.remove(user_to_remove)
            messages.success(
                self.request,
                f"{user_to_remove.get_short_name()} removed from {study.name}.",
                extra_tags="user_removed",
            )

    def send_study_email(self, user, permission):
        study = self.get_object()
        context = {
            "permission": permission,
            "study_name": study.name,
            "study_id": study.id,
            "lab_name": study.lab.name,
            "researcher_name": user.get_short_name(),
        }
        send_mail.delay(
            "notify_researcher_of_study_permissions",
            f"New access granted for study {self.get_object().name}",
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
        context["current_researchers"] = self.get_annotated_study_researchers()
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
        """Pulls researchers that belong to any study access groups for displaying/managing that access

        Not showing Lab admin & Lab read in this list (even though they technically can view the project)
        """
        study = self.get_object()
        all_study_users = reduce(
            lambda x, y: (x | y),
            [group.user_set.all() for group in study.all_study_groups()],
            User.objects.none(),
        )
        return all_study_users

    def get_annotated_study_researchers(self):
        """Gets current study researchers and their highest-level study-specific perm descriptions"""
        study = self.get_object()
        study_researchers = self.get_study_researchers()
        return [
            {"current_group": study.get_group_of_researcher(user), "user": user}
            for user in study_researchers
        ]

    def search_researchers(self):
        """Searches user first, last, and middle names for search query.
        Does not display researchers that are already on project.
        """
        current_researcher_ids = self.get_study_researchers().values_list(
            "id", flat=True
        )
        user_queryset = User.objects.filter(lab=self.get_object().lab, is_active=True)
        search_query = self.request.GET.get("match", None)
        if search_query:
            user_queryset = user_queryset.filter(
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
        researchers_result = (
            user_queryset.exclude(id__in=current_researcher_ids)
            .distinct()
            .order_by(Lower("family_name").asc())
        )

        return self.build_researchers_paginator(researchers_result)

    def build_researchers_paginator(self, researchers_result):
        """Builds paginated search results for researchers."""
        page = self.request.GET.get("page")
        return self.paginated_queryset(researchers_result, page, 10)


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

    def get_researchers(self):  # TODO
        """Pulls researchers that can contact participants."""
        study = self.get_object()
        return get_users_with_perms(
            study,
            only_with_perms_in=[StudyPermission.CONTACT_STUDY_PARTICIPANTS.codename],
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


class StudyPreviewDetailView(
    ExperimenterLoginRequiredMixin, UserPassesTestMixin, generic.DetailView
):

    queryset = Study.objects.all()
    http_method_names = ["get", "post"]
    raise_exception = True
    template_name = "../../web/templates/web/study-detail.html"

    def can_preview(self):
        user = self.request.user
        study = self.get_object()
        # Relevant permission in order to preview is READ_STUDY_DETAILS (previewing is essentially
        # examining the study protocol configuration), rather than READY_STUDY_PREVIEW_DATA
        # (which has to do with accessing data from other preview sessions)
        return user.has_study_perms(StudyPermission.READ_STUDY_DETAILS, study)

    test_func = can_preview

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
            StudyPermission.READ_STUDY_DETAILS, study
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


# UTILITY FUNCTIONS
def get_permitted_triggers(view_instance, triggers):
    """Takes in the available triggers (next possible states) for a study and restricts that list
    based on the current user's permissions.
    The view_instance is the StudyDetailView or the StudyUpdateView.
    """
    permitted_triggers = []
    user = view_instance.request.user
    study = view_instance.object
    can_change_status = user.has_study_perms(StudyPermission.CHANGE_STUDY_STATUS, study)

    admin_triggers = ["approve"]

    for trigger in triggers:
        # remove autogenerated triggers
        if trigger.startswith("to_"):
            continue

        # Trigger valid if superuser or user can change study status and trigger is non-admin-only
        if (not user.is_superuser) and (
            (trigger in admin_triggers) or not can_change_status
        ):
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
