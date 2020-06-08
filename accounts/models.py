import base64
import hashlib
import uuid

import pydenticon
from bitfield import BitField
from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import Group, Permission, PermissionsMixin
from django.contrib.postgres.fields.array import ArrayField
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import get_template
from django.utils.html import mark_safe
from django.utils.text import slugify
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django_countries.fields import CountryField
from guardian.mixins import GuardianUserMixin
from guardian.shortcuts import assign_perm, get_objects_for_user
from kombu.utils import cached_property
from localflavor.us.models import USStateField
from localflavor.us.us_states import USPS_CHOICES
from model_utils import Choices
from multiselectfield import MultiSelectField

from accounts.queries import BitfieldQuerySet
from project.fields.datetime_aware_jsonfield import DateTimeAwareJSONField
from project.settings import EMAIL_FROM_ADDRESS
from studies.fields import CONDITIONS, GESTATIONAL_AGE_CHOICES, LANGUAGES
from studies.helpers import send_mail
from studies.permissions import (
    UMBRELLA_LAB_PERMISSION_MAP,
    StudyPermission,
    LabPermission,
)


class UserManager(BaseUserManager):
    def create_user(self, username, password=None):
        if not username:
            raise ValueError("Users must have a username")

        user = self.model(username=self.normalize_email(username), is_active=True)

        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password):
        user = self.create_user(username, password=password)
        user.is_superuser = True
        user.is_staff = True
        user.is_active = True
        user.save(using=self._db)
        return user


class Organization(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=False, null=False, db_index=True)
    url = models.URLField(verbose_name="Website")

    def __str__(self):
        return f"<Organization: {self.name}>"

    class Meta:
        permissions = (
            ("can_view_organization", _("Can View Organization")),
            ("can_edit_organization", _("Can Edit Organization")),
            ("can_create_organization", _("Can Create Organization")),
            ("can_remove_organization", _("Can Remove Organization")),
            ("can_view_experimenter", _("Can View Experimenter")),
            ("can_view_analytics", _("Can View Analytics")),
        )
        ordering = ["name"]


