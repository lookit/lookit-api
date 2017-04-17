from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.contrib.postgres.fields.array import ArrayField
from django.contrib.postgres.forms.ranges import FloatRangeField
from django.db import models
from django.utils.translation import ugettext as _

from django_countries.fields import CountryField
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


class User(AbstractBaseUser, PermissionsMixin):
    username = models.EmailField(unique=True)
    USERNAME_FIELD = EMAIL_FIELD = "username"

    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)

    def get_short_name():
        return self.username

    objects = UserManager()


class CollaboratorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='collaborator_profile', related_query_name='collaborator')


class ParticipantProfile(models.Model):
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
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='participant_profile', related_query_name='participant')

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
    extra = DateTimeAwareJSONField()

    def __str__(self):
        return f'<ParticipantProfile: {self.user.username}>'
