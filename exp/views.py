from django.shortcuts import reverse
from django.views import generic

from accounts.forms import CollaboratorStudiesForm
from accounts.models import Collaborator, User
from studies.models import Study


class AssignCollaboratorStudies(generic.UpdateView):
    queryset = Collaborator.objects.filter()
    form_class = CollaboratorStudiesForm

    def get_context_data(self, **kwargs):
        context = super(AssignCollaboratorStudies, self).get_context_data(**kwargs)
        context['studies'] = Study.objects.all()
        return context


class CollaboratorCreateView(generic.CreateView):
    model = User
    fields = (
        'username',
        'given_name',
        'middle_name',
        'family_name'
    )

    def get_success_url(self):
        return reverse('assign_studies', kwargs={'pk': self.object.collaborator.id})

    def form_valid(self, form):
        self.object = form.save()
        Collaborator.objects.create(user=self.object)
        return super(CollaboratorCreateView, self).form_valid(form)
