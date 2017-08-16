import csv
import io
import json
import operator
import uuid
from functools import reduce

from django.core.mail import BadHeaderError
from django.contrib import messages
from django.contrib.auth.mixins import \
    PermissionRequiredMixin as DjangoPermissionRequiredMixin
from django.db.models import Case, Count, Q, When
from django.db.models.functions import Lower
from django.http import HttpResponseRedirect
from django.shortcuts import reverse
from django.utils import timezone
from django.views import generic

from accounts.models import User
from accounts.utils import (get_permitted_triggers, status_tooltip_text,
                            update_trigger)
from exp.mixins.paginator_mixin import PaginatorMixin
from guardian.mixins import PermissionRequiredMixin
from exp.views.mixins import ExperimenterLoginRequiredMixin
from guardian.shortcuts import get_objects_for_user
from project import settings
from studies.helpers import send_mail
from revproxy.views import ProxyView
from studies.forms import StudyBuildForm, StudyEditForm, StudyForm
from studies.models import Study, StudyLog


class StudyCreateView(ExperimenterLoginRequiredMixin, DjangoPermissionRequiredMixin, generic.CreateView):
    '''
    StudyCreateView allows a user to create a study and then redirects
    them to the detail view for that study.
    '''
    model = Study
    permission_required = 'studies.can_create_study'
    raise_exception = True
    form_class = StudyForm

    def form_valid(self, form):
        """
        Add the logged-in user as the study creator and the user's organization as the
        study's organization. If the form is valid, save the associated study and
        redirect to the supplied URL
        """
        user = self.request.user
        form.instance.creator = user
        form.instance.organization = user.organization
        self.object = form.save()
        self.add_creator_to_study_admin_group()
        # Adds success message that study has been created.
        messages.success(self.request, f"{self.object.name} created.")
        return HttpResponseRedirect(self.get_success_url())

    def add_creator_to_study_admin_group(self):
        """
        Add the study's creator to the study admin group.
        """
        study_admin_group = self.object.study_admin_group
        study_admin_group.user_set.add(self.request.user)
        return study_admin_group

    def get_success_url(self):
        return reverse('exp:study-detail', kwargs=dict(pk=self.object.id))

    def get_initial(self):
        """
        Returns initial data to use for the create study form - make default
        structure field data an empty dict
        """
        initial = super().get_initial()
        initial['structure'] = json.dumps(Study._meta.get_field('structure').default)
        return initial


class StudyListView(ExperimenterLoginRequiredMixin, DjangoPermissionRequiredMixin, generic.ListView, PaginatorMixin):
    '''
    StudyListView shows a list of studies that a user has permission to.
    '''
    model = Study
    permission_required = 'accounts.can_view_experimenter'
    raise_exception = True
    template_name = 'studies/study_list.html'

    def get_queryset(self, *args, **kwargs):
        """
        Returns paginated list of items for the StudyListView - handles filtering on state, match,
        and sort.
        """
        request = self.request.GET
        queryset = get_objects_for_user(self.request.user, 'studies.can_view_study').exclude(state='archived')
        queryset = queryset.select_related('creator')
        queryset = queryset.annotate(completed_responses_count=Count(Case(When(responses__completed=True, then=1))))
        queryset = queryset.annotate(incomplete_responses_count=Count(Case(When(responses__completed=False, then=1))))

        state = request.get('state')
        if state and state != 'all':
            if state == 'myStudies':
                queryset = queryset.filter(creator=self.request.user)
            else:
                queryset = queryset.filter(state=state)

        match = request.get('match')
        if match:
            queryset = queryset.filter(reduce(operator.or_,
              (Q(name__icontains=term) | Q(short_description__icontains=term) for term in match.split())))

        sort = request.get('sort', '')
        if 'name' in sort:
            queryset = queryset.order_by(Lower('name').desc() if '-' in sort else Lower('name').asc())
        elif 'beginDate' in sort:
            # TODO optimize using subquery
            queryset = sorted(queryset, key=lambda t: t.begin_date or timezone.now(), reverse=True if '-' in sort else False)
        elif 'endDate' in sort:
            # TODO optimize using subquery
            queryset = sorted(queryset, key=lambda t: t.end_date or timezone.now(), reverse=True if '-' in sort else False)
        else:
            queryset = queryset.order_by(Lower('name'))

        return self.paginated_queryset(queryset, request.get('page'), 10)

    def get_context_data(self, **kwargs):
        """
        Gets the context for the StudyListView and supplements with the state, match, and sort query params.
        """
        context = super().get_context_data(**kwargs)
        context['state'] = self.request.GET.get('state', 'all')
        context['match'] = self.request.GET.get('match', '')
        context['sort'] = self.request.GET.get('sort', 'name')
        context['page'] = self.request.GET.get('page', '1')
        context['can_create_study'] = self.request.user.has_perm('studies.can_create_study')
        return context


