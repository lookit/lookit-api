import logging
import uuid
from datetime import datetime
from enum import Enum

import boto3
import dateutil
import fleep
import pytz
from botocore.exceptions import ClientError
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.utils.translation import gettext as _
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase
from guardian.shortcuts import get_users_with_perms
from kombu.utils import cached_property
from model_utils import Choices
from transitions import Machine

from accounts.models import Child, DemographicData, User
from attachment_helpers import get_download_url
from project import settings
from studies import workflow
from studies.helpers import FrameActionDispatcher, send_mail
from studies.permissions import (
    UMBRELLA_LAB_PERMISSION_MAP,
    LabGroup,
    LabPermission,
    SiteAdminGroup,
    StudyGroup,
    StudyPermission,
    create_groups_for_instance,
)
from studies.tasks import delete_video_from_cloud

logger = logging.getLogger(__name__)
date_parser = dateutil.parser

# Consent ruling stuff
PENDING = "pending"
ACCEPTED = "accepted"
REJECTED = "rejected"
CONSENT_RULINGS = (ACCEPTED, REJECTED, PENDING)

S3_RESOURCE = boto3.resource("s3")
S3_BUCKET = S3_RESOURCE.Bucket(settings.BUCKET_NAME)

dispatch_frame_action = FrameActionDispatcher()


def default_configuration():
    return {
        # task module should have a build_experiment method decorated as a
        # celery task that takes a study uuid
        "task_module": "studies.tasks",
        "metadata": {
            # defines the default metadata fields for that type of study
            "fields": {
                "player_repo_url": settings.EMBER_EXP_PLAYER_REPO,
                "last_known_player_sha": None,
            }
        },
    }


class Lab(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True)
    name = models.CharField(
        max_length=255, unique=True, blank=False, verbose_name="Lab Name"
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
        null=True,
        default=None,
        verbose_name="Custom URL",
        help_text="A unique URL (slug) that will show discoverable, active studies for this lab "
        "only, e.g. https://lookit.mit.edu/studies/my-lab-name",
    )
    institution = models.CharField(max_length=255, blank=True)
    principal_investigator_name = models.CharField(max_length=255, blank=False)
    contact_email = models.EmailField(
        unique=True,
        verbose_name="Contact Email",
        help_text="This will be the reply-to address when you contact participants, so make sure "
        "it is a monitored address or list that lab members can access.",
    )
    contact_phone = models.CharField(max_length=255, verbose_name="Contact Phone")
    lab_website = models.URLField(
        blank=True,
        verbose_name="Lab Website",
        help_text="A link to an external website, such as your university lab page",
    )
    description = models.TextField(
        blank=False,
        help_text="A short (2-3 sentences), parent-facing description of what "
        "your lab studies or other information of interest to families.",
    )
    irb_contact_info = models.TextField(
        blank=False,
        verbose_name="IRB contact info",
        help_text="A statement about what organization conducts ethical review of your research, "
        "and contact information for that organization. E.g., 'All of our Lookit studies are "
        "approved by MIT's Committee on the Use of Humans as Experimental Subjects (COUHES), "
        "[address], phone: [phone], email: [email].",
    )
    approved_to_test = models.BooleanField(default=False)
    # The related_name convention seems silly, but django complains about reverse
    # accessor clashes if these aren't unique :/ regardless, we won't be using
    # the reverse accessors much so it doesn't really matter.
    guest_group = models.OneToOneField(
        Group, related_name="lab_for_guests", on_delete=models.SET_NULL, null=True
    )
    readonly_group = models.OneToOneField(
        Group, related_name="lab_for_readonly", on_delete=models.SET_NULL, null=True
    )
    member_group = models.OneToOneField(
        Group, related_name="lab_for_members", on_delete=models.SET_NULL, null=True
    )
    admin_group = models.OneToOneField(
        Group, related_name="lab_to_administer", on_delete=models.SET_NULL, null=True
    )
    researchers = models.ManyToManyField(
        "accounts.User",
        blank=True,
        help_text=_(
            "The Users who belong to this Lab. A user in this lab will be able to create "
            "studies associated with this Lab and can be added to this Lab's studies."
        ),
        related_name="labs",
        related_query_name="lab",  # User.objects.filter(lab=...)
    )
    requested_researchers = models.ManyToManyField(
        "accounts.User",
        blank=True,
        help_text=_("The Users who have requested to join this Lab."),
        related_name="requested_labs",
        related_query_name="requested_lab",  # User.objects.filter(requested_lab=...)
    )

    class Meta:
        permissions = LabPermission
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.principal_investigator_name}, {self.institution})"


