from django.shortcuts import reverse
from django.views import generic

from accounts.forms import UserStudiesForm
from accounts.models import User
from guardian.shortcuts import get_objects_for_user
from studies.models import Study


class UserListView(generic.ListView):
    queryset = User.objects.filter(participant__isnull=True)
    model = User

    # TODO Pagination pls


class UserDetailView(generic.UpdateView):
    queryset = User.objects.filter(participant__isnull=True)
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
    template_name = 'accounts/assign_studies_form.html'
    queryset = User.objects.filter(participant__isnull=True)
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
    model = User
    fields = (
        'username',
        'given_name',
        'middle_name',
        'family_name'
    )

    def get_success_url(self):
        return reverse('assign-studies', kwargs={'pk': self.object.id})
