import operator
from functools import reduce

from django.contrib import messages
from django.contrib.auth.mixins import (
    PermissionRequiredMixin as DjangoPermissionRequiredMixin,
)
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.db.models.functions import Lower
from django.http import Http404
from django.shortcuts import reverse
from django.views import generic
from guardian.mixins import PermissionRequiredMixin
from guardian.shortcuts import get_objects_for_user

from accounts.forms import UserStudiesForm
from accounts.models import User
from accounts.utils import build_org_group_name
from exp.mixins.paginator_mixin import PaginatorMixin
from exp.mixins.participant_mixin import ParticipantMixin
from exp.views.mixins import ExperimenterLoginRequiredMixin
from project.settings import EXPERIMENTER_LOGIN_URL as login_url
from studies.helpers import send_mail
from studies.models import Response
from studies.queries import get_consented_responses_qs


class ParticipantListView(
    ExperimenterLoginRequiredMixin, ParticipantMixin, generic.ListView, PaginatorMixin
):
    """
    ParticipantListView shows a list of participants that have responded to the studies the
    user has permission to view.
    """

    template_name = "accounts/participant_list.html"

    def get_queryset(self):
        """
        Returns users that researcher has permission to view. Handles sorting and pagination.
        """
        qs = super().get_queryset()
        match = self.request.GET.get("match", False)
        order = self.request.GET.get("sort", "nickname")
        if "nickname" not in order and "last_login" not in order:
            order = "nickname"

        if match:
            qs = qs.filter(
                reduce(
                    operator.or_,
                    (Q(nickname__icontains=term) for term in match.split()),
                )
            )
        return self.paginated_queryset(
            qs.order_by(order), self.request.GET.get("page"), 10
        )

    def get_context_data(self, **kwargs):
        """
        Adds match and sort query params to context_data dict
        """
        context = super().get_context_data(**kwargs)
        context["match"] = self.request.GET.get("match", "")
        context["sort"] = self.request.GET.get("sort", "")
        return context


class ParticipantDetailView(
    ExperimenterLoginRequiredMixin, ParticipantMixin, generic.DetailView, PaginatorMixin
):
    """
    ParticipantDetailView shows demographic information, children information, and
    studies that a participant has responded to.

    Participant (account) + demographic data should only show up if the participant
    has at least one child who has at least one confirmed-consented response that the
    researcher can see. Each child should only show up if they have such a response, i.e.
    the siblings don't show up "for free."
    """

    fields = ("is_active",)
    template_name = "accounts/participant_detail.html"

    def get_context_data(self, **kwargs):
        """
        Adds user's latest demographics and studies to the context_data dictionary
        """
        context = super().get_context_data(**kwargs)
        user = context["user"]
        context["demographics"] = (
            user.latest_demographics.to_display() if user.latest_demographics else None
        )
        context["studies"] = self.get_study_info()
        context["children"] = user.children.filter(
            id__in=self.valid_responses().values_list("child", flat=True)
        )
        return context

    def get_study_info(self):
        """
        Returns paginated responses from a user with the study title, response
        id, completion status, and date modified.
        """
        resps = (
            self.valid_responses()
            .filter(child__user=self.get_object())
            .select_related("child__user")
        )
        orderby = self.request.GET.get("sort", "-date_created")
        if orderby:
            if "date_created" in orderby:
                resps = resps.order_by(orderby)
            elif "completed" in orderby:
                resps = resps.order_by(
                    orderby.replace("-", "") if "-" in orderby else "-" + orderby
                )
        studies = [
            {
                "modified": resp.date_modified,
                "created": resp.date_created,
                "study": resp.study,
                "name": resp.study.name,
                "completed": resp.completed,
                "response": resp,
            }
            for resp in resps
        ]
        if orderby and "name" in orderby:
            studies = sorted(
                studies,
                key=operator.itemgetter("name"),
                reverse=True if "-" in orderby else False,
            )
        return self.paginated_queryset(studies, self.request.GET.get("page"), 10)

    def get_success_url(self):
        return reverse("exp:participant-detail", kwargs={"pk": self.object.id})