class User(AbstractBaseUser, PermissionsMixin, GuardianUserMixin):
    USERNAME_FIELD = EMAIL_FIELD = "username"
    uuid = models.UUIDField(
        verbose_name="identifier", default=uuid.uuid4, unique=True, db_index=True
    )
    former_lookit_id = models.CharField(max_length=255, blank=True)
    linked_former_lookit_ids = ArrayField(
        models.CharField(max_length=255), blank=True, default=list
    )
    username = models.EmailField(
        unique=True, verbose_name="Email address", db_index=True
    )
    given_name = models.CharField(max_length=255, blank=True)
    middle_name = models.CharField(max_length=255, blank=True)
    family_name = models.CharField(max_length=255)
    nickname = models.CharField(max_length=255, blank=True)
    _identicon = models.TextField(verbose_name="identicon")
    time_zone = models.CharField(max_length=255)
    locale = models.CharField(max_length=255)

    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_researcher = models.BooleanField(default=False)

    email_next_session = models.BooleanField(default=True)
    email_new_studies = models.BooleanField(default=True)
    email_study_updates = models.BooleanField(default=True)
    email_response_questions = models.BooleanField(default=True)

    date_created = models.DateTimeField(auto_now_add=True)

    def __init__(self, *args, **kwargs):
        super(User, self).__init__(*args, **kwargs)
        if self.id:
            setattr(self, f"__original_groups", self.groups.all())

    @cached_property
    def osf_profile_url(self):
        try:
            return self.socialaccount_set.first().extra_data["data"]["links"]["html"]
        except AttributeError:
            return "#"

    @property
    def identicon(self):
        if not self._identicon:
            rbw = self._make_rainbow()
            generator = pydenticon.Generator(
                5, 5, digest=hashlib.sha512, foreground=rbw, background="rgba(0,0,0,0)"
            )
            png = generator.generate(str(self.uuid), 64, 64)
            b64_png = base64.b64encode(png)
            self._identicon = f"data:image/png;base64,{b64_png.decode()}"
            self.save()
        return self._identicon

    @property
    def latest_demographics(self):
        return self.demographics.first()

    @property
    def identicon_small_html(self):
        return mark_safe(f'<img src="{str(self.identicon)}" width="18" />')

    @property
    def identicon_html(self):
        return mark_safe(f'<img src="{str(self.identicon)}" width="64" />')

    @cached_property
    def is_participant(self):
        return self.demographics.exists()

    @property
    def studies(self):  # TODO remove??
        if not self.is_participant:
            return get_objects_for_user(
                self, ["studies.can_view_study", "studies.can_edit_study"]
            )
        return None

    @property
    def display_permission(self):  # TODO
        if self.is_org_admin:
            return "Organization Admin"
        elif self.is_org_read:
            return "Organization Read"
        elif self.is_org_researcher:
            return "Researcher"
        else:
            return "No organization groups"

    @property
    def slug(self):
        """Temporary workaround."""
        return f"{slugify(self.nickname or 'anonymous')}-{str(self.uuid).split('-')[0]}"

    def _make_rainbow(self):
        rbw = []
        for i in range(0, 255, 10):
            for j in range(0, 255, 10):
                for k in range(0, 255, 10):
                    rbw.append(f"rgb({i},{j},{k})")
        return rbw

    def has_study_perms(self, study_perm: StudyPermission, study) -> bool:
        # 1) Modeled perm should be passed already
        has_study_perm = self.has_perm(study_perm.codename, study)
        if has_study_perm:
            return True
        else:
            umbrella_lab_perm = UMBRELLA_LAB_PERMISSION_MAP.get(study_perm)
            lab = study.lab
            if lab:
                return self.has_perm(umbrella_lab_perm.codename, study.lab)
            else:
                return False

    def studies_for_perm(self, study_perm: StudyPermission):
        from studies.models import Study, Lab

        specifically_granted_studies = get_objects_for_user(
            self, study_perm.codename, klass=Study
        )

        umbrella_lab_perm = UMBRELLA_LAB_PERMISSION_MAP.get(study_perm)
        labs_with_labwide_perms = get_objects_for_user(
            self, umbrella_lab_perm.codename, klass=Lab
        )
        lab_granted_studies = Study.objects.filter(lab__in=labs_with_labwide_perms)

        return specifically_granted_studies.union(lab_granted_studies)

    def can_create_study(self):
        return any(
            [
                self.has_perm(
                    LabPermission.CREATE_LAB_ASSOCIATED_STUDY.codename, obj=lab
                )
                for lab in self.labs.all()
            ]
        )

    def has_any_perms(self, perm_list, obj=None):
        """
        Returns True if the user has ANY of the specified permissions. If
        object is passed, it checks if the user has any required perms for this
        object.
        """
        return any(self.has_perm(perm, obj) for perm in perm_list)

    def get_short_name(self):
        return f"{self.given_name} {self.family_name}"

    def get_full_name(self):
        return f"{self.given_name} {self.middle_name} {self.family_name}"

    def __str__(self):
        return f"<User: ID {self.id}, {self.uuid}>"

    objects = UserManager()

    class JSONAPIMeta:
        resource_name = "users"
        lookup_field = "uuid"

    class Meta:
        permissions = (
            ("can_create_users", _("Can Create User")),
            ("can_view_users", _("Can View User")),
            ("can_edit_users", _("Can Edit User")),
            ("can_remove_users", _("Can Remove User")),
            ("can_view_user_permissions", _("Can View User Permissions")),
            ("can_edit_user_permissions", _("Can Edit User Permissions")),
            ("can_read_all_user_data", _("Can Read All User Data")),
            ("can_read_usernames", _("Can Read User Usernames")),
        )
        ordering = ["id"]


