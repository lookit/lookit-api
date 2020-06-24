from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import generic


class ExperimenterDashboardView(generic.TemplateView):
    """
    ExperimenterDashboard will show a customized view to each user based on the
    role and tasks that they perform.
    """

    template_name = "exp/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        # non-researchers, send back to web app
        if (
            not hasattr(request.user, "is_researcher")
        ) or not request.user.is_researcher:
            return redirect(reverse_lazy("web:home"))
        # For researchers, default to study-list
        if self.request.path.endswith("/"):
            return redirect(reverse_lazy("exp:study-list"))
        # If no trailing slash, append slash and redirect.
        return redirect(self.request.path + "/")
