from hashlib import sha1
from typing import Text
from urllib.parse import parse_qs, urlencode, urlparse

from django.contrib import messages
from django.contrib.auth import authenticate, login, signals
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Prefetch
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
from accounts.forms import PastStudiesForm, StudyListSearchFormTabChoices
from accounts.models import Child, DemographicData, User, create_string_listing_children
from accounts.queries import (
    age_range_eligibility_for_study,
    get_child_eligibility_for_study,
)
from accounts.utils import hash_id
from exp.mixins.paginator_mixin import PaginatorMixin
from project import settings
from studies.models import Response, Study, Video


@receiver(signals.user_logged_out)
def on_user_logged_out(sender, request, **kwargs):
    messages.success(request, "You've successfully logged out.")


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
        if self.request.user.children.filter(deleted=False).exists():
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


class StudiesListView(generic.ListView, PaginatorMixin, FormView):
    """
    List all active, public studies.
    """

    form_class = forms.StudyListSearchForm
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
        page = self.request.GET.get("page", 1)

        studies = super().get_queryset().filter(state="active", public=True)

        # values from session
        search_value = session.get("search", "")
        child_value = session.get("child", "")
        hide_studies_we_have_done_value = session.get("hide_studies_we_have_done", "")
        tab_value = session.get("tabs", "")

        if search_value:
            studies = studies.filter(name__icontains=search_value)

        # Covers the corner case where user has filter set and then logs in.  This will clear the
        # age range filter that would have been previously set while logged out.
        if (
            user.is_authenticated
            and user.children.filter(deleted=False).count()
            and "," in child_value
        ):
            child_value = ""

        query = None

        if tab_value == StudyListSearchFormTabChoices.lookit_studies.value[0]:
            query = Q(study_type__name="Ember Frame Player (default)")
        elif tab_value == StudyListSearchFormTabChoices.external_studies.value[0]:
            query = Q(study_type__name="External")
        elif tab_value == StudyListSearchFormTabChoices.synchronous_studies.value[0]:
            query = Q(study_type__name="External", metadata__scheduled=False) | Q(
                study_type__name="Ember Frame Player (default)"
            )
        elif tab_value == StudyListSearchFormTabChoices.asynchronous_studies.value[0]:
            query = Q(study_type__name="External", metadata__scheduled=True)

        if query:
            studies = studies.filter(query)

        if child_value:
            if child_value.isnumeric() and user.is_authenticated:
                child = Child.objects.get(pk=child_value, user=user)

                if hide_studies_we_have_done_value:
                    studies = self.studies_without_completed_consent_frame(
                        studies, child
                    )

                studies = [
                    s for s in studies if get_child_eligibility_for_study(child, s)
                ]

            else:
                age_range = [int(c) for c in child_value.split(",")]
                studies = [
                    s for s in studies if age_range_eligibility_for_study(age_range, s)
                ]

        studies = sorted(studies, key=self.sort_fn())

        self.set_eligible_children_per_study(studies)

        return self.paginated_queryset(studies, page)

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
        ### TODO: Add in support for external studies
        return studies.exclude(
            responses__in=Response.objects.filter(
                child=child, completed_consent_frame=True
            )
        )

    def set_eligible_children_per_study(self, studies):
        user = self.request.user

        if user.is_authenticated:
            children = user.children.filter(deleted=False)

            # add eligible children to study object
            for study in studies:
                study.eligible_children = create_string_listing_children(
                    [c for c in children if get_child_eligibility_for_study(c, study)]
                )

    def sort_fn(self):
        user = self.request.user
        if user.is_anonymous:
            return lambda s: s.uuid.bytes
        else:
            return lambda s: sha1(user.uuid.bytes + s.uuid.bytes).hexdigest()


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

    def dispatch(self, request, *args, **kwargs):
        study = self.get_object()
        user = self.request.user

        if study.state == "active":
            if request.method == "POST":
                child_uuid = request.POST["child_id"]
                if study.study_type.is_external:
                    child = Child.objects.get(uuid=child_uuid)
                    response, _ = Response.objects.get_or_create(
                        study=study,
                        child=child,
                        study_type=study.study_type,
                        demographic_snapshot=user.latest_demographics,
                    )
                    external_url = self.external_url(study, response)
                    return HttpResponseRedirect(external_url)
                else:
                    return redirect("web:experiment-proxy", study.uuid, child_uuid)
            return super().dispatch(request)
        else:
            response_text = (
                "The study %s is not currently collecting data - the study is either completed or paused. If you think this is an error, please contact %s"
                % (study.name, study.contact_info)
            )
            return HttpResponseForbidden(_(response_text))

    def external_url(self, study: Study, response: Response) -> Text:
        """Get the external url for this study.  Additionally, while preserving the existing query
        string, add our hashed child id.

        Args:
            study (Study): Study model object
            child_id (Text): Hashed child id for study

        Returns:
            Text: External study url
        """
        url = urlparse(study.metadata["url"])
        qs = parse_qs(url.query)
        qs["child"] = hash_id(
            response.child.uuid,
            response.study.uuid,
            response.study.salt,
            response.study.hash_digits,
        )
        url = url._replace(query=urlencode(qs, doseq=True))
        return url.geturl()


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
        _, _, study_uuid, _, _, *rest = request.path.split("/")
        path = f"{study_uuid}/{'/'.join(rest)}"
        if not rest:
            path += "index.html"

        return super().dispatch(request, path)
