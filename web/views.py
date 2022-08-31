import re
from hashlib import sha256
from typing import Any, Dict, Text
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import UUID

from django.contrib import messages
from django.contrib.auth import authenticate, login, signals
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Prefetch
from django.db.models.query import QuerySet
from django.db.models.query_utils import Q
from django.dispatch import receiver
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, reverse
from django.utils.translation import gettext_lazy as _
from django.views import generic
from django.views.generic.edit import FormView
from django_countries import countries
from guardian.mixins import LoginRequiredMixin
from localflavor.us.us_states import USPS_CHOICES
from revproxy.views import ProxyView

from accounts import forms
from accounts.forms import (
    PastStudiesForm,
    PastStudiesFormTabChoices,
    StudyListSearchForm,
)
from accounts.models import Child, DemographicData, User
from accounts.queries import (
    age_range_eligibility_for_study,
    get_child_eligibility_for_study,
)
from accounts.utils import hash_id
from project import settings
from studies.models import Response, Study, StudyType, Video


@receiver(signals.user_logged_out)
def on_user_logged_out(sender, request, **kwargs):
    messages.success(request, "You've successfully logged out.")


def create_external_response(study: Study, child_uuid: UUID, preview=False) -> Response:
    """Creates a response object for an external study.

    Args:
        study (Study): model object
        child_uuid (UUID): child's UUID
        preview (bool, optional): Set to True if this is a preview response. Defaults to False.

    Returns:
        Response: model object
    """
    child = Child.objects.get(uuid=child_uuid)
    return Response.objects.create(
        study=study,
        child=child,
        study_type=study.study_type,
        demographic_snapshot=child.user.latest_demographics,
        is_preview=preview,
    )


def get_external_url(study: Study, response: Response) -> Text:
    """Get the external url for a study.  This includes an update to the query string with a child's
    hashed id and the response uuid.

    Args:
        study (Study): model object
        response (Response): model object

    Returns:
        Text: URL string
    """
    url = urlparse(study.metadata["url"])
    qs = parse_qs(url.query)

    qs["child"] = hash_id(
        response.child.uuid,
        response.study.uuid,
        response.study.salt,
        response.study.hash_digits,
    )
    qs["response"] = response.uuid

    url = url._replace(query=urlencode(qs, doseq=True))
    return url.geturl()


class HomeView(generic.TemplateView):
    template_name = "frontpages/home.html"


class FAQView(generic.TemplateView):
    template_name = "frontpages/faq.html"


class PrivacyView(generic.TemplateView):
    template_name = "frontpages/privacy.html"


class ScientistsView(generic.TemplateView):
    template_name = "frontpages/scientists.html"


class ContactView(generic.TemplateView):
    template_name = "frontpages/contact.html"


class ResourcesView(generic.TemplateView):
    template_name = "frontpages/resources.html"


class TermsOfUseView(generic.TemplateView):
    template_name = "frontpages/termsofuse.html"


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

    def store_study_in_session(self) -> None:
        study_url = self.request.GET.get("next", "")
        if study_url:
            p = re.compile("^/studies/([\w]{8}-[\w]{4}-[\w]{4}-[\w]{4}-[\w]{12})")
            m = p.match(study_url)
            if m:
                study_uuid = m.group(1)
                study = Study.objects.only("name").get(uuid=study_uuid)
                self.request.session["study_name"] = study.name
                self.request.session["study_uuid"] = study_uuid

    def get_success_url(self):
        """Get the url if the form is successful.  Additionally, the previous url is stored on the
        "next" value on GET.  This url is stored in the user's session.

        Returns:
            str: URL of next view of form submission.
        """
        self.store_study_in_session()
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
        if self.request.user.children.filter(deleted=False).exists():
            return reverse("web:demographic-data-update")
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
        context["has_study_child"] = self.request.user.has_study_child(self.request)
        return context


class ChildrenListView(LoginRequiredMixin, generic.TemplateView):
    """
    Allows user to view a list of current children and add children
    """

    template_name = "web/children-list.html"

    def get_context_data(self, **kwargs):
        """
        Add children that have not been deleted that belong to the current user
        to the context_dict.  Also add info to hide the Add Child form on page load.
        """
        user = self.request.user

        context = super().get_context_data(**kwargs)
        context["children"] = Child.objects.filter(deleted=False, user=user)
        context["has_study_child"] = user.has_study_child(self.request)
        return context


