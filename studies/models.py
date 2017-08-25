import uuid

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify
from guardian.shortcuts import assign_perm, get_groups_with_perms
from kombu.utils import cached_property
from transitions.extensions import GraphMachine as Machine

from accounts.models import Child, DemographicData, Organization, User
from accounts.utils import build_study_group_name
from project.fields.datetime_aware_jsonfield import DateTimeAwareJSONField
from studies import workflow
from studies.helpers import send_mail
from studies.tasks import build_experiment


class StudyType(models.Model):
    name = models.CharField(max_length=255, blank=False, null=False)
    configuration = DateTimeAwareJSONField(default={
        # task module should have a build_experiment method decorated as a
        # celery task that takes a study uuid and a preview kwarg which
        # defaults to true
        "task_module": "studies.tasks",
        "metadata": {
            # defines the default metadata fields for that type of study
            "fields": {
                "addons_repo_url": settings.EMBER_ADDONS_REPO,
                "last_known_player_sha": None,
                "last_known_addons_sha": None
            }
        }
    })


class Study(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=False, null=False, db_index=True)
    date_modified = models.DateTimeField(auto_now=True)
    short_description = models.TextField()
    long_description = models.TextField()
    criteria = models.TextField()
    duration = models.TextField()
    contact_info = models.TextField()
    max_age = models.TextField(default='')
    min_age = models.TextField(default='')
    image = models.ImageField(null=True, upload_to='study_images/')
    comments = models.TextField(blank=True, null=True)
    study_type = models.ForeignKey('StudyType', on_delete=models.DO_NOTHING, null=False, blank=False, verbose_name='type')
    organization = models.ForeignKey(
        Organization,
        on_delete=models.DO_NOTHING,
        related_name='studies',
        related_query_name='study'
    )
    structure = DateTimeAwareJSONField(default={
        "frames": {},
        "sequence": []
    })
    display_full_screen = models.BooleanField(default=True)
    exit_url = models.URLField(default='')
    state = models.CharField(
        choices=workflow.STATE_CHOICES,
        max_length=25,
        default=workflow.STATE_CHOICES.created,
        db_index=True
    )
    public = models.BooleanField(default=False)
    creator = models.ForeignKey(User, on_delete=models.DO_NOTHING)

    metadata = DateTimeAwareJSONField(default={})

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
        self.__monitoring_fields = ['structure', 'name', 'short_description', 'long_description', 'criteria', 'duration', 'contact_info', 'max_age', 'min_age', 'image', 'exit_url']
        for field in self.__monitoring_fields:
            setattr(self, f'__original_{field}', getattr(self, field))

    def __str__(self):
        return f'<Study: {self.name}>'

    def important_fields_changed(self):
        """
        Check if fields in self.__monitoring fields have changed.
        """
        for field in self.__monitoring_fields:
            if getattr(self, f'__original_{field}') != getattr(self, field):
                return True
        return False

    class Meta:
        permissions = (
            ('can_view_study', 'Can View Study'),
            ('can_create_study', 'Can Create Study'),
            ('can_edit_study', 'Can Edit Study'),
            ('can_remove_study', 'Can Remove Study'),
            ('can_activate_study', 'Can Activate Study'),
            ('can_deactivate_study', 'Can Deactivate Study'),
            ('can_pause_study', 'Can Pause Study'),
            ('can_resume_study', 'Can Resume Study'),
            ('can_approve_study', 'Can Approve Study'),
            ('can_submit_study', 'Can Submit Study'),
            ('can_retract_study', 'Can Retract Study'),
            ('can_resubmit_study', 'Can Resubmit Study'),
            ('can_edit_study_permissions', 'Can Edit Study Permissions'),
            ('can_view_study_permissions', 'Can View Study Permissions'),
            ('can_view_study_responses', 'Can View Study Responses'),
            ('can_view_study_video_responses', 'Can View Study Video Responses'),
            ('can_view_study_demographics', 'Can View Study Demographics'),
            ('can_archive_study', 'Can Archive Study')
        )
        ordering = ['name']

    class JSONAPIMeta:
        resource_name = 'studies'
        lookup_field = 'uuid'

    @cached_property
    def begin_date(self):
        try:
            return self.logs.filter(action='active').first().created_at
        except AttributeError:
            return None

    @property
    def end_date(self):
        try:
            return self.logs.filter(action='deactivated').first().created_at
        except AttributeError:
            return None

    @property
    def study_admin_group(self):
        ''' Fetches the study admin group '''
        groups = get_groups_with_perms(self)
        for group in groups:
            if 'STUDY' in group.name and 'ADMIN' in group.name:
                return group
        return None

    @property
    def study_organization_admin_group(self):
        ''' Fetches the study organization admin group '''
        groups = get_groups_with_perms(self)
        for group in groups:
            if 'ORG' in group.name and 'ADMIN' in group.name:
                return group
        return None

    @property
    def study_read_group(self):
        ''' Fetches the study read group '''
        groups = get_groups_with_perms(self)
        for group in groups:
            if 'STUDY' in group.name and 'READ' in group.name:
                return group
        return None

    # WORKFLOW CALLBACKS
    def check_permission(self, ev):
        user = ev.kwargs.get('user')
        if user.is_superuser:
            return
        # raise TODO NOT RAISING ANYTHING
        return

    def clone(self):
        ''' Create a new, unsaved copy of the study. '''
        copy = self.__class__.objects.get(pk=self.pk)
        copy.id = None
        copy.public = False
        copy.state = 'created'
        copy.name = 'Copy of ' + copy.name

        # empty the fks
        fk_field_names = [f.name for f in self._meta.model._meta.get_fields() if isinstance(f, (models.ForeignKey))]
        for field_name in fk_field_names:
            setattr(copy, field_name, None)
        try:
            copy.uuid = uuid.uuid4()
        except AttributeError:
            pass
        return copy

    def notify_administrators_of_submission(self, ev):
        context = {
            'study': self,
            'action': ev.transition.dest,
            'researcher': ev.kwargs.get('user')
        }
        send_mail.delay('notify_admins_of_study_action', 'Study Submission Notification', settings.EMAIL_FROM_ADDRESS, bcc=list(self.study_organization_admin_group.user_set.values_list('username', flat=True)), **context)

    def notify_submitter_of_approval(self, ev):
        context = {
            'study': self,
            'approved': True,
            'comments': self.comments
        }
        send_mail.delay('notify_researchers_of_approval_decision', '{} Approval Notification'.format(self.name), settings.EMAIL_FROM_ADDRESS, bcc=list(self.study_admin_group.user_set.values_list('username', flat=True)), **context)

    def notify_submitter_of_rejection(self, ev):
        context = {
            'study': self,
            'approved': False,
            'comments': self.comments
        }
        send_mail.delay('notify_researchers_of_approval_decision', '{} Rejection Notification'.format(self.name), settings.EMAIL_FROM_ADDRESS, bcc=list(self.study_admin_group.user_set.values_list('username', flat=True)), **context)

    def notify_submitter_of_recission(self, ev):
        context = {
            'study': self,
        }
        send_mail.delay('notify_researchers_of_approval_rescission', '{} Rescinded Notification'.format(self.name), settings.EMAIL_FROM_ADDRESS, bcc=list(self.study_admin_group.user_set.values_list('username', flat=True)), **context)

    def notify_administrators_of_retraction(self, ev):
        context = {
            'study': self,
            'action': ev.transition.dest,
            'researcher': ev.kwargs.get('user')
        }
        send_mail.delay('notify_admins_of_study_action', 'Study Retraction Notification', settings.EMAIL_FROM_ADDRESS, bcc=list(self.study_organization_admin_group.user_set.values_list('username', flat=True)), **context)

    def notify_administrators_of_activation(self, ev):
        context = {
            'study': self,
            'action': ev.transition.dest,
            'researcher': ev.kwargs.get('user')
        }
        send_mail.delay('notify_admins_of_study_action', 'Study Activation Notification', settings.EMAIL_FROM_ADDRESS, bcc=list(self.study_organization_admin_group.user_set.values_list('username', flat=True)), **context)

    def deploy_study(self, ev):
        self.state = 'deploying'
        self.save()
        build_experiment.delay(self.uuid, preview=False)

    def notify_administrators_of_pause(self, ev):
        context = {
            'study': self,
            'action': ev.transition.dest,
            'researcher': ev.kwargs.get('user')
        }
        send_mail.delay('notify_admins_of_study_action', 'Study Pause Notification', settings.EMAIL_FROM_ADDRESS, bcc=list(self.study_organization_admin_group.user_set.values_list('username', flat=True)), **context)

    def notify_administrators_of_deactivation(self, ev):
        context = {
            'study': self,
            'action': ev.transition.dest,
            'researcher': ev.kwargs.get('user')
        }
        send_mail.delay('notify_admins_of_study_action', 'Study Deactivation Notification', settings.EMAIL_FROM_ADDRESS, bcc=list(self.study_organization_admin_group.user_set.values_list('username', flat=True)), **context)

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

