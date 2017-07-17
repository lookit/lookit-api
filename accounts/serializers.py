from accounts.models import Child, DemographicData, Organization, User
from api.serializers import (ModelSerializer, UUIDResourceRelatedField,
                             UUIDSerializerMixin)
from rest_framework_json_api import serializers


class OrganizationSerializer(UUIDSerializerMixin, ModelSerializer):
    resource_name = 'organizations'
    url = serializers.HyperlinkedIdentityField(
        view_name='organization-detail',
        lookup_field='uuid'
    )

    class Meta:
        model = Organization
        fields = (
            'name',
            'url',
        )


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

    # included_serializers = {
    #     'demographics': DemographicDataSerializer,
    # }
    demographics = UUIDResourceRelatedField(
        queryset=DemographicData.objects,
        many=True,
        related_link_view_name='user-demographics-list',
        related_link_url_kwarg='user_uuid',
        related_link_lookup_field='uuid',
    )
    organization = UUIDResourceRelatedField(
        queryset=Organization.objects,
        many=False,
        related_link_view_name='organization-detail',
        related_link_lookup_field='uuid',
    )
    children = UUIDResourceRelatedField(
        queryset=Child.objects,
        many=True,
        related_link_view_name='user-children-list',
        related_link_url_kwarg='user_uuid',
        related_link_lookup_field='uuid',
    )

    class Meta:
        model = User
        fields = (
            'url',
            'given_name',
            'middle_name',
            'family_name',
            'identicon',
            'is_active',
            'is_staff',
            'demographics',
            'organization',
            'children'
        )

    # class JSONAPIMeta:
    #     included_resources = ['demographics', ]


class ChildSerializer(UUIDSerializerMixin, ModelSerializer):
    lookup_field = 'uuid'
    url = serializers.HyperlinkedIdentityField(
        view_name='child-detail',
        lookup_field='uuid'
    )
    # included_serializers = {
    #     'user': UserSerializer,
    # }

    user = UUIDResourceRelatedField(
        queryset=User.objects,
        many=False,
        related_link_view_name='user-detail',
        related_link_lookup_field='uuid'
    )

    class Meta:
        model = Child
        fields = (
            'url',
            'user',
            'given_name',
            'birthday',
            'gender',
            'age_at_birth',
            'additional_information',
            'deleted',
        )

    # class JSONAPIMeta:
        # included_resources = ['user', ]
