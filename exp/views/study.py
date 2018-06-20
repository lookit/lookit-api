import io
import json
import operator
import os
import zipfile
from functools import reduce

import requests
from django.contrib import messages
from django.contrib.auth.mixins import \
    PermissionRequiredMixin as DjangoPermissionRequiredMixin
from django.core.mail import BadHeaderError
from django.db.models import Case, Count, Q, When
from django.db.models.functions import Lower
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, reverse
from django.utils import timezone
from django.views import generic
from guardian.mixins import PermissionRequiredMixin
from guardian.shortcuts import get_objects_for_user, get_perms
from localflavor import pk
from revproxy.views import ProxyView

import attachment_helpers
from accounts.models import User
from accounts.utils import (get_permitted_triggers, status_tooltip_text,
                            update_trigger)
from exp.mixins.paginator_mixin import PaginatorMixin
from exp.mixins.study_responses_mixin import StudyResponsesMixin
from exp.views.mixins import ExperimenterLoginRequiredMixin, StudyTypeMixin
from project import settings
from studies.forms import StudyBuildForm, StudyEditForm, StudyForm
from studies.helpers import send_mail
from studies.models import Study, StudyLog, StudyType
from studies.tasks import build_experiment, build_zipfile_of_videos


class StudyCreateView(ExperimenterLoginRequiredMixin, DjangoPermissionRequiredMixin, generic.CreateView, StudyTypeMixin):
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
        form.instance.metadata = self.extract_type_metadata()
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

    def get_context_data(self, **kwargs):
        """
        Adds study types to get_context_data
        """
        context = super().get_context_data(**kwargs)
        context['types'] = [study_type['metadata']['fields'] for study_type in StudyType.objects.all().values_list('configuration', flat=True)]
        return context

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
            clone.study_type = self.get_object().study_type
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
        context['email_next_session'] = self.get_study_participants('email_next_session')
        context['email_new_studies'] = self.get_study_participants('email_new_studies')
        context['email_study_updates'] = self.get_study_participants('email_study_updates')
        context['email_response_questions'] = self.get_study_participants('email_response_questions')
        return context

    def get_study_participants(self, email_field):
        '''
        Restricts list to participants that have responded to this study as well as participants
        that have given their permission to be emailed personally
        '''
        return User.objects.filter(Q(children__response__study=self.get_object()) & Q(**{f'{email_field}': True })).distinct()

    def post(self, request, *args, **kwargs):
        """
        Post form for emailing participants.
        """
        retval = super().get(request, *args, **kwargs)
        email_form = self.request.POST

        sender = email_form['sender']
        subject = email_form['subject']
        message = email_form['message']
        recipients = list(User.objects.filter(pk__in=email_form.getlist('recipients')).values_list('username', flat=True))
        try:
            context = {
                'custom_message': message
            }
            send_mail.delay('custom_email', subject, settings.EMAIL_FROM_ADDRESS, bcc=recipients, from_email=sender, **context)
            messages.success(self.request, "Your message has been sent.")
            self.create_email_log(recipients, message, subject)
            return HttpResponseRedirect(self.get_success_url())
        except BadHeaderError:
            messages.error(self.request, "Invalid header found.")
        return HttpResponseRedirect(reverse('exp:study-participant-email'))

    def create_email_log(self, recipients, body, subject ):
        return StudyLog.objects.create(
                extra={"researcher_id": self.request.user.id, "participant_ids": recipients, "body": body, "subject": subject},
                action="email sent",
                study=self.get_object(),
                user=self.request.user
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

    def adequate_study_admins(self, admin_group, researcher):
        # Returns true if researchers's permissions can be edited, or researcher deleted,
        # with the constraint of there being at least one study admin at all times
        admins = User.objects.filter(groups__name=admin_group.name)
        return len(admins) - (researcher in admins) > 0

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
            self.send_study_email(add_user_object, 'read')
        if remove_user:
            # Removes user from both study read and study admin groups
            remove = User.objects.get(pk=remove_user)
            if self.adequate_study_admins(study_admin_group, remove):
                study_read_group.user_set.remove(remove)
                study_admin_group.user_set.remove(remove)
                messages.success(self.request, f"{remove.get_short_name()} removed from {self.get_object().name}.", extra_tags='user_removed')
            else:
                messages.error(self.request, "Could not delete this researcher. There must be at least one study admin.", extra_tags='user_removed')
        if update_user:
            update = User.objects.get(pk=update_user)
            if permissions == 'study_admin':
                # if admin, removes user from study read and adds to study admin
                study_read_group.user_set.remove(update)
                study_admin_group.user_set.add(update)
                self.send_study_email(update, 'admin')
            if permissions == 'study_read':
                # if read, removes user from study admin and adds to study read
                if self.adequate_study_admins(study_admin_group, update):
                    study_read_group.user_set.add(update)
                    study_admin_group.user_set.remove(update)
                    self.send_study_email(update, 'read')
        return

    def send_study_email(self, user, permission):
        study = self.get_object()
        context = {
            'permission': permission,
            'study_name': study.name,
            'study_id': study.id,
            'org_name': user.organization.name,
            'researcher_name': user.get_short_name()
        }
        send_mail.delay('notify_researcher_of_study_permissions', f' Invitation to collaborate on {self.get_object().name}', user.username, from_address=settings.EMAIL_FROM_ADDRESS, **context)

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
        admin_group = self.get_object().study_admin_group

        context['current_researchers'] = self.get_study_researchers()
        context['users_result'] = self.search_researchers()
        context['search_query'] = self.request.GET.get('match')
        context['status_tooltip'] = status_tooltip_text.get(state, state)
        context['triggers'] = get_permitted_triggers(self, self.object.machine.get_triggers(state))
        context['name'] = self.request.GET.get('match', None)
        context['save_confirmation'] = state in ['approved', 'active', 'paused', 'deactivated']
        context['multiple_admins'] = len(User.objects.filter(groups__name=admin_group.name)) > 1
        context['study_admins'] = User.objects.filter(groups__name=admin_group.name).values_list('id', flat=True)
        return context


    def get_success_url(self):
        return reverse('exp:study-edit', kwargs={'pk': self.object.id})


class StudyBuildView(ExperimenterLoginRequiredMixin, PermissionRequiredMixin, generic.UpdateView, StudyTypeMixin):
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

    def post(self, request, *args, **kwargs):
        """
        Form for allowing user to change study type and study metadata fields
        """
        study = self.get_object()
        if 'structure' not in self.request.POST:
            study.metadata = self.extract_type_metadata()
            study.study_type_id = StudyType.objects.filter(id=self.request.POST.get('study_type')).values_list('id', flat=True)[0]
            study.save()
            messages.success(self.request, f"{self.get_object().name} type and metadata saved.")
            return HttpResponseRedirect(reverse('exp:study-build', kwargs=dict(pk=study.pk)))
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds whether save confirmation is needed to study, as well as all study_types
        and current metadata
        """
        context = super().get_context_data(**kwargs)
        context['save_confirmation'] = self.object.state in ['approved', 'active', 'paused', 'deactivated']
        context['study_types'] = StudyType.objects.all()
        context['study_metadata'] = self.object.metadata
        context['types'] = [exp_type.configuration['metadata']['fields'] for exp_type in context['study_types']]

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


class StudyResponsesList(StudyResponsesMixin, generic.DetailView, PaginatorMixin):
    """
    Study Responses View allows user to view individual responses to a study.
    """
    template_name = 'studies/study_responses.html'

    def get_responses_orderby(self):
        """
        Determine sort field and order. Sorting on id actually sorts on user id, not response id.
        Sorting on status, actually sorts on 'completed' field, where we are alphabetizing
        "in progress" and "completed"
        """
        orderby = self.request.GET.get('sort', 'id')
        reverse = '-' in orderby
        if 'id' in orderby:
            orderby = '-child__user__id' if reverse else 'child__user__id'
        if 'status' in orderby:
            orderby = 'completed' if reverse else '-completed'
        return orderby

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.  Study results
        are paginated.
        """
        context = super().get_context_data(**kwargs)
        page = self.request.GET.get('page', None)
        orderby = self.get_responses_orderby()
        responses = context['study'].responses.order_by(orderby)
        context['responses'] = self.paginated_queryset(responses, page, 10)
        context['response_data'] = self.build_responses(context['responses'])
        context['csv_data'] = self.build_individual_csv(context['responses'])
        context['attachment_list'] = self.sort_attachments_by_response(context['responses'])
        return context

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

    def sort_attachments_by_response(self, responses):
        """
        Build a list of list of videos for each response
        """
        study = self.get_object()
        attachments = attachment_helpers.get_study_attachments(study)
        all_attachments = []
        for response in responses:
            uuid = str(response.uuid)
            att_list = []
            for attachment in attachments:
                if uuid in attachment.key:
                    att_list.append({'key': attachment.key, 'display': self.build_video_display_name(str(study.uuid), uuid, attachment.key) })
            all_attachments.append(att_list)
        return all_attachments

    def build_video_display_name(self, study_uuid, response_uuid, vid_name):
        """
        Strips study_uuid and response_uuid out of video responses titles for better display.
        """
        return '. . .'+ '. . .'.join(vid_name.split(study_uuid + '_')[1].split('_' + response_uuid + '_'))


class StudyResponsesAll(StudyResponsesMixin, generic.DetailView):
    """
    StudyResponsesAll shows all study responses in JSON and CSV format.
    Either format can be downloaded
    """
    template_name = 'studies/study_responses_all.html'

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.  Study results
        are paginated.
        """
        context = super().get_context_data(**kwargs)
        responses = context['study'].responses.order_by('id')
        context['all_responses'] = ', '.join(self.build_responses(responses))
        context['csv_responses'] = self.build_all_csv(responses)
        return context

    def build_all_csv(self, responses):
        """
        Builds CSV file contents for all responses
        """
        output, writer = self.csv_output_and_writer()
        writer.writerow(self.get_csv_headers())
        for resp in responses:
            writer.writerow(self.csv_row_data(resp))
        return output.getvalue()


class StudyResponsesAllDownloadJSON(StudyResponsesMixin, generic.DetailView):
    """
    Hitting this URL downloads all study responses in JSON format.
    """
    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.responses.order_by('id')
        cleaned_data = ', '.join(self.build_responses(responses))
        filename = '{}-{}.json'.format(study.name, 'all_responses')
        response = HttpResponse(cleaned_data, content_type='text/json')
        response['Content-Disposition'] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponsesAllDownloadCSV(StudyResponsesAll):
    """
    Hitting this URL downloads all study responses in CSV format.
    """
    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.responses.order_by('id')
        cleaned_data = self.build_all_csv(responses)
        filename = '{}-{}.csv'.format(study.name, 'all_responses')
        response = HttpResponse(cleaned_data, content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="{}"'.format(filename)
        return response

class StudyDemographics(StudyResponsesMixin, generic.DetailView):
    """
    StudyParticiapnts view shows participant demographic snapshots associated
    with each response to the study
    """
    template_name = 'studies/study_demographics.html'

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.  Study results
        are paginated.
        """
        context = super().get_context_data(**kwargs)
        responses = context['study'].responses.order_by('id')
        context['all_responses'] = ', '.join(self.build_participant_data(responses))
        context['csv_responses'] = self.build_all_participant_csv(responses)
        return context

    def build_all_participant_csv(self, responses):
        """
        Builds CSV file contents for all participant data
        """
        output, writer = self.csv_output_and_writer()
        writer.writerow(self.get_csv_participant_headers())
        for resp in responses:
            writer.writerow(self.build_csv_participant_row_data(resp))
        return output.getvalue()

class StudyDemographicsDownloadJSON(StudyResponsesMixin, generic.DetailView):
    """
    Hitting this URL downloads all participant demographics in JSON format.
    """
    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.responses.order_by('id')
        cleaned_data = ', '.join(self.build_participant_data(responses))
        filename = '{}-{}.json'.format(study.name, 'all_demographic_snapshots')
        response = HttpResponse(cleaned_data, content_type='text/json')
        response['Content-Disposition'] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyDemographicsDownloadCSV(StudyDemographics):
    """
    Hitting this URL downloads all participant demographics in CSV format.
    """
    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = study.responses.order_by('id')
        cleaned_data = self.build_all_participant_csv(responses)
        filename = '{}-{}.csv'.format(study.name, 'all_demographic_snapshots')
        response = HttpResponse(cleaned_data, content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyAttachments(StudyResponsesMixin, generic.DetailView, PaginatorMixin):
    """
    StudyAttachments View shows video attachments for the study
    """
    template_name = 'studies/study_attachments.html'

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.  Study results
        are paginated.
        """
        context = super().get_context_data(**kwargs)
        orderby = self.request.GET.get('sort', 'id') or 'id'
        match = self.request.GET.get('match', '')
        context['attachments'] = attachment_helpers.get_study_attachments(context['study'], orderby, match)
        context['match'] = match
        return context

    def post(self, request, *args, **kwargs):
        '''
        Downloads study video
        '''
        attachment = self.request.POST.get('attachment')
        match = self.request.GET.get('match', '')
        orderby = self.request.GET.get('sort', 'id') or 'id'
        if attachment:
            download_url = attachment_helpers.get_download_url(attachment)
            return redirect(download_url)

        if self.request.POST.get('all-attachments'):
            build_zipfile_of_videos.delay(f'{self.get_object().uuid}_all_attachments', self.get_object().uuid, orderby, match, self.request.user.uuid)
            messages.success(request, f"An archive of videos for {self.get_object().name} is being generated. You will be emailed a link when it's completed.")

        if self.request.POST.get('all-consent-videos'):
            build_zipfile_of_videos.delay(f'{self.get_object().uuid}_all_consent', self.get_object().uuid, orderby, match, self.request.user.uuid, consent=True)
            messages.success(request, f"An archive of consent videos for {self.get_object().name} is being generated. You will be emailed a link when it's completed.")

        return HttpResponseRedirect(reverse('exp:study-attachments', kwargs=dict(pk=self.get_object().pk)))


class StudyPreviewBuildView(generic.detail.SingleObjectMixin, generic.RedirectView):
    '''
    Checks to make sure an existing build isn't running, that the user has permissions
    to preview, and then triggers a preview build.
    '''
    http_method_names = ['post', ]
    model = Study
    _object = None

    @property
    def object(self):
        if not self._object:
            self._object = self.get_object(queryset=self.get_queryset())
        return self._object

    def get_redirect_url(self, *args, **kwargs):
        return reverse('exp:study-build', kwargs={'pk': str(self.object.pk)})

    def post(self, request, *args, **kwargs):
        study_permissions = get_perms(request.user, self.object)

        if study_permissions and 'can_edit_study' in study_permissions:
            build_experiment.delay(self.object.uuid, request.user.uuid, preview=True)
            messages.success(request, f"Scheduled Study {self.object.name} for preview. You will be emailed when it's completed.")
        return super().post(request, *args, **kwargs)

    def get_object(self, queryset=None):
        """
        Returns the object the view is displaying.
        By default this requires `self.queryset` and a `pk` or `slug` argument
        in the URLconf, but subclasses can override this to return any object.
        """
        # Use a custom queryset if provided; this is required for subclasses
        # like DateDetailView
        if queryset is None:
            queryset = self.get_queryset()
        uuid = self.kwargs.get('uuid')
        if uuid is not None:
            queryset = queryset.filter(uuid=uuid)

        if uuid is None:
            raise AttributeError("View %s must be called with "
                                 "a uuid."
                                 % self.__class__.__name__)
        try:
            # Get the single item from the filtered queryset
            obj = queryset.get()
        except queryset.model.DoesNotExist:
            raise Http404(_("No %(verbose_name)s found matching the query") %
                          {'verbose_name': queryset.model._meta.verbose_name})
        return obj


class PreviewProxyView(ProxyView, ExperimenterLoginRequiredMixin):
    '''
    Proxy view to forward researcher to preview page in the Ember app
    '''
    upstream = settings.PREVIEW_EXPERIMENT_BASE_URL

    def dispatch(self, request, path, *args, **kwargs):
        if request.path[-1] == '/':
            path = f"{path.split('/')[0]}/index.html"
        return super().dispatch(request, path)
