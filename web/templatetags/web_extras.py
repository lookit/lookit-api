from django import template

from accounts.queries import get_child_eligibility

register = template.Library()


@register.simple_tag
def child_is_valid_for_study_criteria_expression(child, study):
    return get_child_eligibility(child, study.criteria_expression)
