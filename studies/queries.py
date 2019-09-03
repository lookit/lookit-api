from django.db import models
from django.db.models.functions import Coalesce

from studies.models import ACCEPTED, PENDING, ConsentRuling, Response


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