# Using Direct foreign keys for guardian, see:
# https://django-guardian.readthedocs.io/en/stable/userguide/performance.html
class LabUserObjectPermission(UserObjectPermissionBase):
    content_object = models.ForeignKey(Lab, on_delete=models.CASCADE)


class LabGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(Lab, on_delete=models.CASCADE)


@receiver(post_save, sender=User)
def add_researcher_to_labs(sender, **kwargs):
    """
    Add researchers to default labs upon initial creation. Note will need to add researchers
    to labs if turning a participant account into a researcher account.
    """
    user, created = (kwargs["instance"], kwargs["created"])
    # Note: if new researcher creation will involve setting saving first,
    # # then editing, will need to add groups at that point too.
    if user.is_researcher and created:
        if Lab.objects.filter(name="Demo lab").exists():
            demo_lab = Lab.objects.get(name="Demo lab")
            demo_lab.researchers.add(user)
            demo_lab.readonly_group.user_set.add(user)
            demo_lab.save()
        if Lab.objects.filter(name="Sandbox lab").exists():
            sandbox_lab = Lab.objects.get(name="Sandbox lab")
            sandbox_lab.researchers.add(user)
            sandbox_lab.guest_group.user_set.add(user)
            sandbox_lab.save()


@receiver(post_save, sender=Lab)
def lab_post_save(sender, **kwargs):
    """
    Create groups for all newly created Lab instances.
    We only run on Lab creation to avoid having to check
    existence on each call to Lab.save.
    """
    lab, created = kwargs["instance"], kwargs["created"]

    if created:
        create_groups_for_instance(
            lab, LabGroup, Group, Permission, LabGroupObjectPermission
        )


@receiver(pre_save, sender=Lab)
def notify_lab_of_approval(sender, instance, **kwargs):
    """
    If lab is approved, email the lab admins to let them know.
    """
    lab_in_db = Lab.objects.filter(pk=instance.id).first()
    if not lab_in_db:
        return
    if (not lab_in_db.approved_to_test) and instance.approved_to_test:
        context = {"lab_name": instance.name, "lab_id": instance.pk}
        send_mail.delay(
            "notify_lab_admins_of_approval",
            "Lab Approval Notification",
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(instance.admin_group.user_set.values_list("username", flat=True)),
            **context,
        )


class StudyTypeEnum(Enum):
    external = "External"
    ember_frame_player = "Ember Frame Player (default)"


class StudyType(models.Model):
    name = models.CharField(max_length=255, blank=False, null=False)
    configuration = models.JSONField(default=default_configuration)

    def __str__(self):
        return self.name

    @classmethod
    def default_pk(cls):
        return cls.objects.get(name=StudyTypeEnum.ember_frame_player.value).pk

    @property
    def is_ember_frame_player(self):
        return self.name == StudyTypeEnum.ember_frame_player.value

    @property
    def is_external(self):
        return self.name == StudyTypeEnum.external.value

    @classmethod
    def get_ember_frame_player(cls):
        return cls.objects.get(name=StudyTypeEnum.ember_frame_player.value)

    @classmethod
    def get_external(cls):
        return cls.objects.get(name=StudyTypeEnum.external.value)


def default_study_structure():
    return {"frames": {}, "sequence": []}


