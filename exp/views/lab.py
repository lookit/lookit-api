import operator
from functools import reduce

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.models import Group
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, reverse
from django.views import generic
from django.views.generic.detail import SingleObjectMixin

from accounts.models import User
from exp.mixins.paginator_mixin import PaginatorMixin
from exp.views.mixins import ResearcherLoginRequiredMixin, SingleObjectFetchProtocol
from project import settings
from studies.forms import LabApprovalForm, LabForm
from studies.helpers import send_mail
from studies.models import Lab, Study
from studies.permissions import LabPermission, SiteAdminGroup


class LabDetailView(
    ResearcherLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectFetchProtocol[Lab],
    generic.DetailView,
):
    """
    LabDetailView shows information about a lab and provides links to request to join,
    update metadata, and view/manage researchers.
    """

    queryset = Lab.objects.all()
    template_name = "studies/lab_detail.html"
    model = Lab
    raise_exception = True

    def user_can_see_lab(self):
        """Allow viewing any lab as a researcher."""
        user = self.request.user
        return user.is_researcher

        # Also considered allowing only labs you're in or that are approved to test, but suspect
        # that people will want to start setting up (adding researchers, creating studies) ahead of being
        # able to actually test.
        # lab = self.get_object()
        # return (
        #     user.labs.filter(id=lab.pk).exists()
        #     or user.requested_labs.filter(id=lab.pk).exists()
        #     or lab.approved_to_test
        #     or user in LOOKIT_ADMIN_GROUP.user_set.all() # replace with specific perm
        # )

    test_func = user_can_see_lab

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        lab = self.get_object()
        context["in_this_lab"] = lab in user.labs.all()
        context["requested_this_lab"] = user.requested_labs.filter(
            pk=self.object.pk
        ).exists()
        context["can_edit_lab"] = user.has_perm(
            LabPermission.EDIT_LAB_METADATA.codename, self.object
        ) or user.has_perm(LabPermission.EDIT_LAB_METADATA.prefixed_codename)
        context["can_see_lab_researchers"] = (
            context["in_this_lab"]
            or user.has_perm(LabPermission.READ_LAB_RESEARCHERS.codename, lab)
            or user.has_perm(LabPermission.READ_LAB_RESEARCHERS.prefixed_codename)
        )
        context["custom_url"] = self.request.build_absolute_uri(
            reverse("web:lab-studies-list", args=[lab.slug])
        )
        return context


