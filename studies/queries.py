import operator
from collections import defaultdict
from datetime import timedelta
from functools import reduce
from typing import Dict

from django.core.exceptions import FieldError
from django.db import models
from django.db.models import Count, F, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.fields import CharField
from django.db.models.functions import Coalesce, Concat
from django.utils.timezone import now
from guardian.shortcuts import get_objects_for_user

from attachment_helpers import get_url
from studies.models import (
    ACCEPTED,
    PENDING,
    REJECTED,
    ConsentRuling,
    Response,
    Study,
    StudyLog,
    Video,
)
from studies.permissions import UMBRELLA_LAB_PERMISSION_MAP, StudyPermission


class SubqueryCount(Subquery):
    template = "(SELECT count(*) FROM (%(subquery)s) _count)"
    output_field = IntegerField()


def get_annotated_responses_qs(include_comments=False, include_time=False):
    """Retrieve a queryset for the set of responses belonging to a set of studies."""
    # Create the subquery where we get the action from the most recent ruling.
    newest_ruling_subquery = models.Subquery(
        ConsentRuling.objects.filter(response=models.OuterRef("pk"))
        .order_by("-created_at")
        .values("action")[:1],
        output_field=CharField(),
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
            .values("comments")[:1],
            output_field=CharField(),
        )
        annotated_query = annotated_query.annotate(
            ruling_comments=Coalesce(comment_subquery, models.Value("N/A"))
        )

    if include_time:
        time_subquery = models.Subquery(
            ConsentRuling.objects.filter(response=models.OuterRef("pk"))
            .order_by("-created_at")
            .values("created_at")[:1],
            output_field=CharField(),
        )
        annotated_query = annotated_query.annotate(time_of_ruling=time_subquery)

    return annotated_query


def get_responses_with_current_rulings_and_videos(study_id, preview_only):
    """Gets all the responses for a given study, including the current ruling and consent videos.

    Args:
        study_id: The study ID related to the responses we want.
        preview_only: Whether to include only preview responses (True), or all data (False)

    Returns:
        A queryset of responses with attached consent videos.
    """
    three_weeks_ago = now() - timedelta(weeks=3)
    dont_show_old_approved = Q(study_id=study_id) & (
        Q(time_of_ruling__gt=three_weeks_ago) | ~Q(current_ruling=ACCEPTED)
    )

    responses_for_study = get_annotated_responses_qs(
        include_comments=True, include_time=True
    ).filter(dont_show_old_approved)

    if preview_only:
        responses_for_study = responses_for_study.filter(is_preview=True)

    responses_for_study = (
        responses_for_study.select_related(
            "child", "child__user", "demographic_snapshot"
        )
        .order_by("-date_created")
        .values(
            "id",
            "uuid",
            "sequence",
            "global_event_timings",
            "current_ruling",
            "ruling_comments",
            "completed",
            "survey_consent",
            "date_created",
            "is_preview",
            "child_id",
            "child__uuid",
            "child__birthday",
            "child__gender",
            "child__gestational_age_at_birth",
            "child__additional_information",
            "child__given_name",
            "study__name",
            "study_id",
            "study__uuid",
            "study__salt",
            "study__hash_digits",
            "child__user_id",
            "child__user__uuid",
            "child__user__nickname",
            "demographic_snapshot_id",
            "demographic_snapshot__country",
            "demographic_snapshot__state",
        )
    )

    # Not prefetching videos above because the inability to use values() and
    # prefetch_related in tandem without combinatorial explosion of result set is precluding us
    # from relying on django's join machinery. Instead, we need to manually join here.
    # See: https://code.djangoproject.com/ticket/26565n
    consent_videos = Video.objects.filter(
        study_id=study_id, is_consent_footage=True
    ).values("full_name", "response_id")
    study_type_is_jspsych = Study.objects.get(pk=study_id).study_type.is_jspsych
    videos_per_response = defaultdict(list)
    for video in consent_videos:
        recording_is_pipe = Video.objects.get(
            full_name=video["full_name"]
        ).recording_method_is_pipe
        videos_per_response[video["response_id"]].append(
            {
                "aws_url": get_url(
                    video["full_name"], recording_is_pipe, study_type_is_jspsych, False
                ),
                "filename": video["full_name"],
            }
        )

    for response in responses_for_study:
        response["videos"] = videos_per_response.get(response["id"], [])

    return responses_for_study


