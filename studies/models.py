from django.db import models

from project.fields.datetime_aware_jsonfield import DateTimeAwareJSONField


class Study(models.Model):
    blocks = DateTimeAwareJSONField(default=list)
