from rest_framework_json_api import serializers

from accounts.models import Child, DemographicData, User
from api.serializers import ModelSerializer, UUIDSerializerMixin


class DemographicDataSerializer(UUIDSerializerMixin, ModelSerializer):
    resource_name = 'demographics'
    url = serializers.HyperlinkedIdentityField(
        view_name='demographicdata-detail',
        lookup_field='uuid'
    )

    class Meta:
        model = DemographicData
        fields = (
            'url',
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


class UserSerializer(UUIDSerializerMixin, ModelSerializer):
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
            'given_name',
            'middle_name',
            'family_name',
            'identicon',
            'is_active',
            'is_staff',
            'demographics'
        )

    class JSONAPIMeta:
        included_resources = ['demographics', ]


class ChildSerializer(UUIDSerializerMixin, ModelSerializer):
    lookup_field = 'uuid'
    url = serializers.HyperlinkedIdentityField(
        view_name='child-detail',
        lookup_field='uuid'
    )
    included_serializers = {
        'user': UserSerializer,
    }

    class Meta:
        model = Child
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
