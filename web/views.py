from django.contrib import messages
from django.contrib.auth import authenticate, login, signals, update_session_auth_hash
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Prefetch
from django.dispatch import receiver
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, reverse, render
from django.views import generic
from django_countries import countries

from web.mixins import LoginRequiredMixin

from localflavor.us.us_states import USPS_CHOICES
from revproxy.views import ProxyView

from accounts import forms
from accounts.models import Child, DemographicData, User
from project import settings
from studies.models import Response, Study, Video

from django.utils.translation import get_language, gettext_lazy as _

from django.contrib.flatpages import views


@receiver(signals.user_logged_out)
def on_user_logged_out(sender, request, **kwargs):
    messages.success(request, "You've successfully logged out.")

class HomeView(generic.TemplateView):
    template_name = 'flatpages/home.html'

class FAQView(generic.TemplateView):
    template_name = 'flatpages/faq.html'

class PrivacyView(generic.TemplateView):
    template_name = 'flatpages/privacy.html'

class ScientistsView(generic.TemplateView):
    template_name = 'flatpages/scientists.html'

class ContactView(generic.TemplateView):
    template_name = 'flatpages/contact.html'

class ParticipantSignupView(generic.CreateView):
    """
    Allows a participant to sign up. Redirects them to a page to add their demographic data.
    """

    template_name = "web/participant-signup.html"
    model = User
    form_class = forms.ParticipantSignupForm

    def form_valid(self, form):
        resp = super().form_valid(form)
        new_user = authenticate(
            self.request,
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password1"],
        )
        login(
            self.request, new_user, backend="django.contrib.auth.backends.ModelBackend"
        )
        messages.success(self.request, _("Participant created."))
        return resp

    def get_success_url(self):
        return reverse("web:demographic-data-update")


class DemographicDataUpdateView(LoginRequiredMixin, generic.CreateView):
    """
    Allows user to update demographic data - but actually creates new version instead of updating old one.
    """

    template_name = "web/demographic-data-update.html"
    model = DemographicData
    form_class = forms.DemographicDataForm

    def form_valid(self, form):
        """
        Before saving form, adds user relationship to demographic data, and sets "previous"
         as the last saved demographic data.
        """
        resp = super().form_valid(form)
        self.object.user = self.request.user
        self.object.previous = self.request.user.latest_demographics or None
        self.object.save()
        messages.success(self.request, _("Demographic data saved."))
        return resp

    def get_initial(self):
        """
        Returns the initial data to use for forms on this view. Prepopulates
        demographic data form with the latest demographic data.
        """
        demographic_data = self.request.user.latest_demographics or None
        if demographic_data:
            demographic_data_dict = demographic_data.__dict__
            demographic_data_dict.pop("id")
            demographic_data_dict.pop("uuid")
            return demographic_data_dict
        return demographic_data

    def get_success_url(self):
        if self.request.user.children.exists():
            return reverse("web:studies-list")
        else:
            return reverse("web:children-list")

    def get_context_data(self, **kwargs):
        """
        Adds the context for form1 and form2 on the page - a little extra code due to the
        two forms on the page.  The form that was not edited is unbound so data
        is not validated.
        """
        context = super().get_context_data(**kwargs)
        context["countries"] = countries
        context["states"] = USPS_CHOICES
        return context


class ChildrenListView(LoginRequiredMixin, generic.CreateView):
    """
    Allows user to view a list of current children and add children
    """

    template_name = "web/children-list.html"
    model = Child
    form_class = forms.ChildForm

    def get_context_data(self, **kwargs):
        """
        Add children that have not been deleted that belong to the current user
        to the context_dict.  Also add info to hide the Add Child form on page load.
        """
        context = super().get_context_data(**kwargs)
        children = Child.objects.filter(deleted=False, user=self.request.user)
        context["objects"] = children
        context["form_hidden"] = kwargs.get("form_hidden", True)
        return context

    def form_invalid(self, form):
        """
        If form invalid, add child form needs to be open when page reloads.
        """
        return self.render_to_response(
            self.get_context_data(form=form, form_hidden=False)
        )

    def form_valid(self, form):
        """
        Add the current user to the child before saving the child.
        """
        user = self.request.user
        form.instance.user = user
        messages.success(self.request, _("Child added."))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("web:children-list")


class ChildUpdateView(LoginRequiredMixin, generic.UpdateView):
    """
    Allows user to update or delete a child.
    """

    template_name = "web/child-update.html"
    model = Child
    form_class = forms.ChildUpdateForm

    def get_success_url(self):
        return reverse("web:children-list")

    def get_object(self, queryset=None):
        """
        Returns the object the view is displaying.
        ChildUpdate View needs to be called with slug or pk - but uuid in URLconf
        instead so use this to lookup child
        """
        uuid = self.kwargs.get("uuid")
        return get_object_or_404(Child, uuid=uuid)

    def post(self, request, *args, **kwargs):
        """
        If deleteChild form submitted, mark child as deleted in the db.
        """
        if "deleteChild" in self.request.POST and self.request.method == "POST":
            child = self.get_object()
            child.deleted = True
            child.save()
            messages.success(self.request, _("Child deleted."))
            return HttpResponseRedirect(self.get_success_url())
        messages.success(self.request, _("Child updated."))
        return super().post(request, *args, **kwargs)


