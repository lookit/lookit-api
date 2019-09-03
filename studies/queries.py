from django.db import models
from django.db.models import Q, Count, IntegerField, OuterRef, Prefetch, Subquery
from django.db.models.functions import Coalesce
from guardian.shortcuts import get_objects_for_user, get_perms

from studies.models import ACCEPTED, PENDING, ConsentRuling, Response, StudyLog


def get_annotated_responses_qs():
    """Retrieve a queryset for the set of responses belonging to a set of studies."""
    # Create the subquery where we get the action from the most recent ruling.
    newest_ruling_subquery = models.Subquery(
        ConsentRuling.objects.filter(response=models.OuterRef("pk"))
        .order_by("-created_at")
        .values("action")[:1]
    )

    # Annotate that value as "current ruling" on our response queryset.
    return (
        Response.objects.prefetch_related("consent_rulings")
        .filter(completed_consent_frame=True)
        .annotate(
            current_ruling=Coalesce(newest_ruling_subquery, models.Value(PENDING))
        )
    )


def get_consented_responses_qs():
    """Retrieve a queryset for the set of consented responses belonging to a set of studies."""
    # Create the subquery where we get the action from the most recent ruling.
    return get_annotated_responses_qs().filter(current_ruling=ACCEPTED)


def get_pending_responses_qs():
    """Retrieve a queryset for the set of pending judgement responses belonging to a set of studies."""
    # Create the subquery where we get the action from the most recent ruling.
    return get_annotated_responses_qs().filter(
        models.Q(current_ruling=PENDING) | models.Q(current_ruling=None)
    )


def get_study_list_qs(user):
    """

    Args:
        user: django.utils.functional.SimpleLazyObject masquerading as a user.

    Returns:
        A heavily annotated queryset for the list of studies.
    """
    annotated_responses_qs = get_annotated_responses_qs()

    queryset = (
        get_objects_for_user(user, "studies.can_view_study")
        .exclude(state="archived")
        .select_related("creator")
        .annotate(
            completed_responses_count=Subquery(
                Response.objects.filter(
                    study=OuterRef("pk"), completed_consent_frame=True, completed=True
                )
                .values("completed")
                .order_by()
                .annotate(count=Count("completed"))
                .values("count")[:1],  # [:1] ensures that a queryset is returned
                output_field=IntegerField(),
            ),
            incomplete_responses_count=Subquery(
                Response.objects.filter(
                    study=OuterRef("pk"), completed_consent_frame=True, completed=False
                )
                .values("completed")
                .order_by()
                .annotate(count=Count("completed"))
                .values("count")[:1],  # [:1] ensures that a queryset is returned
                output_field=IntegerField(),
            ),
            valid_consent_count=Subquery(
                annotated_responses_qs.filter(
                    study=OuterRef("pk"), current_ruling="accepted"
                )
                .values("current_ruling")
                .order_by("current_ruling")  # Need this for GROUP BY to work properly
                .annotate(count=Count("current_ruling"))
                .values("count")[:1],  # [:1] ensures that a queryset is returned
                output_field=IntegerField(),
            ),
            pending_consent_count=Subquery(
                annotated_responses_qs.filter(
                    study=OuterRef("pk"), current_ruling="pending"
                )
                .values("current_ruling")
                .order_by("current_ruling")
                .annotate(count=Count("current_ruling"))
                .values("count")[:1],
                output_field=IntegerField(),
            ),
            starting_date=Subquery(
                StudyLog.objects.filter(study=OuterRef("pk"))
                .order_by("-created_at")
                .filter(action="active")
                .values("created_at")[:1]
            ),
            ending_date=Subquery(
                StudyLog.objects.filter(study=OuterRef("pk"))
                .order_by("-created_at")
                .filter(action="deactivated")
                .values("created_at")[:1]
            ),
        )
    )

    return queryset
