from django.views import generic


class SupportView(generic.TemplateView):
    template_name = "exp/support.html"
