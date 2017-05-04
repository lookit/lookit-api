import base64
import hashlib

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.contrib.postgres.fields.array import ArrayField
from django.db import models
from django.utils.html import mark_safe
from django.utils.translation import ugettext as _

import pydenticon
from django_countries.fields import CountryField
from guardian.shortcuts import get_objects_for_user
from localflavor.us.models import USStateField
from localflavor.us.us_states import USPS_CHOICES
from project.fields.datetime_aware_jsonfield import DateTimeAwareJSONField


class UserManager(BaseUserManager):
    def create_user(self, username, password=None):
        if not username:
            raise ValueError('Users must have a username')

        user = self.model(
            username=self.normalize_email(username),
            is_active=True,
        )

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
    name = models.CharField(max_length=255, blank=False, null=False)
    url = models.URLField(verbose_name='Website')

    def __str__(self):
        return f'<Organization: {self.name}>'

    class Meta:
        permissions = (
            ('is_admin', 'Organization Administrator'),
            ('can_add_collaborators', 'Can Add Collaborators'),
            ('can_approve_studies', 'Can Approve Studies'),
            ('can_disable_studies', 'Can Disable Studies'),
            ('can_view', 'Can View'),
            ('can_add_study', 'Can Add Study'),
        )


class User(AbstractBaseUser, PermissionsMixin):
    USERNAME_FIELD = EMAIL_FIELD = 'username'
    username = models.EmailField(unique=True)
    given_name = models.CharField(max_length=255)
    middle_name = models.CharField(max_length=255, blank=True)
    family_name = models.CharField(max_length=255)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='users', related_query_name='user', null=True, blank=True)
    _identicon = models.TextField(verbose_name='identicon')

    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)

    @property
    def identicon(self):
        if not self._identicon:
            rbw = self._make_rainbow()
            generator = pydenticon.Generator(5, 5, digest=hashlib.sha512, foreground=rbw, background='rgba(0,0,0,0)')
            png = generator.generate(f'{self.username} {self.given_name} {self.middle_name} {self.family_name} {self.organization}', 64, 64)
            b64_png = base64.b64encode(png)
            self._identicon = f'data:image/png;base64,{b64_png.decode()}'
            self.save()
        return self._identicon

    def _make_rainbow(self):
        rbw = []
        for i in range(0, 255, 10):
            for j in range(0, 255, 10):
                for k in range(0, 255, 10):
                    rbw.append(f'rgb({i},{j},{k})')
        return rbw



    @property
    def identicon_html(self):
        return mark_safe(f'<img src="{str(self.identicon)}" width="64"/>')

    def get_short_name(self):
        return self.identicon_html

    def get_full_name(self):
        return f'{self.given_name} {self.middle_name} {self.family_name}'

    def __str__(self):
        return f'<User: {self.username}>'

    @property
    def is_participant(self):
        return self.demographics.exists()

    @property
    def studies(self):
        if not self.is_participant:
            return get_objects_for_user(self, ['studies.view_study', 'studies.edit_study'])
        return None

    objects = UserManager()


