import textwrap
from typing import Text

from django import template
from django.utils.safestring import mark_safe

from accounts.queries import get_child_eligibility
from project import settings

register = template.Library()


@register.simple_tag
def child_is_valid_for_study_criteria_expression(child, study):
    return get_child_eligibility(child, study.criteria_expression)


@register.simple_tag
def google_analytics() -> Text:
    if not settings.DEBUG:
        ga_js = textwrap.dedent(
            """
                <script async src="https://www.googletagmanager.com/gtag/js?id=UA-163886699-1"></script>
                <script>
                window.dataLayer = window.dataLayer || [];
                function gtag(){dataLayer.push(arguments);}
                gtag('js', new Date());
                gtag('config', 'UA-163886699-1');
                </script>
            """
        )
        return mark_safe(ga_js)
    else:
        return ""
