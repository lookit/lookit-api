from django.db import models

from accounts.models import DemographicData, Organization, User
from project.fields.datetime_aware_jsonfield import DateTimeAwareJSONField


class Study(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.DO_NOTHING, related_name='studies', related_query_name='study')
    name = models.CharField(max_length=255, blank=False, null=False)
    is_active = models.BooleanField(default=True)
    blocks = DateTimeAwareJSONField(default=dict)
    # TODO record activity logs: created, submitted for approval, approved, rejected, started, participant_started, paused, started, paused, participant_finished, deactivated

    def __str__(self):
        return f'<Study: {self.name}>'

    class Meta:
        permissions = (
            ('view_study', 'View Study'),
            ('edit_study', 'Edit Study'),
            ('can_respond', 'Can Respond?'),
        )


class Response(models.Model):
    study = models.ForeignKey(Study, on_delete=models.DO_NOTHING)
    participant = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    demographic_snapshot = models.ForeignKey(DemographicData, on_delete=models.DO_NOTHING)
    results = DateTimeAwareJSONField(default=dict)
    def __str__(self):
        return f'<Response: {self.study} {self.participant.username}>'

    class Meta:
        permissions = (
            ('view_response', 'View Response'),
        )


class Log(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)

    def __str__(self):
        return f'<{self.__class__.name}: {self.action} @ {self.created_at:%c}>'

    class Meta:
        abstract = True

STUDY_ACTIONS = (
    ('created', 'Created'),
    ('submitted', 'Submitted for Approval'),
    ('rejected', 'Rejected'),
    ('approved', 'Approved'),
    ('started', 'Started'),
    ('paused', 'Paused'),
    ('resumed', 'Resumed'),
    ('deactivated', 'Deactivated'),
    ('retracted', 'Retracted'),
    ('viewed_data', 'Viewed Data'),
)


class StudyLog(Log):
    action = models.CharField(max_length=128, choices=STUDY_ACTIONS)
    study = models.ForeignKey(Study, on_delete=models.DO_NOTHING)


RESPONSE_ACTIONS = (
    ('started', 'Started'),
    ('paused', 'Paused'),
    ('abandoned', 'Abandoned'),
    ('finished', 'Finished'),
)


class ResponseLog(Log):
    action = models.CharField(max_length=128, choices=RESPONSE_ACTIONS)
    response = models.ForeignKey(Response, on_delete=models.DO_NOTHING)
