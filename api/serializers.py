from collections import OrderedDict

from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (
    ModelSerializer as JSONAPIModelSerializer,
)


class UUIDResourceRelatedField(ResourceRelatedField):
    related_link_lookup_field = "uuid"


class ModelSerializer(JSONAPIModelSerializer):
    serializer_related_field = UUIDResourceRelatedField


class UUIDSerializerMixin(ModelSerializer):
    def to_representation(self, instance):
        # this might not do anything
        retval = super().to_representation(instance)
        retval = OrderedDict(
            ("id", instance.uuid) if key == "id" else (key, value)
            for key, value in retval.items()
        )
        return retval
