from rest_framework import serializers

from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (
    ModelSerializer as JSONAPIModelSerializer,
)


class UUIDResourceRelatedField(ResourceRelatedField):
    related_link_lookup_field = "uuid"

    def to_representation(self, value):
        """What I think is the proper way to do this."""
        representation = super().to_representation(value)
        representation["id"] = str(value.uuid)
        return representation


class ModelWithUuidPkSerializer(JSONAPIModelSerializer):
    """Ensuring that pk is never shown, but UUID is used instead.

    Per the docstring of the DJA class we're inheriting from:

    If the `ModelSerializer` class *doesn't* generate the set of fields that
    you need you should either declare the extra/differing fields explicitly on
    the serializer class, or simply use a `Serializer` class.
    """

    serializer_related_field = UUIDResourceRelatedField

    uuid = serializers.UUIDField(source="uuid", read_only=True)
