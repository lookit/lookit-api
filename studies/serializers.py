from rest_framework_json_api import serializers

from accounts.models import Child, DemographicData, Organization, User
from api.serializers import (
    ModelSerializer,
    UUIDResourceRelatedField,
    UUIDSerializerMixin,
)
from studies.models import Feedback, Response, Study


class StudySerializer(UUIDSerializerMixin, ModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="study-detail", lookup_field="uuid"
    )
    organization = UUIDResourceRelatedField(
        queryset=Organization.objects,
        related_link_view_name="organization-detail",
        related_link_lookup_field="uuid",
        many=False,
    )
    creator = UUIDResourceRelatedField(
        queryset=User.objects,
        related_link_view_name="user-detail",
        related_link_lookup_field="uuid",
        many=False,
    )
    responses = UUIDResourceRelatedField(
        queryset=Response.objects,
        many=True,
        related_link_view_name="study-responses-list",
        related_link_url_kwarg="study_uuid",
        related_link_lookup_field="uuid",
    )

    class Meta:
        model = Study
        fields = (
            "url",
            "name",
            "date_modified",
            "short_description",
            "long_description",
            "criteria",
            "duration",
            "contact_info",
            "image",
            "structure",
            "display_full_screen",
            "exit_url",
            "state",
            "public",
            "organization",
            "creator",
            "responses",
            "pk",
        )


class FeedbackSerializer(UUIDSerializerMixin, ModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="feedback-detail", lookup_field="uuid"
    )
    response = UUIDResourceRelatedField(
        queryset=Response.objects,
        many=False,
        related_link_view_name="response-detail",
        related_link_lookup_field="uuid",
    )
    researcher = UUIDResourceRelatedField(
        read_only=True,
        many=False,
        related_link_view_name="user-detail",
        related_link_lookup_field="uuid",
    )

    class Meta:
        model = Feedback
        fields = ("url", "comment", "response", "researcher")
        read_only_fields = ("researcher",)


class ResponseSerializer(UUIDSerializerMixin, ModelSerializer):
    created_on = serializers.DateTimeField(read_only=True, source="date_created")
    url = serializers.HyperlinkedIdentityField(
        view_name="response-detail", lookup_field="uuid"
    )

    study = UUIDResourceRelatedField(
        queryset=Study.objects,
        many=False,
        related_link_view_name="study-detail",
        related_link_lookup_field="uuid",
    )
    user = UUIDResourceRelatedField(
        source="child.user",
        queryset=User.objects,
        many=False,
        related_link_view_name="user-detail",
        related_link_lookup_field="uuid",
        required=False,
    )
    child = UUIDResourceRelatedField(
        queryset=Child.objects,
        many=False,
        related_link_view_name="child-detail",
        related_link_lookup_field="uuid",
    )
    demographic_snapshot = UUIDResourceRelatedField(
        queryset=DemographicData.objects,
        many=False,
        related_link_view_name="demographicdata-detail",
        related_link_lookup_field="uuid",
        required=False,
    )

    class Meta:
        model = Response
        fields = (
            "url",
            "conditions",
            "global_event_timings",
            "exp_data",
            "sequence",
            "completed",
            "child",
            "user",
            "study",
            "completed_consent_frame",
            "demographic_snapshot",
            "created_on",
            "pk",
            "withdrawn",
        )


class ResponseWriteableSerializer(ResponseSerializer):
    def create(self, validated_data):
        """
        Use the ids for objects so django rest framework doesn't
        try to create new objects out of spite
        """
        study = validated_data.pop("study")
        validated_data["study_id"] = study.id
        # implicitly set the demographic data because we know what it will be
        validated_data["demographic_snapshot_id"] = validated_data.get(
            "child"
        ).user.latest_demographics.id
        child = validated_data.pop("child")
        validated_data["child_id"] = child.id
        return super().create(validated_data)