@receiver(post_save, sender=Study)
def add_study_created_log(sender, instance, created, **kwargs):
    if created:
        StudyLog.objects.create(
            action='created',
            study=instance,
            user=instance.creator
        )

@receiver(post_save, sender=Study)
def check_modification_of_approved_study(sender, instance, created, **kwargs):
    """
    Puts study back in "rejected" state if study is modified after it's already been approved.
    Leaves comment for user with explanation.
    """
    approved_states = ['approved', 'active', 'paused', 'deactivated']
    if instance.state in approved_states and instance.important_fields_changed():
        instance.state = 'rejected'
        instance.comments = 'Your study has been modified following approval.  You must resubmit this study to get it approved again.'
        instance.save()
        StudyLog.objects.create(
            action='rejected',
            study=instance,
            user=instance.creator
    )

@receiver(post_save, sender=Study)
def remove_rejection_comments_after_approved(sender, instance, created, **kwargs):
    """
    If study moved into approved state, remove any previous rejection comments
    """
    if instance.state == 'approved' and instance.comments != '':
        instance.comments = ''
        instance.save()

@receiver(post_save, sender=Study)
def study_post_save(sender, **kwargs):
    '''
    Add study permissions to organization groups and
    create groups for all newly created Study instances. We only
    run on study creation to avoid having to check for existence
    on each call to Study.save.
    '''
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
                name=build_study_group_name(study.organization.name, study.name, study.pk, group)
            )
            for perm, _ in Study._meta.permissions:
                # add only view permissions to non-admin
                if group == 'read' and 'view' not in perm:
                    continue
                if 'approve' not in perm:
                    assign_perm(perm, study_group_instance, obj=study)


