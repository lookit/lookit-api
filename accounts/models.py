from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.localflavor.us.models import USStateField
from django.contrib.postgres.fields.array import ArrayField
from django.contrib.postgres.forms.ranges import FloatRangeField
from django.db import models

from django_countries.fields import CountryField
from project.fields.datetime_aware_jsonfield import DateTimeAwareJSONField


class User(AbstractBaseUser):
    pass


class CollaboratorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='collaborator_profile', related_query_name='collaborator')


class ParticipantProfile(models.Model):
    GENDERS = (
        ('m', 'Male'),
        ('f', 'Female'),
    )
    EDUCATION = (
        ('none', 'None'),
        ('elem', 'Elementary'),
        ('hs', 'Some High School'),
        ('hsd', 'High School Degree'),
        ('col', 'Some College'),
        ('assoc', 'Associates Degree'),
        ('bach', 'Bachelor\'s Degree'),
        ('mast', 'Master\'s Degree'),
        ('prof', 'Professional Degree'),
        ('doct', 'Doctorate'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='participant_profile', related_query_name='participant')

    number_of_children = models.PositiveSmallIntegerField(verbose_name='number of children', default=1)
    child_birthdays = ArrayField(models.DateField(), verbose_name='children\'s birthdays')
    languages_spoken_at_home = models.TextField(verbose_name='langues spoken at home')
    number_of_guardians = models.PositiveIntegerField()
    number_of_guardians_explanation = models.TextField()
    race_identification = models.TextField()
    age = models.PositiveIntegerField()
    gender = models.CharField(max_length=1, choices=GENDERS)
    education_level = models.CharField(max_length=5, choices=EDUCATION)
    spouse_education_level = models.CharField(max_length=5, choices=EDUCATION)
    annual_income = FloatRangeField()
    number_of_books = models.IntegerField()
    additional_comments = models.TextField()
    country = CountryField()
    state = USStateField(choices=('XX', _('Select a State')) + USPS_CHOICES[:])
    density = models.TextField()
    extra = DateTimeAwareJSONField()