class Study(models.Model):

    MONITORING_FIELDS = [
        "structure",
        "generator",
        "use_generator",
        "name",
        "short_description",
        "purpose",
        "duration",
        "contact_info",
        "image",
        "exit_url",
        "metadata",
        "study_type",
        "compensation_description",
        "lab",
    ]

    DAY_CHOICES = [(i, i) for i in range(0, 32)]
    MONTH_CHOICES = [(i, i) for i in range(0, 12)]
    YEAR_CHOICES = [(i, i) for i in range(0, 19)]
    salt = models.UUIDField(default=uuid.uuid4, unique=True)
    hash_digits = models.IntegerField(default=6)
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=False, null=False, db_index=True)
    date_modified = models.DateTimeField(auto_now=True)
    preview_summary = models.CharField(max_length=500, default="")
    short_description = models.TextField()
    purpose = models.TextField()
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
    exit_url = models.URLField(default="https://lookit.mit.edu/studies/history/")
    comments = models.TextField(blank=True, null=True)
    study_type = models.ForeignKey(
        "StudyType",
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        verbose_name="type",
    )
    lab = models.ForeignKey(
        Lab,
        on_delete=models.PROTECT,  # don't allow deleting lab without moving out studies. Could also switch to a default lab.
        related_name="studies",
        related_query_name="study",
        null=True,
    )
    structure = models.JSONField(default=default_study_structure)
    use_generator = models.BooleanField(default=False)
    generator = models.TextField(default="")
    display_full_screen = models.BooleanField(default=True)
    state = models.CharField(
        choices=workflow.STATE_CHOICES,
        max_length=25,
        default=workflow.STATE_CHOICES.created,
        db_index=True,
    )
    public = models.BooleanField(default=False)
    shared_preview = models.BooleanField(default=False)
    creator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    metadata = models.JSONField(default=dict)
    built = models.BooleanField(default=False)
    is_building = models.BooleanField(default=False)
    compensation_description = models.TextField(blank=True)
    criteria_expression = models.TextField(blank=True)

    # Groups
    # The related_name convention seems silly, but django complains about reverse
    # accessor clashes if these aren't unique :/ regardless, we won't be using
    # the reverse accessors much so it doesn't really matter.
    preview_group = models.OneToOneField(
        Group, related_name="study_to_preview", on_delete=models.SET_NULL, null=True
    )
    design_group = models.OneToOneField(
        Group, related_name="study_to_design", on_delete=models.SET_NULL, null=True
    )
    analysis_group = models.OneToOneField(
        Group, related_name="study_for_analysis", on_delete=models.SET_NULL, null=True
    )
    submission_processor_group = models.OneToOneField(
        Group,
        related_name="study_for_submission_processing",
        on_delete=models.SET_NULL,
        null=True,
    )
    researcher_group = models.OneToOneField(
        Group, related_name="study_for_research", on_delete=models.SET_NULL, null=True
    )
    manager_group = models.OneToOneField(
        Group, related_name="study_to_manage", on_delete=models.SET_NULL, null=True
    )
    admin_group = models.OneToOneField(
        Group, related_name="study_to_administer", on_delete=models.SET_NULL, null=True
    )

    def all_study_groups(self):
        """Returns a list of all the groups that grant permissions on this study"""
        return [
            self.preview_group,
            self.design_group,
            self.analysis_group,
            self.submission_processor_group,
            self.researcher_group,
            self.manager_group,
            self.admin_group,
        ]

    def get_group_of_researcher(self, user):
        """Returns label for the highest-level group the researcher is in for this study, or None if not in any study groups"""
        user_groups = user.groups.all()
        if self.admin_group in user_groups:
            return "Admin"
        if self.manager_group in user_groups:
            return "Manager"
        if self.researcher_group in user_groups:
            return "Researcher"
        if self.submission_processor_group in user_groups:
            return "Submission Processor"
        if self.analysis_group in user_groups:
            return "Analysis"
        if self.design_group in user_groups:
            return "Design"
        if self.preview_group in user_groups:
            return "Preview"
        return None

    def __init__(self, *args, **kwargs):

        super(Study, self).__init__(*args, **kwargs)
        self.machine = Machine(
            self,
            states=workflow.states,
            transitions=workflow.transitions,
            initial=self.state,
            send_event=True,
            after_state_change="_finalize_state_change",
        )

    def __str__(self):
        return f"<Study: {self.name} ({self.uuid})>"

    class Meta:
        permissions = StudyPermission
        ordering = ["name"]

    class JSONAPIMeta:
        resource_name = "studies"
        lookup_field = "uuid"

    def users_with_study_perms(self, study_perm: StudyPermission):
        users_with_perms = get_users_with_perms(
            self, only_with_perms_in=[study_perm.codename]
        )
        if self.lab and study_perm in UMBRELLA_LAB_PERMISSION_MAP:
            umbrella_lab_perm = UMBRELLA_LAB_PERMISSION_MAP.get(study_perm)
            users_with_perms = users_with_perms.union(
                get_users_with_perms(
                    self.lab, only_with_perms_in=[umbrella_lab_perm.codename]
                )
            )
        return users_with_perms

    @cached_property
    def begin_date(self):
        try:
            return self.logs.filter(action="active").first().created_at
        except AttributeError:
            return None

    @property
    def participants(self):
        """Get all participants for the given study."""
        participants = self.responses.values_list("child__user", flat=True)
        return User.objects.filter(pk__in=participants)

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

    def responses_for_researcher(self, user):
        """Return all responses to this study that the researcher has access to read"""

        if self.study_type.is_external:
            responses = self.responses
        else:
            responses = self.consented_responses

        responses = responses.filter(study_type=self.study_type)

        if not user.has_study_perms(StudyPermission.READ_STUDY_RESPONSE_DATA, self):
            responses = responses.filter(is_preview=True)
        if not user.has_study_perms(StudyPermission.READ_STUDY_PREVIEW_DATA, self):
            responses = responses.filter(is_preview=False)
        return responses

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
    def needs_to_be_built(self):
        return self.study_type.is_ember_frame_player and not self.built

    @property
    def expressed_interest_count(self) -> int:
        """Return the number of responses that aren't previews.  This is interpreted as "expressed
        interest".

        Returns:
            int: Count of responses
        """
        return self.responses.filter(is_preview=False).count()

    @property
    def show_videos(self):
        return self.study_type.is_ember_frame_player

    @property
    def show_frame_data(self):
        return self.study_type.is_ember_frame_player

    @property
    def show_consent(self):
        return self.study_type.is_ember_frame_player

    @property
    def show_responses(self):
        return self.study_type.is_ember_frame_player

    @property
    def show_build_experiment_runner(self):
        return self.study_type.is_ember_frame_player

    @property
    def show_expressed_interest(self):
        return self.study_type.is_external

    @property
    def show_scheduled(self):
        return self.study_type.is_external and self.metadata["scheduled"]

    # WORKFLOW CALLBACKS

    def clone(self):
        """Create a new, unsaved copy of the study."""
        copy = self.__class__.objects.get(pk=self.pk)
        copy.id = None
        copy.salt = uuid.uuid4()
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
            "lab_name": self.lab.name,
            "study_name": self.name,
            "study_id": self.pk,
            "study_uuid": str(self.uuid),
            "researcher_name": ev.kwargs.get("user").get_short_name(),
            "action": ev.transition.dest,
            "comments": self.comments,
        }
        send_mail.delay(
            "notify_admins_of_study_action",
            "Study Submission Notification",
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(
                Group.objects.get(
                    name=SiteAdminGroup.LOOKIT_ADMIN.name
                ).user_set.values_list("username", flat=True)
            ),
            reply_to=[ev.kwargs.get("user").username],
            **context,
        )

    def notify_submitter_of_approval(self, ev):

        context = {
            "study_name": self.name,
            "study_id": self.pk,
            "approved": True,
            "comments": self.comments,
        }
        send_mail.delay(
            "notify_researchers_of_approval_decision",
            "{} Approval Notification".format(self.name),
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(
                self.users_with_study_perms(
                    StudyPermission.CHANGE_STUDY_STATUS
                ).values_list("username", flat=True)
            ),
            **context,
        )

    def notify_submitter_of_rejection(self, ev):
        context = {
            "study_name": self.name,
            "study_id": self.pk,
            "approved": False,
            "comments": self.comments,
        }
        send_mail.delay(
            "notify_researchers_of_approval_decision",
            "{}: Changes requested notification".format(self.name),
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(
                self.users_with_study_perms(
                    StudyPermission.CHANGE_STUDY_STATUS
                ).values_list("username", flat=True)
            ),
            **context,
        )

    def notify_submitter_of_recission(self, ev):
        context = {"study_name": self.name}
        send_mail.delay(
            "notify_researchers_of_approval_rescission",
            "{} Rescinded Notification".format(self.name),
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(
                self.users_with_study_perms(
                    StudyPermission.CHANGE_STUDY_STATUS
                ).values_list("username", flat=True)
            ),
            **context,
        )

    def notify_administrators_of_retraction(self, ev):
        context = {
            "lab_name": self.lab.name,
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
                Group.objects.get(
                    name=SiteAdminGroup.LOOKIT_ADMIN.name
                ).user_set.values_list("username", flat=True)
            ),
            **context,
        )

    def check_if_built(self, ev):
        """Check if study is built.

        :param ev: The event object
        :type ev: transitions.core.EventData
        :raise: RuntimeError
        """
        if self.needs_to_be_built:
            raise RuntimeError(
                f'Cannot activate study - experiment runner for "{self.name}" ({self.id}) has not been built!'
            )

    def notify_administrators_of_activation(self, ev):
        context = {
            "lab_name": self.lab.name,
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
                Group.objects.get(
                    name=SiteAdminGroup.LOOKIT_ADMIN.name
                ).user_set.values_list("username", flat=True)
            ),
            **context,
        )

    def notify_administrators_of_pause(self, ev):
        context = {
            "lab_name": self.lab.name,
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
                Group.objects.get(
                    name=SiteAdminGroup.LOOKIT_ADMIN.name
                ).user_set.values_list("username", flat=True)
            ),
            **context,
        )

    def notify_administrators_of_deactivation(self, ev):
        context = {
            "lab_name": self.lab.name,
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
                Group.objects.get(
                    name=SiteAdminGroup.LOOKIT_ADMIN.name
                ).user_set.values_list("username", flat=True)
            ),
            **context,
        )

    # Runs for every transition to log action
    def _log_action(self, ev):
        StudyLog.objects.create(
            action=ev.state.name,
            study=ev.model,
            user=ev.kwargs.get("user"),
            extra={"comments": ev.model.comments},
        )

    # Runs for every transition to save state and log action
    def _finalize_state_change(self, ev):
        ev.model.save()
        self._log_action(ev)

    def columns_included_in_summary(self):
        if self.study_type.is_ember_frame_player:
            return [
                "response__id",
                "response__uuid",
                "response__date_created",
                "response__completed",
                "response__withdrawn",
                "response__parent_feedback",
                "response__birthdate_difference",
                "response__video_privacy",
                "response__databrary",
                "response__is_preview",
                "response__sequence",
                "participant__global_id",
                "participant__hashed_id",
                "participant__nickname",
                "child__global_id",
                "child__hashed_id",
                "child__name",
                "child__age_rounded",
                "child__gender",
                "child__age_at_birth",
                "child__language_list",
                "child__condition_list",
                "child__additional_information",
            ]
        if self.study_type.is_external:
            return [
                "response__id",
                "response__uuid",
                "response__date_created",
                "response__parent_feedback",
                "response__birthdate_difference",
                "response__databrary",
                "response__is_preview",
                "participant__global_id",
                "participant__hashed_id",
                "participant__nickname",
                "child__global_id",
                "child__hashed_id",
                "child__name",
                "child__age_rounded",
                "child__gender",
                "child__age_at_birth",
                "child__language_list",
                "child__condition_list",
                "child__additional_information",
            ]


