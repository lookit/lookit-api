import operator
from functools import reduce

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.models import Group
from django.db.models import Q
from django.db.models.functions import Lower
from django.shortcuts import reverse, get_object_or_404
from django.views import generic

from accounts.models import User
from exp.mixins.paginator_mixin import PaginatorMixin
from exp.views.mixins import (
    ExperimenterLoginRequiredMixin,
    SingleObjectParsimoniousQueryMixin,
)
from project import settings
from studies.forms import LabForm
from studies.helpers import send_mail
from studies.models import Lab, Study
from studies.permissions import LabPermission


class LabDetailView(
    ExperimenterLoginRequiredMixin, UserPassesTestMixin, generic.DetailView
):
    """
    LabDetailView shows information about a lab.
    """

    queryset = Lab.objects.all()
    template_name = "studies/lab_detail.html"
    model = Lab
    raise_exception = True

    def user_can_see_lab(self):
        """Allow viewing labs that you are in/requested or that are approved to test already."""
        user = self.request.user
        lab = self.get_object()
        return user.is_researcher and (
            user.labs.filter(id=lab.pk).exists()
            or user.requested_labs.filter(id=lab.pk).exists()
            or lab.approved_to_test
        )

    test_func = user_can_see_lab

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["in_this_lab"] = user.labs.filter(pk=self.object.pk).exists()
        context["requested_this_lab"] = user.requested_labs.filter(
            pk=self.object.pk
        ).exists()
        context["can_edit_lab"] = user.has_perm(
            LabPermission.EDIT_LAB_METADATA, self.object
        )
        context["can_see_lab_researchers"] = context["in_this_lab"] or user.has_perm(
            LabPermission.MANAGE_LAB_RESEARCHERS
        )
        return context