class ChildAddView(LoginRequiredMixin, generic.CreateView):
    template_name = "web/child-add.html"
    model = Child
    form_class = forms.ChildForm

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

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["has_study_child"] = self.request.user.has_study_child(self.request)
        return context


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

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["has_study_child"] = self.request.user.has_study_child(self.request)
        return context


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

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["has_study_child"] = self.request.user.has_study_child(self.request)
        return context


class StudiesListView(generic.ListView, FormView):
    """
    List all active, public studies.
    """

    form_class = StudyListSearchForm
    template_name = "web/studies-list.html"
    model = Study

    def post(self, request, *args, **kwargs):
        form = self.get_form()

        if form.is_valid():
            for field, value in form.clean().items():
                request.session[field] = value

            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_queryset(self):
        session = self.request.session
        user = self.request.user

        studies = super().get_queryset().filter(state="active", public=True)

        # child value from session
        child_value = session.get("child", "")

        # Covers the corner case where user has filter set and then logs in.  This will clear the
        # age range filter that would have been previously set while logged out.
        if (
            user.is_authenticated
            and user.children.filter(deleted=False).count()
            and "," in child_value
        ):
            child_value = ""

        studies = self.filter_studies(studies)

        studies = sorted(studies, key=self.sort_fn())

        # convert studies in to a 3d list of four elements
        return [studies[x : x + 4] for x in range(0, len(studies), 4)]

    def filter_studies(self, studies: QuerySet) -> QuerySet:
        session = self.request.session
        user = self.request.user

        # get form values from session
        search_value = session.get("search", "")
        child_value = session.get("child", "")
        hide_studies_we_have_done_value = session.get("hide_studies_we_have_done", "")
        tab_value = session.get("study_list_tabs", "0")
        study_location_value = session.get("study_location", "0")

        # title search
        if search_value:
            studies = studies.filter(name__icontains=search_value)

        query = None

        # study location
        if study_location_value == StudyListSearchForm.StudyLocation.lookit.value[0]:
            query = Q(study_type__name="Ember Frame Player (default)")
        elif (
            study_location_value == StudyListSearchForm.StudyLocation.external.value[0]
        ):
            query = Q(study_type__name="External")

        if query:
            studies = studies.filter(query)
            query = None

        # Scheduled or unscheduled studies
        if tab_value == StudyListSearchForm.Tabs.synchronous_studies.value[0]:
            query = Q(study_type__name="External", metadata__scheduled=False) | Q(
                study_type__name="Ember Frame Player (default)"
            )
        elif tab_value == StudyListSearchForm.Tabs.asynchronous_studies.value[0]:
            query = Q(study_type__name="External", metadata__scheduled=True)

        if query:
            studies = studies.filter(query)

        if child_value:
            # filter for authenticated users that has selected one of their children
            if child_value.isnumeric() and user.is_authenticated:
                child = Child.objects.get(pk=child_value, user=user)

                if hide_studies_we_have_done_value:
                    studies = self.studies_without_completed_consent_frame(
                        studies, child
                    )

                studies = [
                    s for s in studies if get_child_eligibility_for_study(child, s)
                ]
            # filter for unauthenticated users that have selected a child age range
            else:
                age_range = [int(c) for c in child_value.split(",")]
                studies = [
                    s for s in studies if age_range_eligibility_for_study(age_range, s)
                ]

        return studies

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        kwargs = super().get_initial()

        for field in self.form_class().fields:
            if field in self.request.session:
                kwargs[field] = self.request.session.get(field)

        return kwargs

    def get_success_url(self):
        return reverse("web:studies-list")

    def studies_without_completed_consent_frame(self, studies, child):
        return studies.exclude(
            responses__in=Response.objects.filter(
                Q(
                    child=child,
                    completed_consent_frame=True,
                    study_type=StudyType.get_ember_frame_player(),
                )
                | Q(child=child, study_type=StudyType.get_external())
            )
        )

    def sort_fn(self):
        user = self.request.user
        if user.is_anonymous:
            return lambda s: s.uuid.bytes
        else:
            return lambda s: sha256(user.uuid.bytes + s.uuid.bytes).hexdigest()