# Using Direct foreign keys for guardian, see:
# https://django-guardian.readthedocs.io/en/stable/userguide/performance.html
# Opting not to use "enabled" feature and just to load custom perms directly.
class StudyUserObjectPermission(UserObjectPermissionBase):
    content_object = models.ForeignKey(Study, on_delete=models.CASCADE)


class StudyGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(Study, on_delete=models.CASCADE)


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

    # Special treatment for metadata and structure fields which may have superficial
    # changes that shouldn't be treated as actual changes
    important_fields_changed = False
    for field, (current, new) in field_transitions.items():
        if (
            field == "metadata"
            and build_changed_metadata
            and not current.get("last_known_player_sha", None)
        ):
            continue  # Skip, since we're technically just encoding the most recent SHA.
        if (
            field == "structure"
            and current.get("frames") == new.get("frames")
            and current.get("sequence") == new.get("sequence")
        ):
            continue  # Skip, since the actual JSON content is the same - only exact_text changing
        if new != current:
            important_fields_changed = True
            break

    if instance.state in approved_states and important_fields_changed:
        instance.state = "rejected"
        instance.comments = "Your study has been modified following approval.  You must resubmit this study to get it approved again."
        # Don't store a user because it's confusing unless that person is actually the one who made the change,
        # and we don't have access to who made the change from this signal.
        StudyLog.objects.create(action="rejected", study=instance)


