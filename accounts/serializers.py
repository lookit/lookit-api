from accounts.models import DemographicData, Profile, User
from rest_framework_json_api import serializers


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = '__all__'


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'


class DemographicDataSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    profiles = ProfileSerializer(many=True, source='user.profiles.all')

    class Meta:
        model = DemographicData
        fields = (
            'user',
            'profiles',
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
