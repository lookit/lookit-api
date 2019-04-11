from collections import OrderedDict

from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (
    ModelSerializer as JSONAPIModelSerializer,
)


class UUIDResourceRelatedField(ResourceRelatedField):
    related_link_lookup_field = "uuid"

    def to_representation(self, value):
        """What I think is the proper way to do this."""
        representation = super().to_representation(value)
        representation["id"] = value.uuid
        return representation


class ModelSerializer(JSONAPIModelSerializer):
    serializer_related_field = UUIDResourceRelatedField


class UUIDSerializerMixin(ModelSerializer):
    def to_representation(self, instance):
        # this might not do anything
        retval = super().to_representation(instance)
        retval["id"] = instance.uuid
        retval["pk"] = instance.uuid
        return retval