@receiver(post_save, sender=Study)
def create_study_groups(sender, **kwargs):
    """
    Create groups for newly created Study instances. We only
    run on study creation to avoid having to check for existence
    on each call to Study.save.
    """
    study, created = kwargs["instance"], kwargs["created"]
    if created:
        create_groups_for_instance(
            study, StudyGroup, Group, Permission, StudyGroupObjectPermission
        )


@receiver(pre_save, sender=Study)
def remove_old_lab_researchers(sender, instance, **kwargs):
    """
    If changing the lab of a study, remove any researchers who are not in the
    new lab from all study access groups.
    """
    study_in_db = Study.objects.filter(pk=instance.id).first()
    if not study_in_db:
        return
    old_lab = study_in_db.lab
    # When cloning, fks have been emptied so there's no previous lab
    if old_lab:
        new_lab = instance.lab
        if old_lab.pk != new_lab.pk:
            new_lab_researchers = new_lab.researchers.all()
            for group in instance.all_study_groups():
                for user in group.user_set.all():
                    if user not in new_lab_researchers:
                        group.user_set.remove(user)


class ResponseApiManager(models.Manager):
    """Overrides to enable the display name."""

    def get_queryset(self):
        return super().get_queryset().select_related("child", "child__user")


class Response(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    study = models.ForeignKey(
        Study, on_delete=models.PROTECT, related_name="responses"
    )  # Integrity constraints will also prevent deleting study that has responses
    completed = models.BooleanField(default=False)
    completed_consent_frame = models.BooleanField(default=False)
    exp_data = models.JSONField(default=dict)
    conditions = models.JSONField(default=dict)
    sequence = ArrayField(models.CharField(max_length=128), blank=True, default=list)
    date_modified = models.DateTimeField(auto_now=True)
    date_created = models.DateTimeField(auto_now_add=True)
    global_event_timings = models.JSONField(default=dict)
    # For now, don't allow deleting Child still associated with responses. If we need to
    # delete all data on parent request, delete the associated responses manually. May want
    # to be able to keep some minimal info about those responses though (e.g. #, # unique
    # users they came from).
    child = models.ForeignKey(Child, on_delete=models.PROTECT)
    is_preview = models.BooleanField(default=False)
    demographic_snapshot = models.ForeignKey(
        DemographicData, on_delete=models.SET_NULL, null=True
    )  # Allow deleting a demographic snapshot even though a response points to it
    objects = models.Manager()
    related_manager = ResponseApiManager()
    study_type = models.ForeignKey(
        StudyType, on_delete=models.PROTECT, default=StudyType.default_pk
    )

    def __str__(self):
        return self.display_name

    class Meta:
        permissions = (
            (
                "view_all_response_data_in_analytics",
                "View all response data in analytics",
            ),
        )
        base_manager_name = "related_manager"

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

    def exit_frame_properties(self, property):
        exit_frame_values = [
            f.get(property, None)
            for f in self.exp_data.values()
            if f.get("frameType", None) == "EXIT"
        ]
        if exit_frame_values and exit_frame_values != [None]:
            return exit_frame_values[-1]
        else:
            return None

    @property
    def withdrawn(self):
        return bool(self.exit_frame_properties("withdrawal"))

    @property
    def databrary(self):
        return self.exit_frame_properties("databraryShare")

    @property
    def privacy(self):
        return self.exit_frame_properties("useOfMedia")

    @property
    def parent_feedback(self):
        return self.exit_frame_properties("feedback")

    @property
    def birthdate_difference(self):
        """Difference between birthdate on exit survey (if any) and registered child's birthday."""
        exit_survey_birthdate = self.exit_frame_properties("birthDate")
        registered_birthdate = self.child.birthday
        if exit_survey_birthdate and registered_birthdate:
            try:
                return (
                    datetime.strptime(exit_survey_birthdate[:10], "%Y-%m-%d").date()
                    - self.child.birthday
                ).days
            except (ValueError, TypeError):
                return None
        else:
            return None

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
                                is_consent_footage=event_data.get("frameType", None)
                                == "CONSENT",
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


class FeedbackApiManager(models.Manager):
    """Prefetch all the things."""

    def get_queryset(self):
        """Prefetch things that matter."""
        return (
            super()
            .get_queryset()
            .select_related("researcher")
            .prefetch_related(
                models.Prefetch(
                    "response",
                    queryset=Response.objects.select_related("child", "child__user"),
                )
            )
        )


class Feedback(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    response = models.ForeignKey(
        Response, on_delete=models.CASCADE, related_name="feedback"
    )  # When deleting a Response, also delete any associated feedback
    researcher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    comment = models.TextField()

    objects = models.Manager()  # Set a default
    related_manager = FeedbackApiManager()

    def __str__(self):
        return f"<Feedback: on {self.response} by {self.researcher}>"

    class Meta:
        permissions = (("can_view_feedback", "Can View Feedback"),)
        base_manager_name = "related_manager"

    class JSONAPIMeta:
        resource_name = "responses"
        lookup_field = "uuid"


class Log(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"<{self.__class__.name}: {self.action} @ {self.created_at:%c}>"

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class StudyLog(Log):
    action = models.CharField(max_length=128, db_index=True)
    extra = models.JSONField(null=True)
    study = models.ForeignKey(
        Study,
        on_delete=models.CASCADE,  # If a study is deleted, delete its logs also
        related_name="logs",
        related_query_name="logs",
    )

    def __str__(self):
        return f"<StudyLog: {self.action} on {self.study.name} at {self.created_at}"  # noqa

    class JSONAPIMeta:
        resource_name = "study-logs"
        lookup_field = "uuid"

    class Meta:
        index_together = ("study", "action")


class ResponseLog(Log):
    """Unused class, keeping for migrations only."""

    action = models.CharField(max_length=128, db_index=True)
    # if deleting Response, also delete its logs
    response = models.ForeignKey(Response, on_delete=models.CASCADE)

    class Meta:
        index_together = ("response", "action")

    class JSONAPIMeta:
        resource_name = "response-logs"
        lookup_field = "uuid"


class Video(models.Model):
    """Metadata abstraction to capture information on videos."""

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    s3_timestamp = models.DateTimeField()
    pipe_name = models.CharField(max_length=255, unique=True, blank=False)
    pipe_numeric_id = models.IntegerField(
        null=True
    )  # Sad that we don't keep this metadata elsewhere...
    frame_id = models.CharField(max_length=255, blank=False)
    full_name = models.CharField(
        max_length=255, blank=False, unique=True, db_index=True
    )
    study = models.ForeignKey(Study, on_delete=models.PROTECT, related_name="videos")
    response = models.ForeignKey(
        Response, on_delete=models.CASCADE, related_name="videos"
    )  # If a response is deleted, also delete related videos
    is_consent_footage = models.BooleanField(default=False, db_index=True)

    @classmethod
    def check_and_parse_pipe_payload(cls, pipe_payload: str):
        """Confirm that pipe payload is in expected format and extract study, response, etc."""
        consent_type_label = "consent-"
        marked_as_consent = pipe_payload.startswith(consent_type_label)
        if marked_as_consent:
            pipe_payload = pipe_payload[len(consent_type_label) :]

        try:
            _, study_uuid, frame_id, response_uuid, timestamp, _ = pipe_payload.split(
                "_"
            )
        except ValueError:
            logger.error(
                f"Could not parse video filename {pipe_payload} to extract study and response"
            )
            raise

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

        return marked_as_consent, pipe_payload, study, frame_id, response, timestamp

    @classmethod
    def from_pipe_payload(cls, pipe_response_dict: dict):
        """Factory method for use in the Pipe webhook.

        Note that this is taking over previous attachment_helpers functionality, which means that it's doing the
        file renaming as well. Keeping this logic inline makes more sense because it's the only place where we do it.
        """

        data = pipe_response_dict["data"]

        # Confirm payload is in expected format and references real study, response - errors if not and will not rename
        (
            marked_as_consent,
            pipe_payload,
            study,
            frame_id,
            response,
            timestamp,
        ) = cls.check_and_parse_pipe_payload(data["payload"])

        old_pipe_name = f"{data['videoName']}.{data['type'].lower()}"
        new_full_name = f"{pipe_payload}.{data['type'].lower()}"
        throwaway_jpg_name = f"{data['videoName']}.jpg"

        # No way to directly rename in boto3, so copy and delete original (this is dumb, but let's get it working)
        try:  # Create a copy with the correct new name, if the original exists. Could also
            # wait until old_name_full exists using orig_video.wait_until_exists()
            S3_RESOURCE.Object(settings.BUCKET_NAME, new_full_name).copy_from(
                CopySource=(settings.BUCKET_NAME + "/" + old_pipe_name)
            )
        except ClientError:  # old_name_full not found!
            logger.error(
                f"Amazon S3 couldn't find the video for Pipe ID {old_pipe_name} in bucket {settings.BUCKET_NAME}"
            )
            raise
        else:  # Go on to remove the originals
            orig_video = S3_RESOURCE.Object(settings.BUCKET_NAME, old_pipe_name)
            orig_video.delete()
            # remove the .jpg thumbnail.
            S3_RESOURCE.Object(settings.BUCKET_NAME, throwaway_jpg_name).delete()

        # Determine whether this is consent footage based on payload and/or response data.
        # TODO: move to only using payload info about whether this is consent footage. We only have frame data in
        # exp_data once that's saved to the db after completing the frame, whereas the video may be uploaded sooner
        # (especially for consent videos which are reviewed by the participant). To avoid this race condition newer
        # versions of the frameplayer send a payload marked 'consent-<videoname>' for consent videos. See
        # https://github.com/lookit/lookit-api/issues/598. However, we don't want to remove the check for frameType
        # before everyone's using a recent version of the frameplayer that marks consent footage in the payload,
        # as then NOTHING would get marked as consent footage in those studies - whereas the current solution works
        # >95% of the time.
        is_consent_footage = (
            marked_as_consent
            or response.exp_data.get(frame_id, {}).get("frameType", "") == "CONSENT"
        )

        # Once we've completed the renaming, create our db object referencing it
        return cls.objects.create(
            pipe_name=old_pipe_name,
            pipe_numeric_id=data["id"],
            s3_timestamp=datetime.fromtimestamp(int(timestamp) / 1000, tz=pytz.utc),
            frame_id=frame_id,
            full_name=new_full_name,
            study=study,
            response=response,
            is_consent_footage=is_consent_footage,
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


@receiver(pre_delete, sender=Video)
def delete_video_on_s3(sender, instance, using, **kwargs):
    """Delete video from S3 when deleting Video object.

    Do this in a pre_delete hook rather than a custom delete function because this will
    be called when cascading deletion from responses."""
    delete_video_from_cloud.apply_async(
        args=(instance.full_name,), countdown=60 * 60 * 24 * 7
    )  # Delete after 1 week.


class ConsentRuling(models.Model):
    """A consent ruling for a given response."""

    RULINGS = Choices(*CONSENT_RULINGS)

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    action = models.CharField(max_length=100, choices=RULINGS, db_index=True)
    response = models.ForeignKey(
        Response, on_delete=models.CASCADE, related_name="consent_rulings"
    )  # If a response is deleted, also delete related consent rulings.
    arbiter = models.ForeignKey(
        User, on_delete=models.SET_NULL, related_name="consent_rulings", null=True
    )  # If a user is deleted, keep their previous consent rulings
    comments = models.TextField(null=True)

    class Meta:
        ordering = ["-created_at"]
        index_together = (("response", "action"), ("response", "arbiter"))

    def __str__(self):
        return f"<{self.arbiter.get_short_name()}: {self.action} {self.response} @ {self.created_at:%c}>"
