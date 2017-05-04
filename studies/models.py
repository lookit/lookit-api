from django.db import models

from accounts.models import DemographicData, Organization, User
from project.fields.datetime_aware_jsonfield import DateTimeAwareJSONField
from transitions.extensions import GraphMachine as Machine

from . import workflow


class Study(models.Model):
    name = models.CharField(max_length=255, blank=False, null=False)
    organization = models.ForeignKey(Organization, on_delete=models.DO_NOTHING, related_name='studies', related_query_name='study')
    blocks = DateTimeAwareJSONField(default=dict)
    state = models.CharField(choices=workflow.STATE_CHOICES, max_length=25, default=workflow.STATE_CHOICES[0][0])

    def __init__(self, *args, **kwargs):
        super(Study, self).__init__(*args, **kwargs)
        self.machine = Machine(
            self,
            states=workflow.states,
            transitions=workflow.transitions,
            initial=self.state,
            send_event=True,
            before_state_change='check_permission',
            after_state_change='_finalize_state_change'
        )

    def __str__(self):
        return f'<Study: {self.name}>'

    class Meta:
        permissions = (
            ('view_study', 'View Study'),
            ('edit_study', 'Edit Study'),
            ('can_respond', 'Can Respond?'),
        )

    # WORKFLOW CALLBACKS
    def check_permission(self, ev):
        user = ev.kwargs.get('user')
        if user.is_superuser:
            return
        raise 

    def notify_administrators_of_submission(self, ev):
        # TODO
        pass

    def notify_submitter_of_approval(self, ev):
        # TODO
        pass

    def notify_submitter_of_rejection(self, ev):
        # TODO
        pass

    def notify_administrators_of_retraction(self, ev):
        # TODO
        pass

    def notify_administrators_of_activation(self, ev):
        # TODO
        pass

    def notify_administrators_of_pause(self, ev):
        # TODO
        pass

    def notify_administrators_of_deactivation(self, ev):
        # TODO
        pass

    # Runs for every transition to log action
    def _log_action(self, ev):
        StudyLog.objects.create(action=ev.state.name, study=ev.model, user=ev.kwargs.get('user'))

    # Runs for every transition to save state and log action
    def _finalize_state_change(self, ev):
        ev.model.save()
        self._log_action(ev)

class Response(models.Model):
    study = models.ForeignKey(Study, on_delete=models.DO_NOTHING, related_name='responses')
    participant = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    demographic_snapshot = models.ForeignKey(DemographicData, on_delete=models.DO_NOTHING)
    results = DateTimeAwareJSONField(default=dict)
    def __str__(self):
        return f'<Response: {self.study} {self.participant.get_short_name}>'

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


class StudyLog(Log):
    action = models.CharField(max_length=128)
    study = models.ForeignKey(Study, on_delete=models.DO_NOTHING, related_name='logs', related_query_name='logs')

    def __str__(self):
        return f'<StudyLog: {self.action} on {self.study.name} at {self.created_at} by {self.user.username}'


class ResponseLog(Log):
    action = models.CharField(max_length=128)
    response = models.ForeignKey(Response, on_delete=models.DO_NOTHING)
