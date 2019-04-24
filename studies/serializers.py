from rest_framework_json_api import serializers

from accounts.models import Child, DemographicData, Organization, User
from api.serializers import (
    UuidHyperlinkedModelSerializer,
    UuidResourceModelSerializer,
    PatchedHyperlinkedRelatedField,
    PatchedResourceRelatedField,
)
from studies.models import Feedback, Response, Study


class StudySerializer(UuidHyperlinkedModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="study-detail", lookup_field="uuid"
    )
    organization = PatchedHyperlinkedRelatedField(
        queryset=Organization.objects,
        related_link_view_name="organization-detail",
        related_link_lookup_field="organization.uuid",
        related_link_url_kwarg="uuid",
    )

    creator = PatchedHyperlinkedRelatedField(
        queryset=User.objects,
        related_link_view_name="user-detail",
        related_link_lookup_field="creator.uuid",
        related_link_url_kwarg="uuid",
    )
    responses = PatchedHyperlinkedRelatedField(
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


class FeedbackSerializer(UuidResourceModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="feedback-detail", lookup_field="uuid"
    )
    response = PatchedResourceRelatedField(
        queryset=Response.related_manager,
        related_link_view_name="response-detail",
        related_link_lookup_field="response.uuid",
        related_link_url_kwarg="uuid",
    )
    researcher = PatchedResourceRelatedField(
        read_only=True,
        related_link_view_name="user-detail",
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
        view_name="response-detail", lookup_field="uuid"
    )

    study = PatchedHyperlinkedRelatedField(
        read_only=True,
        related_link_view_name="study-detail",
        related_link_lookup_field="study.uuid",
        related_link_url_kwarg="uuid",
    )
    user = PatchedHyperlinkedRelatedField(
        read_only=True,
        source="child",
        related_link_view_name="user-detail",
        related_link_lookup_field="child.user.uuid",
        related_link_url_kwarg="uuid",
        required=False,
    )
    child = PatchedHyperlinkedRelatedField(
        read_only=True,
        related_link_view_name="child-detail",
        related_link_lookup_field="child.uuid",
        related_link_url_kwarg="uuid",
    )
    demographic_snapshot = PatchedHyperlinkedRelatedField(
        read_only=True,
        related_link_view_name="demographicdata-detail",
        related_link_lookup_field="demographic_snapshot.uuid",
        related_link_url_kwarg="uuid",
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


class ResponseWriteableSerializer(UuidResourceModelSerializer):
    """Serialize according to the way the frontend likes to send data - true-ID specific."""

    url = serializers.HyperlinkedIdentityField(
        view_name="response-detail", lookup_field="uuid"
    )

    study = PatchedResourceRelatedField(
        queryset=Study.objects,
        related_link_view_name="study-detail",
        related_link_lookup_field="study_id",
        related_link_url_kwarg="uuid",
    )

    child = PatchedResourceRelatedField(
        queryset=Child.objects,
        related_link_view_name="child-detail",
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
            "pk",
            "withdrawn",
        )