def studies_for_which_user_has_perm(user, study_perm: StudyPermission):
    study_level_perm_study_ids = get_objects_for_user(
        user, study_perm.prefixed_codename
    ).values_list("id", flat=True)

    umbrella_lab_perm = UMBRELLA_LAB_PERMISSION_MAP.get(study_perm)
    labs_with_labwide_perms = get_objects_for_user(
        user, umbrella_lab_perm.prefixed_codename
    )

    return Study.objects.filter(
        Q(lab__in=labs_with_labwide_perms) | Q(id__in=study_level_perm_study_ids)
    )


def get_consent_statistics(study_id, preview_only):
    """Retrieve summary statistics for consent manager and responses views.

    Required Fields:
    # Pending Responses
    # Accepted Responses
    # Rejected Responses
    # Total Responses
    # Total Unique Children w/accepted responses
    # Total Unique Children with no accepted responses
    # Total Unique Children

    Args:
        study_id: The integer ID for the study we want.
        preview_only: Whether to include only preview responses (True), or all data (False)

    Returns:
        A dict containing the summary stats.
    """
    statistics = {
        "responses": {"total": 0, "rejected": 0, "pending": 0, "accepted": 0},
        "children": {},
    }
    response_stats = statistics["responses"]
    child_stats = statistics["children"]

    response_qs = get_annotated_responses_qs().filter(study_id=study_id)
    if preview_only:
        response_qs = response_qs.filter(is_preview=True)

    response_counts = (
        response_qs.values("current_ruling")
        .order_by("current_ruling")
        .annotate(count=Count("current_ruling"))
    )

    for count_obj in response_counts:
        count_for_ruling = count_obj["count"]
        response_stats[count_obj["current_ruling"]] = count_for_ruling
        response_stats["total"] += count_for_ruling

    children_with_rulings = (
        get_annotated_responses_qs()
        .filter(study_id=study_id)
        .values("child_id", "current_ruling")
    )

    unique_accepted_children = set(
        [
            resp["child_id"]
            for resp in children_with_rulings
            if resp["current_ruling"] == ACCEPTED
        ]
    )

    child_stats["with_accepted_responses"] = len(unique_accepted_children)

    unique_rejected_children = set(
        [
            resp["child_id"]
            for resp in children_with_rulings
            if resp["current_ruling"] == REJECTED
        ]
    )

    child_stats["without_accepted_responses"] = len(
        unique_rejected_children - unique_accepted_children
    )

    child_stats["total"] = len(
        set([resp["child_id"] for resp in children_with_rulings])
    )

    return statistics


def get_summary_statistics_external(study, preview_only: bool) -> Dict:
    """Build summary_statistics for external studies (no consent rulings).

    The external-study version of get_consent_statistics, which is used to get summary data without any consent-related
    properties (accepted, pending, rejected, with_accepted_responses, without_accepted_responses).

    Returns a dict with the following keys:
    - total_responses: total response count
    - total children: total unique children who have responded
    """
    response_qs = study.responses.all()
    if preview_only:
        response_qs = response_qs.filter(is_preview=True)
    total = response_qs.count()
    total_children = response_qs.values("child_id").distinct().count()
    return {
        "total_responses": total,
        "total_children": total_children,
    }


