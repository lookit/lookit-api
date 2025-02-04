import operator
from functools import reduce

from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Q
from django.shortcuts import reverse
from django.views import generic

from exp.mixins.paginator_mixin import PaginatorMixin
from exp.mixins.participant_mixin import ParticipantMixin
from exp.views.mixins import ResearcherLoginRequiredMixin


class ParticipantListView(
    ResearcherLoginRequiredMixin,
    UserPassesTestMixin,
    ParticipantMixin,
    generic.ListView,
):
    """
    ParticipantListView shows a list of participants that have responded to the studies the
    user has permission to view.
    """

    template_name = "accounts/participant_list.html"
    paginate_by = 10

    def can_see_participant_list(self):
        return self.request.user.is_researcher

    test_func = can_see_participant_list

    def get_queryset(self):
        """
        Returns users that researcher has permission to view
        """
        qs = super().get_queryset()
        ordering = self.get_ordering()

        match = self.request.GET.get("match", False)

        if match:
            qs = qs.filter(
                reduce(
                    operator.or_,
                    (
                        Q(nickname__icontains=term) | Q(uuid__icontains=term)
                        for term in match.split()
                    ),
                )
            )

        if ordering:
            qs = qs.order_by(self.get_ordering())

        return qs

    def get_ordering(self):
        return self.request.GET.get("sort")

    def get_context_data(self, **kwargs):
        """
        Adds match and sort query params to context_data dict
        """
        context = super().get_context_data(**kwargs)
        context.update(
            match=self.request.GET.get("match", ""),
            sort=self.request.GET.get("sort", ""),
            page=self.request.GET.get("page", ""),
        )
        return context


class ParticipantDetailView(
    ResearcherLoginRequiredMixin, ParticipantMixin, generic.DetailView, PaginatorMixin
):
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
        return self.request.user.is_researcher

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
            elif "completed_exit_frame" in orderby:
                resps = resps.order_by(
                    orderby.replace("-", "") if "-" in orderby else "-" + orderby
                )
        studies = [
            {
                "modified": resp.date_modified,
                "created": resp.date_created,
                "study": resp.study,
                "name": resp.study.name,
                "completed_exit_frame": resp.completed_exit_frame,
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