class LabMembersView(
    ResearcherLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectFetchProtocol[Lab],
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
        """Allow viewing members for labs you're in, and managing members if specific perms."""
        lab = self.get_object()
        user = self.request.user

        if not user.is_researcher:
            return False

        if self.request.method == "POST":
            return user.has_perm(
                LabPermission.MANAGE_LAB_RESEARCHERS.codename, lab
            ) or user.has_perm(LabPermission.MANAGE_LAB_RESEARCHERS.prefixed_codename)
        else:
            return (
                lab in user.labs.all()
                or user.has_perm(LabPermission.READ_LAB_RESEARCHERS.codename, lab)
                or user.has_perm(LabPermission.READ_LAB_RESEARCHERS.prefixed_codename)
            )

    test_func = user_can_view_lab_members

    def get_lab_members(self, *args, **kwargs):
        """
        Returns paginated list of items for the LabMembersView - handles filtering on match
        and fetches some additional information for display (current perms).
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

        return queryset

    def members_with_group_labels(self, qs):
        return [
            {"user": user, "user_data": {"group_label": self.get_group_label(user)}}
            for user in qs
        ]

    def get_group_label(self, member):
        """
        Returns a label for the highest-level LabGroup a member is in with respect to this lab.
        """
        lab = self.get_object()
        if member in lab.admin_group.user_set.all():
            return "Admin"
        elif member in lab.member_group.user_set.all():
            return "Member"
        elif member in lab.readonly_group.user_set.all():
            return "View"
        elif member in lab.guest_group.user_set.all():
            return "Guest"
        elif member in lab.researchers.all():
            return "No groups"
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
        lab_members = self.get_lab_members()
        context["lab_members"] = self.members_with_group_labels(lab_members)
        context["lab_members_qs"] = lab_members
        context["can_edit"] = self.request.user.has_perm(
            LabPermission.MANAGE_LAB_RESEARCHERS.codename, lab
        ) or self.request.user.has_perm(
            LabPermission.MANAGE_LAB_RESEARCHERS.prefixed_codename
        )
        return context

    def post(self, request, *args, **kwargs):
        """
        Post form for changing researcher permissions.
        """
        retval = super().get(request, *args, **kwargs)
        action = self.request.POST.get("user_action", "")
        if not action:
            return retval
        researcher = get_object_or_404(User, pk=self.request.POST.get("user_id", ""))
        lab = self.get_object()

        # First check we are not trying to remove the only admin
        if (
            action in ["make_guest", "make_member", "remove_researcher"]
            and researcher in lab.admin_group.user_set.all()
            and lab.admin_group.user_set.count() == 1
        ):
            messages.error(
                self.request,
                "Could not change permissions for this researcher. There must be at least one lab admin.",
            )
            return retval

        if action == "make_guest":
            lab.requested_researchers.remove(researcher)
            lab.researchers.add(researcher)
            lab.guest_group.user_set.add(researcher)
            lab.readonly_group.user_set.remove(researcher)
            lab.member_group.user_set.remove(researcher)
            lab.admin_group.user_set.remove(researcher)
            messages.success(
                self.request,
                f"Changed {researcher.get_full_name()} to a guest of {lab.name}.",
            )
            context = {
                "permission": "Guest",
                "lab_id": lab.pk,
                "lab_name": lab.name,
                "researcher_name": researcher.get_short_name(),
            }
            send_mail.delay(
                "notify_researcher_of_lab_permissions",
                f"You are now part of the Lookit lab {lab.name}",
                researcher.username,
                reply_to=[lab.contact_email],
                **context,
            )
        if action == "make_member":
            lab.requested_researchers.remove(researcher)
            lab.researchers.add(researcher)
            lab.guest_group.user_set.remove(researcher)
            lab.readonly_group.user_set.remove(researcher)
            lab.member_group.user_set.add(researcher)
            lab.admin_group.user_set.remove(researcher)
            messages.success(
                self.request,
                f"Changed {researcher.get_full_name()} to have lab member permissions for {lab.name}.",
            )
            context = {
                "permission": "View all studies (you will still need to be added to individual studies to view data)",
                "lab_id": lab.pk,
                "lab_name": lab.name,
                "researcher_name": researcher.get_short_name(),
            }
            send_mail.delay(
                "notify_researcher_of_lab_permissions",
                f"You now have lab member permissions for the Lookit lab {lab.name}",
                researcher.username,
                reply_to=[lab.contact_email],
                **context,
            )
        if action == "make_admin":
            lab.requested_researchers.remove(researcher)
            lab.researchers.add(researcher)
            lab.guest_group.user_set.remove(researcher)
            lab.readonly_group.user_set.remove(researcher)
            lab.member_group.user_set.remove(researcher)
            lab.admin_group.user_set.add(researcher)
            messages.success(
                self.request,
                f"Changed {researcher.get_full_name()} to have admin permissions for {lab.name}.",
            )
            context = {
                "permission": "Admin (view and manage all studies, and manage lab members' permissions). You will still need to be added to individual studies to view data.",
                "lab_id": lab.pk,
                "lab_name": lab.name,
                "researcher_name": researcher.get_short_name(),
            }
            send_mail.delay(
                "notify_researcher_of_lab_permissions",
                f"You are now an admin of the Lookit lab {lab.name}",
                researcher.username,
                reply_to=[lab.contact_email],
                **context,
            )
        if action == "remove_researcher":
            lab.requested_researchers.remove(researcher)
            lab.researchers.remove(researcher)
            lab.guest_group.user_set.remove(researcher)
            lab.readonly_group.user_set.remove(researcher)
            lab.member_group.user_set.remove(researcher)
            lab.admin_group.user_set.remove(researcher)
            # Remove from all lab study groups. Note that this could
            # remove the sole study admin, but we're enforcing that there's at least
            # one lab admin, who could give someone else access.
            for study in Study.objects.filter(lab=lab):
                for gr in study.all_study_groups():
                    gr.user_set.remove(researcher)
                    gr.save()
                study.save()
            messages.success(
                self.request,
                f"Removed {researcher.get_full_name()} from {lab.name} and from all of this lab's studies.",
            )
            context = {
                "permission": "None",
                "lab_id": lab.pk,
                "lab_name": lab.name,
                "researcher_name": researcher.get_short_name(),
            }
            send_mail.delay(
                "notify_researcher_of_lab_permissions",
                f"You have been removed from the Lookit lab {lab.name}",
                researcher.username,
                reply_to=[lab.contact_email],
                **context,
            )
        if action == "reset_password":
            self.send_reset_password_email(researcher)

        return HttpResponseRedirect(
            reverse("exp:lab-members", kwargs={"pk": self.object.id})
        )

    def send_reset_password_email(self, researcher):
        """
        Send reset_password email to researcher./
        """
        context = {
            "researcher_name": researcher.get_short_name(),
            "lab_name": self.get_object().name,
            "login_url": self.login_url,
        }
        subject = "Reset password to login to Lookit"
        send_mail.delay("reset_password", subject, researcher.username, **context)
        messages.success(
            self.request, f"Reset password email sent to {researcher.username}."
        )


class LabUpdateView(
    ResearcherLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectFetchProtocol[Lab],
    generic.UpdateView,
):
    """
    LabUpdateView allows updating lab metadata.
    """

    template_name = "studies/lab_update.html"
    model = Lab
    raise_exception = True

    def get_form_class(self):
        if self.request.user.has_perm(
            LabPermission.EDIT_LAB_APPROVAL.prefixed_codename
        ):
            return LabApprovalForm
        else:
            return LabForm

    def user_can_edit_lab(self):
        lab = self.get_object()
        return self.request.user.is_researcher and (
            self.request.user.has_perm(LabPermission.EDIT_LAB_METADATA.codename, lab)
            or self.request.user.has_perm(
                LabPermission.EDIT_LAB_METADATA.prefixed_codename
            )
        )

    test_func = user_can_edit_lab

    def get_success_url(self):
        return reverse("exp:lab-detail", kwargs={"pk": self.object.id})


class LabCreateView(
    ResearcherLoginRequiredMixin, UserPassesTestMixin, generic.CreateView
):
    """
    LabCreateView allows creating a new lab.
    """

    object: Lab
    template_name = "studies/lab_create.html"
    form_class = LabForm
    model = Lab
    raise_exception = True

    # This is just duplicating the researcher login requirement; leaving as a
    # placeholder in case we institute requirements beyond that or want to decouple
    # the login form from user permissions in the future
    def user_can_create_lab(self):
        return self.request.user.is_researcher

    test_func = user_can_create_lab

    def get_success_url(self):
        return reverse("exp:lab-detail", kwargs={"pk": self.object.id})

    def notify_admins_of_lab_submission(self):
        email_context = {
            "lab_name": self.object.name,
            "researcher_name": self.request.user.get_short_name(),
            "lab_id": self.object.id,
        }
        send_mail.delay(
            "notify_admins_of_lab_creation",
            "Lab Submission Notification",
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(
                Group.objects.get(
                    name=SiteAdminGroup.LOOKIT_ADMIN.name
                ).user_set.values_list("username", flat=True)
            ),
            reply_to=[self.request.user.username],
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
    ResearcherLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectFetchProtocol[Lab],
    SingleObjectMixin,
    generic.RedirectView,
):
    http_method_names = ["post"]
    model = Lab

    def can_request_lab_membership(self):
        user = self.request.user
        # Also considered requiring lab approval before adding members, but suspect people will want to set up
        # ahead of getting approved to test
        # lab = self.get_object()
        # return user.is_researcher and lab.approved_to_test
        return user.is_researcher

    test_func = can_request_lab_membership

    def get_redirect_url(self, *args, **kwargs):
        return self.request.META.get("HTTP_REFERER", reverse("exp:lab-list"))

    def post(self, request, *args, **kwargs):
        user = self.request.user
        lab = self.get_object()

        # Technically allow re-requesting if already in a lab; won't have any effect
        # but will re-notify lab admins.
        if lab not in user.labs.all():
            # Add the request to the user/lab
            user.requested_labs.add(lab)
            user.save()
            # Notify lab admins so they can go approve the request.
            # TODO: could also handle this via m2m post-add signals on Lab model
            # (see https://docs.djangoproject.com/en/3.0/ref/signals/#m2m-changed)
            researcher_name = user.get_full_name()
            context = {
                "researcher_name": researcher_name,
                "lab_name": lab.name,
                "url": reverse("exp:lab-members", kwargs={"pk": lab.pk}),
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


class LabListView(ResearcherLoginRequiredMixin, UserPassesTestMixin, generic.ListView):
    """
    Shows a list of all labs.
    """

    model = Lab
    raise_exception = True
    template_name = "studies/lab_list.html"
    paginate_by = 10
    ordering = ("name",)

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
        lab_set = query_dict.get("set")

        # Originally considered displaying only approved-to-test labs and those you are in.
        # Now simplified to show all labs so people can easily request to join labs
        # ahead of approval.
        if lab_set == "all":
            queryset = Lab.objects.all()
        elif lab_set == "unapproved":
            queryset = Lab.objects.filter(approved_to_test=False)
        else:  # lab_set == "myLabs": (should match default in context["set"] )
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

        return queryset

    def get_context_data(self, **kwargs):
        """
        Gets the context for the LabListView and supplements with the state, match, and sort query params,
        and some information about which labs the current user is in.
        """
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["user_labs"] = user.labs.all()
        context["user_requested_labs"] = user.requested_labs.all()
        context["can_approve_labs"] = user.has_perm(
            LabPermission.EDIT_LAB_APPROVAL.prefixed_codename
        )
        context["set"] = self.request.GET.get("set", "myLabs")
        context["match"] = self.request.GET.get("match", "")
        context["page"] = self.request.GET.get("page", "1")
        return context
