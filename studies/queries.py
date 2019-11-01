from collections import defaultdict

from django.db import models
from django.db.models import Q, Count, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce
from guardian.shortcuts import get_objects_for_user

from accounts.models import Child, User
from studies.models import ACCEPTED, PENDING, ConsentRuling, Response, StudyLog, Video


def get_annotated_responses_qs(include_comments=False):
    """Retrieve a queryset for the set of responses belonging to a set of studies."""
    # Create the subquery where we get the action from the most recent ruling.
    newest_ruling_subquery = models.Subquery(
        ConsentRuling.objects.filter(response=models.OuterRef("pk"))
        .order_by("-created_at")
        .values("action")[:1]
    )

    # Annotate that value as "current ruling" on our response queryset.
    annotated_query = (
        Response.objects.prefetch_related("consent_rulings")
        .filter(completed_consent_frame=True)
        .annotate(
            current_ruling=Coalesce(newest_ruling_subquery, models.Value(PENDING))
        )
    )

    if include_comments:
        comment_subquery = models.Subquery(
            ConsentRuling.objects.filter(response=models.OuterRef("pk"))
            .order_by("-created_at")
            .values("comments")[:1]
        )
        annotated_query = annotated_query.annotate(
            ruling_comments=Coalesce(comment_subquery, models.Value("N/A"))
        )

    return annotated_query


def get_responses_with_current_rulings_and_videos(study_id):
    """Gets all the responses for a given study, including the current ruling and videos.

    Args:
        study_id: The study ID related to the responses we want.

    Returns:
        A queryset of responses with prefetched videos.
    """
    responses_for_study = (
        get_annotated_responses_qs(include_comments=True)
        .filter(study_id=study_id)
        # .prefetch_related(
        #     models.Prefetch(
        #         "videos",
        #         queryset=Video.objects.filter(is_consent_footage=True).only(
        #             "full_name"
        #         ),
        #         to_attr="consent_videos",
        #     )
        # )
        .select_related("child", "child__user")
        .order_by("-date_created")
        .values(
            "id",
            "uuid",
            "sequence",
            "conditions",
            "global_event_timings",
            "current_ruling",
            "ruling_comments",
            "completed",
            "date_created",
            "exp_data",
            "child_id",
            "child__uuid",
            "child__birthday",
            "child__gender",
            "child__gestational_age_at_birth",
            "child__additional_information",
            "child__given_name",
            "study__name",
            "study_id",
            "child__user_id",
            "child__user__uuid",
            "child__user__nickname",
        )
    )

    # See: https://code.djangoproject.com/ticket/26565
    #     The inability to use values() and prefetch in tandem without combinatorial
    #     explosion of result set is precluding us from being efficient about this.
    consent_videos = Video.objects.filter(study_id=study_id, is_consent_footage=True)
    videos_per_response = defaultdict(list)
    for video in consent_videos:
        videos_per_response[video.response_id].append(video)

    for response in responses_for_study:
        response["videos"] = videos_per_response.get(response["id"], [])

    return responses_for_study


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


def get_registration_analytics_qs():
    """

    Args:
        user: django.utils.functional.SimpleLazyObject masquerading as a user.

    Returns:
        An annotated queryset containing user data.
    """


def get_study_list_qs(user):
    """Gets a study list query set annotated with response counts.

    TODO: Factor in all the query mutation from the (view) caller.
    TODO: Upgrade to Django 2.x and use the improved query mechanisms to clean this up.

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
