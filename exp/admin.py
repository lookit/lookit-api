from django.contrib import admin

from guardian.admin import GuardedModelAdmin

from studies.models import Response, ResponseLog, Study, StudyLog


class StudyAdmin(GuardedModelAdmin):
    pass

class ResponseAdmin(GuardedModelAdmin):
    pass

class StudyLogAdmin(GuardedModelAdmin):
    pass

class ResponseLogAdmin(GuardedModelAdmin):
    pass

admin.site.register(Study, StudyAdmin)
admin.site.register(Response, ResponseAdmin)
admin.site.register(StudyLog, StudyLogAdmin)
admin.site.register(ResponseLog, ResponseLogAdmin)