def get_response_type_counts_external(study) -> Dict:
    """Like get_response_type_counts but for external studies, which have no consent rulings.

    Returns a dict with the following keys:
    - preview: preview responses
    - untallied: all effectively untallied non-preview responses
    - tallied: all effectively tallied non-preview responses
    - total: all responses (preview/tallied/untallied)
    """
    is_effectively_tallied = Q(
        is_tallied_researcher_override__isnull=False,
        is_tallied_researcher_override=True,
    ) | Q(is_tallied_researcher_override__isnull=True, is_tallied=True)
    is_effectively_untallied = Q(
        is_tallied_researcher_override__isnull=False,
        is_tallied_researcher_override=False,
    ) | Q(is_tallied_researcher_override__isnull=True, is_tallied=False)

    counts = study.responses.aggregate(
        preview=Count("id", filter=Q(is_preview=True)),
        tallied=Count("id", filter=Q(is_preview=False) & is_effectively_tallied),
        untallied=Count("id", filter=Q(is_preview=False) & is_effectively_untallied),
    )
    counts["total"] = counts["preview"] + counts["tallied"] + counts["untallied"]
    return counts


def get_response_type_counts(study) -> Dict:
    """Produce a break down of consent status x tallied/untallied/preview status for internal studies.

    The breakdown is somewhat non-intuitive because the pending repsonses count towards the study's tallied/untallied response counts (for the purpose of response limits), but rejected counts do not. Responses with rejected consents are automatically untallied, which means that rejected consent responses are not broken down into tallied/untallied.

    Returns a dict with the following keys:
    - preview_approved: preview responses with accepted consent
    - preview_pending: preview responses with pending/null consent ruling
    - preview_rejected: preview responses with rejected consent
    - tallied_approved: non-preview, effectively tallied, accepted consent
    - tallied_pending: non-preview, effectively tallied, pending/null consent ruling
    - untallied_approved: non-preview, effectively untallied, accepted consent
    - untallied_pending: non-preview, effectively untallied, pending/null consent ruling
    - nonpreview_rejected: non-preview responses with rejected consent
    - preview: all preview responses (preview_approved + preview_pending)
    - tallied: all effectively tallied non-preview responses (tallied_approved + tallied_pending)
    - untallied: all effectively untallied non-preview responses (untallied_approved + untallied_pending)
    - total_available: all responses with accepted consent (preview_approved + tallied_approved + untallied_approved)
    - total_pending: all responses with pending/null consent (preview_pending + tallied_pending + untallied_pending)
    - total_rejected: all responses with rejected consent (preview_rejected + nonpreview_rejected)
    - total: total_available + total_pending (excludes rejected)
    """
    is_effectively_tallied = Q(
        is_tallied_researcher_override__isnull=False,
        is_tallied_researcher_override=True,
    ) | Q(is_tallied_researcher_override__isnull=True, is_tallied=True)
    is_effectively_untallied = Q(
        is_tallied_researcher_override__isnull=False,
        is_tallied_researcher_override=False,
    ) | Q(is_tallied_researcher_override__isnull=True, is_tallied=False)
    newest_ruling = Subquery(
        ConsentRuling.objects.filter(response=OuterRef("pk"))
        .order_by("-created_at")
        .values("action")[:1]
    )
    is_pending_ruling = Q(current_ruling__isnull=True) | Q(current_ruling="pending")
    counts = study.responses.annotate(current_ruling=newest_ruling).aggregate(
        preview_approved=Count(
            "id", filter=Q(is_preview=True) & Q(current_ruling="accepted")
        ),
        preview_pending=Count("id", filter=Q(is_preview=True) & is_pending_ruling),
        preview_rejected=Count(
            "id", filter=Q(is_preview=True) & Q(current_ruling="rejected")
        ),
        tallied_approved=Count(
            "id",
            filter=Q(is_preview=False)
            & is_effectively_tallied
            & Q(current_ruling="accepted"),
        ),
        tallied_pending=Count(
            "id",
            filter=Q(is_preview=False) & is_effectively_tallied & is_pending_ruling,
        ),
        untallied_approved=Count(
            "id",
            filter=Q(is_preview=False)
            & is_effectively_untallied
            & Q(current_ruling="accepted"),
        ),
        untallied_pending=Count(
            "id",
            filter=Q(is_preview=False) & is_effectively_untallied & is_pending_ruling,
        ),
        nonpreview_rejected=Count(
            "id", filter=Q(is_preview=False) & Q(current_ruling="rejected")
        ),
    )
    counts["preview"] = counts["preview_approved"] + counts["preview_pending"]
    counts["tallied"] = counts["tallied_approved"] + counts["tallied_pending"]
    counts["untallied"] = counts["untallied_approved"] + counts["untallied_pending"]
    counts["total_available"] = (
        counts["preview_approved"]
        + counts["tallied_approved"]
        + counts["untallied_approved"]
    )
    counts["total_pending"] = (
        counts["preview_pending"]
        + counts["tallied_pending"]
        + counts["untallied_pending"]
    )
    counts["total_rejected"] = (
        counts["preview_rejected"] + counts["nonpreview_rejected"]
    )
    counts["total"] = counts["total_available"] + counts["total_pending"]
    return counts


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