class LabMembersView(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectParsimoniousQueryMixin,
    PaginatorMixin,
    generic.DetailView,
):
    """
    Shows a list of all members of a lab.
    """

    model = Lab
    raise_exception = True
    template_name = "studies/lab_member_list.html"

    def user_can_view_lab_members(self):
        lab = self.get_object()
        user = self.request.user
        if self.request.method == "POST":
            return user.has_perm(LabPermission.MANAGE_LAB_RESEARCHERS, lab)
        else:
            return lab in user.labs.all() or user.has_perm(
                LabPermission.MANAGE_LAB_RESEARCHERS, lab
            )

    test_func = user_can_view_lab_members

    def get_lab_members(self, *args, **kwargs):
        """
        Returns paginated list of items for the LabListView - handles filtering on set, match,
        and sort.
        """
        lab = self.get_object()
        query_dict = self.request.GET
        # List labs that you are part of and labs that are approved to test already
        queryset = lab.researchers.all().union(lab.requested_researchers.all())
        queryset = User.objects.filter(
            Q(id__in=lab.researchers.all().values_list("id"))
            | Q(id__in=lab.requested_researchers.all().values_list("id"))
        )
        match = query_dict.get("match")
        if match:
            queryset = queryset.filter(
                reduce(
                    operator.and_,
                    (
                        Q(given_name__icontains=term)
                        | Q(middle_name__icontains=term)
                        | Q(family_name__icontains=term)
                        for term in match.split()
                    ),
                )
            )
        queryset = queryset.order_by("family_name")
        queryset = self.paginated_queryset(queryset, query_dict.get("page", 1), 20)

        return [
            {"user": user, "user_data": {"group_label": self.get_group_label(user)}}
            for user in queryset
        ]

    def get_group_label(self, member):
        lab = self.get_object()
        if member in lab.admin_group.user_set.all():
            return "Admin"
        elif member in lab.view_group.user_set.all():
            return "View"
        elif member in lab.researchers.all():
            return "Member"
        elif member in lab.requested_researchers.all():
            return "Requested to join"
        else:
            return "Not in this lab"

    def get_context_data(self, **kwargs):
        """
        Gets the context for the LabMembersView and supplements with lab member info
        """
        context = super().get_context_data(**kwargs)
        context["match"] = self.request.GET.get("match", "")
        context["page"] = self.request.GET.get("page", "1")
        lab = self.get_object()
        context["lab"] = lab
        context["lab_members"] = self.get_lab_members()
        context["can_edit"] = self.request.user.has_perm(
            LabPermission.MANAGE_LAB_RESEARCHERS, lab
        )
        return context

    # TODO: adapt for lab
    def post(self, request, *args, **kwargs):
        """
        Post form for disabling a researcher. If researcher is deleted - is actually disabled, then removed
        from org admin, org read, and org researcher groups.
        """
        retval = super().get(request, *args, **kwargs)
        action = self.request.POST.get("user_action", [])
        if not action:
            return retval
        researcher = get_object_or_404(User, pk=self.request.POST.get("user_id", ""))
        lab = self.get_object()

        # First check we are not trying to remove the only admin
        if (
            action in ["make_member", "make_view", "remove_researcher"]
            and researcher in lab.admin_group.user_set.all()
            and lab.admin_group.user_set.count() == 1
        ):
            messages.error(
                self.request,
                "Could not change permissions for this researcher. There must be at least one lab admin.",
            )
            return retval

        if action == "make_member":
            lab.requested_researchers.remove(researcher)
            lab.researchers.add(researcher)
            lab.view_group.user_set.remove(researcher)
            lab.admin_group.user_set.remove(researcher)
            messages.success(
                self.request,
                f"Changed {researcher.get_full_name()} to a member of {lab.name}.",
            )
            context = {
                "permission": permission,
                "lab_id": lab.pk,
                "lab_name": study.lab.name,
                "researcher_name": user.get_short_name(),
            }
            send_mail.delay(
                "notify_researcher_of_org_permissions",
                f"You are now a member of the Lookit lab {lab.name}",
                researcher.username,
                from_address=settings.EMAIL_FROM_ADDRESS,
                **context,
            )
        if action == "make_view":
            lab.view_group.user_set.add(researcher)
            lab.admin_group.user_set.remove(researcher)
            messages.success(
                self.request,
                f"Changed {researcher.get_full_name()} to have view permissions for {lab.name}.",
            )
            context = {
                "permission": permission,
                "lab_id": lab.pk,
                "lab_name": study.lab.name,
                "researcher_name": user.get_short_name(),
            }
            send_mail.delay(
                "notify_researcher_of_org_permissions",
                f"You now have view permissions for the Lookit lab {lab.name}",
                researcher.username,
                from_address=settings.EMAIL_FROM_ADDRESS,
                **context,
            )
        if action == "make_admin":
            lab.view_group.user_set.remove(researcher)
            lab.admin_group.user_set.add(researcher)
            messages.success(
                self.request,
                f"Changed {researcher.get_full_name()} to have admin permissions for {lab.name}.",
            )
            send_mail.delay(
                "notify_researcher_of_org_permissions",
                f"You are now an admin of the Lookit lab {lab.name}",
                researcher.username,
                from_address=settings.EMAIL_FROM_ADDRESS,
                **context,
            )
        if action == "remove_researcher":
            lab.requested_researchers.remove(researcher)
            lab.researchers.remove(researcher)
            lab.view_group.user_set.remove(researcher)
            lab.admin_group.user_set.remove(researcher)
            # Remove from all lab study groups. Note that this could
            # remove the sole study admin, but we're enforcing that there's at least
            # one lab admin, who could give someone else access.
            for study in Study.objects.filter(lab=lab):
                for gr in study.all_study_groups():
                    gr.user_set.remove(researcher)
            messages.success(
                self.request,
                f"Removed {researcher.get_full_name()} from {lab.name} and from all of this lab's studies.",
            )
            messages.success(
                self.request,
                f"Changed {researcher.get_full_name()} to have admin permissions for {lab.name}.",
            )
            send_mail.delay(
                "notify_researcher_of_org_permissions",
                f"You have been removed from the Lookit lab {lab.name}",
                researcher.username,
                from_address=settings.EMAIL_FROM_ADDRESS,
                **context,
            )
        if action == "reset_password":
            self.send_reset_password_email(researcher)
        if action == "resend_confirmation":
            self.send_resend_confirmation_email(researcher)

        return retval

    def send_reset_password_email(self, researcher):
        """
        Send reset_password email to researcher
        """
        context = {
            "researcher_name": researcher.get_short_name(),
            "org_name": self.get_object().name,
            "login_url": self.login_url,
        }
        subject = "Reset OSF password to login to Lookit"
        send_mail.delay("reset_password", subject, researcher.username, **context)
        messages.success(
            self.request, f"Reset password email sent to {researcher.username}."
        )
        return

    def send_resend_confirmation_email(self, researcher):
        """
        Send resend_confirmation_email to researcher
        """
        context = {
            "researcher_name": researcher.get_short_name(),
            "org_name": self.get_object().name,
            "login_url": self.login_url,
        }
        subject = "Confirm OSF account to login to Lookit"
        send_mail.delay("resend_confirmation", subject, researcher.username, **context)
        messages.success(
            self.request, f"Confirmation email resent to {researcher.username}."
        )
        return


class LabUpdateView(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.UpdateView,
):
    """
    LabUpdateView allows updating lab metadata.
    """

    queryset = Lab.objects.all()
    template_name = "studies/lab_update.html"
    form_class = LabForm
    model = Lab
    raise_exception = True

    def user_can_edit_lab(self):
        lab = self.get_object()
        return self.request.user.has_perm(LabPermission.EDIT_LAB_METADATA, lab)

    test_func = user_can_edit_lab

    def get_success_url(self):
        return reverse("exp:lab-detail", kwargs={"pk": self.object.id})