class ParticipantEmailPreferencesView(LoginRequiredMixin, generic.UpdateView):
    """
    Allows a participant to update their email preferences - when they can be contacted.
    """

    template_name = "web/participant-email-preferences.html"
    model = User
    form_class = forms.EmailPreferencesForm

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return reverse("web:email-preferences")

    def form_valid(self, form):
        """
        Adds success message
        """
        messages.success(self.request, _("Email preferences saved."))
        return super().form_valid(form)


class StudiesListView(generic.ListView):
    """
    List all active, public studies.
    """

    template_name = "web/studies-list.html"
    model = Study

    def get_queryset(self):
        # TODO if we need to filter by study demographics vs user demographics
        # or by if they've taken the study before this is the spot
        return super().get_queryset().filter(state="active", public=True).order_by("?")


class StudiesHistoryView(LoginRequiredMixin, generic.ListView):
    """
    List all active, public studies.
    """

    template_name = "web/studies-history.html"
    model = Study

    def get_queryset(self):
        children_ids = Child.objects.filter(user__id=self.request.user.id).values_list(
            "id", flat=True
        )
        responses = (
            Response.objects.filter(
                completed_consent_frame=True, child__id__in=children_ids
            )
            .select_related("child")
            .prefetch_related(
                Prefetch(
                    "videos",
                    queryset=Video.objects.order_by("pipe_numeric_id", "s3_timestamp"),
                ),
                "consent_rulings",
                "feedback",
            )
            .order_by("-date_created")
        )

        study_ids = responses.values_list("study_id", flat=True)

        return Study.objects.filter(id__in=study_ids).prefetch_related(
            Prefetch("responses", queryset=responses)
        )


class StudyDetailView(generic.DetailView):
    """
    Show the details of a study.  If the user has selected a child, they can
    participate in the study and be forwarded/proxied to the js application
    """

    template_name = "web/study-detail.html"
    model = Study

    def get_queryset(self):
        return super().get_queryset().filter(state="active", public=True)

    def get_object(self, queryset=None):
        """
        Needed because view expecting pk or slug, but url has UUID. Looks up
        study by uuid.
        """
        uuid = self.kwargs.get("uuid")
        return get_object_or_404(Study, uuid=uuid)

    def get_context_data(self, **kwargs):
        """
        If authenticated, add demographic presence, and children to context data dict
        """
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context["has_demographic"] = self.request.user.latest_demographics
            context["children"] = self.request.user.children.filter(deleted=False)

        return context

    def dispatch(self, request, *args, **kwargs):
        study = self.get_object()
        if study.state == "active":
            if request.method == "POST":
                return redirect(
                    "web:experiment-proxy", study.uuid, request.POST["child_id"]
                )
            return super().dispatch(request)
        else:
            return HttpResponseForbidden(
                _(f"The study {study.name} is not currently collecting data - the study is either completed or paused. If you think this is an error, please contact {study.contact_info}")
            )


class ExperimentAssetsProxyView(LoginRequiredMixin, ProxyView):
    upstream = settings.EXPERIMENT_BASE_URL

    def dispatch(self, request, *args, **kwargs):
        """Bypass presence of child ID."""
        uuid = kwargs.pop("uuid")
        asset_path = kwargs.pop("path")
        path = f"{uuid}/{asset_path}"
        return super().dispatch(request, path, *args, **kwargs)


class ExperimentProxyView(LoginRequiredMixin, UserPassesTestMixin, ProxyView):
    """
    Proxy view to forward user to participate page in the Ember app
    """

    upstream = settings.EXPERIMENT_BASE_URL

    def user_can_participate(self):
        request = self.request
        kwargs = self.kwargs
        user = request.user

        try:
            child = Child.objects.get(uuid=kwargs.get("child_id", None))
        except Child.DoesNotExist:
            return False

        try:
            study = Study.objects.get(uuid=kwargs.get("uuid", None))
        except Study.DoesNotExist:
            return False

        if child.user != user:
            # requesting user doesn't belong to that child
            return False

        return True

    test_func = user_can_participate

    def dispatch(self, request, *args, **kwargs):

        _, _, study_uuid, _, _, *rest = request.path.split("/")
        path = f"{study_uuid}/{'/'.join(rest)}"
        if not rest:
            path += "index.html"

        return super().dispatch(request, path)
