from rest_framework import serializers

from accounts.models import DemographicData, Profile, User
from rest_framework_json_api.relations import ResourceRelatedField


class DemographicDataSerializer(serializers.ModelSerializer):
    resource_name = 'demographics'

    class Meta:
        model = DemographicData
        fields = (
            'uuid',
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


class UserSerializer(serializers.ModelSerializer):
    resource_name = 'users'
    url = serializers.HyperlinkedIdentityField(
        view_name='user-detail',
        lookup_field='uuid'
    )

    included_serializers = {
        'demographics': DemographicDataSerializer,
    }

    class Meta:
        model = User
        fields = (
            'url',
            'uuid',
            'organization',
            'identicon',
            'is_active',
            'is_staff',
            'demographics'
        )

    class JSONAPIMeta:
        included_resources = ['demographics', ]


class ProfileSerializer(serializers.ModelSerializer):
    lookup_field = 'uuid'
    url = serializers.HyperlinkedIdentityField(
        view_name='profile-detail',
        lookup_field='uuid'
    )
    included_serializers = {
        'user': UserSerializer,
    }

    class Meta:
        model = Profile
        fields = (
            'url',
            'user',
            'uuid',
            'given_name',
            'birthday',
            'gender',
            'age_at_birth',
            'additional_information',
            'deleted',
        )

    class JSONAPIMeta:
        included_resources = ['user', ]