class ResearcherListView(
    ExperimenterLoginRequiredMixin,
    DjangoPermissionRequiredMixin,
    generic.ListView,
    PaginatorMixin,
):
    """
    Displays a list of researchers that belong to the org admin, org read, or org researcher groups.
    """

    template_name = "accounts/researcher_list.html"
    queryset = User.objects.filter(is_researcher=True, is_active=True)
    model = User
    permission_required = "accounts.can_view_organization"  # TODO
    raise_exception = True

    def get_org_groups(self):
        """
        Fetches the org admin, org read, and org researcher groups for the organization that
        the current user belongs to
        """
        # TODO: change organization -> lab(s) if we actually need this
        user_org = self.request.user.organization
        if user_org:
            user_org_name = user_org.name
            admin_group = Group.objects.get(
                name=build_org_group_name(user_org_name, "admin")
            )
            read_group = Group.objects.get(
                name=build_org_group_name(user_org_name, "read")
            )
            researcher_group = Group.objects.get(
                name=build_org_group_name(user_org_name, "researcher")
            )
            return admin_group, read_group, researcher_group
        else:
            raise PermissionDenied

    # TODO: adapt for lab
    def get_queryset(self):
        """
        Restricts queryset on active users that belong to the org admin, org read, or org researcher groups. Handles filtering on name and sorting.
        """
        qs = super().get_queryset()
        admin_group, read_group, researcher_group = self.get_org_groups()
        queryset = (
            qs.filter(
                Q(
                    Q(
                        Q(groups=admin_group)
                        | Q(groups=read_group)
                        | Q(groups=researcher_group)
                    )
                    | Q(
                        is_researcher=True,
                        groups__isnull=True,
                        organization__isnull=True,
                    )
                )
            )
            .distinct()
            .order_by(Lower("family_name").asc())
        )

        match = self.request.GET.get("match")
        # Can filter on first, middle, and last names
        queryset = queryset.select_related("organization")

        if match:
            queryset = queryset.filter(
                reduce(
                    operator.or_,
                    (
                        Q(family_name__icontains=term)
                        | Q(given_name__icontains=term)
                        | Q(middle_name__icontains=term)
                        for term in match.split()
                    ),
                )
            )
        sort = self.request.GET.get("sort")
        if sort:
            if "family_name" in sort:
                queryset = (
                    queryset.order_by(Lower("family_name").desc())
                    if "-" in sort
                    else queryset.order_by(Lower("family_name").asc())
                )
            if "permissions" in sort:
                queryset = sorted(
                    queryset,
                    key=lambda m: m.display_permission,
                    reverse=True if "-" in sort else False,
                )
        return self.paginated_queryset(queryset, self.request.GET.get("page"), 10)

    # TODO: adapt for lab
    def post(self, request, *args, **kwargs):
        """
        Post form for disabling a researcher. If researcher is deleted - is actually disabled, then removed
        from org admin, org read, and org researcher groups.
        """
        retval = super().get(request, *args, **kwargs)
        if "disable" in self.request.POST and self.request.method == "POST":
            researcher = User.objects.get(pk=self.request.POST["disable"])
            researcher.is_active = False
            researcher.save()
            messages.success(
                self.request,
                f"{researcher.get_short_name()} removed from the {self.request.user.organization.name} organization.",
            )
            self.remove_researcher_from_org_groups(researcher)
        return retval

    def remove_researcher_from_org_groups(self, researcher):
        """
        Post form for disabling a researcher. If researcher is deleted - is actually disabled, then removed
        from org admin, org read, and org researcher groups.
        """
        # TODO: remove from labs
        admin_group, read_group, researcher_group = self.get_org_groups()
        admin_group.user_set.remove(researcher)
        read_group.user_set.remove(researcher)
        researcher_group.user_set.remove(researcher)
        return

    def get_context_data(self, **kwargs):
        """
        Adds match and sort query params to the context data
        """
        context = super().get_context_data(**kwargs)
        context["match"] = self.request.GET.get("match", "")
        context["sort"] = self.request.GET.get("sort", "")
        return context


