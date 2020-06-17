import operator
from functools import reduce

from django.contrib import messages
from django.contrib.auth.mixins import (
    PermissionRequiredMixin as DjangoPermissionRequiredMixin,
)
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.db.models.functions import Lower
from django.http import Http404
from django.shortcuts import reverse
from django.views import generic
from guardian.mixins import PermissionRequiredMixin
from guardian.shortcuts import get_objects_for_user

from accounts.forms import UserStudiesForm
from accounts.models import User
from accounts.utils import build_org_group_name
from exp.mixins.paginator_mixin import PaginatorMixin
from exp.mixins.participant_mixin import ParticipantMixin
from project.settings import EXPERIMENTER_LOGIN_URL as login_url
from studies.helpers import send_mail
from studies.models import Response
from studies.queries import get_consented_responses_qs


class ParticipantListView(
    UserPassesTestMixin, ParticipantMixin, generic.ListView, PaginatorMixin
):
    """
    ParticipantListView shows a list of participants that have responded to the studies the
    user has permission to view.
    """

    template_name = "accounts/participant_list.html"

    def can_see_participant_list(self):
        return self.is_researcher

    test_func = can_see_participant_list

    def get_queryset(self):
        """
        Returns users that researcher has permission to view. Handles sorting and pagination.
        """
        qs = super().get_queryset()
        match = self.request.GET.get("match", False)
        order = self.request.GET.get("sort", "nickname")
        if "nickname" not in order and "last_login" not in order:
            order = "nickname"

        if match:
            qs = qs.filter(
                reduce(
                    operator.or_,
                    (Q(nickname__icontains=term) for term in match.split()),
                )
            )
        return self.paginated_queryset(
            qs.order_by(order), self.request.GET.get("page"), 10
        )

    def get_context_data(self, **kwargs):
        """
        Adds match and sort query params to context_data dict
        """
        context = super().get_context_data(**kwargs)
        context["match"] = self.request.GET.get("match", "")
        context["sort"] = self.request.GET.get("sort", "")
        return context


class ParticipantDetailView(ParticipantMixin, generic.DetailView, PaginatorMixin):
    """
    ParticipantDetailView shows demographic information, children information, and
    studies that a participant has responded to.

    Participant (account) + demographic data should only show up if the participant
    has at least one child who has at least one confirmed-consented response that the
    researcher can see. Each child should only show up if they have such a response, i.e.
    the siblings don't show up "for free."
    """

    fields = ("is_active",)
    template_name = "accounts/participant_detail.html"

    def can_see_participant_detail(self):
        return self.is_researcher

    test_func = can_see_participant_detail

    def get_context_data(self, **kwargs):
        """
        Adds user's latest demographics and studies to the context_data dictionary
        """
        context = super().get_context_data(**kwargs)
        user = context["user"]
        context["demographics"] = (
            user.latest_demographics.to_display() if user.latest_demographics else None
        )
        context["studies"] = self.get_study_info()
        context["children"] = user.children.filter(
            id__in=self.valid_responses().values_list("child", flat=True)
        )
        return context

    def get_study_info(self):
        """
        Returns paginated responses from a user with the study title, response
        id, completion status, and date modified.
        """
        resps = (
            self.valid_responses()
            .filter(child__user=self.get_object())
            .select_related("child__user")
        )
        orderby = self.request.GET.get("sort", "-date_created")
        if orderby:
            if "date_created" in orderby:
                resps = resps.order_by(orderby)
            elif "completed" in orderby:
                resps = resps.order_by(
                    orderby.replace("-", "") if "-" in orderby else "-" + orderby
                )
        studies = [
            {
                "modified": resp.date_modified,
                "created": resp.date_created,
                "study": resp.study,
                "name": resp.study.name,
                "completed": resp.completed,
                "response": resp,
            }
            for resp in resps
        ]
        if orderby and "name" in orderby:
            studies = sorted(
                studies,
                key=operator.itemgetter("name"),
                reverse=True if "-" in orderby else False,
            )
        return self.paginated_queryset(studies, self.request.GET.get("page"), 10)

    def get_success_url(self):
        return reverse("exp:participant-detail", kwargs={"pk": self.object.id})
