from django.contrib.auth import authenticate, login
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import reverse
from django.utils.translation import ugettext as _
from django.views import generic
from django.contrib.auth import update_session_auth_hash
from django.http import HttpResponseRedirect

from guardian.mixins import LoginRequiredMixin
from revproxy.views import ProxyView

from accounts import forms
from accounts.models import Child, DemographicData, User
from project import settings
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

class ChildrenListView(LoginRequiredMixin, generic.CreateView):
    """
    Allows user to view a list of current children and add children
    """
    template_name = 'web/children-list.html'
    model = Child
    form_class = forms.ChildForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        children = Child.objects.filter(deleted = False, user=self.request.user)
        context["objects"] = children
        context["form_hidden"] = kwargs.get('form_hidden', True)
        return context

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form, form_hidden=False))

    def form_valid(self, form):
        user = self.request.user
        form.instance.user = user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('web:children-list')

class ChildUpdateView(LoginRequiredMixin, generic.UpdateView):
    """
    Allows user to view a list of current children and add children
    """
    template_name = 'web/child-update.html'
    model = Child
    form_class = forms.ChildForm

    def get_success_url(self):
        return reverse('web:children-list')

    def get_object(self, queryset=None):
        '''
        Returns the object the view is displaying.
        By default this requires `self.queryset` and a `pk` or `slug` argument
        in the URLconf, but subclasses can override this to return any object.
        '''
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

    def post(self, request, *args, **kwargs):
        if 'deleteChild' in self.request.POST and self.request.method == 'POST':
            child = self.get_object()
            child.deleted = True
            child.save()
            return HttpResponseRedirect(self.get_success_url())
        return super().post(request, *args, **kwargs)

class DemographicDataCreateView(LoginRequiredMixin, generic.CreateView):
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

class DemographicDataUpdateView(DemographicDataCreateView):
    """
    Allows user to update demographic data - but actually creates new version instead of updating old one.
    """
    template_name = 'web/demographic-data-update.html'

    def get_success_url(self):
        return reverse('web:demographic-data-update')

    def form_valid(self, form):
        resp = super().form_valid(form)
        self.object.user = self.request.user
        self.object.previous = self.request.user.latest_demographics or None
        self.object.save()
        return resp

    def get_initial(self):
        """
        Returns the initial data to use for forms on this view.
        """
        demographic_data = self.request.user.latest_demographics or None
        if demographic_data:
            demographic_data_dict = demographic_data.__dict__
            demographic_data_dict['previous'] = demographic_data
            demographic_data_dict.pop('id')
            demographic_data_dict.pop('uuid')
            return demographic_data_dict
        return demographic_data


class ParticipantEmailPreferencesView(LoginRequiredMixin, generic.UpdateView):
    """
    Allows a participant to update their email preferences - when they can be contacted.
    """
    template_name = 'web/participant-email-preferences.html'
    model = User
    form_class = forms.EmailPreferencesForm

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return reverse('web:email-preferences')


class ParticipantUpdateView(LoginRequiredMixin, generic.UpdateView):
    """
    Allows a participant to update their names and password
    """
    template_name = 'web/participant-update.html'
    model = User
    form_class = forms.ParticipantUpdateForm
    second_form_class = forms.ParticipantPasswordForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if 'participant_update' in self.request.POST:
            context['form2'].is_bound = False
        if 'password_update' in self.request.POST:
            context['form'].is_bound = False
            context['form'].initial = {'username': user.username, 'given_name': user.given_name, 'middle_name': user.middle_name, 'family_name': user.family_name}
        if 'form' not in context:
            context['form'] = self.form_class(self.request.GET)
        if 'form2' not in context:
            context['form2'] = self.second_form_class(self.request.POST)
        return context

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return reverse('web:participant-update')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if 'password_update' in self.request.POST:
            kwargs['user'] =  kwargs.pop('instance')
        else:
            if 'user' in kwargs:
                kwargs.pop('user')
        return kwargs

    def form_invalid(self, **kwargs):
        return self.render_to_response(self.get_context_data(**kwargs))

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if 'participant_update' in request.POST:
            form_class = self.get_form_class()
            form_name = 'form'
        if 'password_update' in request.POST:
            form_class = self.second_form_class
            form_name = 'form2'

        form = self.get_form(form_class)
        if form.is_valid():
            form.save()
            if form_name == 'form2':
                update_session_auth_hash(self.request, form.user)
                return HttpResponseRedirect(self.get_success_url())
            return super().form_valid(form)
        else:
            return self.form_invalid(**{form_name: form})

class ExperimentAssetsProxyView(ProxyView, LoginRequiredMixin):
    upstream = settings.EXPERIMENT_BASE_URL


class ExperimentProxyView(ProxyView, LoginRequiredMixin):
    upstream = settings.EXPERIMENT_BASE_URL

    def dispatch(self, request, path, *args, **kwargs):
        try:
            child = Child.objects.get(uuid=kwargs.get('child_id', None))
        except Child.DoesNotExist:
            raise Http404()

        if child.user != request.user:
            # requesting user doesn't belong to that child
            raise PermissionDenied()

        return super().dispatch(request, path)
