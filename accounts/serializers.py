from rest_framework_json_api import serializers

from accounts.models import Child, DemographicData, Organization, User
from api.serializers import (
    PatchedHyperlinkedRelatedField,
    UuidHyperlinkedModelSerializer,
)


class OrganizationSerializer(UuidHyperlinkedModelSerializer):
    resource_name = "organizations"
    url = serializers.HyperlinkedIdentityField(
        view_name="organization-detail", lookup_field="uuid"
    )

    class Meta:
        model = Organization
        fields = ("name", "url", "pk")


class DemographicDataSerializer(UuidHyperlinkedModelSerializer):
    resource_name = "demographics"
    country = serializers.CharField(default="")
    date_created = serializers.DateTimeField(read_only=True, source="created_at")

    url = serializers.HyperlinkedIdentityField(
        view_name="demographicdata-detail", lookup_field="uuid"
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
        view_name="user-detail", lookup_field="uuid"
    )

    demographics = PatchedHyperlinkedRelatedField(
        queryset=DemographicData.objects,
        many=True,
        related_link_view_name="user-demographics-list",
        related_link_url_kwarg="user_uuid",
        related_link_lookup_field="uuid",
    )
    # organization = PatchedHyperlinkedRelatedField(
    #     queryset=Organization.objects,
    #     related_link_view_name="organization-detail",
    #     related_link_lookup_field="organization.uuid",
    #     related_link_url_kwarg="uuid",
    # )
    children = PatchedHyperlinkedRelatedField(
        queryset=Child.objects,
        many=True,
        related_link_view_name="user-children-list",
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
            # "organization",
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
        view_name="child-detail", lookup_field="uuid"
    )

    user = PatchedHyperlinkedRelatedField(
        queryset=User.objects,
        related_link_view_name="user-detail",
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
            "deleted",
            "former_lookit_profile_id",
            "pk",
        )
