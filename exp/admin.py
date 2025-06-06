from django.contrib import admin
from guardian.admin import GuardedModelAdmin

from studies.models import (
    ConsentRuling,
    Feedback,
    Lab,
    Response,
    Study,
    StudyLog,
    StudyType,
    Video,
)


@admin.register(Study)
class StudyAdmin(GuardedModelAdmin):
    list_display = ("uuid", "name", "state", "public", "creator", "built")
    list_filter = ("state", "lab")
    search_fields = ["name"]
    raw_id_fields = (
        "creator",
        "lab",
        "preview_group",
        "design_group",
        "analysis_group",
        "submission_processor_group",
        "researcher_group",
        "manager_group",
        "admin_group",
    )


@admin.register(Lab)
class LabAdmin(GuardedModelAdmin):
    list_display = ("uuid", "name", "institution", "principal_investigator_name")
    search_fields = ["name", "institution", "principal_investigator_name"]
    raw_id_fields = ("guest_group", "readonly_group", "member_group", "admin_group")
    list_filter = ("approved_to_test",)
    filter_horizontal = ("researchers", "requested_researchers")


@admin.register(Response)
class ResponseAdmin(GuardedModelAdmin):
    list_display = (
        "date_created",
        "uuid",
        "study",
        "child",
        "completed",
        "completed_consent_frame",
        "withdrawn",
        "is_preview",
        "eligibility",
    )
    raw_id_fields = ("child", "demographic_snapshot")
    empty_value_display = "None"
    list_filter = ("study",)
    date_hierarchy = "date_created"


@admin.register(Feedback)
class FeedbackAdmin(GuardedModelAdmin):
    list_display = ("uuid", "researcher", "response", "comment")
    search_fields = (
        "uuid",
        "researcher__given_name",
        "researcher__family_name",
        "response__uuid",
        "comment",
    )
    raw_id_fields = ("researcher", "response")


@admin.register(StudyLog)
class StudyLogAdmin(GuardedModelAdmin):
    list_filter = ("study",)
    raw_id_fields = ("study", "user")


@admin.register(StudyType)
class StudyTypeAdmin(GuardedModelAdmin):
    pass


@admin.register(Video)
class VideoAdmin(GuardedModelAdmin):
    list_display = (
        "uuid",
        "created_at",
        "study",
        "response",
        "full_name",
        "is_consent_footage",
    )
    list_filter = ("study",)
    # Use raw_id_fields to avoid a large number of queries to display every possible
    # option for response & study in the update form, which was making it impossible
    # to use on staging/production. (
    raw_id_fields = ("response", "study")
    date_hierarchy = "created_at"
    search_fields = ["uuid", "full_name"]


@admin.register(ConsentRuling)
class ConsentRulingAdmin(GuardedModelAdmin):
    list_display = ("uuid", "created_at", "action", "arbiter")
    list_filter = ("response__study", "arbiter")
    date_hierarchy = "created_at"
    raw_id_fields = ("arbiter", "response")