class StudyDetailView(ExperimenterLoginRequiredMixin, PermissionRequiredMixin, generic.DetailView, PaginatorMixin):
    '''
    StudyDetailView shows information about a study. Can view basic metadata about a study, can view
    study logs, and can change a study's state.
    '''
    template_name = 'studies/study_detail.html'
    model = Study
    permission_required = 'studies.can_view_study'
    raise_exception = True

    def post(self, *args, **kwargs):
        """
        Post method can update the trigger if the state of the study has changed.  If "clone" study
        button is pressed, clones study and redirects to the clone.
        """
        if 'trigger' in self.request.POST:
            update_trigger(self)
        if self.request.POST.get('clone_study'):
            clone = self.get_object().clone()
            clone.creator = self.request.user
            clone.organization = self.request.user.organization
            clone.save()
            # Adds success message when study is cloned
            messages.success(self.request, f"{self.get_object().name} copied.")
            self.add_creator_to_study_admin_group(clone)
            return HttpResponseRedirect(reverse('exp:study-detail', kwargs=dict(pk=clone.pk)))
        return HttpResponseRedirect(reverse('exp:study-detail', kwargs=dict(pk=self.get_object().pk)))

    def add_creator_to_study_admin_group(self, clone):
            """
            Add the study's creator to the clone's study admin group.
            """
            study_admin_group = clone.study_admin_group
            study_admin_group.user_set.add(self.request.user)
            return study_admin_group

    def get_queryset(self):
        """
        Returns the queryset that is used to lookup the study object. Annotates
        the queryset with the completed and incomplete responses counts.
        """
        queryset = super().get_queryset()
        queryset = queryset.annotate(completed_responses_count=Count(Case(When(responses__completed=True, then=1))))
        queryset = queryset.annotate(incomplete_responses_count=Count(Case(When(responses__completed=False, then=1))))
        return queryset

    @property
    def study_logs(self):
        """ Returns a page object with 10 study logs"""
        logs_list = self.object.logs.all().order_by('-created_at')
        page = self.request.GET.get('page')
        return self.paginated_queryset(logs_list, page, 10)

    def get_context_data(self, **kwargs):
        """
        Adds several items to the context dictionary - the study, applicable triggers for the study,
        paginated study logs, and a tooltip that is dependent on the study's current state
        """
        context = super(StudyDetailView, self).get_context_data(**kwargs)
        context['triggers'] = get_permitted_triggers(self,
            self.object.machine.get_triggers(self.object.state))
        context['logs'] = self.study_logs
        state = self.object.state
        context['status_tooltip'] = status_tooltip_text.get(state, state)
        return context


class StudyParticipantEmailView(ExperimenterLoginRequiredMixin, PermissionRequiredMixin, generic.DetailView):
    '''
    StudyParticipantEmailView allows user to send a custom email to a participant.
    '''
    model = Study
    permission_required = 'studies.can_edit_study'
    raise_exception = True
    template_name = 'studies/study_participant_email.html'

    def get_context_data(self, **kwargs):
        """
        Adds email to the context_data dictionary
        """
        context = super().get_context_data(**kwargs)
        context['sender'] = settings.EMAIL_FROM_ADDRESS
        context['participants'] = self.get_study_participants()
        return context

    def get_study_participants(self):
        '''
        Restricts list to participants that have responded to this study as well as participants
        that have given their permission to be emailed personally
        '''
        return User.objects.filter(Q(children__response__study__id=self.get_object().id) & Q(email_personally=True)).distinct()

    def post(self, request, *args, **kwargs):
        """
        Post form for emailing participants.
        """
        retval = super().get(request, *args, **kwargs)
        email_form = self.request.POST
        researcher = User.objects.get(id=self.request.user.id)

        sender = email_form['sender']
        subject = email_form['subject']
        message = email_form['message']
        recipients = list(User.objects.filter(pk__in=email_form.getlist('recipients')).values_list('username', flat=True))
        try:
            send_mail(None, subject, recipients, bcc=recipients, custom_message=message, from_email=sender)
            messages.success(self.request, "Your message has been sent.")
            self.create_email_log(researcher, recipients, message, subject)
            return HttpResponseRedirect(self.get_success_url())
        except BadHeaderError:
            messages.error(self.request, "Invalid header found.")
        return HttpResponseRedirect(reverse('exp:study-participant-email'))

    def create_email_log(self, researcher, recipients, body, subject ):
        return StudyLog.objects.create(
                extra={"researcher_id": researcher.id, "participant_ids": recipients, "body": body, "subject": subject},
                action="email sent",
                study=self.get_object(),
                user=researcher
            )

    def get_success_url(self):
        return reverse('exp:study-detail', kwargs={'pk': self.object.id})


