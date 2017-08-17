
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import generic

from exp.views.mixins import ExperimenterLoginRequiredMixin


class ExperimenterDashboardView(ExperimenterLoginRequiredMixin, generic.TemplateView):
    '''
    ExperimenterDashboard will show a customized view to each user based on the
    role and tasks that they perform.
    '''
    template_name = 'exp/dashboard.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_researcher:
            return redirect(reverse_lazy('web:home'))
        if self.request.path.endswith('/'):
            if self.request.user.groups.exists():
                # Redirect to manage studies if user has been approved
                return redirect(reverse_lazy('exp:study-list'))
            return super().dispatch(request, *args, **kwargs)
        # If no trailing slash, append slash and redirect.
        return redirect(self.request.path + '/')
