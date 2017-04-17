from rest_framework import serializers as drf_serializers

from accounts.models import ParticipantProfile, User
from rest_framework_json_api import serializers


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'


class ParticipantSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    class Meta:
        model = ParticipantProfile
        fields = (
            'user',
            'number_of_children',
            'child_birthdays',
            'languages_spoken_at_home',
            'number_of_guardians',
            'number_of_guardians_explanation',
            'race_identification',
            'age',
            'gender',
            'education_level',
            'spouse_education_level',
            'annual_income',
            'number_of_books',
            'additional_comments',
            'country',
            'state',
            'density',
            'extra',
        )
