import json
import logging
import uuid

import boto3
import dateutil
import fleep
from botocore.exceptions import ClientError
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models.functions import Coalesce
from django.db.models.signals import post_save, pre_save, pre_delete
from django.dispatch import receiver
from django.utils.text import slugify
from guardian.shortcuts import assign_perm, get_groups_with_perms
from kombu.utils import cached_property
from model_utils import Choices
from transitions.extensions import GraphMachine as Machine

from accounts.models import Child, DemographicData, Organization, User
from accounts.utils import build_study_group_name
from attachment_helpers import get_download_url
from project import settings
from project.fields.datetime_aware_jsonfield import DateTimeAwareJSONField
from project.settings import EMAIL_FROM_ADDRESS
from studies import workflow
from studies.helpers import send_mail, FrameActionDispatcher
from studies.tasks import build_experiment, delete_video_from_cloud

logger = logging.getLogger(__name__)
date_parser = dateutil.parser


VALID_CONSENT_FRAMES = ("1-video-consent",)
VALID_EXIT_FRAME_POSTFIXES = ("exit-survey",)
STOPPED_CAPTURE_EVENT_TYPE = "exp-video-consent:stoppingCapture"

# Consent ruling stuff
PENDING = "pending"
ACCEPTED = "accepted"
REJECTED = "rejected"
CONSENT_RULINGS = (ACCEPTED, REJECTED, PENDING)

S3_RESOURCE = boto3.resource("s3")
S3_BUCKET = S3_RESOURCE.Bucket(settings.BUCKET_NAME)

dispatch_frame_action = FrameActionDispatcher()


# Probably want a queries module for this...
def get_annotated_responses_qs():
    """Retrieve a queryset for the set of responses belonging to a set of studies."""
    # Create the subquery where we get the action from the most recent ruling.
    newest_ruling_subquery = models.Subquery(
        ConsentRuling.objects.filter(response=models.OuterRef("pk"))
        .order_by("-created_at")
        .values("action")[:1]
    )

    # Annotate that value as "current ruling" on our response queryset.
    return (
        Response.objects.prefetch_related("consent_rulings")
        .filter(completed_consent_frame=True)
        .annotate(
            current_ruling=Coalesce(newest_ruling_subquery, models.Value(PENDING))
        )
    )


def get_consented_responses_qs():
    """Retrieve a queryset for the set of consented responses belonging to a set of studies."""
    # Create the subquery where we get the action from the most recent ruling.
    return get_annotated_responses_qs().filter(current_ruling=ACCEPTED)


def get_pending_responses_qs():
    """Retrieve a queryset for the set of pending judgement responses belonging to a set of studies."""
    # Create the subquery where we get the action from the most recent ruling.
    return get_annotated_responses_qs().filter(
        models.Q(current_ruling=PENDING) | models.Q(current_ruling=None)
    )


class StudyType(models.Model):
    name = models.CharField(max_length=255, blank=False, null=False)
    configuration = DateTimeAwareJSONField(
        default={
            # task module should have a build_experiment method decorated as a
            # celery task that takes a study uuid and a preview kwarg which
            # defaults to true
            "task_module": "studies.tasks",
            "metadata": {
                # defines the default metadata fields for that type of study
                "fields": {
                    "player_repo_url": settings.EMBER_EXP_PLAYER_REPO,
                    "last_known_player_sha": None,
                }
            },
        }
    )

    def __str__(self):
        return f"<Study Type: {self.name}>"


