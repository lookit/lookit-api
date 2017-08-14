from django.contrib.auth import authenticate, login
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import reverse, get_object_or_404, redirect
from django.utils.translation import ugettext as _
from django.views import generic
from django.contrib.auth import update_session_auth_hash
from django.http import HttpResponseRedirect
from django.contrib import messages
from django_countries import countries
from guardian.mixins import LoginRequiredMixin
from revproxy.views import ProxyView

from accounts import forms
from accounts.models import Child, DemographicData, User
from project import settings
from studies.models import Study
from localflavor.us.us_states import USPS_CHOICES


class ParticipantSignupView(generic.CreateView):
    '''
    Allows a participant to sign up. Redirects them to a page to add their demographic data.
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
        messages.success(self.request, "Participant created.")
        return resp

    def get_success_url(self):
        return reverse('web:demographic-data-update')


class DemographicDataUpdateView(LoginRequiredMixin, generic.CreateView):
    """
    Allows user to update demographic data - but actually creates new version instead of updating old one.
    """
    template_name = 'web/demographic-data-update.html'
    model = DemographicData
    form_class = forms.DemographicDataForm

    def get_success_url(self):
        return reverse('web:demographic-data-update')

    def form_valid(self, form):
        """
        Before saving form, adds user relationship to demographic data, and sets "previous"
         as the last saved demographic data.
        """
        resp = super().form_valid(form)
        self.object.user = self.request.user
        self.object.previous = self.request.user.latest_demographics or None
        self.object.save()
        messages.success(self.request, "Demographic data saved.")
        return resp

    def get_initial(self):
        """
        Returns the initial data to use for forms on this view. Prepopulates
        demographic data form with the latest demographic data.
        """
        demographic_data = self.request.user.latest_demographics or None
        if demographic_data:
            demographic_data_dict = demographic_data.__dict__
            demographic_data_dict.pop('id')
            demographic_data_dict.pop('uuid')
            return demographic_data_dict
        return demographic_data


    def get_context_data(self, **kwargs):
        """
        Adds the context for form1 and form2 on the page - a little extra code due to the
        two forms on the page.  The form that was not edited is unbound so data
        is not validated.
        """
        context = super().get_context_data(**kwargs)
        context['countries'] = countries
        context['states'] = USPS_CHOICES
        return context



class ParticipantUpdateView(LoginRequiredMixin, generic.UpdateView):
    """
    Allows a participant to update their name and password -
    extra code in this view because there are multiple forms on this page.
    """
    template_name = 'web/participant-update.html'
    model = User
    form_class = forms.ParticipantUpdateForm
    second_form_class = forms.ParticipantPasswordForm

    def get_context_data(self, **kwargs):
        """
        Adds the context for form1 and form2 on the page - a little extra code due to the
        two forms on the page.  The form that was not edited is unbound so data
        is not validated.
        """
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
        """
        Returns the keyword arguments for instantiating the form. -
        if updating password section, need the 'user' kwarg
        """
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
        """
        Returns the keyword arguments for instantiating the form. -
        if updating password section, need the 'user' kwarg
        """
        self.object = self.get_object()
        # Depending on the keywords in the POST, choose the participant update
        # or the password update form.
        if 'participant_update' in request.POST:
            form_class = self.get_form_class()
            form_name = 'form'
        if 'password_update' in request.POST:
            form_class = self.second_form_class
            form_name = 'form2'

        form = self.get_form(form_class)
        if form.is_valid():
            form.save()
            messages.success(self.request, "Participant information saved.")
            if form_name == 'form2':
                # If updating password, need to reauthenticate
                update_session_auth_hash(self.request, form.user)
                return HttpResponseRedirect(self.get_success_url())
            return super().form_valid(form)
        else:
            return self.form_invalid(**{form_name: form})


class ChildrenListView(LoginRequiredMixin, generic.CreateView):
    """
    Allows user to view a list of current children and add children
    """
    template_name = 'web/children-list.html'
    model = Child
    form_class = forms.ChildForm

    def get_context_data(self, **kwargs):
        """
        Add children that have not been deleted that belong to the current user
        to the context_dict.  Also add info to hide the Add Child form on page load.
        """
        context = super().get_context_data(**kwargs)
        children = Child.objects.filter(deleted = False, user=self.request.user)
        context["objects"] = children
        context["form_hidden"] = kwargs.get('form_hidden', True)
        return context

    def form_invalid(self, form):
        """
        If form invalid, add child form needs to be open when page reloads.
        """
        return self.render_to_response(self.get_context_data(form=form, form_hidden=False))

    def form_valid(self, form):
        """
        Add the current user to the child before saving the child.
        """
        user = self.request.user
        form.instance.user = user
        messages.success(self.request, "Child added.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('web:children-list')


class ChildUpdateView(LoginRequiredMixin, generic.UpdateView):
    """
    Allows user to update or delete a child.
    """
    template_name = 'web/child-update.html'
    model = Child
    form_class = forms.ChildForm

    def get_success_url(self):
        return reverse('web:children-list')

    def get_object(self, queryset=None):
        '''
        Returns the object the view is displaying.
        ChildUpdate View needs to be called with slug or pk - but uuid in URLconf
        instead so use this to lookup child
        '''
        uuid = self.kwargs.get('uuid')
        return get_object_or_404(Child, uuid=uuid)

    def post(self, request, *args, **kwargs):
        '''
        If deleteChild form submitted, mark child as deleted in the db.
        '''
        if 'deleteChild' in self.request.POST and self.request.method == 'POST':
            child = self.get_object()
            child.deleted = True
            child.save()
            messages.success(self.request, "Child deleted.")
            return HttpResponseRedirect(self.get_success_url())
        messages.success(self.request, "Child updated.")
        return super().post(request, *args, **kwargs)


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

    def form_valid(self, form):
        """
        Adds success message
        """
        messages.success(self.request, "Email preferences saved.")
        return super().form_valid(form)

class StudiesListView(generic.ListView):
    '''
    List all active, public studies.
    '''
    template_name = 'web/studies-list.html'
    model = Study

    def get_queryset(self):
        # TODO if we need to filter by study demographics vs user demographics
        # TODO or by if they've taken the study before this is the spot
        return super().get_queryset().filter(state='active', public=True)


class StudyDetailView(generic.DetailView):
    '''
    Show the details of a study.  If the user has selected a child, they can
    participate in the study and be forwarded/proxied to the js application
    '''
    template_name = 'web/study-detail.html'
    model = Study

    def get_queryset(self):
        return super().get_queryset().filter(state='active', public=True)

    def get_object(self, queryset=None):
        '''
        Needed because view expecting pk or slug, but url has UUID. Looks up
        study by uuid.
        '''
        uuid = self.kwargs.get('uuid')
        return get_object_or_404(Study, uuid=uuid)

    def get_context_data(self, **kwargs):
        '''
        If authenticated, add demographic presence, and children to context data dict
        '''
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context['has_demographic'] = self.request.user.latest_demographics
            context['children'] = self.request.user.children.all()

        return context


class ExperimentAssetsProxyView(ProxyView, LoginRequiredMixin):
    upstream = settings.EXPERIMENT_BASE_URL

    def dispatch(self, request, path, *args, **kwargs):
        path = self.request.path
        if path.endswith('/') or 'js' in path or 'css' in path:
            return super().dispatch(request, path, *args, **kwargs)
        return redirect(self.request.path + '/')


class ExperimentProxyView(ProxyView, LoginRequiredMixin):
    '''
    Proxy view to forward user to participate page in the Ember app
    '''
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
