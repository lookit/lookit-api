import json
import operator
from functools import reduce
from typing import NamedTuple

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Q
from django.db.models.functions import Lower
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.http.response import HttpResponse
from django.shortcuts import get_object_or_404, reverse
from django.views import generic
from django.views.generic.detail import SingleObjectMixin
from revproxy.views import ProxyView

from accounts.models import Child, User
from exp.mixins.paginator_mixin import PaginatorMixin
from exp.views.mixins import (
    ResearcherLoginRequiredMixin,
    SingleObjectFetchProtocol,
    StudyTypeMixin,
)
from project import settings
from studies.forms import StudyCreateForm, StudyEditForm
from studies.helpers import send_mail
from studies.models import Study, StudyType
from studies.permissions import LabPermission, StudyPermission
from studies.queries import get_study_list_qs
from studies.tasks import ember_build_and_gcp_deploy
from studies.workflow import (
    COMMENTS_HELP_TEXT,
    STATE_UI_SIGNALS,
    STATUS_HELP_TEXT,
    TRANSITION_HELP_TEXT,
    TRANSITION_LABELS,
)
from web.views import create_external_response, get_external_url


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
    "url": "Study URL",
    "scheduling": "Scheduling",
    "study_platform": "Study Platform",
}

KEY_HELP_TEXT = {
    "url": "This is the link that participants will be sent to from the Lookit details page.",
    "scheduling": "Indicate how participants schedule appointments for your section. Remember that Lookit encourages you to use its messaging system rather than collecting email addresses - this presents a privacy risk for your participants.",
    "study_platform": "What software or website will you use to present & collect data for your study?",
}


