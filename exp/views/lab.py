from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import HttpResponseRedirect
from django.shortcuts import reverse
from django.views import generic
from exp.views.mixins import (
    ExperimenterLoginRequiredMixin,
    SingleObjectParsimoniousQueryMixin,
)
from studies.models import Lab
from studies.permissions import LabPermission
from studies.forms import LabEditForm


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
    form_class = LabEditForm
    model = Lab
    raise_exception = True

    def user_can_edit_lab(self):
        lab = self.get_object()
        return self.request.user.has_perm(LabPermission.EDIT_LAB_METADATA, lab)

    test_func = user_can_edit_lab

    def get_success_url(self):
        return reverse("exp:lab-detail", kwargs={"pk": self.object.id})
