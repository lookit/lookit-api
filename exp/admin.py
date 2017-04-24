from django.contrib import admin

# Register your models here.
from studies.models import Study, Response, StudyLog, ResponseLog

admin.site.register(Study)
admin.site.register(Response)
admin.site.register(StudyLog)
admin.site.register(ResponseLog)
