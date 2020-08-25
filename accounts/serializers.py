from rest_framework_json_api import serializers

from accounts.models import Child, DemographicData, User
from api.serializers import (
    PatchedHyperlinkedRelatedField,
    UuidHyperlinkedModelSerializer,
)
from studies.models import Lab


class LabSerializer(UuidHyperlinkedModelSerializer):
    resource_name = "labs"
    url = serializers.HyperlinkedIdentityField(
        view_name="api:lab-detail", lookup_field="uuid"
    )

    class Meta:
        model = Lab
        fields = (
            "name",
            "institution",
            "principal_investigator_name",
            "lab_website",
            "description",
            "approved_to_test",
            "url",
            "pk",
        )


class DemographicDataSerializer(UuidHyperlinkedModelSerializer):
    resource_name = "demographics"
    country = serializers.CharField(default="")
    date_created = serializers.DateTimeField(read_only=True, source="created_at")

    url = serializers.HyperlinkedIdentityField(
        view_name="api:demographicdata-detail", lookup_field="uuid"
    )

    class Meta:
        model = DemographicData
        fields = (
            "url",
            "number_of_children",
            "child_birthdays",
            "languages_spoken_at_home",
            "number_of_guardians",
            "number_of_guardians_explanation",
            "race_identification",
            "age",
            "gender",
            "education_level",
            "spouse_education_level",
            "annual_income",
            "former_lookit_annual_income",
            "lookit_referrer",
            "number_of_books",
            "additional_comments",
            "country",
            "state",
            "density",
            "extra",
            "date_created",
            "pk",
        )


class BasicUserSerializer(UuidHyperlinkedModelSerializer):
    resource_name = "users"
    url = serializers.HyperlinkedIdentityField(
        view_name="api:user-detail", lookup_field="uuid"
    )

    demographics = PatchedHyperlinkedRelatedField(
        queryset=DemographicData.objects,
        many=True,
        related_link_view_name="api:user-demographics-list",
        related_link_url_kwarg="user_uuid",
        related_link_lookup_field="uuid",
    )
    children = PatchedHyperlinkedRelatedField(
        queryset=Child.objects,
        many=True,
        related_link_view_name="api:user-children-list",
        related_link_url_kwarg="user_uuid",
        related_link_lookup_field="uuid",
    )

    class Meta:
        model = User
        fields = (
            "url",
            "given_name",
            "middle_name",
            "family_name",
            "nickname",
            "identicon",
            "is_active",
            "is_staff",
            "is_researcher",
            "demographics",
            "children",
            "former_lookit_id",
            "linked_former_lookit_ids",
            "email_next_session",
            "email_new_studies",
            "email_study_updates",
            "email_response_questions",
            "date_created",
            "pk",
        )


class FullUserSerializer(BasicUserSerializer):
    class Meta:
        model = User
        fields = BasicUserSerializer.Meta.fields + ("username",)


class ChildSerializer(UuidHyperlinkedModelSerializer):
    lookup_field = "uuid"
    url = serializers.HyperlinkedIdentityField(
        view_name="api:child-detail", lookup_field="uuid"
    )

    user = PatchedHyperlinkedRelatedField(
        queryset=User.objects,
        related_link_view_name="api:user-detail",
        related_link_lookup_field="user.uuid",
        related_link_url_kwarg="uuid",
    )

    class Meta:
        model = Child
        fields = (
            "url",
            "user",
            "given_name",
            "birthday",
            "gender",
            "age_at_birth",
            "additional_information",
            "language_list",
            "condition_list",
            "deleted",
            "former_lookit_profile_id",
            "pk",
        )
