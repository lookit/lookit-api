from django import template

from accounts.queries import get_child_eligibility_for_study

register = template.Library()


@register.simple_tag
def child_is_valid_for_study(child, study):
    return get_child_eligibility_for_study(child, study)