class StudyCreateView(
    ResearcherLoginRequiredMixin,
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
        return self.request.user.is_researcher and self.request.user.can_create_study()

    # Make PyCharm happy - otherwise we'd just override get_test_func()
    test_func = user_can_make_study

    def form_valid(self, form):
        """
        Add the logged-in user as the study creator. If the form is valid,
        save the associated study and redirect to the supplied URL
        """

        user = self.request.user

        if form.cleaned_data["external"]:
            target_study_type = StudyType.get_external()
        else:
            target_study_type = StudyType.get_ember_frame_player()

        form.instance.metadata = self.extract_type_metadata(target_study_type)
        form.instance.creator = user
        form.instance.study_type = target_study_type

        # Add user to admin group for study.
        new_study = self.object = form.save()
        new_study.admin_group.user_set.add(user)
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
        context["study_types"] = StudyType.objects.all()
        context["key_display_names"] = KEY_DISPLAY_NAMES
        context["key_help_text"] = KEY_HELP_TEXT
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

    def form_invalid(self, form: StudyCreateForm) -> HttpResponse:
        if not form.is_valid():
            messages.error(self.request, form.errors)
        return super().form_invalid(form)


class StudyUpdateView(
    ResearcherLoginRequiredMixin,
    UserPassesTestMixin,
    StudyTypeMixin,
    SingleObjectFetchProtocol[Study],
    generic.UpdateView,
):
    """
    StudyUpdateView allows user to edit study metadata, add researchers to study, update researcher permissions, and delete researchers from study.
    Also allows you to update the study status.
    """

    model = Study
    template_name = "studies/study_edit.html"
    form_class = StudyEditForm
    raise_exception = True

    def user_can_edit_study(self):
        """Test predicate for the study editing view.

        Returns:
            True if this user can edit this Study, False otherwise

        """
        user: User = self.request.user  # Weird that PyCharm can't figure out the type?
        study = self.get_object()

        return user.is_researcher and user.has_study_perms(
            StudyPermission.WRITE_STUDY_DETAILS, study
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    # Make PyCharm happy - otherwise we'd just override
    # UserPassesTestMixin.get_test_func()
    test_func = user_can_edit_study

    def get_initial(self):
        """Get initial data for the study update form.

        Provides the exact_text stored in the structure field as the initial
        value to edit, to preserve ordering and formatting from user's standpoint.

        Provides the initial value of the generator function if current value is empty.

        Returns:
            A dictionary containing initial data for the form

        """
        initial = super().get_initial()
        # For editing, display the exact text that was used to generate the structure,
        # if available. We rely on form validation to make sure structure["exact_text"]
        # is valid JSON.
        structure = self.object.structure
        if structure:
            if "exact_text" in structure:
                initial["structure"] = structure["exact_text"]
            else:
                initial["structure"] = json.dumps(structure)
        if not self.object.generator.strip():
            initial["generator"] = StudyEditForm.base_fields["generator"].initial

        if self.object.study_type.is_external:
            initial["external"] = True
            initial["scheduled"] = self.object.metadata.get("scheduled", False)

        return initial

    def form_valid(self, form: StudyEditForm):
        study = form.instance

        metadata, meta_errors = self.validate_and_fetch_metadata(
            study_type=study.study_type
        )
        if meta_errors:
            messages.error(
                self.request,
                f'WARNING: Changes to experiment were not saved: {", ".join(meta_errors)}',
            )
        else:
            # Check that study type hasn't changed.
            if metadata != study.metadata:
                # Invalidate the previous build
                study.built = False
                # May still be building, but we're now good to allow another build
                study.is_building = False
                # Update metadata
                study.metadata = metadata

            study.save()
            messages.success(self.request, f"{study.name} study details saved.")

        return super().form_valid(form)

    def form_invalid(self, form: StudyEditForm):
        messages.error(self.request, form.errors)
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.
        """
        context = super().get_context_data(**kwargs)

        context["study_types"] = StudyType.objects.all()
        context["key_display_names"] = KEY_DISPLAY_NAMES
        context["key_help_text"] = KEY_HELP_TEXT
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
    ResearcherLoginRequiredMixin, UserPassesTestMixin, generic.ListView
):
    """
    StudyListView shows a list of studies that a user has permission to.
    """

    model = Study
    raise_exception = True
    template_name = "studies/study_list.html"
    paginate_by = 10
    ordering = ("name",)

    def can_see_study_list(self):
        return self.request.user.is_researcher

    test_func = can_see_study_list

    def get_queryset(self, *args, **kwargs):
        """
        Returns paginated list of items for the StudyListView - handles filtering on state, match,
        and sort.
        """
        user = self.request.user
        query_dict = self.request.GET

        queryset = get_study_list_qs(user, query_dict)  # READ_STUDY_DETAILS permission

        return queryset

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
    ResearcherLoginRequiredMixin,
    UserPassesTestMixin,
    PaginatorMixin,
    SingleObjectFetchProtocol[Study],
    generic.DetailView,
):
    """
    StudyDetailView shows information about a study. It can view basic metadata about a study and
    view study logs.
    """

    model = Study
    template_name = "studies/study_detail.html"
    raise_exception = True

    def user_can_see_or_edit_study_details(self):
        """Checks if user has permission to view study details.

        Returns:
            A boolean indicating whether or not the user should be able to see
            this view.
        """
        is_researcher = self.request.user.is_researcher
        has_perms = self.request.user.has_study_perms(
            StudyPermission.READ_STUDY_DETAILS, self.get_object()
        )
        return is_researcher and has_perms

    # Make PyCharm happy - otherwise we'd just override
    # UserPassesTestMixin.get_test_func()
    test_func = user_can_see_or_edit_study_details

    @property
    def study_logs(self):
        """Returns a page object with 10 study logs"""
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
        context["comments_help"] = json.dumps(COMMENTS_HELP_TEXT)
        context["transition_help"] = json.dumps(TRANSITION_HELP_TEXT)
        context["triggers_with_labels"] = [
            {"name": trigger, "label": TRANSITION_LABELS[trigger]}
            for trigger in context["triggers"]
        ]
        context["can_change_status"] = self.request.user.has_study_perms(
            StudyPermission.CHANGE_STUDY_STATUS, study
        )
        context["can_manage_researchers"] = self.request.user.has_study_perms(
            StudyPermission.MANAGE_STUDY_RESEARCHERS, study
        )
        context["can_create_study"] = self.request.user.can_create_study()
        # Since get_obj_perms template tag doesn't collect study + lab perms
        context["study_perms"] = self.request.user.perms_for_study(study)
        context["can_edit_study_details"] = (
            "edit_study__<DETAILS>" in context["study_perms"]
        )

        context["comments"] = self.comments(study)
        return context

    def comments(self, study: Study):
        if not study.lab.approved_to_test:
            return f"It is not possible to submit or start this study until the lab {study.lab.name} is approved to test."
        else:
            return study.comments

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


class ManageResearcherPermissionsView(
    ResearcherLoginRequiredMixin, UserPassesTestMixin, generic.DetailView
):
    model = Study

    def user_can_change_study_permissions(self):
        """Checks if user has permission to update researcher permissions.

        Returns:
            bool: Returns false if user does not have permission.
        """
        user = self.request.user
        return user.is_researcher and user.has_study_perms(
            StudyPermission.MANAGE_STUDY_RESEARCHERS, self.get_object()
        )

    # Make PyCharm happy - otherwise we'd just override
    # UserPassesTestMixin.get_test_func()
    test_func = user_can_change_study_permissions

    def post(self, *args, **kwargs):
        """Updates user permissions on form submission."""
        if not self.manage_researcher_permissions():
            return HttpResponseForbidden()

        return HttpResponseRedirect(
            reverse("exp:study-detail", kwargs=dict(pk=self.get_object().pk))
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
            from_email=study.lab.contact_email,
            **context,
        )

    def manage_researcher_permissions(self) -> bool:
        """
        Handles adding, updating, and deleting researcher from study. Users are
        added to study read group by default.
        """
        study = self.get_object()
        add_user_id = self.request.POST.get("add_user")
        remove_user_id = self.request.POST.get("remove_user")

        if self.request.POST.get("name") == "update_user":
            return self.update_user(study)

        elif add_user_id:
            return self.add_user(study, add_user_id)

        elif remove_user_id:
            return self.remove_user(study, remove_user_id)

        else:
            return True

    def update_user(self, study: Study) -> bool:
        roles_to_groups = {
            "study_preview": study.preview_group,
            "study_design": study.design_group,
            "study_analysis": study.analysis_group,
            "study_submission_processor": study.submission_processor_group,
            "study_researcher": study.researcher_group,
            "study_manager": study.manager_group,
            "study_admin": study.admin_group,
        }

        update_user = User.objects.get(pk=self.request.POST.get("pk"))

        # Enforce not changing a current admin unless there's another admin
        if self.user_only_admin(study, update_user):
            messages.error(
                self.request,
                "Could not change permissions for this researcher. There must be at least one study admin.",
                extra_tags="user_removed",
            )
            return False
        else:
            for study_group in study.all_study_groups():
                study_group.user_set.remove(update_user)

            enable_role = self.request.POST.get("value")
            update_user.groups.add(roles_to_groups[enable_role])
            self.send_study_email(update_user, enable_role)
            # TODO: format role name for email
            return True

    def add_user(self, study: Study, add_user_id) -> bool:
        # Adds user to study read by default
        user_to_add = User.objects.get(pk=add_user_id)
        user_to_add.groups.add(study.preview_group)
        messages.success(
            self.request,
            f"{user_to_add.get_short_name()} given {study.name} Preview Permissions.",
            extra_tags="user_added",
        )
        self.send_study_email(user_to_add, "study_preview")
        return True

    def remove_user(self, study: Study, remove_user_id) -> bool:
        # Removes user from both study read and study admin groups
        remove_user = User.objects.get(pk=remove_user_id)
        if self.user_only_admin(study, remove_user):
            messages.error(
                self.request,
                "Could not delete this researcher. There must be at least one study admin.",
                extra_tags="user_removed",
            )
            return False

        for study_group in study.all_study_groups():
            study_group.user_set.remove(remove_user)
        messages.success(
            self.request,
            f"{remove_user.get_short_name()} removed from {study.name}.",
            extra_tags="user_removed",
        )
        return True

    def user_only_admin(self, study: Study, user: User):
        return (
            study.admin_group in user.groups.all()
            and study.admin_group.user_set.count() <= 1
        )


class ChangeStudyStatusView(
    ResearcherLoginRequiredMixin, UserPassesTestMixin, generic.DetailView
):
    model = Study

    def user_can_change_study_status(self):
        """Checks that the user has permission to change study status.

        Returns:
            bool: Returns false if user does not have permission.
        """
        user = self.request.user
        return user.is_researcher and user.has_study_perms(
            StudyPermission.CHANGE_STUDY_STATUS, self.get_object()
        )

    # Make PyCharm happy - otherwise we'd just override
    # UserPassesTestMixin.get_test_func()
    test_func = user_can_change_study_status

    def post(self, *args, **kwargs):
        """Update study status on form submission."""
        try:
            self.update_trigger()
        except Exception as e:
            messages.error(self.request, f"TRANSITION ERROR: {e}")

        return HttpResponseRedirect(
            reverse("exp:study-detail", kwargs=dict(pk=self.get_object().pk))
        )

    def update_trigger(self):
        """Transition to next state in study workflow.

        :param self: An instance of the django view.
        :type self: StudyDetailView or StudyUpdateView
        """
        trigger = self.request.POST.get("trigger")
        object = self.get_object()
        if trigger:
            if hasattr(object, trigger):
                if "comments-text" in self.request.POST.keys():
                    object.comments = self.request.POST["comments-text"]
                    object.save()
                # transition through workflow state
                getattr(object, trigger)(user=self.request.user)
        displayed_state = object.state if object.state != "active" else "activated"
        messages.success(self.request, f"Study {object.name} {displayed_state}.")
        return object


class CloneStudyView(
    ResearcherLoginRequiredMixin, UserPassesTestMixin, generic.DetailView
):
    model = Study

    def user_can_clone_study(self):
        """Checks if user has permissions to clone study.

        Returns:
            bool: Returns false if user does not have permission.
        """
        user = self.request.user
        return user.is_researcher and user.can_create_study()

    test_func = user_can_clone_study

    def add_creator_to_study_admin_group(self, clone):
        """
        Add the study's creator to the clone's study admin group.
        """
        user = self.request.user
        study_admin_group = clone.admin_group
        user.groups.add(study_admin_group)
        return study_admin_group

    def post(self, *args, **kwargs):
        """Clone study on form submission."""
        orig_study = self.get_object()
        clone = orig_study.clone()
        clone.creator = self.request.user

        # Clone within the current lab if user is allowed to. Otherwise, choose the first possible
        if self.request.user.has_perm(
            LabPermission.CREATE_LAB_ASSOCIATED_STUDY.codename, obj=orig_study.lab
        ):
            clone.lab = orig_study.lab
        else:
            for lab in self.request.user.labs.only("id"):
                if clone.creator.has_perm(
                    LabPermission.CREATE_LAB_ASSOCIATED_STUDY.codename, obj=lab
                ):
                    clone.lab = lab
                    break
            else:
                # Shouldn't end up here because we checked can_create_study, but just in case
                return HttpResponseForbidden()

        clone.study_type = orig_study.study_type
        clone.built = False
        clone.is_building = False
        clone.comments = ""
        clone.save()

        # Adds success message when study is cloned
        messages.success(self.request, f"{orig_study.name} copied.")
        self.add_creator_to_study_admin_group(clone)
        return HttpResponseRedirect(reverse("exp:study-edit", kwargs=dict(pk=clone.pk)))


class StudyBuildView(
    ResearcherLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectFetchProtocol[Study],
    SingleObjectMixin,
    generic.RedirectView,
):
    """
    Checks to make sure an existing build isn't running, that the user has permissions
    to build, and then triggers a build.
    """

    model = Study
    http_method_names = ["post"]
    slug_url_kwarg = "uuid"
    slug_field = "uuid"

    def get_redirect_url(self, *args, **kwargs):
        return reverse("exp:study-detail", kwargs={"pk": str(self.get_object().pk)})

    def user_can_build_study(self):
        user = self.request.user
        study = self.get_object()
        if study.built or study.is_building:
            messages.warning(
                self.request,
                f"Experiment runner for {study.name} is already built or in progress. This may take up to 30 minutes. You will be emailed when it's completed.",
            )
            return False
        return user.is_researcher and user.has_study_perms(
            StudyPermission.WRITE_STUDY_DETAILS, study
        )

    test_func = user_can_build_study

    def post(self, request, *args, **kwargs):
        study = self.get_object()
        study.is_building = True
        study.save(update_fields=["is_building"])
        ember_build_and_gcp_deploy.delay(study.uuid, self.request.user.uuid)
        messages.success(
            request,
            f"Scheduled experiment runner build for {study.name}. You will be emailed when it's completed. This may take up to 30 minutes.",
        )
        return super().post(request, *args, **kwargs)


class StudyPreviewDetailView(
    ResearcherLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectFetchProtocol[Study],
    generic.DetailView,
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
        return user.is_researcher and (
            user.has_study_perms(StudyPermission.READ_STUDY_DETAILS, study)
            or (study.shared_preview and user.is_researcher)
        )

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
            web and researcher views to be more reasonably sane.
        """
        child_id = self.request.POST.get("child_id")
        kwargs["child_id"] = child_id
        return HttpResponseRedirect(reverse("exp:preview-proxy", kwargs=kwargs))


class PreviewProxyView(ResearcherLoginRequiredMixin, UserPassesTestMixin, ProxyView):
    """
    Proxy view to forward researcher to preview page in the Ember app
    """

    # So we are definitely not doing PREVIEW_EXPERIMENT_BASE_URL anymore
    upstream = settings.EXPERIMENT_BASE_URL

    def user_can_view_previews(self):
        request = self.request
        kwargs = self.kwargs
        user = request.user

        if not user.is_researcher:
            return False

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

        # Relevant permission in order to preview is READ_STUDY_DETAILS (previewing is essentially
        # examining the study protocol configuration), rather than READY_STUDY_PREVIEW_DATA
        # (which has to do with accessing data from other preview sessions)
        return (study.shared_preview and user.is_researcher) or user.has_study_perms(
            StudyPermission.READ_STUDY_DETAILS, study
        )

    test_func = user_can_view_previews

    def dispatch(self, request, *args, **kwargs):
        """Override to fix argument signature mismatch w.r.t. ProxyView.

        Also, the redirect functionality in revproxy is broken so we have to patch
        path replacement manually. Great! Just wonderful.
        """

        study = Study.objects.get(uuid=kwargs.get("uuid", None))

        if study.study_type.is_external:
            child_uuid = kwargs["child_id"]
            response = create_external_response(study, child_uuid, preview=True)
            return HttpResponseRedirect(get_external_url(study, response))
        else:
            _, _, _, study_uuid, _, _, _, *rest = request.path.split("/")
            path = f"{study_uuid}/{'/'.join(rest)}"
            if not rest:
                path += "index.html"
            path = f"{kwargs['uuid']}/index.html"

            return super().dispatch(request, path)


# UTILITY FUNCTIONS
def get_permitted_triggers(view_instance, triggers):
    """Takes in the available triggers (next possible states) for a study and restricts that list
    based on the current user's permissions and whether the lab has been approved.
    The view_instance is the StudyDetailView or the StudyUpdateView.
    """
    permitted_triggers = []
    user = view_instance.request.user
    study = view_instance.object
    lab_approved = study.lab.approved_to_test
    can_change_status = user.has_study_perms(StudyPermission.CHANGE_STUDY_STATUS, study)

    admin_triggers = ["approve", "reject"]

    only_for_approved_labs_triggers = ["activate", "approve", "submit", "resubmit"]

    for trigger in triggers:
        # remove autogenerated triggers
        if trigger.startswith("to_"):
            continue

        if trigger in only_for_approved_labs_triggers and not lab_approved:
            continue

        if (
            not user.has_perm(StudyPermission.APPROVE_REJECT_STUDY.prefixed_codename)
        ) and (not can_change_status or (trigger in admin_triggers)):
            continue

        permitted_triggers.append(trigger)

    return permitted_triggers
