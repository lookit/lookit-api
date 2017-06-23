from collections import OrderedDict

from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import \
    ModelSerializer as JSONAPIModelSerializer
from rest_framework_json_api.utils import (get_included_serializers,
                                           get_resource_type_from_instance,
                                           get_resource_type_from_serializer)


class UUIDResourceRelatedField(ResourceRelatedField):
    def to_representation(self, value):
        # force pk to be UUID
        pk = value.uuid

        # check to see if this resource has a different resource_name when
        # included and use that name
        resource_type = None
        root = getattr(self.parent, 'parent', self.parent)
        field_name = self.field_name if self.field_name else self.parent.field_name
        if getattr(root, 'included_serializers', None) is not None:
            includes = get_included_serializers(root)
            if field_name in includes.keys():
                resource_type = get_resource_type_from_serializer(includes[field_name])

        resource_type = resource_type if resource_type else get_resource_type_from_instance(value)
        return OrderedDict([('type', resource_type), ('id', str(pk))])


class ModelSerializer(JSONAPIModelSerializer):
    serializer_related_field = UUIDResourceRelatedField


class UUIDSerializerMixin(ModelSerializer):
    def to_representation(self, instance):
        # this might not do anything
        retval = super().to_representation(instance)
        retval = OrderedDict(('id', instance.uuid) if key == 'id' else (
            key, value) for key, value in retval.items())
        return retval