class StudyUpdateView(ExperimenterLoginRequiredMixin, PermissionRequiredMixin, generic.UpdateView, PaginatorMixin):
    '''
    StudyUpdateView allows user to edit study metadata, add researchers to study, update researcher permissions, and delete researchers from study.
    Also allows you to update the study status.
    '''
    template_name = 'studies/study_edit.html'
    form_class = StudyEditForm
    model = Study
    permission_required = 'studies.can_edit_study'
    raise_exception = True

    def get_study_researchers(self):
        '''  Pulls researchers that belong to Study Admin and Study Read groups - Not showing Org Admin and Org Read in this list (even though they technically
        can view the project.) '''
        study = self.get_object()
        return User.objects.filter(Q(groups__name=self.get_object().study_admin_group.name) | Q(groups__name=self.get_object().study_read_group.name)).distinct().order_by(Lower('family_name').asc())

    def search_researchers(self):
        ''' Searches user first, last, and middle names for search query. Does not display researchers that are already on project '''
        search_query = self.request.GET.get('match', None)
        researchers_result = None
        if search_query:
            current_researcher_ids = self.get_study_researchers().values_list('id', flat=True)
            user_queryset = User.objects.filter(organization=self.get_object().organization,is_active=True)
            researchers_result = user_queryset.filter(reduce(operator.or_,
              (Q(family_name__icontains=term) | Q(given_name__icontains=term)  | Q(middle_name__icontains=term) for term in search_query.split()))).exclude(id__in=current_researcher_ids).distinct().order_by(Lower('family_name').asc())
            researchers_result = self.build_researchers_paginator(researchers_result)
        return researchers_result

    def build_researchers_paginator(self, researchers_result):
        '''
        Builds paginated search results for researchers
        '''
        page = self.request.GET.get('page')
        return self.paginated_queryset(researchers_result, page, 5)

    def manage_researcher_permissions(self):
        '''
        Handles adding, updating, and deleting researcher from study. Users are
        added to study read group by default.
        '''
        study_read_group = self.get_object().study_read_group
        study_admin_group = self.get_object().study_admin_group
        add_user = self.request.POST.get('add_user')
        remove_user = self.request.POST.get('remove_user')
        update_user = None
        if self.request.POST.get('name') == 'update_user':
             update_user = self.request.POST.get('pk')
             permissions = self.request.POST.get('value')

        if add_user:
            # Adds user to study read by default
            add_user_object = User.objects.get(pk=add_user)
            study_read_group.user_set.add(add_user_object)
            messages.success(self.request, f"{add_user_object.get_short_name()} given {self.get_object().name} Read Permissions.", extra_tags='user_added')
        if remove_user:
            # Removes user from both study read and study admin groups
            remove = User.objects.get(pk=remove_user)
            study_read_group.user_set.remove(remove)
            study_admin_group.user_set.remove(remove)
            messages.success(self.request, f"{remove.get_short_name()} removed from {self.get_object().name}.", extra_tags='user_removed')
        if update_user:
            update = User.objects.get(pk=update_user)
            if permissions == 'study_admin':
                # if admin, removes user from study read and adds to study admin
                study_read_group.user_set.remove(update)
                study_admin_group.user_set.add(update)
            if permissions == 'study_read':
                # if read, removes user from study admin and adds to study read
                study_read_group.user_set.add(update)
                study_admin_group.user_set.remove(update)

    def post(self, request, *args, **kwargs):
        '''
        Handles all post forms on page - 1) study metadata like name, short_description, etc. 2) researcher add 3) researcher update
        4) researcher delete 5) Changing study status / adding rejection comments
        '''
        if 'trigger' in self.request.POST:
            update_trigger(self)
        self.manage_researcher_permissions()
        if 'short_description' in self.request.POST:
            # Study metadata is being edited
            return super().post(request, *args, **kwargs)

        return HttpResponseRedirect(reverse('exp:study-edit', kwargs=dict(pk=self.get_object().pk)))

    def form_valid(self, form):
        """
        Add success message that edits to study have been saved.
        """
        ret = super().form_valid(form)
        messages.success(self.request, f"{self.get_object().name} study details saved.")
        return ret

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.
        """
        context = super().get_context_data(**kwargs)
        state = self.object.state

        context['current_researchers'] = self.get_study_researchers()
        context['users_result'] = self.search_researchers()
        context['search_query'] = self.request.GET.get('match')
        context['status_tooltip'] = status_tooltip_text.get(state, state)
        context['triggers'] = get_permitted_triggers(self, self.object.machine.get_triggers(state))
        context['name'] = self.request.GET.get('match', None)
        context['save_confirmation'] = state in ['approved', 'active', 'paused', 'deactivated']
        return context


    def get_success_url(self):
        return reverse('exp:study-edit', kwargs={'pk': self.object.id})


class StudyBuildView(ExperimenterLoginRequiredMixin, PermissionRequiredMixin, generic.UpdateView):
    """
    StudyBuildView allows user to modify study structure - JSON field.
    """
    model = Study
    form_class = StudyBuildForm
    template_name = 'studies/study_json.html'
    permission_required = 'studies.can_edit_study'
    raise_exception = True

    def get_initial(self):
        """
        Returns the initial data to use for forms on this view.
        """
        initial = super().get_initial()
        structure = self.object.structure
        if structure:
            # Ensures that json displayed in edit form is valid json w/ double quotes,
            # so incorrect json is not saved back into the db
            initial['structure'] = json.dumps(structure)
        return initial

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds whether save confirmation is needed to study.
        """
        context = super().get_context_data(**kwargs)
        context['save_confirmation'] = self.object.state in ['approved', 'active', 'paused', 'deactivated']
        return context

    def get_success_url(self):
        return reverse('exp:study-build', kwargs=dict(pk=self.object.id))

    def form_valid(self, form):
        """
        Add success message that study JSON has been successfully saved.
        """
        ret = super().form_valid(form)
        messages.success(self.request, f"{self.get_object().name} study JSON saved.")
        return ret


