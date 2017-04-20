from django.db import models

from project.fields.datetime_aware_jsonfield import DateTimeAwareJSONField


class Study(models.Model):
    name = models.CharField(max_length=255, blank=False, null=False)
    blocks = DateTimeAwareJSONField(default=list)

    def __str__(self):
        return f'<Study: {self.name}>'

    class Meta:
        permissions = (
            ('view_study', 'View Study'),
            ('edit_study', 'Edit Study')
        )
