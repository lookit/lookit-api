import os
import textwrap
from typing import Text

from django import template
from django.urls.base import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from accounts.forms import StudyListSearchForm
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
def google_tag_manager() -> Text:
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
def nav_item(request, url_name, text):
    li_class = ""
    url = reverse(url_name)

    if request.path == url:
        li_class = "active"

    return mark_safe(f'<li class="{li_class}"><a href="{url}">{_(text)}</a></li>')


@register.simple_tag
def nav_login(request, text="Login", button=False):
    """Login button suited for either navigation bar or as it's own button.

    Args:
        request (Request): Request object passed by the template.
        text (str, optional): Text to be displayed in button. Defaults to "Login".
        button (bool, optional): Should this login button be a button else it'll be styled as a link. Defaults to False.

    Returns:
        SafeText: Returned HTML is marked as safe.
    """
    url = reverse("login")

    if button:
        css_class = "btn btn-lg btn-default"
    else:
        css_class = "btn-link"

    form = f"""<form action="{url}" method="get">
    <button class="{css_class}" type="submit" value="login">{_(text)}</button>
    <input type="hidden" name="next" value="{request.path}" />
    </form>"""

    if not button:
        form = f"<li>{form}</li>"

    return mark_safe(form)


@register.simple_tag
def studies_tab_text(tabs):
    for tab in tabs:
        if tab.data["selected"]:
            value = tab.data["value"]
            if value == StudyListSearchForm.Tabs.all_studies.value[0]:
                return _(
                    "Lookit is growing! We are now showing links to outside studies along with those happening here on Lookit. Use the tabs above to see activities you can do right now, or scheduled activities you can sign up for.\n\nPlease note you'll need a laptop or desktop computer (not a mobile device) running Chrome or Firefox to participate, unless a specific study says otherwise."
                )
            elif value == StudyListSearchForm.Tabs.synchronous_studies.value[0]:
                return _(
                    'You and your child can participate in these studies right now by choosing a study and then clicking "Participate." Please note you\'ll need a laptop or desktop computer (not a mobile device) running Chrome or Firefox to participate, unless a specific study says otherwise.'
                )
            elif value == StudyListSearchForm.Tabs.asynchronous_studies.value[0]:
                return _(
                    'You and your child can participate in these studies by scheduling a time to meet with a researcher (usually over video conferencing). Choose a study and then click "Participate" to sign up for a study session in the future.'
                )
