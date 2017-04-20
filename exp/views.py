from django.shortcuts import reverse
from django.views import generic

from accounts.forms import UserStudiesForm
from accounts.models import User
from studies.models import Study


class AssignUserStudies(generic.UpdateView):
    template_name = 'accounts/assign_studies_form.html'
    queryset = User.objects.filter()
    form_class = UserStudiesForm

    def get_context_data(self, **kwargs):
        context = super(AssignUserStudies, self).get_context_data(**kwargs)
        context['studies'] = Study.objects.all()
        return context
    # TODO Make this save the relationship between the studies and the collabs


class UserCreateView(generic.CreateView):
    model = User
    fields = (
        'username',
        'given_name',
        'middle_name',
        'family_name'
    )

    def get_success_url(self):
        return reverse('assign_studies', kwargs={'pk': self.object.id})