class Child(models.Model):
    GENDER_CHOICES = Choices(
        ("m", _("male")),
        ("f", _("female")),
        ("o", _("other")),
        ("na", _("prefer not to answer")),
    )

    # Deprecating
    AGE_AT_BIRTH_CHOICES = Choices(
        ("na", _("Not sure or prefer not to answer")),
        ("<24", _("Under 24 weeks")),
        ("24", _("24 weeks")),
        ("25", _("25 weeks")),
        ("26", _("26 weeks")),
        ("27", _("27 weeks")),
        ("28", _("28 weeks")),
        ("29", _("29 weeks")),
        ("30", _("30 weeks")),
        ("31", _("31 weeks")),
        ("32", _("32 weeks")),
        ("33", _("33 weeks")),
        ("34", _("34 weeks")),
        ("35", _("35 weeks")),
        ("36", _("36 weeks")),
        ("37", _("37 weeks")),
        ("38", _("38 weeks")),
        ("39", _("39 weeks")),
        ("40>", _("40 or more weeks")),
    )

    uuid = models.UUIDField(
        verbose_name="identifier", default=uuid.uuid4, unique=True, db_index=True
    )
    given_name = models.CharField(max_length=255)
    birthday = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=2, choices=GENDER_CHOICES)
    gestational_age_at_birth = models.PositiveSmallIntegerField(
        choices=GESTATIONAL_AGE_CHOICES,
        default=GESTATIONAL_AGE_CHOICES.no_answer,
        null=True,
        blank=True,
    )
    additional_information = models.TextField(blank=True)
    deleted = models.BooleanField(default=False)
    former_lookit_profile_id = models.CharField(max_length=255, blank=True)
    existing_conditions = BitField(flags=CONDITIONS, default=0)
    languages_spoken = BitField(flags=LANGUAGES, default=0)

    user = models.ForeignKey(
        "accounts.User",
        related_name="children",
        related_query_name="children",
        on_delete=models.CASCADE  # if deleting User, also delete associated Child -
        # although may not be possible depending on Responses already associated
    )

    objects = BitfieldQuerySet.as_manager()

    def __str__(self):
        return f"<Child: {self.given_name}>"

    @property
    def age_at_birth(self):
        return GESTATIONAL_AGE_CHOICES[self.gestational_age_at_birth]

    @property
    def language_list(self):
        return " ".join(
            [langcode for langcode, boolean in self.languages_spoken.items() if boolean]
        )

    @property
    def condition_list(self):
        return " ".join(
            [
                condition
                for condition, boolean in self.existing_conditions.items()
                if boolean
            ]
        )

    class Meta:
        permissions = [
            ("can_view_all_children_in_analytics", "Can view all children in analytics")
        ]
        ordering = ["-birthday"]

    class JSONAPIMeta:
        resource_name = "children"
        lookup_field = "uuid"


# TODO: adapt for lab or remove
@receiver(post_save, sender=User)
def send_email_when_receive_groups(sender, instance, created, **kwargs):
    """
    If researcher is given groups for the first time, send an email letting them know.
    """
    if instance.is_researcher and hasattr(instance, "__original_groups"):
        original_groups = getattr(instance, "__original_groups")
        if not original_groups and set(instance.groups.all()) != set(
            instance.__original_groups
        ):
            permission = "permission description placeholder"  # TODO

            context = {
                "researcher_name": instance.get_short_name(),
                "org_name": instance.organization.name,
                "permission": permission,
            }
            send_mail.delay(
                "notify_researcher_of_org_permissions",
                f"Invitation to access studies on {instance.organization.name}",
                instance.username,
                from_address=EMAIL_FROM_ADDRESS,
                **context,
            )