class Response(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    study = models.ForeignKey(
        Study, on_delete=models.DO_NOTHING,
        related_name='responses'
    )
    completed = models.BooleanField(default=False)
    exp_data = DateTimeAwareJSONField(default=dict)
    conditions = DateTimeAwareJSONField(default=dict)
    sequence = ArrayField(models.CharField(max_length=128), blank=True, default=list)
    date_modified = models.DateTimeField(auto_now=True)
    global_event_timings = DateTimeAwareJSONField(default=dict)
    child = models.ForeignKey(Child, on_delete=models.DO_NOTHING)
    demographic_snapshot = models.ForeignKey(
        DemographicData,
        on_delete=models.DO_NOTHING
    )

    def __str__(self):
        return f'<Response: {self.study} {self.child.user.get_short_name}>'

    class Meta:
        permissions = (
            ('view_response', 'View Response'),
        )
        ordering = ['-demographic_snapshot__created_at']

    class JSONAPIMeta:
        resource_name = 'responses'
        lookup_field = 'uuid'


class Log(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)

    def __str__(self):
        return f'<{self.__class__.name}: {self.action} @ {self.created_at:%c}>'

    class Meta:
        abstract = True
        ordering = ['-created_at']


class StudyLog(Log):
    action = models.CharField(max_length=128, db_index=True)
    extra = DateTimeAwareJSONField(null=True)
    study = models.ForeignKey(
        Study,
        on_delete=models.DO_NOTHING,
        related_name='logs',
        related_query_name='logs'
    )

    def __str__(self):
        return f'<StudyLog: {self.action} on {self.study.name} at {self.created_at} by {self.user.username}'  # noqa

    class JSONAPIMeta:
        resource_name = 'study-logs'
        lookup_field = 'uuid'

    class Meta:
        index_together = (
            ('study', 'action')
        )


class ResponseLog(Log):
    action = models.CharField(max_length=128, db_index=True)
    response = models.ForeignKey(Response, on_delete=models.DO_NOTHING)

    class Meta:
        index_together = (
            ('response', 'action')
        )

    class JSONAPIMeta:
        resource_name = 'response-logs'
        lookup_field = 'uuid'
