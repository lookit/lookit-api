from django.contrib import admin
from guardian.admin import GuardedModelAdmin

from studies.models import (
    ConsentRuling,
    Feedback,
    Response,
    ResponseLog,
    Study,
    StudyLog,
    StudyType,
    Video,
)


class StudyAdmin(GuardedModelAdmin):
    list_display = ("uuid", "name", "state", "public", "creator", "built")
    list_filter = ("state", "creator")
    search_fields = ["name"]
    pass


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
    )
    empty_value_display = "None"
    list_filter = ("study",)
    date_hierarchy = "date_created"
    pass


class FeedbackAdmin(GuardedModelAdmin):
    list_display = ("uuid", "researcher", "response", "comment")
    list_filter = ("response__study", "researcher")
    pass


class StudyLogAdmin(GuardedModelAdmin):
    list_filter = ("study",)
    pass


class ResponseLogAdmin(GuardedModelAdmin):
    pass


class StudyTypeAdmin(GuardedModelAdmin):
    pass


class VideoAdmin(GuardedModelAdmin):
    list_display = (
        "uuid",
        "created_at",
        "study",
        "response",
        "full_name",
        "size",
        "is_consent_footage",
    )
    list_filter = ("study",)
    date_hierarchy = "created_at"
    search_fields = ["uuid", "full_name"]
    pass


class ConsentRulingAdmin(GuardedModelAdmin):
    list_display = ("uuid", "created_at", "action", "arbiter")
    list_filter = ("response__study", "arbiter")
    date_hierarchy = "created_at"
    pass


admin.site.register(Study, StudyAdmin)
admin.site.register(Response, ResponseAdmin)
admin.site.register(StudyLog, StudyLogAdmin)
admin.site.register(ResponseLog, ResponseLogAdmin)
admin.site.register(Feedback, FeedbackAdmin)
admin.site.register(StudyType, StudyTypeAdmin)
admin.site.register(Video, VideoAdmin)
admin.site.register(ConsentRuling, ConsentRulingAdmin)
