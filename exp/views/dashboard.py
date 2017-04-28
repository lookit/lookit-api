
from django.views import generic


class ExperimenterDashboard(generic.TemplateView):
    template_name = 'exp/dashboard.html'
    def get_context_data(self, *args, **kwargs):
        return super().get_context_data(*args, **kwargs)