def get_study_list_qs(user, query_dict):
    """Gets a study list query set annotated with response counts.

    TODO: Factor in all the query mutation from the (view) caller.
    TODO: Upgrade to Django 2.x and use the improved query mechanisms to clean this up.

    Args:
        user: django.utils.functional.SimpleLazyObject masquerading as a user.
        query_dict: django.http.QueryDict from the self.request.GET property.

    Returns:
        A heavily annotated queryset for the list of studies.
    """
    annotated_responses_qs = get_annotated_responses_qs().only(
        "id",
        "completed",
        "completed_consent_frame",
        "date_created",
        "date_modified",
        "is_preview",
    )

    queryset = (
        studies_for_which_user_has_perm(user, StudyPermission.READ_STUDY_DETAILS)
        # .select_related("lab")
        # .select_related("creator")
        .only(
            "id",
            "state",
            "uuid",
            "name",
            "date_modified",
            "short_description",
            "image",
            "comments",
            "lab__name",
            "creator__given_name",
            "creator__family_name",
        )
        .exclude(state="archived")
        .filter(lab_id__isnull=False, creator_id__isnull=False)
        .annotate(
            lab_name=F("lab__name"),
            creator_name=Concat(
                "creator__given_name", Value(" "), "creator__family_name"
            ),
            completed_responses_count=SubqueryCount(
                Response.objects.filter(
                    study=OuterRef("pk"),
                    is_preview=False,
                    completed_consent_frame=True,
                    completed=True,
                ).values("id")
            ),
            incomplete_responses_count=SubqueryCount(
                Response.objects.filter(
                    study=OuterRef("pk"),
                    is_preview=False,
                    completed_consent_frame=True,
                    completed=False,
                ).values("id")
            ),
            valid_consent_count=SubqueryCount(
                annotated_responses_qs.filter(
                    study=OuterRef("pk"), is_preview=False, current_ruling="accepted"
                )
            ),
            pending_consent_count=SubqueryCount(
                annotated_responses_qs.filter(
                    study=OuterRef("pk"), is_preview=False, current_ruling="pending"
                )
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

    # Request filtering

    state = query_dict.get("state")
    if state and state != "all":
        if state == "myStudies":
            queryset = queryset.filter(creator=user)
        else:
            queryset = queryset.filter(state=state)

    match = query_dict.get("match")
    if match:
        queryset = queryset.filter(
            reduce(
                operator.and_,
                (
                    Q(name__icontains=term) | Q(short_description__icontains=term)
                    for term in match
                ),
            )
        )

    # Sort value is in a list
    sort = "".join(query_dict.get("sort", []))
    if sort:
        try:
            queryset = queryset.order_by(sort)
        except FieldError:
            # if someone attempts to manually enter a field that doesn't exist
            pass

    return queryset