class DemographicData(models.Model):
    RACE_CHOICES = (
        ('white', 'White'),
        ('hisp', 'Hispanic, Latino, or Spanish origin'),
        ('black', 'Black or African American'),
        ('asian', 'Asian'),
        ('native', 'American Indian or Alaska Native'),
        ('mideast-naf', 'Middle Eastern or North African'),
        ('hawaiian-pac-isl', 'Native Hawaiian or Other Pacific Islander'),
        ('other', 'Another race, ethnicity, or origin')
    )
    GENDER_CHOICES = (
        ('m', 'male'),
        ('f', 'female'),
        ('o', 'other'),
        ('na', 'prefer not to answer')
    )
    EDUCATION_CHOICES = (
        ('some', 'some or attending high school'),
        ('hs', 'high school diploma or GED'),
        ('col', 'some or attending college'),
        ('assoc', '2-year college degree'),
        ('bach', '4-year college degree'),
        ('grad', 'some or attending graduate or professional school'),
        ('prof', 'graduate or professional degree')
    )
    SPOUSE_EDUCATION_CHOICES = (
        ('some', 'some or attending high school'),
        ('hs', 'high school diploma or GED'),
        ('col', 'some or attending college'),
        ('assoc', '2-year college degree'),
        ('bach', '4-year college degree'),
        ('grad', 'some or attending graduate or professional school'),
        ('prof', 'graduate or professional degree'),
        ('na', 'not applicable - no spouse or partner')
    )
    NO_CHILDREN_CHOICES = (
        ('0', '0'),
        ('1', '1'),
        ('2', '2'),
        ('3', '3'),
        ('4', '4'),
        ('5', '5'),
        ('6', '6'),
        ('7', '7'),
        ('8', '8'),
        ('9', '9'),
        ('10', '10'),
        ('>10', 'More than 10')
    )
    AGE_CHOICES = (
        ('<18', 'under 18'),
        ('18-21', '18-21'),
        ('22-24', '22-24'),
        ('25-29', '25-29'),
        ('30-34', '30-34'),
        ('35-39', '35-39'),
        ('40-44', '40-44'),
        ('45-59', '45-49'),
        ('50s', '50-59'),
        ('60s', '60-69'),
        ('>70', '70 or over')
    )

    GUARDIAN_CHOICES = (
        ('1', '1'),
        ('2', '2'),
        ('3>', '3 or more'),
        ('varies', 'varies')
    )
    INCOME_CHOICES = (
        ('0', '0'),
        ('5000', '5000'),
        ('10000', '10000'),
        ('15000', '15000'),
        ('20000', '20000'),
        ('30000', '30000'),
        ('40000', '40000'),
        ('50000', '50000'),
        ('60000', '60000'),
        ('70000', '70000'),
        ('80000', '80000'),
        ('90000', '90000'),
        ('100000', '100000'),
        ('110000', '110000'),
        ('120000', '120000'),
        ('130000', '130000'),
        ('140000', '140000'),
        ('150000', '150000'),
        ('160000', '160000'),
        ('170000', '170000'),
        ('180000', '180000'),
        ('190000', '190000'),
        ('>200000', 'over 200000'),
        ('na', 'prefer not to answer')
    )
    DENSITY_CHOICES = (
        ('urban','urban'),
        ('suburban','suburban'),
        ('rural', 'rural')
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='demographics', related_query_name='demographics')
    created_at = models.DateTimeField(auto_now_add=True)
    previous = models.ForeignKey('self', on_delete=models.CASCADE, related_name='next_demographic_data', related_query_name='next_demographic_data', null=True, blank=True)

    number_of_children = models.CharField(choices=NO_CHILDREN_CHOICES, max_length=3)
    child_birthdays = ArrayField(models.DateField(), verbose_name='children\'s birthdays')
    languages_spoken_at_home = models.TextField(verbose_name='languages spoken at home')
    number_of_guardians = models.CharField(choices=GUARDIAN_CHOICES, max_length=6)
    number_of_guardians_explanation = models.TextField()
    race_identification = models.CharField(max_length=16, choices=RACE_CHOICES)
    age = models.CharField(max_length=5, choices=AGE_CHOICES)
    gender = models.CharField(max_length=2, choices=GENDER_CHOICES)
    education_level = models.CharField(max_length=5, choices=EDUCATION_CHOICES)
    spouse_education_level = models.CharField(max_length=5, choices=SPOUSE_EDUCATION_CHOICES)
    annual_income = models.CharField(max_length=7, choices=INCOME_CHOICES)
    number_of_books = models.IntegerField()
    additional_comments = models.TextField()
    country = CountryField()
    state = USStateField(choices=('XX', _('Select a State')) + USPS_CHOICES[:])
    density = models.CharField(max_length=8, choices=DENSITY_CHOICES)
    extra = DateTimeAwareJSONField(null=True)

    def __str__(self):
        return f'<DemographicData: {self.user.get_short_name} @ {self.created_at:%c}>'