class StudyResponsesList(ExperimenterLoginRequiredMixin, PermissionRequiredMixin, generic.DetailView, PaginatorMixin):
    """
    Study Responses View allows user to view responses to a study. Responses can be viewed individually,
    all responses can be downloaded, and study attachments can be downloaded.
    """
    template_name = 'studies/study_responses.html'
    model = Study
    permission_required = 'studies.can_view_study_responses'
    raise_exception = True

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.  Study results
        are paginated.
        """
        context = super().get_context_data(**kwargs)
        orderby = self.request.GET.get('sort', 'id')
        page = self.request.GET.get('page', None)
        study = context['study']
        responses = study.responses.order_by(orderby)
        context['responses'] = self.paginated_queryset(responses, page, 10)
        context['response_data'] = self.build_responses(context['responses'])
        context['csv_data'] = self.build_individual_csv(context['responses'])
        context['all_responses'] = ', '.join(self.build_responses(responses))
        context['csv_responses'] = self.build_all_csv(responses)
        return context

    def build_responses(self, responses):
        """
        Builds the JSON response data for the researcher to download
        """
        return [json.dumps({
            'sequence': resp.sequence,
            'conditions': resp.conditions,
            'exp_data': resp.exp_data,
            'participant_id': resp.child.user.id,
            'global_event_timings': resp.global_event_timings,
            'child_id': resp.child.id,
            'completed': resp.completed,
            'study_id': resp.study.id,
            'response_id': resp.id,
            'demographic_id': resp.demographic_snapshot.id
            }, indent=4) for resp in responses]

    def get_csv_headers(self):
        """
        Returns header row for csv data
        """
        return ['sequence', 'conditions', 'exp_data', 'participant_id', 'global_event_timings',
            'child_id', 'completed', 'study_id', 'response_id', 'demographic_id']

    def build_individual_csv(self, responses):
        """
        Builds CSV for individual responses and puts them in array
        """
        csv_responses = []
        for resp in responses:
            output, writer = self.csv_output_and_writer()
            writer.writerow(self.get_csv_headers())
            writer.writerow(self.csv_row_data(resp))
            csv_responses.append(output.getvalue())
        return csv_responses

    def csv_row_data(self, resp):
        """
        Builds individual row for csv responses
        """
        return [resp.sequence, resp.conditions, resp.exp_data, resp.child.user.id,
        resp.global_event_timings, resp.child.id, resp.completed, resp.study.id, resp.id,
        resp.demographic_snapshot.id]

    def csv_output_and_writer(self):
        output = io.StringIO()
        return output, csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)

    def build_all_csv(self, responses):
        """
        Builds CSV file contents for all responses
        """
        output, writer = self.csv_output_and_writer()
        writer.writerow(self.get_csv_headers())
        for resp in responses:
            writer.writerow(self.csv_row_data(resp))
        return output.getvalue()


class PreviewProxyView(ProxyView, ExperimenterLoginRequiredMixin):
    '''
    Proxy view to forward researcher to preview page in the Ember app
    '''
    upstream = settings.EXPERIMENT_BASE_URL

    def dispatch(self, request, path, *args, **kwargs):
        return super().dispatch(request, path)
