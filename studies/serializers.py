from accounts.models import Child, DemographicData, Organization, User
from api.serializers import (ModelSerializer, UUIDResourceRelatedField,
                             UUIDSerializerMixin)
from rest_framework_json_api import serializers
from studies.models import Response, Study


class StudySerializer(UUIDSerializerMixin, ModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='study-detail',
        lookup_field='uuid'
    )
    organization = UUIDResourceRelatedField(
        queryset=Organization.objects,
        related_link_view_name='organization-detail',
        related_link_lookup_field='uuid', many=False
    )
    creator = UUIDResourceRelatedField(
        queryset=User.objects,
        related_link_view_name='user-detail',
        related_link_lookup_field='uuid', many=False
    )
    responses = UUIDResourceRelatedField(
        queryset=Response.objects,
        many=True,
        related_link_view_name='study-responses-list',
        related_link_url_kwarg='study_uuid',
        related_link_lookup_field='uuid',
    )

    class Meta:
        model = Study
        fields = (
            'url',
            'name',
            'date_modified',
            'short_description',
            'long_description',
            'criteria',
            'duration',
            'contact_info',
            'image',
            'structure',
            'display_full_screen',
            'exit_url',
            'state',
            'public',
            'organization',
            'creator',
            'responses',
        )


class ResponseSerializer(UUIDSerializerMixin, ModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='response-detail',
        lookup_field='uuid'
    )
    study = UUIDResourceRelatedField(
        queryset=Study.objects,
        many=False,
        related_link_view_name='study-detail',
        related_link_lookup_field='uuid',
    )
    user = UUIDResourceRelatedField(
        source='child.user',
        queryset=User.objects,
        many=False,
        related_link_view_name='user-list',
        related_link_lookup_field='uuid',
        required=False
    )
    child = UUIDResourceRelatedField(
        queryset=Child.objects,
        many=False,
        related_link_view_name='child-detail',
        related_link_lookup_field='uuid',
    )
    demographic_snapshot = UUIDResourceRelatedField(
        queryset=DemographicData.objects,
        many=False,
        related_link_view_name='demographicdata-detail',
        related_link_lookup_field='uuid'
    )

    class Meta:
        model = Response
        fields = (
            'url',
            'conditions',
            'global_event_timings',
            'exp_data',
            'sequence',
            'completed',
            'child',
            'user',
            'study',
            'demographic_snapshot',
        )
