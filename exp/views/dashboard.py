
from django.views import generic

from guardian.mixins import LoginRequiredMixin


class ExperimenterDashboard(LoginRequiredMixin, generic.TemplateView):
    template_name = 'exp/dashboard.html'
    def get_context_data(self, *args, **kwargs):
        return super().get_context_data(*args, **kwargs)
