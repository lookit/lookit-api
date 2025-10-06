import logging

from rest_framework_json_api import serializers

from accounts.models import Child
from accounts.utils import hash_child_id_from_model
from api.serializers import (
    PatchedHyperlinkedRelatedField,
    PatchedResourceRelatedField,
    UuidHyperlinkedModelSerializer,
    UuidResourceModelSerializer,
)
from studies.models import Feedback, Response, Study, Video

logger = logging.getLogger(__name__)


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
            "survey_consent",
            "demographic_snapshot",
            "created_on",
            "is_preview",
            "pk",
            "withdrawn",
            "hash_child_id",
            "recording_method",
            "eligibility",
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

    def validate_exp_data(self, exp_data):
        """
        jsPsych studies only: enforce append-only for exp_data rows. PATCH requests must have the same or larger number of rows (trials) as the existing data, though the trial data itself can be modified.
        """
        instance = self.instance

        # validation is for jsPsych responses and PATCH updates only
        if instance is not None and instance.study.study_type.is_jspsych:
            if exp_data is None and instance.exp_data is not None:
                logger.warning(
                    f"Rejected jsPsych exp_data update for response {instance.uuid}: "
                    f"jsPsych exp_data cannot be overwritten with null"
                )
                raise serializers.ValidationError(
                    "Rejected jsPsych PATCH update: jsPsych exp_data cannot be overwritten with null"
                )

            # If exp_data is provided, validate its type and length
            if exp_data is not None:
                if not isinstance(exp_data, list):
                    logger.warning(
                        f"Rejected jsPsych exp_data update for response {instance.uuid}: "
                        f"jsPsych exp_data must be a list, instead received {type(exp_data).__name__}"
                    )
                    raise serializers.ValidationError(
                        f"Rejected jsPsych PATCH update: jsPsych exp_data must be a list, instead received {type(exp_data).__name__}"
                    )

                old_exp_data = instance.exp_data or []
                if not isinstance(old_exp_data, list):
                    old_exp_data = []

                if len(exp_data) < len(old_exp_data):
                    logger.warning(
                        f"Rejected jsPsych exp_data update for response {instance.uuid}: "
                        f"new length {len(exp_data)} < old length {len(old_exp_data)}"
                    )
                    raise serializers.ValidationError(
                        "Rejected jsPsych PATCH update: exp_data cannot reduce in length"
                    )

        return exp_data

    def update(self, instance, validated_data):
        """
        Override response update/save request so that, for jsPsych studies,
        the frame sequence is computed automatically from exp_data.
        """
        exp_data = validated_data.get("exp_data")

        if instance.study.study_type.is_jspsych and exp_data is not None:
            validated_data["sequence"] = self.compute_sequence(exp_data)

        return super().update(instance, validated_data)

    def compute_sequence(self, exp_data):
        """
        Safely generate the sequence list from jsPsych exp_data.
        Each row should be a dict with trial_index and trial_type.
        """
        if not isinstance(exp_data, list):
            return []

        sequence = []
        for el in exp_data:
            # skip non-dict/object elements
            if not isinstance(el, dict):
                continue
            trial_index = el.get("trial_index")
            trial_type = el.get("trial_type")
            # skip dicts that are missing required keys
            if trial_index is None or trial_type is None:
                continue
            sequence.append(f"{trial_index}-{trial_type}")

        return sequence

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
            "survey_consent",
            "is_preview",
            "pk",
            "withdrawn",
            "recording_method",
            "eligibility",
        )


class VideoSerializer(UuidResourceModelSerializer):
    """Create and return a new Video instance, given validated data."""

    url = serializers.HyperlinkedIdentityField(
        view_name="api:video-detail", lookup_field="uuid"
    )

    study = PatchedResourceRelatedField(
        queryset=Study.objects,
        related_link_view_name="api:study-detail",
        related_link_lookup_field="study_id",
        related_link_url_kwarg="uuid",
    )

    response = PatchedResourceRelatedField(
        queryset=Response.objects,
        related_link_view_name="api:response-detail",
        related_link_lookup_field="response_id",
        related_link_url_kwarg="uuid",
    )

    class Meta:
        model = Video
        fields = (
            "url",
            "pipe_name",
            "pipe_numeric_id",
            "s3_timestamp",
            "frame_id",
            "full_name",
            "study",
            "response",
            "is_consent_footage",
        )
