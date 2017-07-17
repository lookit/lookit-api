from django.contrib.auth import authenticate, login
from django.http import Http404
from django.shortcuts import reverse
from django.utils.translation import ugettext as _
from django.views import generic

from accounts import forms
from accounts.models import DemographicData, User
from studies.models import Study


class StudiesListView(generic.ListView):
    '''
    List all active studies.
    '''
    template_name = 'web/studies-list.html'
    model = Study

    def get_queryset(self):
        # TODO if we need to filter by study demographics vs user demographics
        # TODO or by if they've taken the study before this is the spot
        return super().get_queryset().filter(state='active', public=True)


class StudyDetailView(generic.DetailView):
    '''
    Show the details of a study, should offer to allow a participant
    to take the study and forward/proxy them to the js application
    '''
    template_name = 'web/study-detail.html'
    model = Study

    def get_object(self, queryset=None):
        '''
        Returns the object the view is displaying.
        By default this requires `self.queryset` and a `pk` or `slug` argument
        in the URLconf, but subclasses can override this to return any object.
        '''
        # Use a custom queryset if provided; this is required for subclasses
        # like DateDetailView
        if queryset is None:
            queryset = self.get_queryset()

        uuid = self.kwargs.get('uuid')

        if uuid is not None:
            queryset = queryset.filter(uuid=uuid)
        try:
            # Get the single item from the filtered queryset
            obj = queryset.get()
        except queryset.model.DoesNotExist:
            raise Http404(_('No %(verbose_name)s found matching the query') %
                          {'verbose_name': queryset.model._meta.verbose_name})
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        if self.request.user.is_authenticated:
            context['has_demographic'] = self.request.user.latest_demographics
            context['children'] = self.request.user.children.all()

        return context


class ParticipantSignupView(generic.CreateView):
    '''
    Allows a participant to sign up
    '''
    template_name = 'web/participant-signup.html'
    model = User
    form_class = forms.ParticipantSignupForm

    def form_valid(self, form):
        resp = super().form_valid(form)
        new_user = authenticate(
            self.request,
            username=form.cleaned_data['username'],
            password=form.cleaned_data['password1']
        )
        login(self.request, new_user, backend='django.contrib.auth.backends.ModelBackend')
        return resp

    def get_success_url(self):
        return reverse('web:demographic-data-create')


class DemographicDataCreateView(generic.CreateView):
    '''
    Allows a participant to provide demographic data
    '''
    template_name = 'web/demographic-data-create.html'
    model = DemographicData
    form_class = forms.DemographicDataForm

    def form_valid(self, form):
        resp = super().form_valid(form)
        self.object.user = self.request.user
        self.object.save()
        return resp

    def get_success_url(self):
        return reverse('web:studies-list')

class ParticipantUpdateView(generic.UpdateView):
    template_name = 'web/participant-update.html'
    model = User
    form_class = forms.ParticipantUpdateForm
    second_form_class = forms.ParticipantPasswordForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'form' not in context:
            context['form'] = self.form_class(self.request.GET)
        if 'form2' not in context:
            context['form2'] = self.second_form_class(self.request.GET)
        return context

    def get_object(self, queryset=None):
        return self.request.user;

    def get_success_url(self):
        return reverse('web:participant-update')

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        import pdb; pdb.set_trace()
        if 'participant_update' in request.POST:
            form_class = self.get_form_class()
            form_name = 'form'
        if 'password_update' in request.POST:
            form_class = self.second_form_class
            form_name = 'form2'

        form = self.get_form(form_class)

        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(**{form_name: form})
