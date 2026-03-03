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
    """
    Response = apps.get_model("studies", "Response")
    ConsentRuling = apps.get_model("studies", "ConsentRuling")

    # Step 1: Mark all preview responses as invalid
    Response.objects.filter(is_preview=True).update(is_valid=False)

    # Step 2: Mark responses with ineligible eligibility as invalid
    # Valid eligibility: empty list OR contains "Eligible"
    # Invalid: non-empty list that doesn't contain "Eligible"
    Response.objects.exclude(
        models.Q(eligibility=[]) | models.Q(eligibility__contains=["Eligible"])
    ).update(is_valid=False)

    # Step 3: For internal studies only, mark incomplete responses and responses without consent frames as invalid
    Response.objects.exclude(study__study_type_id=EXTERNAL_STUDY_TYPE_ID).filter(
        models.Q(completed=False) | models.Q(completed_consent_frame=False)
    ).update(is_valid=False)

    # Step 4: For internal studies, mark responses with rejected consent as invalid
    # Get the most recent consent ruling for each response using a subquery
    newest_ruling_subquery = models.Subquery(
        ConsentRuling.objects.filter(response=models.OuterRef("pk"))
        .order_by("-created_at")
        .values("action")[:1]
    )
    rejected_response_ids = list(
        Response.objects.exclude(study__study_type_id=EXTERNAL_STUDY_TYPE_ID)
        .annotate(current_ruling=newest_ruling_subquery)
        .filter(current_ruling=REJECTED)
        .values_list("id", flat=True)
    )
    if rejected_response_ids:
        Response.objects.filter(id__in=rejected_response_ids).update(is_valid=False)


class Migration(migrations.Migration):
    dependencies = [
        ("studies", "0105_add_max_responses_to_study"),
    ]

    operations = [
        migrations.AddField(
            model_name="response",
            name="is_valid",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(compute_is_valid, migrations.RunPython.noop),
    ]
