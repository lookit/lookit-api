from django.db import migrations, models

REJECTED = "rejected"
EXTERNAL_STUDY_TYPE_ID = 2


def compute_is_valid(apps, schema_editor):
    """Compute is_valid for all existing responses using the valid_response_count criteria.

    A response is valid if:
    - is_preview is False
    - eligibility is "Eligible" or blank/empty

    For internal studies, responses must also:
    - completed is True
    - completed_consent_frame is True
    - the most recent consent ruling is not "rejected"

    All responses start as False (the field default). This function marks passing responses True.
    """
    Response = apps.get_model("studies", "Response")
    ConsentRuling = apps.get_model("studies", "ConsentRuling")

    # Filter on eligibiliety (must be "Eligible" or an empty array for backwards compatibility)
    eligible_filter = models.Q(eligibility=[]) | models.Q(
        eligibility__contains=["Eligible"]
    )

    # Change is_valid for external study responses to True if: non-preview, eligible
    Response.objects.filter(
        study__study_type_id=EXTERNAL_STUDY_TYPE_ID,
        is_preview=False,
    ).filter(eligible_filter).update(is_valid=True)

    # Change is_valid internal study responses to True if: non-preview, eligible, completed, has consent, consent not rejected
    newest_ruling_subquery = models.Subquery(
        ConsentRuling.objects.filter(response=models.OuterRef("pk"))
        .order_by("-created_at")
        .values("action")[:1]
    )
    valid_internal_ids = list(
        Response.objects.exclude(study__study_type_id=EXTERNAL_STUDY_TYPE_ID)
        .filter(is_preview=False, completed=True, completed_consent_frame=True)
        .filter(eligible_filter)
        .annotate(current_ruling=newest_ruling_subquery)
        .exclude(current_ruling=REJECTED)
        .values_list("id", flat=True)
    )
    if valid_internal_ids:
        Response.objects.filter(id__in=valid_internal_ids).update(is_valid=True)


class Migration(migrations.Migration):
    dependencies = [
        ("studies", "0105_add_max_responses_to_study"),
    ]

    operations = [
        migrations.AddField(
            model_name="response",
            name="is_valid",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(compute_is_valid, migrations.RunPython.noop),
        migrations.AddField(
            model_name="response",
            name="is_valid_researcher_override",
            field=models.BooleanField(blank=True, default=None, null=True),
        ),
    ]
