import operator
from functools import reduce

from django.http import Http404
from guardian.mixins import PermissionRequiredMixin
from django.contrib.auth.mixins import PermissionRequiredMixin as DjangoPermissionRequiredMixin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.db.models.functions import Lower
from django.shortcuts import reverse
from django.views import generic
from guardian.mixins import LoginRequiredMixin
from guardian.shortcuts import get_objects_for_user
from django.db.models import Q

from accounts.forms import UserStudiesForm
from accounts.models import User
from accounts.utils import build_org_group_name
from guardian.mixins import LoginRequiredMixin
from guardian.shortcuts import get_objects_for_user
from studies.models import Response, Study


class ParticipantListView(LoginRequiredMixin, DjangoPermissionRequiredMixin, generic.ListView):
    '''
    ParticipantListView shows a list of participants that have participated in studies
    related to organizations that the current user has permissions to.
    '''
    template_name = 'accounts/participant_list.html'
    queryset = User.objects.all().exclude(demographics__isnull=True)
    permission_required = 'accounts.can_view_experimenter'
    raise_exception = True
    model = User

    def get_queryset(self):
        qs = super().get_queryset()
        # TODO this should probably use permissions eventually, just to be safe
        match = self.request.GET.get('match', False)
        order = self.request.GET.get('sort', False) or 'family_name' # to prevent empty string overriding default here
        if match:
            qs = qs.filter(reduce(operator.or_,
              (Q(family_name__icontains=term) | Q(given_name__icontains=term) | Q(username__icontains=term) for term in match.split())))
        return qs.order_by(order)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['match'] = self.request.GET.get('match', '')
        context['sort'] = self.request.GET.get('sort', '')
        return context


class ParticipantDetailView(LoginRequiredMixin, PermissionRequiredMixin, generic.UpdateView):
    '''
    ParticipantDetailView shows information about a participant that has participated in studies
    related to organizations that the current user has permission to.
    '''
    queryset = User.objects.exclude(demographics__isnull=True)
    fields = ('is_active', )
    template_name = 'accounts/participant_detail.html'
    permission_required = 'accounts.can_view_users'
    raise_exception = True
    model = User

    def get_context_data(self, **kwargs):
        context = super(ParticipantDetailView, self).get_context_data(**kwargs)
        user = context['user']
        context['demographics'] = user.latest_demographics.to_display() if user.latest_demographics else None
        context['studies'] = self.get_study_info()
        return context

    def get_study_info(self):
        """ Pulls responses belonging to user and returns study info """
        resps = Response.objects.filter(child__user=self.get_object())
        orderby = self.request.GET.get('sort', None)
        if orderby:
            if 'date_modified' in orderby:
                resps = resps.order_by(orderby)
            elif 'completed' in orderby:
                resps = resps.order_by(orderby.replace('-', '') if '-' in orderby else '-' + orderby)
        studies = [{'modified': resp.date_modified, 'study': resp.study, 'name': resp.study.name, 'completed': resp.completed} for resp in resps]
        if orderby and 'name' in orderby:
            studies = sorted(studies, key=operator.itemgetter('name'), reverse=True if '-' in orderby else False)
        return studies

    def get_success_url(self):
        return reverse('exp:participant-detail', kwargs={'pk': self.object.id})


