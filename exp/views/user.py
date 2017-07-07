import operator
from functools import reduce

from django.shortcuts import reverse
from django.db.models import Q
from django.db.models.functions import Lower
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import PermissionRequiredMixin

from django.views import generic
from guardian.mixins import LoginRequiredMixin
from guardian.shortcuts import get_objects_for_user
from django.db.models import Q


from accounts.forms import UserStudiesForm
from accounts.models import User
from accounts.utils import build_group_name
from studies.models import Response, Study


class ParticipantListView(LoginRequiredMixin, generic.ListView):
    '''
    ParticipantListView shows a list of participants that have participated in studies
    related to organizations that the current user has permissions to.
    '''
    template_name = 'accounts/participant_list.html'
    queryset = User.objects.all().exclude(demographics__isnull=True)
    model = User

    def get_queryset(self):
        filter_val = self.request.GET.get('match', False)
        order = self.request.GET.get('sort', False) or 'family_name' # to prevent empty string overriding default here
        # TODO participants who have responded to studies the current user has permission to.
        q = Q(organization=self.request.user.organization)
        # q = Q(organization__isnull=False)
        if filter_val:
            q = q & (Q(family_name__icontains=filter_val) | Q(username__icontains=filter_val) | Q(given_name__icontains=filter_val))
        qs = super(ParticipantListView, self).get_queryset()
        return qs.filter(q).order_by(order)


class ParticipantDetailView(LoginRequiredMixin, generic.UpdateView):
    '''
    ParticipantDetailView shows information about a participant that has participated in studies
    related to organizations that the current user has permission to.
    '''
    # queryset = User.objects.exclude(demographics__isnull=True).select_related('organization')
    queryset = User.objects.all().select_related('organization')
    fields = ('is_active', )
    template_name = 'accounts/participant_detail.html'
    model = User

    def get_queryset(self):
        qs = super(ParticipantDetailView, self).get_queryset()
        return qs.filter(organization=self.request.user.organization)

    def get_context_data(self, **kwargs):
        context = super(ParticipantDetailView, self).get_context_data(**kwargs)
        orderby = self.request.GET.get('sort', None)
        user = context['user']
        context['children'] = [{
            'name': child.given_name,
            'birthday': child.birthday,
            'gender': child.get_gender_display(),
            'age_at_birth': child.age_at_birth,
            'age': child.age,
            'extra': child.additional_information
        } for child in user.children.all()]
        context['full_name'] = user.get_full_name()
        context['demographics'] = user.latest_demographics.to_display()
        # TODO studies no longer showing, cannot find a relationship, although this page showed them at some point
        context['studies'] = user.studies.order_by(orderby) if orderby else user.studies
        return context


    def get_success_url(self):
        return reverse('exp:participant-detail', kwargs={'pk': self.object.id})


class ResponseListView(LoginRequiredMixin, generic.ListView):
    '''
    Displays a list of responses for studies that the current user can view.
    '''
    template_name = 'accounts/response_list.html'

    def get_queryset(self):
        studies = get_objects_for_user(self.request.user, 'studies.can_view')
        return Response.objects.filter(study__in=studies).order_by('study__name')


class ResponseDetailView(LoginRequiredMixin, generic.DetailView):
    '''
    Displays a response.
    '''
    template_name = 'accounts/response_detail.html'

    def get_queryset(self):
        studies = get_objects_for_user(self.request.user, 'studies.can_view')
        return Response.objects.filter(study__in=studies).order_by('study__name')


class ResearcherListView(LoginRequiredMixin, PermissionRequiredMixin, generic.ListView):
    '''
    Displays a list of researchers in the same organization as the current user.
    '''
    template_name = 'accounts/researcher_list.html'
    queryset = User.objects.filter(demographics__isnull=True)
    model = User
    permission_required = 'accounts.can_view_users'
    raise_exception = True

    def get_queryset(self):
        qs = super(ResearcherListView, self).get_queryset()
        # TODO this should probably use permissions eventually, just to be safe
        queryset = qs.filter(organization=self.request.user.organization,is_active=True)
        match = self.request.GET.get('match')
        if match:
            queryset = queryset.filter(reduce(operator.or_,
              (Q(family_name__icontains=term) | Q(given_name__icontains=term) | Q(middle_name__icontains=term) for term in match.split())))
        sort = self.request.GET.get('sort')
        if sort:
            if 'family_name' in sort:
                queryset = queryset.order_by(Lower('family_name').desc()) if '-' in sort else queryset.order_by(Lower('family_name').asc())
        return queryset

    def post(self, request, *args, **kwargs):
        retval = super().get(request, *args, **kwargs)
        if 'disable' in self.request.POST and self.request.method == "POST":
            researcher = User.objects.get(pk=self.request.POST['disable'])
            researcher.is_active = False
            researcher.save()
        return retval

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['match'] = self.request.GET.get('match') or ''
        context['sort'] = self.request.GET.get('sort') or ''
        return context


