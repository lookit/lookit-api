from django.db import models

from project.fields.datetime_aware_jsonfield import DateTimeAwareJSONField


class FrameType(models.Model):
    pass


class Frame(models.Model):
    kind = models.ForeignKey(FrameType, on_delete=models.CASCADE, related_name='frame')
    blocks = DateTimeAwareJSONField(default=list)


class Study(models.Model):
    frames = models.ManyToManyField(Frame, related_name='study', limit_choices_to=None, through=None)
