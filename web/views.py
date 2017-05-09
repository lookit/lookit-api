from django.shortcuts import reverse
from django.views import generic

from accounts import forms
from accounts.models import DemographicData, User
from studies.models import Study


class StudiesListView(generic.ListView):
    '''
    List all active studies
    '''
    template_name = 'web/studies-list.html'
    model = Study

    def get_queryset(self, *args, **kwargs):
        # TODO if we need to filter by study demographics vs user demographics
        # TODO or by if they've taken the study before this is the spot
        # self.request.user
        qs = super().get_queryset(*args, **kwargs)
        qs = qs.filter(state='active')
        return qs


class StudyDetailView(generic.DetailView):
    '''
    Show the details of a study, should offer to allow a participant
    to take the study and forward/proxy them to the js application
    '''
    template_name = 'web/study-detail.html'
    model = Study


class ParticipantSignupView(generic.CreateView):
    '''
    Allows a participant to sign up
    '''
    template_name = 'web/participant-signup.html'
    model = User
    form_class = forms.ParticipantSignupForm

    def get_success_url(self):
        return reverse('demographic-data-create')


class DemographicDataCreateView(generic.CreateView):
    '''
    Allows a participant to provide demographic data
    '''
    template_name = 'web/demographic-data-create.html'
    model = DemographicData
    form_class = forms.DemographicDataForm

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('studies-list')