class DemographicData(models.Model):
    RACE_CHOICES = Choices(
        ("white", _("White")),
        ("hisp", _("Hispanic, Latino, or Spanish origin")),
        ("black", _("Black or African American")),
        ("asian", _("Asian")),
        ("native", _("American Indian or Alaska Native")),
        ("mideast-naf", _("Middle Eastern or North African")),
        ("hawaiian-pac-isl", _("Native Hawaiian or Other Pacific Islander")),
        ("other", _("Another race, ethnicity, or origin")),
    )
    GENDER_CHOICES = Choices(
        ("m", _("male")),
        ("f", _("female")),
        ("o", _("other")),
        ("na", _("prefer not to answer")),
    )
    EDUCATION_CHOICES = Choices(
        ("some", _("some or attending high school")),
        ("hs", _("high school diploma or GED")),
        ("col", _("some or attending college")),
        ("assoc", _("2-year college degree")),
        ("bach", _("4-year college degree")),
        ("grad", _("some or attending graduate or professional school")),
        ("prof", _("graduate or professional degree")),
    )
    SPOUSE_EDUCATION_CHOICES = Choices(
        ("some", _("some or attending high school")),
        ("hs", _("high school diploma or GED")),
        ("col", _("some or attending college")),
        ("assoc", _("2-year college degree")),
        ("bach", _("4-year college degree")),
        ("grad", _("some or attending graduate or professional school")),
        ("prof", _("graduate or professional degree")),
        ("na", _("not applicable - no spouse or partner")),
    )
    NO_CHILDREN_CHOICES = Choices(
        ("0", _("0")),
        ("1", _("1")),
        ("2", _("2")),
        ("3", _("3")),
        ("4", _("4")),
        ("5", _("5")),
        ("6", _("6")),
        ("7", _("7")),
        ("8", _("8")),
        ("9", _("9")),
        ("10", _("10")),
        (">10", _("More than 10")),
    )
    AGE_CHOICES = Choices(
        ("<18", _("under 18")),
        ("18-21", _("18-21")),
        ("22-24", _("22-24")),
        ("25-29", _("25-29")),
        ("30-34", _("30-34")),
        ("35-39", _("35-39")),
        ("40-44", _("40-44")),
        ("45-49", _("45-49")),
        ("50s", _("50-59")),
        ("60s", _("60-69")),
        (">70", _("70 or over")),
    )

    GUARDIAN_CHOICES = Choices(
        ("1", _("1")), ("2", _("2")), ("3>", _("3 or more")), ("varies", _("varies"))
    )
    INCOME_CHOICES = Choices(
        ("0", _("0")),
        ("5000", _("5000")),
        ("10000", _("10000")),
        ("15000", _("15000")),
        ("20000", _("20000")),
        ("30000", _("30000")),
        ("40000", _("40000")),
        ("50000", _("50000")),
        ("60000", _("60000")),
        ("70000", _("70000")),
        ("80000", _("80000")),
        ("90000", _("90000")),
        ("100000", _("100000")),
        ("110000", _("110000")),
        ("120000", _("120000")),
        ("130000", _("130000")),
        ("140000", _("140000")),
        ("150000", _("150000")),
        ("160000", _("160000")),
        ("170000", _("170000")),
        ("180000", _("180000")),
        ("190000", _("190000")),
        (">200000", _("over 200000")),
        ("na", _("prefer not to answer")),
    )
    DENSITY_CHOICES = Choices(
        ("urban", _("urban")), ("suburban", _("suburban")), ("rural", _("rural"))
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,  # If deleting user, delete their demographic data
        null=True,
        related_name="demographics",
        related_query_name="demographics",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    previous = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="next_demographic_data",
        related_query_name="next_demographic_data",
        null=True,
        blank=True,
    )

    uuid = models.UUIDField(
        verbose_name="identifier", default=uuid.uuid4, unique=True, db_index=True
    )
    number_of_children = models.CharField(
        choices=NO_CHILDREN_CHOICES, max_length=3, blank=True
    )
    child_birthdays = ArrayField(
        models.DateField(), verbose_name="children's birthdays", blank=True
    )
    languages_spoken_at_home = models.TextField(
        verbose_name="languages spoken at home", blank=True
    )
    number_of_guardians = models.CharField(
        choices=GUARDIAN_CHOICES, max_length=6, blank=True
    )
    number_of_guardians_explanation = models.TextField(blank=True)
    race_identification = MultiSelectField(choices=RACE_CHOICES, blank=True)
    age = models.CharField(max_length=5, choices=AGE_CHOICES, blank=True)
    gender = models.CharField(max_length=2, choices=GENDER_CHOICES, blank=True)
    education_level = models.CharField(
        max_length=5, choices=EDUCATION_CHOICES, blank=True
    )
    spouse_education_level = models.CharField(
        max_length=5, choices=SPOUSE_EDUCATION_CHOICES, blank=True
    )
    annual_income = models.CharField(max_length=7, choices=INCOME_CHOICES, blank=True)
    former_lookit_annual_income = models.CharField(max_length=30, blank=True)
    number_of_books = models.IntegerField(null=True, blank=True, default=None)
    additional_comments = models.TextField(blank=True)
    country = CountryField(blank=True)
    state = USStateField(
        blank=True, choices=("XX", _("Select a State")) + USPS_CHOICES[:]
    )
    density = models.CharField(max_length=8, choices=DENSITY_CHOICES, blank=True)
    lookit_referrer = models.TextField(blank=True)
    extra = DateTimeAwareJSONField(null=True)

    class Meta:
        ordering = ["-created_at"]

    class JSONAPIMeta:
        resource_name = "demographics"
        lookup_field = "uuid"

    def __str__(self):
        return f"<DemographicData: @ {self.created_at:%c}>"

    def to_display(self):
        return dict(
            user=self.user.uuid.hex,
            created_at=self.created_at.isoformat(),
            number_of_children=self.get_number_of_children_display(),
            child_birthdays=[birthday.isoformat() for birthday in self.child_birthdays],
            languages_spoken_at_home=self.languages_spoken_at_home,
            number_of_guardians=self.get_number_of_guardians_display(),
            number_of_guardians_explanation=self.number_of_guardians_explanation,
            race_identification=self.get_race_identification_display(),
            age=self.get_age_display(),
            gender=self.get_gender_display(),
            education_level=self.get_education_level_display(),
            spouse_education_level=self.get_spouse_education_level_display(),
            annual_income=self.get_annual_income_display(),
            number_of_books=self.number_of_books,
            additional_comments=self.additional_comments,
            country=str(self.country),
            state=self.get_state_display(),
            density=self.get_density_display(),
            extra=self.extra,
            lookit_referrer=self.lookit_referrer,
        )


