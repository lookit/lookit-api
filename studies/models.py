import uuid

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify
from guardian.shortcuts import assign_perm
from transitions.extensions import GraphMachine as Machine

from accounts.models import DemographicData, Organization, Child, User
from project.fields.datetime_aware_jsonfield import DateTimeAwareJSONField
from . import workflow


class Study(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True)
    name = models.CharField(max_length=255, blank=False, null=False)
    date_modified = models.DateTimeField(auto_now=True)
    short_description = models.TextField()
    long_description = models.TextField()
    criteria = models.TextField()
    duration = models.TextField()
    contact_info = models.TextField()
    image = models.ImageField(null=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.DO_NOTHING,
        related_name='studies',
        related_query_name='study'
    )
    structure = DateTimeAwareJSONField(default=dict)
    display_full_screen = models.BooleanField(default=True)
    exit_url = models.URLField(default="https://lookit.mit.edu/")
    state = models.CharField(
        choices=workflow.STATE_CHOICES,
        max_length=25,
        default=workflow.STATE_CHOICES.created
    )
    public = models.BooleanField(default=False)
    creator = models.ForeignKey(User)

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
            ('can_view', 'Can View'),
            ('can_create', 'Can Create'),
            ('can_edit', 'Can Edit'),
            ('can_remove', 'Can Remove'),
            ('can_activate', 'Can Activate'),
            ('can_deactivate', 'Can Deactivate'),
            ('can_pause', 'Can Pause'),
            ('can_resume', 'Can Resume'),
            ('can_approve', 'Can Approve'),
            ('can_submit', 'Can Submit'),
            ('can_retract', 'Can Retract'),
            ('can_resubmit', 'Can Resubmit'),
            ('can_edit_permissions', 'Can Edit Permissions'),
            ('can_view_permissions', 'Can View Permissions'),
            ('can_view_responses', 'Can View Responses'),
            ('can_view_video_responses', 'Can View Video Responses'),
            ('can_view_demographics', 'Can View Demographics'),
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
        StudyLog.objects.create(
            action=ev.state.name,
            study=ev.model,
            user=ev.kwargs.get('user')
        )

    # Runs for every transition to save state and log action
    def _finalize_state_change(self, ev):
        ev.model.save()
        self._log_action(ev)

# TODO Need a post_save hook for edit that pulls studies out of approved state
# TODO or disallows editing in pre_save if they are approved


@receiver(post_save, sender=Study)
def study_post_save(sender, **kwargs):
    """
    Add study permissions to organization groups and
    create groups for all newly created Study instances. We only
    run on study creation to avoid having to check for existence
    on each call to Study.save.
    """
    study, created = kwargs['instance'], kwargs['created']
    if created:
        from django.contrib.auth.models import Group

        organization_groups = Group.objects.filter(
            name__startswith=f'{slugify(study.organization.name)}_ORG_'.upper()
        )
        # assign study permissions to organization groups
        for group in organization_groups:
            for perm, _ in Study._meta.permissions:
                if 'ADMIN' in group.name:
                    assign_perm(perm, group, obj=study)
                elif 'READ' in group.name and 'view' in perm:
                    assign_perm(perm, group, obj=study)

        # create study groups and assign permissions
        for group in ['read', 'admin']:
            study_group_instance = Group.objects.create(
                name=f'{slugify(study.organization.name)}_{slugify(study.name)}_STUDY_{group}'.upper()  # noqa
            )
            for perm, _ in Study._meta.permissions:
                # add only view permissions to non-admin
                if group == 'read' and perm != 'can_view':
                    continue
                if 'approve' not in perm:
                    assign_perm(perm, study_group_instance, obj=study)


class Response(models.Model):
    study = models.ForeignKey(
        Study, on_delete=models.DO_NOTHING,
        related_name='responses'
    )
    child = models.ForeignKey(Child, on_delete=models.DO_NOTHING)
    demographic_snapshot = models.ForeignKey(
        DemographicData,
        on_delete=models.DO_NOTHING
    )
    results = DateTimeAwareJSONField(default=dict)

    def __str__(self):
        return f'<Response: {self.study} {self.child.user.get_short_name}>'

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
    study = models.ForeignKey(
        Study,
        on_delete=models.DO_NOTHING,
        related_name='logs',
        related_query_name='logs'
    )

    def __str__(self):
        return f'<StudyLog: {self.action} on {self.study.name} at {self.created_at} by {self.user.username}'  # noqa


class ResponseLog(Log):
    action = models.CharField(max_length=128)
    response = models.ForeignKey(Response, on_delete=models.DO_NOTHING)