class Study(models.Model):

    MONITORING_FIELDS = [
        "structure",
        "name",
        "short_description",
        "long_description",
        "criteria",
        "duration",
        "contact_info",
        "max_age_years",
        "min_age_years",
        "max_age_months",
        "min_age_months",
        "max_age_days",
        "min_age_days",
        "image",
        "exit_url",
        "metadata",
        "study_type",
    ]

    DAY_CHOICES = [(i, i) for i in range(0, 32)]
    MONTH_CHOICES = [(i, i) for i in range(0, 12)]
    YEAR_CHOICES = [(i, i) for i in range(0, 19)]
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=False, null=False, db_index=True)
    date_modified = models.DateTimeField(auto_now=True)
    short_description = models.TextField()
    long_description = models.TextField()
    criteria = models.TextField()
    duration = models.TextField()
    contact_info = models.TextField()
    min_age_days = models.IntegerField(default=0, choices=DAY_CHOICES)
    min_age_months = models.IntegerField(default=0, choices=MONTH_CHOICES)
    min_age_years = models.IntegerField(default=0, choices=YEAR_CHOICES)
    max_age_days = models.IntegerField(default=0, choices=DAY_CHOICES)
    max_age_months = models.IntegerField(default=0, choices=MONTH_CHOICES)
    max_age_years = models.IntegerField(default=0, choices=YEAR_CHOICES)
    image = models.ImageField(null=True, upload_to="study_images/")
    comments = models.TextField(blank=True, null=True)
    study_type = models.ForeignKey(
        "StudyType",
        on_delete=models.DO_NOTHING,
        null=False,
        blank=False,
        verbose_name="type",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.DO_NOTHING,
        related_name="studies",
        related_query_name="study",
    )
    structure = DateTimeAwareJSONField(default={"frames": {}, "sequence": []})
    display_full_screen = models.BooleanField(default=True)
    exit_url = models.URLField(default="")
    state = models.CharField(
        choices=workflow.STATE_CHOICES,
        max_length=25,
        default=workflow.STATE_CHOICES.created,
        db_index=True,
    )
    public = models.BooleanField(default=False)
    creator = models.ForeignKey(User, on_delete=models.DO_NOTHING)

    metadata = DateTimeAwareJSONField(default={})
    previewed = models.BooleanField(default=False)
    built = models.BooleanField(default=False)

    def __init__(self, *args, **kwargs):
        super(Study, self).__init__(*args, **kwargs)
        self.machine = Machine(
            self,
            states=workflow.states,
            transitions=workflow.transitions,
            initial=self.state,
            send_event=True,
            before_state_change="check_permission",
            after_state_change="_finalize_state_change",
        )

    def __str__(self):
        return f"<Study: {self.name}>"

    class Meta:
        permissions = (
            ("can_view_study", "Can View Study"),
            ("can_create_study", "Can Create Study"),
            ("can_edit_study", "Can Edit Study"),
            ("can_remove_study", "Can Remove Study"),
            ("can_activate_study", "Can Activate Study"),
            ("can_deactivate_study", "Can Deactivate Study"),
            ("can_pause_study", "Can Pause Study"),
            ("can_resume_study", "Can Resume Study"),
            ("can_approve_study", "Can Approve Study"),
            ("can_submit_study", "Can Submit Study"),
            ("can_retract_study", "Can Retract Study"),
            ("can_resubmit_study", "Can Resubmit Study"),
            ("can_edit_study_permissions", "Can Edit Study Permissions"),
            ("can_view_study_permissions", "Can View Study Permissions"),
            ("can_view_study_responses", "Can View Study Responses"),
            ("can_view_study_video_responses", "Can View Study Video Responses"),
            ("can_view_study_demographics", "Can View Study Demographics"),
            ("can_archive_study", "Can Archive Study"),
        )
        ordering = ["name"]

    class JSONAPIMeta:
        resource_name = "studies"
        lookup_field = "uuid"

    @cached_property
    def begin_date(self):
        try:
            return self.logs.filter(action="active").first().created_at
        except AttributeError:
            return None

    @property
    def judgeable_responses(self):
        return self.responses.filter(completed_consent_frame=True)

    @property
    def responses_with_consent_videos(self):
        """Custom Queryset for the Consent Manager view."""
        return (
            self.judgeable_responses.prefetch_related(
                models.Prefetch(
                    "videos", queryset=Video.objects.filter(is_consent_footage=True)
                ),
                "consent_rulings",
            )
            .select_related("child", "child__user")
            .order_by("-date_created")
            .all()
        )

    @property
    def responses_with_all_videos(self):
        """Custom Queryset for the Consent Manager view."""
        return (
            self.judgeable_responses.prefetch_related("videos", "consent_rulings")
            .select_related("child", "child__user")
            .order_by("-date_created")
            .all()
        )

    @property
    def consented_responses(self):
        """Get responses for which we have a valid "accepted" consent ruling."""
        # Create the subquery where we get the action from the most recent ruling.
        newest_ruling_subquery = models.Subquery(
            ConsentRuling.objects.filter(response=models.OuterRef("pk"))
            .order_by("-created_at")
            .values("action")[:1]
        )

        # Annotate that value as "current ruling" on our response queryset.
        annotated = self.responses_with_all_videos.annotate(
            current_ruling=newest_ruling_subquery
        )

        # Only return the things for which our annotated property == accepted.
        return annotated.filter(current_ruling="accepted")

    @property
    def videos_for_consented_responses(self):
        """Gets videos but only for consented responses."""
        return Video.objects.filter(response_id__in=self.consented_responses)

    @property
    def consent_videos(self):
        return self.videos.filter(is_consent_footage=True)

    @property
    def end_date(self):
        try:
            return self.logs.filter(action="deactivated").first().created_at
        except AttributeError:
            return None

    @property
    def study_admin_group(self):
        """ Fetches the study admin group """
        groups = get_groups_with_perms(self)
        for group in groups:
            if "STUDY" in group.name and "ADMIN" in group.name:
                return group
        return None

    @property
    def study_organization_admin_group(self):
        """ Fetches the study organization admin group """
        groups = get_groups_with_perms(self)
        for group in groups:
            if "ORG" in group.name and "ADMIN" in group.name:
                return group
        return None

    @property
    def study_read_group(self):
        """ Fetches the study read group """
        groups = get_groups_with_perms(self)
        for group in groups:
            if "STUDY" in group.name and "READ" in group.name:
                return group
        return None

    # WORKFLOW CALLBACKS
    def check_permission(self, ev):
        user = ev.kwargs.get("user")
        if user.is_superuser:
            return
        # raise TODO NOT RAISING ANYTHING
        return

    def clone(self):
        """ Create a new, unsaved copy of the study. """
        copy = self.__class__.objects.get(pk=self.pk)
        copy.id = None
        copy.public = False
        copy.state = "created"
        copy.name = "Copy of " + copy.name

        # empty the fks
        fk_field_names = [
            f.name
            for f in self._meta.model._meta.get_fields()
            if isinstance(f, (models.ForeignKey))
        ]
        for field_name in fk_field_names:
            setattr(copy, field_name, None)
        try:
            copy.uuid = uuid.uuid4()
        except AttributeError:
            pass
        return copy

    def notify_administrators_of_submission(self, ev):
        context = {
            "org_name": self.organization.name,
            "study_name": self.name,
            "study_id": self.pk,
            "study_uuid": str(self.uuid),
            "researcher_name": ev.kwargs.get("user").get_short_name(),
            "action": ev.transition.dest,
        }
        send_mail.delay(
            "notify_admins_of_study_action",
            "Study Submission Notification",
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(
                self.study_organization_admin_group.user_set.values_list(
                    "username", flat=True
                )
            ),
            **context,
        )

    def notify_submitter_of_approval(self, ev):
        context = {
            "study_name": self.name,
            "org_name": self.organization.name,
            "study_id": self.pk,
            "approved": True,
            "comments": self.comments,
        }
        send_mail.delay(
            "notify_researchers_of_approval_decision",
            "{} Approval Notification".format(self.name),
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(
                self.study_admin_group.user_set.values_list("username", flat=True)
            ),
            **context,
        )

    def notify_submitter_of_rejection(self, ev):
        context = {
            "study_name": self.name,
            "org_name": self.organization.name,
            "study_id": self.pk,
            "approved": False,
            "comments": self.comments,
        }
        send_mail.delay(
            "notify_researchers_of_approval_decision",
            "{} Rejection Notification".format(self.name),
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(
                self.study_admin_group.user_set.values_list("username", flat=True)
            ),
            **context,
        )

    def notify_submitter_of_recission(self, ev):
        context = {"study_name": self.name, "org_name": self.organization.name}
        send_mail.delay(
            "notify_researchers_of_approval_rescission",
            "{} Rescinded Notification".format(self.name),
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(
                self.study_admin_group.user_set.values_list("username", flat=True)
            ),
            **context,
        )

    def notify_administrators_of_retraction(self, ev):
        context = {
            "org_name": self.organization.name,
            "study_name": self.name,
            "study_id": self.pk,
            "study_uuid": str(self.uuid),
            "researcher_name": ev.kwargs.get("user").get_short_name(),
            "action": ev.transition.dest,
        }
        send_mail.delay(
            "notify_admins_of_study_action",
            "Study Retraction Notification",
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(
                self.study_organization_admin_group.user_set.values_list(
                    "username", flat=True
                )
            ),
            **context,
        )

    def check_if_built(self, ev):
        """Check if study is built.

        :param ev: The event object
        :type ev: transitions.core.EventData
        :raise: RuntimeError
        """
        if not self.built:
            raise RuntimeError(
                f'Cannot activate study - "{self.name}" ({self.id}) has not been built!'
            )

    def notify_administrators_of_activation(self, ev):
        context = {
            "org_name": self.organization.name,
            "study_name": self.name,
            "study_id": self.pk,
            "study_uuid": str(self.uuid),
            "researcher_name": ev.kwargs.get("user").get_short_name(),
            "action": ev.transition.dest,
        }
        send_mail.delay(
            "notify_admins_of_study_action",
            "Study Activation Notification",
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(
                self.study_organization_admin_group.user_set.values_list(
                    "username", flat=True
                )
            ),
            **context,
        )

    def deploy_study(self, ev):
        # self.state = 'deploying'
        # self.save()
        build_experiment.delay(self.uuid, ev.kwargs.get("user").uuid, preview=False)

    def notify_administrators_of_pause(self, ev):
        context = {
            "org_name": self.organization.name,
            "study_name": self.name,
            "study_id": self.pk,
            "study_uuid": str(self.uuid),
            "researcher_name": ev.kwargs.get("user").get_short_name(),
            "action": ev.transition.dest,
        }
        send_mail.delay(
            "notify_admins_of_study_action",
            "Study Pause Notification",
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(
                self.study_organization_admin_group.user_set.values_list(
                    "username", flat=True
                )
            ),
            **context,
        )

    def notify_administrators_of_deactivation(self, ev):
        context = {
            "org_name": self.organization.name,
            "study_name": self.name,
            "study_id": self.pk,
            "study_uuid": str(self.uuid),
            "researcher_name": ev.kwargs.get("user").get_short_name(),
            "action": ev.transition.dest,
        }
        send_mail.delay(
            "notify_admins_of_study_action",
            "Study Deactivation Notification",
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(
                self.study_organization_admin_group.user_set.values_list(
                    "username", flat=True
                )
            ),
            **context,
        )

    # Runs for every transition to log action
    def _log_action(self, ev):
        StudyLog.objects.create(
            action=ev.state.name, study=ev.model, user=ev.kwargs.get("user")
        )

    # Runs for every transition to save state and log action
    def _finalize_state_change(self, ev):
        ev.model.save()
        self._log_action(ev)