class Message(models.Model):
    """A message can be sent from one person to multiple people."""

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    date_created = models.DateTimeField(auto_now_add=True)
    sender = models.ForeignKey(
        User, on_delete=models.SET_NULL, db_index=True, null=True
    )
    recipients = models.ManyToManyField(User, related_name="messages")
    subject = models.CharField(max_length=255)
    body = models.TextField()
    related_study = models.ForeignKey(
        "studies.Study", on_delete=models.SET_NULL, null=True
    )
    email_sent_timestamp = models.DateTimeField(
        null=True, default=None
    )  # Timestamp serves as a truth check as well.

    def send_as_email(self):
        context = {
            "base_url": settings.BASE_URL,
            "osf_url": settings.OSF_URL,
            "custom_message": mark_safe(self.body),
        }

        text_content = get_template("emails/{}.txt".format("custom_email")).render(
            context
        )
        html_content = get_template("emails/{}.html".format("custom_email")).render(
            context
        )

        email = EmailMultiAlternatives(
            self.subject,
            text_content,
            from_email=EMAIL_FROM_ADDRESS,
            to=[EMAIL_FROM_ADDRESS],
            bcc=self.recipients.values_list("username", flat=True),
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        self.email_sent_timestamp = now()  # will use UTC now (see USE_TZ in settings)
        self.save()
