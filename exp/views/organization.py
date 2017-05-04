from django.shortcuts import reverse
from django.views import generic

from accounts.models import Organization


class OrganizationCreateView(generic.CreateView):
    fields = ('name', 'url', )
    model = Organization

    def get_success_url(self):
        return reverse('organization-list')


class OrganizationListView(generic.ListView):
    model = Organization


class OrganizationDetailView(generic.DetailView):
    model = Organization
