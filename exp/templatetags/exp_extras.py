import json

from django import template

register = template.Library()


@register.simple_tag
def query_transform(request, **kwargs):
    updated = request.GET.copy()

    acceptable_keys = ["state", "page", "match", "sort", "ageoptions", "childoptions"]

    for key in acceptable_keys:
        if kwargs.get(key):
            updated[key] = kwargs.get(key)

    # Assume it was not implemented like this (or as oneliner) for some sort of security reasons...
    # for (key, val) in kwargs.items():
    #    if val:
    #        updated[key] = val

    return updated.urlencode()


@register.filter
def get_key(dictionary, key):
    return dictionary.get(key, None)


@register.simple_tag
def values_list_as_json(queryset, attribute):
    return json.dumps(
        list(
            obj[attribute]
            if type(obj) is dict
            else getattr(obj, attribute)()
            if callable(attribute)
            else getattr(obj, attribute)
            for obj in queryset
        ),
        default=str,
    )


@register.simple_tag
def bit_is_set(bit_handler, bit_number):
    return bit_handler.get_bit(bit_number).is_set


@register.simple_tag
def get_bit_label(bit_handler, bit_number):
    return bit_handler.get_label(bit_number)


@register.filter
def pretty_json(value):
    return json.dumps(value, indent=4, default=str)