@receiver(post_save, sender=Study)
def add_study_created_log(sender, instance, created, **kwargs):
    if created:
        StudyLog.objects.create(action="created", study=instance, user=instance.creator)


@receiver(pre_save, sender=Study)
def check_modification_of_approved_study(
    sender, instance, raw, using, update_fields, **kwargs
):
    """
    Puts study back in "rejected" state if study is modified after it's already been approved.
    Leaves comment for user with explanation.
    """
    approved_states = ["approved", "active", "paused", "deactivated"]
    study_in_db = Study.objects.filter(pk=instance.id).first()
    if not study_in_db:
        return

    field_transitions = {
        field: (getattr(study_in_db, field), getattr(instance, field))
        for field in Study.MONITORING_FIELDS
    }

    build_changed_metadata = update_fields is not None and "metadata" in update_fields

    # Special treatment for metadata field.
    important_fields_changed = False
    for field, (current, new) in field_transitions.items():
        if (
            field == "metadata"
            and build_changed_metadata
            and not current.get("last_known_player_sha", None)
        ):
            continue  # Skip, since we're technically just encoding the most recent SHA.
        else:
            if new != current:
                important_fields_changed = True
                break

    if instance.state in approved_states and important_fields_changed:
        instance.state = "rejected"
        instance.comments = "Your study has been modified following approval.  You must resubmit this study to get it approved again."
        StudyLog.objects.create(
            action="rejected", study=instance, user=instance.creator
        )


