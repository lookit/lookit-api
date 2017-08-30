import json
from collections import OrderedDict

import six
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.relations import reverse

from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import \
    ModelSerializer as JSONAPIModelSerializer
from rest_framework_json_api.utils import (get_included_serializers,
                                           get_resource_type_from_instance,
                                           get_resource_type_from_queryset,
                                           get_resource_type_from_serializer)


class UUIDResourceRelatedField(ResourceRelatedField):

    def __init__(self, self_link_view_name=None, related_link_view_name=None, **kwargs):
        if self_link_view_name is not None:
            self.self_link_view_name = self_link_view_name
        if related_link_view_name is not None:
            self.related_link_view_name = related_link_view_name

        self.related_link_lookup_field = kwargs.pop('related_link_lookup_field', self.related_link_lookup_field)
        self.related_link_url_kwarg = kwargs.pop('related_link_url_kwarg', self.related_link_lookup_field)

        self.many = kwargs.get('many', False)

        # check for a model class that was passed in for the relation type
        model = kwargs.pop('model', None)
        if model:
            self.model = model

        # We include this simply for dependency injection in tests.
        # We can't add it as a class attributes or it would expect an
        # implicit `self` argument to be passed.
        self.reverse = reverse

        super(ResourceRelatedField, self).__init__(**kwargs)

    def to_internal_value(self, data):
        if isinstance(data, six.text_type):
            try:
                data = json.loads(data)
            except ValueError:
                # show a useful error if they send a `pk` instead of resource object
                self.fail('incorrect_type', data_type=type(data).__name__)
        if not isinstance(data, dict):
            self.fail('incorrect_type', data_type=type(data).__name__)
        expected_relation_type = get_resource_type_from_queryset(self.queryset)

        if 'type' not in data:
            self.fail('missing_type')

        if 'id' not in data:
            self.fail('missing_id')

        if data['type'] != expected_relation_type:
            self.conflict('incorrect_relation_type', relation_type=expected_relation_type, received_type=data['type'])

        try:
            return self.get_queryset().get(uuid=data['id'])
        except ObjectDoesNotExist:
            self.fail('does_not_exist', pk_value=data)
        except (TypeError, ValueError):
            self.fail('incorrect_type', data_type=type(data).__name__)

    def to_representation(self, value):
        # force pk to be UUID
        pk = getattr(value, 'uuid', getattr(value, 'pk'))

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
        return OrderedDict([('type', resource_type.lower()), ('id', str(pk))])

    def get_links(self, obj=None, lookup_field='pk'):
        request = self.context.get('request', None)
        view = self.context.get('view', None)
        return_data = OrderedDict()
        lookup_field = getattr(obj.JSONAPIMeta, 'lookup_field', 'pk')

        kwargs = {lookup_field: getattr(obj, lookup_field) if obj else view.kwargs[lookup_field]}

        self_kwargs = kwargs.copy()
        self_kwargs.update({'related_field': self.field_name if self.field_name else self.parent.field_name})
        self_link = self.get_url('self', self.self_link_view_name, self_kwargs, request)

        if not self.many and obj and hasattr(obj, self.field_name) and hasattr(getattr(obj, self.field_name), self.related_link_lookup_field):
            # individual relationships should be referenced by their canonical URL
            related_kwargs = {self.related_link_url_kwarg: getattr(getattr(obj, self.field_name), self.related_link_lookup_field)}
        else:
            related_kwargs = {self.related_link_url_kwarg: kwargs[self.related_link_lookup_field]}

        related_link = self.get_url('related', self.related_link_view_name, related_kwargs, request)

        if self_link:
            return_data.update({'self': self_link})
        if related_link:
            return_data.update({'related': related_link})
        return return_data


class ModelSerializer(JSONAPIModelSerializer):
    serializer_related_field = UUIDResourceRelatedField


class UUIDSerializerMixin(ModelSerializer):
    def to_representation(self, instance):
        # this might not do anything
        retval = super().to_representation(instance)
        retval = OrderedDict(('id', instance.uuid) if key == 'id' else (
            key, value) for key, value in retval.items())
        return retval
