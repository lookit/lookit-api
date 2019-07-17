import json

from django import template


register = template.Library()


@register.simple_tag
def query_transform(request, **kwargs):
    updated = request.GET.copy()

    state = kwargs.get("state")
    if state:
        updated["state"] = state

    if kwargs.get("page"):
        updated["page"] = kwargs.get("page")

    if kwargs.get("match"):
        updated["match"] = kwargs.get("match")

    if kwargs.get("sort"):
        updated["sort"] = kwargs.get("sort")

    return updated.urlencode()


@register.filter
def get_key(dictionary, key):
    return dictionary.get(key, None)


@register.simple_tag
def values_list_as_json(queryset, attribute):
    return json.dumps(
        list(
            getattr(obj, attribute)()
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
