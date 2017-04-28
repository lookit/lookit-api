from django.views import generic

from accounts.models import Organization


class OrganizationCreateView(generic.CreateView):
    model = Organization


class OrganizationListView(generic.ListView):
    model = Organization


class OrganizationDetailView(generic.DetailView):
    model = Organization
