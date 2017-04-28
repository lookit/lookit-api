from django.shortcuts import reverse
from django.views import generic

from accounts.forms import UserStudiesForm
from accounts.models import User
from guardian.shortcuts import get_objects_for_user
from studies.models import Study


class UserListView(generic.ListView):
    queryset = User.objects.filter(demographics__isnull=True)
    model = User

    # TODO Pagination pls


class UserDetailView(generic.UpdateView):
    '''
    UserDetailView shows information about a user and allows enabling or disabling
    a user.
    '''
    queryset = User.objects.filter(demographics__isnull=True)
    fields = ('is_active', )
    template_name = 'accounts/user_detail.html'
    model = User

    def get_success_url(self):
        return reverse('collaborator-detail', kwargs={'pk': self.object.id})

    def post(self, request, *args, **kwargs):
        retval = super(UserDetailView, self).post(request, *args, **kwargs)
        if 'enable' in self.request.POST:
            self.object.is_active = True
        elif 'disable' in self.request.POST:
            self.object.is_active = False
        self.object.save()
        return retval


class AssignUserStudies(generic.UpdateView):
    '''
    AssignUserStudies lists studies available and let's someone assign permissions
    to users.
    '''
    template_name = 'accounts/assign_studies_form.html'
    queryset = User.objects.filter(demographics__isnull=True)
    form_class = UserStudiesForm

    def get_success_url(self):
        return reverse('collaborator-list')

    def get_initial(self):
        permissions = ['studies.view_study', 'studies.edit_study']
        initial = super(AssignUserStudies, self).get_initial()
        initial['studies'] = get_objects_for_user(self.object, permissions)
        return initial

    def get_context_data(self, **kwargs):
        context = super(AssignUserStudies, self).get_context_data(**kwargs)
        context['studies'] = Study.objects.all()
        return context


class UserCreateView(generic.CreateView):
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

    def post(self, request, *args, **kwargs):
        # TODO put this on the view so that we can send the user an email once their user is saved
        self.user_password = User.objects.make_random_password(length=12)
        form = self.get_form()
        query_dict = form.data.copy()
        query_dict.update(is_active=True, is_superuser=False, is_staff=False, password=self.user_password)
        form.data = query_dict
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse('assign-studies', kwargs={'pk': self.object.id})
