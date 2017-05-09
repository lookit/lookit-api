from django.shortcuts import reverse
from django.views import generic

from accounts.models import Organization
from guardian.mixins import LoginRequiredMixin


class OrganizationCreateView(LoginRequiredMixin, generic.CreateView):
    fields = ('name', 'url', )
    model = Organization

    def get_success_url(self):
        return reverse('exp:organization-list')


class OrganizationListView(LoginRequiredMixin, generic.ListView):
    model = Organization


class OrganizationDetailView(LoginRequiredMixin, generic.DetailView):
    model = Organization
