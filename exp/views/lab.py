from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.models import Group
from django.http import HttpResponseRedirect
from django.shortcuts import reverse
from django.views import generic

from exp.views.mixins import (
    ExperimenterLoginRequiredMixin,
    SingleObjectParsimoniousQueryMixin,
)
from project import settings
from studies.forms import LabForm
from studies.helpers import send_mail
from studies.models import Lab
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

    def user_can_see_labs(self):
        user = self.request.user
        return user.is_researcher

    test_func = user_can_see_labs

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
        context["can_manage_lab_researchers"] = user.has_perm(
            LabPermission.MANAGE_LAB_RESEARCHERS
        )
        return context

    def add_user_to_requested_researchers(self, lab):
        """
        Send reset_password email to researcher
        """

        lab.requested_researchers.add(self.request.user)
        lab.save()
        return

    def post(self, request, *args, **kwargs):
        lab = self.get_object()
        if "request_join_lab" in self.request.POST:
            self.add_user_to_requested_researchers(lab)
        return HttpResponseRedirect(reverse("exp:lab-detail", kwargs={"pk": lab.pk}))


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
