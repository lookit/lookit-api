from rest_framework_json_api import serializers

from accounts.models import Child
from accounts.utils import hash_child_id_from_model
from api.serializers import (
    PatchedHyperlinkedRelatedField,
    PatchedResourceRelatedField,
    UuidHyperlinkedModelSerializer,
    UuidResourceModelSerializer,
)
from studies.models import Feedback, Response, Study


class StudySerializer(UuidHyperlinkedModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="api:study-detail", lookup_field="uuid"
    )
    responses = PatchedHyperlinkedRelatedField(
        queryset=Response.objects,
        many=True,
        related_link_view_name="api:study-responses-list",
        related_link_url_kwarg="study_uuid",
        related_link_lookup_field="uuid",
    )

    class Meta:
        model = Study
        fields = (
            "url",
            "name",
            "short_description",
            "purpose",
            "criteria",
            "duration",
            "contact_info",
            "image",
            "structure",
            "generator",
            "use_generator",
            "display_full_screen",
            "exit_url",
            "state",
            "public",
            "responses",
            "pk",
        )


class FeedbackSerializer(UuidResourceModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="api:feedback-detail", lookup_field="uuid"
    )
    response = PatchedResourceRelatedField(
        queryset=Response.related_manager,
        related_link_view_name="api:response-detail",
        related_link_lookup_field="response.uuid",
        related_link_url_kwarg="uuid",
    )
    researcher = PatchedResourceRelatedField(
        read_only=True,
        related_link_view_name="api:user-detail",
        related_link_lookup_field="researcher.uuid",
        related_link_url_kwarg="uuid",
    )

    class Meta:
        model = Feedback
        fields = ("url", "comment", "response", "researcher")
        read_only_fields = ("researcher",)


class ResponseSerializer(UuidHyperlinkedModelSerializer):
    """Gets hyperlink related fields.

    XXX: It's important to keep read_only set to true here - otherwise, a queryset is necessitated, which implicates
    get_attribute from ResourceRelatedField
    """

    created_on = serializers.DateTimeField(read_only=True, source="date_created")
    url = serializers.HyperlinkedIdentityField(
        view_name="api:response-detail", lookup_field="uuid"
    )

    study = PatchedHyperlinkedRelatedField(
        read_only=True,
        related_link_view_name="api:study-detail",
        related_link_lookup_field="study.uuid",
        related_link_url_kwarg="uuid",
    )
    user = PatchedHyperlinkedRelatedField(
        read_only=True,
        source="child",
        related_link_view_name="api:user-detail",
        related_link_lookup_field="child.user.uuid",
        related_link_url_kwarg="uuid",
        required=False,
    )
    child = PatchedHyperlinkedRelatedField(
        read_only=True,
        related_link_view_name="api:child-detail",
        related_link_lookup_field="child.uuid",
        related_link_url_kwarg="uuid",
    )
    demographic_snapshot = PatchedHyperlinkedRelatedField(
        read_only=True,
        related_link_view_name="api:demographicdata-detail",
        related_link_lookup_field="demographic_snapshot.uuid",
        related_link_url_kwarg="uuid",
        required=False,
    )
    hash_child_id = serializers.SerializerMethodField("get_hash_child_id")

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
            "is_preview",
            "pk",
            "withdrawn",
            "hash_child_id",
        )

    def get_hash_child_id(self, obj):
        return hash_child_id_from_model(obj)


class ResponseWriteableSerializer(UuidResourceModelSerializer):
    """Serialize according to the way the frontend likes to send data - true-ID specific."""

    url = serializers.HyperlinkedIdentityField(
        view_name="api:response-detail", lookup_field="uuid"
    )

    study = PatchedResourceRelatedField(
        queryset=Study.objects,
        related_link_view_name="api:study-detail",
        related_link_lookup_field="study_id",
        related_link_url_kwarg="uuid",
    )

    child = PatchedResourceRelatedField(
        queryset=Child.objects,
        related_link_view_name="api:child-detail",
        related_link_lookup_field="child_id",
        related_link_url_kwarg="uuid",
    )

    def create(self, validated_data):
        """Implicitly capture Demographic Data."""
        validated_data["demographic_snapshot_id"] = validated_data.get(
            "child"
        ).user.latest_demographics.id
        return super().create(validated_data)

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
            "study",
            "completed_consent_frame",
            "is_preview",
            "pk",
            "withdrawn",
        )