class ResearcherListView(LoginRequiredMixin, DjangoPermissionRequiredMixin, generic.ListView):
    '''
    Displays a list of researchers that belong to the org admin, org read, or org researcher groups.
    '''
    template_name = 'accounts/researcher_list.html'
    # TODO needs to change once oauth in
    queryset = User.objects.filter(demographics__isnull=True, is_active=True)
    model = User
    permission_required = 'accounts.can_view_organization'
    raise_exception = True

    def get_org_groups(self):
        """
        Fetches the org admin, org read, and org researcher groups for the organization that
        the current user belongs to
        """
        user_org_name = self.request.user.organization.name
        admin_group = Group.objects.get(name=build_org_group_name(user_org_name, 'admin'))
        read_group = Group.objects.get(name=build_org_group_name(user_org_name, 'read'))
        researcher_group = Group.objects.get(name=build_org_group_name(user_org_name, 'researcher'))
        return admin_group, read_group, researcher_group

    def get_queryset(self):
        """
        Restricts queryset on active users that belong to the org admin, org read, or org researcher groups. Handles filtering on name and sorting.
        """
        qs = super().get_queryset()
        admin_group, read_group, researcher_group = self.get_org_groups()
        queryset = qs.filter(Q(groups__name=admin_group.name) | Q(groups__name=read_group.name) | Q(groups__name=researcher_group.name)).distinct().order_by(Lower('family_name').asc())

        match = self.request.GET.get('match')
        # Can filter on first, middle, and last names
        if match:
            queryset = queryset.filter(reduce(operator.or_,
              (Q(family_name__icontains=term) | Q(given_name__icontains=term) | Q(middle_name__icontains=term) for term in match.split())))
        sort = self.request.GET.get('sort')
        if sort:
            if 'family_name' in sort:
                queryset = queryset.order_by(Lower('family_name').desc()) if '-' in sort else queryset.order_by(Lower('family_name').asc())
        queryset = queryset.select_related('organization')
        return queryset

    def post(self, request, *args, **kwargs):
        """
        Post form for disabling a researcher. If researcher is deleted - is actually disabled, then removed
        from org admin, org read, and org researcher groups.
        """
        retval = super().get(request, *args, **kwargs)
        if 'disable' in self.request.POST and self.request.method == 'POST':
            researcher = User.objects.get(pk=self.request.POST['disable'])
            researcher.is_active = False
            researcher.save()
            self.remove_researcher_from_org_groups(researcher)
        return retval

    def remove_researcher_from_org_groups(self, researcher):
        """
        Post form for disabling a researcher. If researcher is deleted - is actually disabled, then removed
        from org admin, org read, and org researcher groups.
        """
        admin_group, read_group, researcher_group = self.get_org_groups()
        admin_group.user_set.remove(researcher)
        read_group.user_set.remove(researcher)
        researcher_group.user_set.remove(researcher)
        return

    def get_context_data(self, **kwargs):
        """
        Adds match and sort query params to the context data
        """
        context = super().get_context_data(**kwargs)
        context['match'] = self.request.GET.get('match', '')
        context['sort'] = self.request.GET.get('sort', '')
        return context


class ResearcherDetailView(LoginRequiredMixin, DjangoPermissionRequiredMixin, generic.UpdateView):
    '''
    ResearcherDetailView shows information about a researcher and allows toggling the permissions
    on a user or modifying.
    '''
    queryset = User.objects.filter(demographics__isnull=True, is_active=True)
    fields = ('is_active', )
    template_name = 'accounts/researcher_detail.html'
    model = User
    permission_required = 'accounts.can_edit_organization'
    raise_exception = True

    def get_queryset(self):
        """
        Restrict queryset so org admins can only modify users in their organization
        """
        qs = super().get_queryset()
        return qs.filter(organization=self.request.user.organization)

    def get_success_url(self):
        return reverse('exp:researcher-detail', kwargs={'pk': self.object.id})

    def post(self, request, *args, **kwargs):
        """
        Handles modification of user given_name, middle_name, family_name as well as
        user permissions
        """
        retval = super().post(request, *args, **kwargs)
        changed_field = self.request.POST.get('name')
        if changed_field == 'given_name':
            self.object.given_name = self.request.POST['value']
        elif changed_field == 'middle_name':
            self.object.middle_name = self.request.POST['value']
        elif changed_field == 'family_name':
            self.object.family_name = self.request.POST['value']
        self.object.is_active = True
        self.object.save()
        if self.request.POST.get('name') == 'user_permissions':
            self.modify_researcher_permissions()
        return retval

    def modify_researcher_permissions(self):
        """
        Modifies researcher permissions by adding the user to the respective admin,
        read, or researcher group. They inherit the permissions of that org group.
        """
        new_perm = self.request.POST['value']
        org_name = self.request.user.organization.name

        admin_group = Group.objects.get(name=build_org_group_name(org_name, 'admin'))
        read_group = Group.objects.get(name=build_org_group_name(org_name, 'read'))
        researcher_group = Group.objects.get(name=build_org_group_name(org_name, 'researcher'))

        researcher = self.get_object()

        if new_perm == 'org_admin':
            admin_group.user_set.add(researcher)
            read_group.user_set.remove(researcher)
            researcher_group.user_set.remove(researcher)
        elif new_perm == 'org_read':
            read_group.user_set.add(researcher)
            admin_group.user_set.remove(researcher)
            researcher_group.user_set.remove(researcher)
        else:
            researcher_group.user_set.add(researcher)
            admin_group.user_set.remove(researcher)
            read_group.user_set.remove(researcher)
        return