@receiver(post_save, sender=Study)
def remove_rejection_comments_after_approved(sender, instance, created, **kwargs):
    """
    If study moved into approved state, remove any previous rejection comments
    """
    if instance.state == "approved" and instance.comments != "":
        instance.comments = ""
        instance.save()


@receiver(post_save, sender=Study)
def study_post_save(sender, **kwargs):
    """
    Add study permissions to organization groups and
    create groups for all newly created Study instances. We only
    run on study creation to avoid having to check for existence
    on each call to Study.save.
    """
    study, created = kwargs["instance"], kwargs["created"]
    if created:
        from django.contrib.auth.models import Group

        organization_groups = Group.objects.filter(
            name__startswith=f"{slugify(study.organization.name)}_ORG_".upper()
        )
        # assign study permissions to organization groups
        for group in organization_groups:
            for perm, _ in Study._meta.permissions:
                if "ADMIN" in group.name:
                    assign_perm(perm, group, obj=study)
                elif "READ" in group.name and "view" in perm:
                    assign_perm(perm, group, obj=study)

        # create study groups and assign permissions
        for group in ["read", "admin"]:
            study_group_instance = Group.objects.create(
                name=build_study_group_name(
                    study.organization.name, study.name, study.pk, group
                )
            )
            for perm, _ in Study._meta.permissions:
                # add only view permissions to non-admin
                if group == "read" and "view" not in perm:
                    continue
                if "approve" not in perm:
                    assign_perm(perm, study_group_instance, obj=study)