# TODO: adapt for Lab
class ResearcherDetailView(
    ExperimenterLoginRequiredMixin, DjangoPermissionRequiredMixin, generic.UpdateView
):
    """
    ResearcherDetailView shows information about a researcher and allows toggling the permissions
    on a user or modifying.
    """

    queryset = User.objects.filter(is_researcher=True, is_active=True)
    fields = ("is_active",)
    template_name = "accounts/researcher_detail.html"
    model = User
    permission_required = "accounts.can_edit_organization"
    raise_exception = True

    def get_queryset(self):
        """
        Restrict queryset so org admins can only modify users in their organization
        or unaffiliated researchers.
        """
        qs = super().get_queryset()
        return qs.filter(
            Q(
                Q(organization=self.request.user.organization)
                | Q(is_researcher=True, groups__isnull=True, organization__isnull=True)
            )
        ).distinct()

    def get_success_url(self):
        return reverse("exp:researcher-detail", kwargs={"pk": self.object.id})

    def send_reset_password_email(self):
        """
        Send reset_password email to researcher
        """
        context = {
            "researcher_name": self.object.get_short_name(),
            "org_name": self.request.user.organization.name,
            "login_url": login_url,
        }
        subject = "Reset OSF password to login to Experimenter"
        send_mail.delay("reset_password", subject, self.object.username, **context)
        messages.success(
            self.request, f"Reset password email sent to {self.object.username}."
        )
        return

    def send_resend_confirmation_email(self):
        """
        Send resend_confirmation_email to researcher
        """
        context = {
            "researcher_name": self.object.get_short_name(),
            "org_name": self.request.user.organization.name,
            "login_url": login_url,
        }
        subject = "Confirm OSF account to login to Experimenter"
        send_mail.delay("resend_confirmation", subject, self.object.username, **context)
        messages.success(
            self.request, f"Confirmation email resent to {self.object.username}."
        )
        return

    def post(self, request, *args, **kwargs):
        """
        Handles modification of user given_name, middle_name, family_name as well as
        user permissions
        """
        retval = super().post(request, *args, **kwargs)

        if "reset_password" in self.request.POST:
            self.send_reset_password_email()
        elif "resend_confirmation" in self.request.POST:
            self.send_resend_confirmation_email()
        else:
            changed_field = self.request.POST.get("name")
            if changed_field == "given_name":
                self.object.given_name = self.request.POST["value"]
            elif changed_field == "middle_name":
                self.object.middle_name = self.request.POST["value"]
            elif changed_field == "family_name":
                self.object.family_name = self.request.POST["value"]
            if self.request.POST.get("name") == "user_permissions":
                self.modify_researcher_permissions()
        self.object.is_active = True
        self.object.save()
        return retval

    # TODO: adapt for Lab
    def modify_researcher_permissions(self):
        """
        Modifies researcher permissions by adding the user to the respective admin,
        read, or researcher group. They inherit the permissions of that org group.
        """
        new_perm = self.request.POST["value"]
        org_name = self.request.user.organization.name

        admin_group = Group.objects.get(name=build_org_group_name(org_name, "admin"))
        read_group = Group.objects.get(name=build_org_group_name(org_name, "read"))
        researcher_group = Group.objects.get(
            name=build_org_group_name(org_name, "researcher")
        )

        researcher = self.object

        if new_perm == "org_admin":
            admin_group.user_set.add(researcher)
            read_group.user_set.remove(researcher)
            researcher_group.user_set.remove(researcher)
        elif new_perm == "org_read":
            read_group.user_set.add(researcher)
            admin_group.user_set.remove(researcher)
            researcher_group.user_set.remove(researcher)
        else:
            researcher_group.user_set.add(researcher)
            admin_group.user_set.remove(researcher)
            read_group.user_set.remove(researcher)
        return