class LabCreateView(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.CreateView,
):
    """
    LabCreateView allows creating a new lab.
    """

    template_name = "studies/lab_create.html"
    form_class = LabForm
    model = Lab
    raise_exception = True

    # This is really just duplicating the experimenter login requirement; leaving as a
    # placeholder in case we institute requirements beyond that or want to decouple
    # the login form from user permissions in the future
    def user_can_create_lab(self):
        return self.request.user.is_researcher

    test_func = user_can_create_lab

    def get_success_url(self):
        return reverse("exp:lab-detail", kwargs={"pk": self.object.id})

    def notify_admins_of_lab_submission(self):
        lookit_admin_group = Group.objects.get(name="LOOKIT_ADMIN")
        email_context = {
            "lab_name": self.object.name,
            "researcher_name": self.request.user.get_short_name(),
            "lab_id": self.object.id,
        }
        send_mail.delay(
            "notify_admins_of_lab_creation",
            "Lab Submission Notification",
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(lookit_admin_group.user_set.values_list("username", flat=True)),
            **email_context,
        )

    def form_valid(self, form):
        """
        Before saving new lab, adds current user to the lab and to the lab's admin group.
        """
        resp = super().form_valid(form)
        lab = self.object
        user = self.request.user
        lab.researchers.add(user)
        user.groups.add(lab.admin_group)
        lab.save()
        messages.success(self.request, "New lab created.")
        self.notify_admins_of_lab_submission()
        return resp


class LabMembershipRequestView(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.RedirectView,
):

    http_method_names = ["post"]
    model = Lab

    def can_request_lab_membership(self):
        user = self.request.user
        lab = self.get_object()
        return user.is_researcher and lab.approved_to_test

    test_func = can_request_lab_membership

    def get_redirect_url(self, *args, **kwargs):
        return self.request.META.get("HTTP_REFERER", reverse("exp:lab-list"))

    def post(self, request, *args, **kwargs):
        user = self.request.user
        lab = self.object

        # Technically allow re-requesting if already in a lab; won't have any effect
        # but will re-notify lab admins.
        if lab not in user.labs.all():
            # Add the request to the user/lab
            user.requested_labs.add(lab)
            user.save()
            # Notify lab admins so they can go approve the request
            researcher_name = user.get_full_name()
            context = {
                "researcher_name": researcher_name,
                "lab_name": lab.name,
                "lab_id": lab.id,
            }
            send_mail.delay(
                "notify_lab_admins_of_request_to_join",
                "Researcher {} has requested access to {}".format(
                    researcher_name, lab.name
                ),
                settings.EMAIL_FROM_ADDRESS,
                bcc=list(lab.admin_group.user_set.values_list("username", flat=True)),
                **context,
            )
            messages.success(
                request,
                f"Requested to join {lab.name}. The lab admins have been notified and you will receive an email when your request is approved.",
            )
        else:
            messages.warning(request, f"You are already a member of {lab.name}.")
        return super().post(request, *args, **kwargs)


class LabListView(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    PaginatorMixin,
    generic.ListView,
):
    """
    Shows a list of all labs.
    """

    model = Lab
    raise_exception = True
    template_name = "studies/lab_list.html"

    def user_can_view_labs(self):
        return self.request.user.is_researcher

    test_func = user_can_view_labs

    def get_queryset(self, *args, **kwargs):
        """
        Returns paginated list of items for the LabListView - handles filtering on set, match,
        and sort.
        """
        user = self.request.user
        query_dict = self.request.GET
        # List labs that you are part of and labs that are approved to test already
        lab_set = query_dict.get("set")
        if lab_set == "all":
            queryset = Lab.objects.filter(
                Q(approved_to_test=True)
                | Q(id__in=user.labs.all())
                | Q(id__in=user.requested_labs.all())
            )
        else:
            queryset = Lab.objects.filter(
                Q(id__in=user.labs.all()) | Q(id__in=user.requested_labs.all())
            )

        match = query_dict.get("match")
        if match:
            queryset = queryset.filter(
                reduce(
                    operator.and_,
                    (
                        Q(name__icontains=term)
                        | Q(principal_investigator_name__icontains=term)
                        | Q(institution__icontains=term)
                        for term in match.split()
                    ),
                )
            )

        queryset = queryset.order_by(Lower("name"))
        return self.paginated_queryset(queryset, query_dict.get("page", 1), 20)

    def get_context_data(self, **kwargs):
        """
        Gets the context for the StudyListView and supplements with the state, match, and sort query params.
        """
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["user_labs"] = user.labs.all()
        context["user_requested_labs"] = user.requested_labs.all()
        context["set"] = self.request.GET.get("set", "myLabs")
        context["match"] = self.request.GET.get("match", "")
        context["page"] = self.request.GET.get("page", "1")
        return context
