import operator
from functools import reduce

from django.http import Http404
from guardian.mixins import PermissionRequiredMixin
from django.contrib.auth.mixins import PermissionRequiredMixin as DjangoPermissionRequiredMixin
from django.contrib import messages
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.db.models.functions import Lower
from django.shortcuts import reverse
from django.views import generic
from exp.views.mixins import ExperimenterLoginRequiredMixin
from guardian.shortcuts import get_objects_for_user
from django.db.models import Q

from accounts.forms import UserStudiesForm
from accounts.models import User
from accounts.utils import build_org_group_name
from guardian.shortcuts import get_objects_for_user
from studies.models import Response, Study
from exp.mixins.paginator_mixin import PaginatorMixin
from exp.mixins.participant_mixin import ParticipantMixin


class ParticipantListView(ExperimenterLoginRequiredMixin, ParticipantMixin, generic.ListView, PaginatorMixin):
    '''
    ParticipantListView shows a list of participants that have responded to the studies the
    user has permission to view.
    '''
    template_name = 'accounts/participant_list.html'

    def get_queryset(self):
        '''
        Returns users that researcher has permission to view. Handles sorting and pagination.
        '''
        qs =  super().get_queryset()
        match = self.request.GET.get('match', False)
        order = self.request.GET.get('sort', 'given_name')
        if 'given_name' not in order and 'last_login' not in order:
            order = 'given_name'

        if match:
            qs = qs.filter(reduce(operator.or_,
              (Q(given_name__icontains=term) | Q(username__icontains=term) for term in match.split())))
        return self.paginated_queryset(qs.order_by(order), self.request.GET.get('page'), 10)

    def get_context_data(self, **kwargs):
        """
        Adds match and sort query params to context_data dict
        """
        context = super().get_context_data(**kwargs)
        context['match'] = self.request.GET.get('match', '')
        context['sort'] = self.request.GET.get('sort', '')
        return context


class ParticipantDetailView(ExperimenterLoginRequiredMixin, ParticipantMixin, generic.UpdateView, PaginatorMixin):
    '''
    ParticipantDetailView shows demographic information, children information, and
    studies that a participant has responded to.
    '''
    fields = ('is_active', )
    template_name = 'accounts/participant_detail.html'

    def get_context_data(self, **kwargs):
        """
        Adds user's latest demographics and studies to the context_data dictionary
        """
        context = super().get_context_data(**kwargs)
        user = context['user']
        context['demographics'] = user.latest_demographics.to_display() if user.latest_demographics else None
        context['studies'] = self.get_study_info()
        return context

    def get_study_info(self):
        """
        Returns paginated responses from a user with the study title, response
        id, completion status, and date modified.
        """
        resps = Response.objects.filter(child__user=self.get_object())
        orderby = self.request.GET.get('sort', None)
        if orderby:
            if 'date_modified' in orderby:
                resps = resps.order_by(orderby)
            elif 'completed' in orderby:
                resps = resps.order_by(orderby.replace('-', '') if '-' in orderby else '-' + orderby)
        studies = [{'modified': resp.date_modified, 'study': resp.study, 'name': resp.study.name, 'completed': resp.completed, 'response': resp} for resp in resps]
        if orderby and 'name' in orderby:
            studies = sorted(studies, key=operator.itemgetter('name'), reverse=True if '-' in orderby else False)
        return self.paginated_queryset(studies, self.request.GET.get('page'), 10)

    def get_success_url(self):
        return reverse('exp:participant-detail', kwargs={'pk': self.object.id})


class ResearcherListView(ExperimenterLoginRequiredMixin, DjangoPermissionRequiredMixin, generic.ListView, PaginatorMixin):
    '''
    Displays a list of researchers that belong to the org admin, org read, or org researcher groups.
    '''
    template_name = 'accounts/researcher_list.html'
    queryset = User.objects.filter(is_researcher=True, is_active=True)
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
        queryset = qs.filter(Q(Q(Q(groups=admin_group) | Q(groups=read_group) | Q(groups=researcher_group)) | Q(is_researcher=True, groups__isnull=True, organization__isnull=True))).distinct().order_by(Lower('family_name').asc())

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
        return self.paginated_queryset(queryset, self.request.GET.get('page'), 10)

    def post(self, request, *args, **kwargs):
        """
        Post form for disabling a researcher. If researcher is deleted - is actually disabled, then removed
        from org admin, org read, and org researcher groups.
        """
        retval = super().get(request, *args, **kwargs)
        if 'disable' in self.request.POST and self.request.method == 'POST':
            researcher = User.objects.get(pk=self.request.POST['disable'])
            researcher.is_active = False
            researcher.organization = None
            researcher.save()
            messages.success(self.request, f"{researcher.get_short_name()} removed from the {self.request.user.organization.name} organization.")
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


class ResearcherDetailView(ExperimenterLoginRequiredMixin, DjangoPermissionRequiredMixin, generic.UpdateView):
    '''
    ResearcherDetailView shows information about a researcher and allows toggling the permissions
    on a user or modifying.
    '''
    queryset = User.objects.filter(is_researcher=True, is_active=True)
    fields = ('is_active', )
    template_name = 'accounts/researcher_detail.html'
    model = User
    permission_required = 'accounts.can_edit_organization'
    raise_exception = True

    def get_queryset(self):
        """
        Restrict queryset so org admins can only modify users in their organization
        or unaffiliated researchers.
        """
        qs = super().get_queryset()
        return qs.filter(Q(Q(organization=self.request.user.organization) | Q(is_researcher=True, groups__isnull=True, organization__isnull=True))).distinct()

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
        if not self.object.organization:
            self.object.organization = request.user.organization
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