class ResearcherDetailView(LoginRequiredMixin, PermissionRequiredMixin, generic.UpdateView):
    '''
    ResearcherDetailView shows information about a researcher and allows enabling or disabling
    a user.
    '''
    queryset = User.objects.filter(demographics__isnull=True)
    fields = ('is_active', )
    template_name = 'accounts/researcher_detail.html'
    model = User
    permission_required = 'accounts.can_view_users'
    raise_exception = True

    def get_success_url(self):
        return reverse('exp:researcher-detail', kwargs={'pk': self.object.id})

    def post(self, request, *args, **kwargs):
        retval = super(ResearcherDetailView, self).post(request, *args, **kwargs)

        if self.request.POST.get('name') == 'given_name':
            self.object.given_name = self.request.POST['value']
        if self.request.POST.get('name') == 'middle_name':
            self.object.middle_name = self.request.POST['value']
        if self.request.POST.get('name') == 'family_name':
            self.object.family_name = self.request.POST['value']
        if self.request.POST.get('name') == 'user_permissions':
            new_perm_short = self.request.POST['value']
            org_name = self.get_object().organization.name
            admin_group = Group.objects.get(name=build_group_name(org_name, 'admin'))
            read_group = Group.objects.get(name=build_group_name(org_name, 'read'))
            researcher = self.get_object()

            if new_perm_short == 'org_admin':
                admin_group.user_set.add(researcher)
            elif new_perm_short == 'org_read':
                read_group.user_set.add(researcher)
                admin_group.user_set.remove(researcher)
            else:
                admin_group.user_set.remove(researcher)
                read_group.user_set.remove(researcher)
        self.object.save()
        return retval


class AssignResearcherStudies(LoginRequiredMixin, generic.UpdateView):
    '''
    AssignUserStudies lists studies available and let's someone assign permissions
    to users.
    '''
    template_name = 'accounts/assign_studies_form.html'
    queryset = User.objects.filter(demographics__isnull=True)
    form_class = UserStudiesForm

    def get_success_url(self):
        return reverse('exp:researcher-list')

    def get_initial(self):
        permissions = ['studies.can_view', 'studies.can_edit']
        initial = super(AssignResearcherStudies, self).get_initial()
        initial['studies'] = get_objects_for_user(self.object, permissions)
        return initial

    def get_context_data(self, **kwargs):
        context = super(AssignResearcherStudies, self).get_context_data(**kwargs)
        # only show studies in their organization
        context['studies'] = Study.objects.filter(organization=context['user'].organization)
        return context


class ResearcherCreateView(LoginRequiredMixin, PermissionRequiredMixin, generic.CreateView):
    '''
    UserCreateView creates a user. It forces is_active to True; is_superuser
    and is_staff to False; and sets a random 12 char password.

    TODO Eventually this should email the user at their username/email once they
    are saved.
    TODO It should set an unusable password, send them an email to a url with that password
    in it as a token, let them set their own password after clicking the link. It should
    definitely check to make sure it's an unusable password before it allows the reset.
    '''
    model = User
    template_name = 'accounts/researcher_form.html'
    fields = (
        'username',
        'given_name',
        'middle_name',
        'family_name',
        'is_active',
        'is_staff',
        'is_superuser',
        'password'
    )
    permission_required = 'accounts.can_create_users'
    raise_exception = True

    def post(self, request, *args, **kwargs):
        # TODO put this on the view so that we can send the user an email once their user is saved
        # TODO alternatively send the password in a post_save signal under certain conditions
        self.user_password = User.objects.make_random_password(length=12)
        form = self.get_form()
        query_dict = form.data.copy()
        query_dict.update(is_active=True, is_superuser=False, is_staff=False, password=self.user_password)
        form.data = query_dict
        if form.is_valid():
            # implicitly add them to their creator's organization
            form.instance.organization = self.request.user.organization
            return self.form_valid(form)
        else:
            self.object = None
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse('exp:researcher-detail', kwargs={'pk': self.object.id})
        # return reverse('exp:assign-studies', kwargs={'pk': self.object.id})