class Response(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    study = models.ForeignKey(
        Study, on_delete=models.DO_NOTHING, related_name="responses"
    )
    completed = models.BooleanField(default=False)
    completed_consent_frame = models.BooleanField(default=False)
    exp_data = DateTimeAwareJSONField(default=dict)
    conditions = DateTimeAwareJSONField(default=dict)
    sequence = ArrayField(models.CharField(max_length=128), blank=True, default=list)
    date_modified = models.DateTimeField(auto_now=True)
    date_created = models.DateTimeField(auto_now_add=True)
    global_event_timings = DateTimeAwareJSONField(default=dict)
    child = models.ForeignKey(Child, on_delete=models.DO_NOTHING)
    demographic_snapshot = models.ForeignKey(
        DemographicData, on_delete=models.DO_NOTHING
    )

    def __str__(self):
        return self.display_name

    class Meta:
        permissions = (("view_response", "View Response"),)
        ordering = ["-demographic_snapshot__created_at"]

    class JSONAPIMeta:
        resource_name = "responses"
        lookup_field = "uuid"

    def _get_recent_consent_ruling(self):
        return self.consent_rulings.first()

    @cached_property
    def display_name(self):
        return f"{self.date_created.strftime('%c')}; Child({self.child.given_name}); Parent({self.child.user.nickname})"

    @property
    def most_recent_ruling(self):
        """Gets the most recent ruling for a Response/Session.

        XXX: This is EXPENSIVE if not called within the context of a prefetched query set!
        """
        ruling = self._get_recent_consent_ruling()
        return ruling.action if ruling else PENDING

    @property
    def has_valid_consent(self):
        return self.most_recent_ruling == ACCEPTED

    @property
    def pending_consent_judgement(self):
        return self.most_recent_ruling == PENDING

    @property
    def currently_rejected(self):
        return self.most_recent_ruling == REJECTED

    @property
    def most_recent_ruling_comment(self):
        ruling = self._get_recent_consent_ruling()
        return ruling.comments if ruling else None

    @property
    def comment_or_reason_for_absence(self):
        ruling = self.consent_rulings.first()
        if ruling:
            if ruling.comments:
                return ruling.comments
            else:
                return "No comment on previous ruling."
        else:
            return "No previous ruling."

    @property
    def most_recent_ruling_date(self):
        ruling = self._get_recent_consent_ruling()
        return ruling.created_at.strftime("%Y-%m-%d %H:%M") if ruling else None

    @property
    def most_recent_ruling_arbiter(self):
        ruling = self._get_recent_consent_ruling()
        return ruling.arbiter.get_full_name() if ruling else None

    @property
    def current_consent_details(self):
        return {
            "ruling": self.most_recent_ruling,
            "arbiter": self.most_recent_ruling_arbiter,
            "comment": self.most_recent_ruling_comment,
            "date": self.most_recent_ruling_date,
        }

    @property
    def withdrawn(self):
        exit_frames = [
            f for f in self.exp_data.values() if f.get("frameType", None) == "EXIT"
        ]
        return exit_frames[0].get("withdrawal", None) if exit_frames else None

    def generate_videos_from_events(self):
        """Creates the video containers/representations for this given response.

        We should only really invoke this as part of a migration as of right now (2/8/2019),
        but it's quite possible we'll have the need for dynamic upsertion later.
        """

        seen_ids = set()
        video_objects = []

        # Using a constructive approach here, but with an ancillary seen_ids list b/c Django models without
        # primary keys are unhashable.
        for frame_id, event_data in self.exp_data.items():
            if event_data.get("videoList", None) and event_data.get("videoId", None):
                # We've officially captured video here!
                events = event_data.get("eventTimings", [])
                for event in events:
                    video_id = event["videoId"]
                    pipe_name = event["pipeId"]  # what we call "ID" they call "name"
                    if (
                        video_id not in seen_ids
                        and pipe_name
                        and event["streamTime"] > 0
                    ):
                        # Try looking for the regular ID first.
                        file_obj = S3_RESOURCE.Object(
                            settings.BUCKET_NAME, f"{video_id}.mp4"
                        )
                        try:
                            response = file_obj.get()
                        except ClientError:
                            try:  # If that doesn't work, use the pipe name.
                                file_obj = S3_RESOURCE.Object(
                                    settings.BUCKET_NAME, f"{pipe_name}.mp4"
                                )
                                response = file_obj.get()
                            except ClientError:
                                logger.warning(
                                    f"could not find {video_id} or {pipe_name} in S3!"
                                )
                                continue
                        # Read first 32 bytes from streaming body (file header) to get actual filetype.
                        streaming_body = response["Body"]
                        file_header_buffer: bytes = streaming_body.read(32)
                        file_info = fleep.get(file_header_buffer)
                        streaming_body.close()

                        video_objects.append(
                            Video(
                                pipe_name=pipe_name,
                                created_at=date_parser.parse(event["timestamp"]),
                                date_modified=response["LastModified"],
                                #  Can't get the *actual* pipe id property, it's in the webhook payload...
                                frame_id=frame_id,
                                full_name=f"{video_id}.{file_info.extension[0]}",
                                study=self.study,
                                response=self,
                                is_consent_footage=frame_id in VALID_CONSENT_FRAMES,
                            )
                        )
                        seen_ids.add(video_id)

        return Video.objects.bulk_create(video_objects)


@receiver(post_save, sender=Response)
def take_action_on_exp_data(sender, instance, created, **kwargs):
    """Performs post-save actions based on the current frame.

    For now, this just includes deleting videos for withdrawn videos.
    """
    response = instance  # Aliasing because instance is hooked as a kwarg.

    if created or not response.sequence:
        return
    else:
        dispatch_frame_action(response)


class Feedback(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    response = models.ForeignKey(
        Response, on_delete=models.DO_NOTHING, related_name="feedback"
    )
    researcher = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    comment = models.TextField()

    def __str__(self):
        return f"<Feedback: on {self.response} by {self.researcher}>"

    class Meta:
        permissions = (("can_view_feedback", "Can View Feedback"),)

    class JSONAPIMeta:
        resource_name = "responses"
        lookup_field = "uuid"


class Log(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)

    def __str__(self):
        return f"<{self.__class__.name}: {self.action} @ {self.created_at:%c}>"

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class StudyLog(Log):
    action = models.CharField(max_length=128, db_index=True)
    extra = DateTimeAwareJSONField(null=True)
    study = models.ForeignKey(
        Study,
        on_delete=models.DO_NOTHING,
        related_name="logs",
        related_query_name="logs",
    )

    def __str__(self):
        return f"<StudyLog: {self.action} on {self.study.name} at {self.created_at} by {self.user.username}"  # noqa

    class JSONAPIMeta:
        resource_name = "study-logs"
        lookup_field = "uuid"

    class Meta:
        index_together = ("study", "action")


class ResponseLog(Log):
    action = models.CharField(max_length=128, db_index=True)
    response = models.ForeignKey(Response, on_delete=models.DO_NOTHING)

    class Meta:
        index_together = ("response", "action")

    class JSONAPIMeta:
        resource_name = "response-logs"
        lookup_field = "uuid"


class Video(models.Model):
    """Metadata abstraction to capture information on videos."""

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    date_modified = models.DateTimeField(auto_now=True)
    pipe_name = models.CharField(max_length=255, unique=True, blank=False)
    pipe_numeric_id = models.IntegerField(
        null=True
    )  # Sad that we don't keep this metadata elsewhere...
    frame_id = models.CharField(max_length=255, blank=False)
    size = models.PositiveIntegerField(null=True)
    full_name = models.CharField(
        max_length=255, blank=False, unique=True, db_index=True
    )
    study = models.ForeignKey(Study, on_delete=models.DO_NOTHING, related_name="videos")
    response = models.ForeignKey(
        Response, on_delete=models.DO_NOTHING, related_name="videos"
    )
    is_consent_footage = models.BooleanField(default=False, db_index=True)

    @classmethod
    def from_pipe_payload(cls, pipe_response_dict: dict):
        """Factory method for use in the Pipe webhook.

        Note that this is taking over previous attachment_helpers functionality, which means that it's doing the
        file renaming as well. Keeping this logic inline makes more sense because it's the only place where we do it.
        """
        data = pipe_response_dict["data"]
        old_pipe_name = f"{data['videoName']}.{data['type'].lower()}"
        new_full_name = f"{data['payload']}.{data['type'].lower()}"
        throwaway_jpg_name = f"{data['payload']}.jpg"

        # No way to directly rename in boto3, so copy and delete original (this is dumb, but let's get it working)
        try:  # Create a copy with the correct new name, if the original exists. Could also
            # wait until old_name_full exists using orig_video.wait_until_exists()
            S3_RESOURCE.Object(settings.BUCKET_NAME, new_full_name).copy_from(
                CopySource=(settings.BUCKET_NAME + "/" + old_pipe_name)
            )
        except ClientError:  # old_name_full not found!
            logger.error("Amazon S3 couldn't find the video for this Pipe ID.")
            raise
        else:  # Go on to remove the originals
            orig_video = S3_RESOURCE.Object(settings.BUCKET_NAME, old_pipe_name)
            orig_video.delete()
            # remove the .jpg thumbnail.
            S3_RESOURCE.Object(settings.BUCKET_NAME, throwaway_jpg_name).delete()

        if "PREVIEW_DATA_DISREGARD" in new_full_name:
            return (
                None
            )  # early exit, since we are not saving an object in the database.
        else:
            _, study_uuid, frame_id, response_uuid, timestamp, _ = new_full_name.split(
                "_"
            )

            # Once we've completed the renaming, we can create our nice db object.
            try:
                study = Study.objects.get(uuid=study_uuid)
            except Study.DoesNotExist as ex:
                logger.error(f"Study with uuid {study_uuid} does not exist. {ex}")
                raise

            try:
                response = Response.objects.get(uuid=response_uuid)
            except Response.DoesNotExist as ex:
                logger.error(f"Response with uuid {response_uuid} does not exist. {ex}")
                raise

            return cls.objects.create(
                pipe_name=old_pipe_name,
                pipe_numeric_id=data["id"],
                frame_id=frame_id,
                size=data["size"],
                full_name=new_full_name,
                study=study,
                response=response,
                is_consent_footage=frame_id in VALID_CONSENT_FRAMES,
            )

    @cached_property
    def filename(self):
        """Alias."""
        return self.full_name

    @cached_property
    def s3_object(self):
        return S3_RESOURCE.Object(settings.BUCKET_NAME, self.full_name)

    @cached_property
    def display_name(self):
        return f"Response({self.full_name.split('_')[3][:8]})"

    @property
    def download_url(self):
        return get_download_url(self.full_name)

    def delete(self, delete_in_s3=False, **kwargs):
        """Delete hook override."""
        super().delete(**kwargs)

        if delete_in_s3:
            delete_video_from_cloud.apply_async(
                args=(self.full_name,), countdown=60 * 60 * 24 * 7
            )  # Delete after 1 week.


class ConsentRuling(models.Model):
    """A consent ruling for a given response."""

    RULINGS = Choices(CONSENT_RULINGS)

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    action = models.CharField(max_length=100, choices=RULINGS, db_index=True)
    response = models.ForeignKey(
        Response, on_delete=models.DO_NOTHING, related_name="consent_rulings"
    )
    arbiter = models.ForeignKey(
        User, on_delete=models.DO_NOTHING, related_name="consent_rulings"
    )
    comments = models.TextField(null=True)

    class Meta:
        ordering = ["-created_at"]
        index_together = (("response", "action"), ("response", "arbiter"))

    def __str__(self):
        return f"<{self.arbiter.get_short_name()}: {self.action} {self.response} @ {self.created_at:%c}>"
