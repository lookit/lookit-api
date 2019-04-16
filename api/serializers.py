from rest_framework import serializers
from collections import OrderedDict
from operator import attrgetter

from rest_framework.relations import (
    PrimaryKeyRelatedField,
    RelatedField,
    MANY_RELATION_KWARGS,
)

from rest_framework_json_api.relations import (
    ResourceRelatedField,
    HyperlinkedMixin,
    SkipDataMixin,
    ManyRelatedFieldWithNoData,
)
from rest_framework_json_api.serializers import (
    ModelSerializer,
    HyperlinkedModelSerializer,
)


# Related fields only.
class UuidRelatedField(PrimaryKeyRelatedField):
    def use_pk_only_optimization(self):
        """We do not want to use the dummy PKOnly Object, or else to_representation will break."""
        return False


class DotPropertyRelatedLookupHyperlinkedMixin(HyperlinkedMixin):
    """Exists for the sheer purpose of overriding the get_links method."""

    def get_links(self, obj=None, lookup_field="some_model.nested_property"):
        """Improving the behavior of get_links to enable nested attribute fetches in kwargs, like so:

        child = PatchedResourceRelatedField(
            queryset=Child.objects,
            related_link_view_name="child-detail",
            related_link_lookup_field="child.uuid",  <--- dot syntax
            related_link_url_kwarg="uuid",
        )

        This is a near-copy of the original method located in the HyperlinkedMixin class.
        """
        request = self.context.get("request", None)
        view = self.context.get("view", None)
        return_data = OrderedDict()

        kwargs = {
            lookup_field: attrgetter(lookup_field)(obj)
            # Above is literally the single changed line of code.
            if obj
            else view.kwargs[lookup_field]
        }

        self_kwargs = kwargs.copy()
        self_kwargs.update(
            {
                "related_field": self.field_name
                if self.field_name
                else self.parent.field_name
            }
        )
        self_link = self.get_url("self", self.self_link_view_name, self_kwargs, request)

        # Assuming RelatedField will be declared in two ways:
        # 1. url(r'^authors/(?P<pk>[^/.]+)/(?P<related_field>\w+)/$',
        #         AuthorViewSet.as_view({'get': 'retrieve_related'}))
        # 2. url(r'^authors/(?P<author_pk>[^/.]+)/bio/$',
        #         AuthorBioViewSet.as_view({'get': 'retrieve'}))
        # So, if related_link_url_kwarg == 'pk' it will add 'related_field' parameter to reverse()
        if self.related_link_url_kwarg == "pk":
            related_kwargs = self_kwargs
        else:
            related_kwargs = {
                self.related_link_url_kwarg: kwargs[self.related_link_lookup_field]
            }

        related_link = self.get_url(
            "related", self.related_link_view_name, related_kwargs, request
        )

        if self_link:
            return_data.update({"self": self_link})
        if related_link:
            return_data.update({"related": related_link})
        return return_data


class PatchedResourceRelatedField(ResourceRelatedField):
    """Shoo-in for rest_framework_json_api.relations.ResourceRelatedField, with better get_links behavior."""

    def to_representation(self, value):
        """ID becomes UUID in the frontend."""
        representation = super().to_representation(value)
        representation["id"] = value.uuid
        return representation


# Hyperlinked Fields.
class PatchedHyperlinkedRelatedField(
    DotPropertyRelatedLookupHyperlinkedMixin, SkipDataMixin, RelatedField
):
    """"Shoo-in for rest_framework_json_api.relations.HyperlinkedRelatedField, with better get_links behavior."""

    @classmethod
    def many_init(cls, *args, **kwargs):
        """XXX: Direct copy of many_init from rest_framework_json_api.relations.HyperlinkedRelatedField.

        Style checkers will see this class and worry about you not having overridden to_representation. This dynamic
        "new"-ing of the class with many_init acts like a factory for ManyRelatedFieldWithNoData, which is how we can
        get away with this.
        """
        list_kwargs = {"child_relation": cls(*args, **kwargs)}
        for key in kwargs:
            if key in MANY_RELATION_KWARGS:
                list_kwargs[key] = kwargs[key]
        return ManyRelatedFieldWithNoData(**list_kwargs)


# Serializers.
class UuidHyperlinkedModelSerializer(HyperlinkedModelSerializer):
    """Ensuring that pk is never shown, but UUID is used instead.

    Per the docstring of the DJA class we're inheriting from:

    If the `ModelSerializer` class *doesn't* generate the set of fields that
    you need you should either declare the extra/differing fields explicitly on
    the serializer class, or simply use a `Serializer` class.
    """

    serializer_related_field = PatchedHyperlinkedRelatedField

    uuid = serializers.UUIDField(source="uuid", read_only=True)


class UuidResourceModelSerializer(ModelSerializer):
    """Same as above, but no hyperlink shortcut."""

    serializer_related_field = PatchedResourceRelatedField

    uuid = serializers.UUIDField(source="uuid", read_only=True)
