from rest_framework import serializers

from rest_framework.relations import HyperlinkedRelatedField

from rest_framework_json_api.relations import (
    ResourceRelatedField,
    HyperlinkedRelatedField as JSONAPIHyperlinkedRelatedField,
)
from rest_framework_json_api.serializers import (
    ModelSerializer as JSONAPIModelSerializer,
)

# from rest_framework_nested.relations import NestedHyperlinkedRelatedField


class ResourceWithUuidAsPkRelatedField(ResourceRelatedField):
    # related_link_lookup_field = "uuid"

    def use_pk_only_optimization(self):
        """We do not want to use the dummy PKOnly Object, or else to_representation will break."""
        return False

    def to_representation(self, value):
        """Changes the JSON representation to obfuscate the ID.

        XXX: THIS IS A HACK!!!!

        Once [insert github bug] is resolved, we should be able to drop this method.
        """
        representation = super().to_representation(value)
        representation["id"] = str(value.uuid)
        return representation


class UuidResourceRelatedField(ResourceWithUuidAsPkRelatedField):
    """UUID Only"""


class UuidHyperlinkedRelatedField(HyperlinkedRelatedField):
    """UUID Hyperlinked version"""

    def use_pk_only_optimization(self):
        return False


class NestedUuidHyperlinkedRelatedField(JSONAPIHyperlinkedRelatedField):
    """Nested UUID Hyperlinked"""


class ModelWithUuidPkSerializer(JSONAPIModelSerializer):
    """Ensuring that pk is never shown, but UUID is used instead.

    Per the docstring of the DJA class we're inheriting from:

    If the `ModelSerializer` class *doesn't* generate the set of fields that
    you need you should either declare the extra/differing fields explicitly on
    the serializer class, or simply use a `Serializer` class.
    """

    serializer_related_field = UuidHyperlinkedRelatedField

    uuid = serializers.UUIDField(source="uuid", read_only=True)