class LabStudiesListView(StudiesListView):
    def get_success_url(self):
        lab_slug = self.kwargs.get("lab_slug")
        return reverse("web:lab-studies-list", args=[lab_slug])

    def filter_studies(self, studies: QuerySet) -> QuerySet:
        lab_slug = self.kwargs.get("lab_slug")
        return super().filter_studies(studies.filter(lab__slug=lab_slug))


class StudiesHistoryView(LoginRequiredMixin, generic.ListView, FormView):
    """
    List all active, public studies.
    """

    template_name = "web/studies-history.html"
    model = Study
    form_class = PastStudiesForm

    def post(self, request, *args, **kwargs):
        form = self.get_form()

        if form.is_valid():
            for field, value in form.clean().items():
                request.session[field] = value

            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_queryset(self):
        tab_value = self.request.session.get("past_studies_tabs", "0")

        response_query = Q()
        study_query = Q()

        if tab_value == PastStudiesFormTabChoices.lookit_studies.value[0]:
            study_query = Q(study_type__name="Ember Frame Player (default)")
            response_query = Q(completed_consent_frame=True)
        elif tab_value == PastStudiesFormTabChoices.external_studies.value[0]:
            study_query = Q(study_type__name="External")

        children_ids = Child.objects.filter(user__id=self.request.user.id).values_list(
            "id", flat=True
        )
        responses = (
            Response.objects.filter(Q(child__id__in=children_ids) & response_query)
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

        return Study.objects.filter(Q(id__in=study_ids) & study_query).prefetch_related(
            Prefetch("responses", queryset=responses)
        )

    def get_success_url(self):
        return reverse("web:studies-history")

    def get_initial(self):
        kwargs = super().get_initial()

        for field in self.form_class().fields:
            if field in self.request.session:
                kwargs[field] = self.request.session.get(field)

        return kwargs


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

    def clear_study(self):
        session = self.request.session
        "study_name" in session and session.pop("study_name")
        "study_uuid" in session and session.pop("study_uuid")
        session.modified = True

    def dispatch(self, request, *args, **kwargs):
        study = self.get_object()

        if study.state == "active":
            if request.method == "POST":
                self.clear_study()
                child_uuid = request.POST["child_id"]
                if study.study_type.is_external:
                    response = create_external_response(study, child_uuid)
                    external_url = get_external_url(study, response)
                    return HttpResponseRedirect(external_url)
                else:
                    return redirect("web:experiment-proxy", study.uuid, child_uuid)
            return super().dispatch(request)
        else:
            response_text = _(
                f"The study {study.name} is not currently collecting data - the study is either completed or paused. If you think this is an error, please contact {study.contact_info}"
            )
            return HttpResponseForbidden(response_text)


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

    def setup(self, request, *args, **kwargs):
        # Give participant 4 days from starting any study before session times out, to allow for cases where the
        # parent does instructions etc. but then waits until a convenient time to do the actual test with the
        # child. This will measure "inactivity" but since we're not saving the session on each request it will
        # effectively expire after 4 days regardless of activity (renewed each time this view is accessed)
        if not request.user.is_anonymous and not request.user.is_researcher:
            request.session.set_expiry(60 * 60 * 24 * 4)
        return super().setup(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        """The redirect functionality in revproxy is broken so we have to patch
        path replacement manually.
        """

        study_uuid = kwargs.get("uuid", None)
        child_uuid = kwargs.get("child_id", None)

        # Check if locale (language code) is present in the URL.
        # If so, we need to re-write the request path without the locale
        # so that it points to a working study URL.
        path = request.path
        locale_pattern = (
            rf"/(?P<locale>[a-zA-Z-].+)/studies/{study_uuid}/{child_uuid}/(?P<rest>.*?)"
        )
        path_match = re.match(locale_pattern, path)
        if path_match:
            path = f"/studies/{study_uuid}/{child_uuid}/{path_match.group('rest')}"
            url = request.build_absolute_uri(path)
            # Using redirect instead of super().dispatch here to get around locale/translation middleware
            return redirect(url)

        if settings.DEBUG and settings.ENVIRONMENT == "develop":
            # If we're in a local environment, then redirect shortcut to switch to the ember server
            url = f"{settings.EXPERIMENT_BASE_URL}{path}"
            return redirect(url)

        path = f"{study_uuid}/index.html"
        return super().dispatch(request, path)
