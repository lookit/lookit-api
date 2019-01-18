from django.contrib import admin
from guardian.admin import GuardedModelAdmin

from studies.models import Feedback, Response, ResponseLog, Study, StudyLog, StudyType


class StudyAdmin(GuardedModelAdmin):
    pass


class ResponseAdmin(GuardedModelAdmin):
    pass


class FeedbackAdmin(GuardedModelAdmin):
    pass


class StudyLogAdmin(GuardedModelAdmin):
    pass


class ResponseLogAdmin(GuardedModelAdmin):
    pass


class StudyTypeAdmin(GuardedModelAdmin):
    pass


admin.site.register(Study, StudyAdmin)
admin.site.register(Response, ResponseAdmin)
admin.site.register(StudyLog, StudyLogAdmin)
admin.site.register(ResponseLog, ResponseLogAdmin)
admin.site.register(Feedback, FeedbackAdmin)
admin.site.register(StudyType, StudyTypeAdmin)
