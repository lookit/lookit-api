
from django.views import generic

from guardian.mixins import LoginRequiredMixin


class ExperimenterDashboard(LoginRequiredMixin, generic.TemplateView):
    '''
    ExperimenterDashboard will show a customized view to each user based on the 
    role and tasks that they perform.
    '''
    template_name = 'exp/dashboard.html'

    def get_context_data(self, **kwargs):
        return super(ExperimenterDashboard, self).get_context_data(**kwargs)
