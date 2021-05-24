import os
import textwrap
from typing import Text

from django import template
from django.utils.safestring import mark_safe

from accounts.queries import get_child_eligibility
from project.settings import DEBUG

register = template.Library()

GOOGLE_TAG_MANAGER_ID = os.environ.get("GOOGLE_TAG_MANAGER_ID", "")


def format(text: Text) -> Text:
    if not DEBUG and GOOGLE_TAG_MANAGER_ID:
        return mark_safe(textwrap.dedent(text))
    else:
        return ""


@register.simple_tag
def child_is_valid_for_study_criteria_expression(child, study):
    return get_child_eligibility(child, study.criteria_expression)


@register.simple_tag
def google_tag_manager_head() -> Text:
    return format(
        f"""
    <script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
    new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
    j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
    'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
    }})(window,document,'script','dataLayer','{GOOGLE_TAG_MANAGER_ID}');</script>
    """
    )


@register.simple_tag
def google_tag_manager_body() -> Text:
    return format(
        f"""
    <noscript><iframe src="https://www.googletagmanager.com/ns.html?id={GOOGLE_TAG_MANAGER_ID}"
    height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
    """
    )
