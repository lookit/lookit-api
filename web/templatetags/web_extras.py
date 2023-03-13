import textwrap
from typing import Text

from django import template
from django.urls.base import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from accounts.forms import StudyListSearchForm
from accounts.queries import get_child_eligibility
from project.settings import GOOGLE_TAG_MANAGER_ID

register = template.Library()


def format(text: Text) -> Text:
    if GOOGLE_TAG_MANAGER_ID:
        return mark_safe(textwrap.dedent(text))
    else:
        return ""


def active_nav(request, url) -> bool:
    """Determine is this button is the active button in the navigation bar.

    Args:
        request (Request): Request object from template
        url (Text): String url for the current view

    Returns:
        boolean: returns true if this path is active
    """
    return request.path == url


def nav_next(request, url, text, button):
    """Create form that will submit the current page as the "next" query arg.

    Args:
        request (Request): Request object submitted from template
        url (Text): Target URL
        text (Text): String to be displayed is button
        button (bool): Is this to be styled as a button or as a link

    Returns:
        SafeText: Returns html form used to capture current view and submit it as the "next" query arg
    """
    active = active_nav(request, url)

    if button:
        css_class = "nav-link navbar-link link-secondary border-0 text-center"
    elif active:
        css_class = "btn active btn-secondary btn-link"
    else:
        css_class = "btn btn-link"

    form = f"""<form action="{url}" method="get">
    <button class="{css_class}" type="submit" value="login">{_(text)}</button>
    <input type="hidden" name="next" value="{request.path}" />
    </form>"""

    if not button:
        form = f"""<li>{form}</li>"""

    return mark_safe(form)


@register.simple_tag
def child_is_valid_for_study_criteria_expression(child, study):
    return get_child_eligibility(child, study.criteria_expression)


@register.simple_tag
def google_tag_manager() -> Text:
    return format(
        f"""
    <!-- Google tag (gtag.js) - Google Analytics -->
    <script async src="https://www.googletagmanager.com/gtag/js?id={GOOGLE_TAG_MANAGER_ID}"></script>
    <script>
        window.dataLayer = window.dataLayer || [];
        function gtag(){{dataLayer.push(arguments);}}
        gtag('js', new Date());
        gtag('config', '{GOOGLE_TAG_MANAGER_ID}');
    </script>
    """
    )


@register.simple_tag
def nav_link(request, url_name, text, html_classes=None):
    """General navigation bar item

    Args:
        request (Request): Reqeust submitted from template
        url_name (Text): Name of url to be looked up by reverse
        text (Text): Text to be displayed in item

    Returns:
        SafeText: HTML of navigation item
    """
    if html_classes is None:
        html_classes = [
            "nav-link",
            "navbar-link",
            "link-secondary",
            "text-center",
            "px-3",
        ]
    url = reverse(url_name)
    aria_current = ""
    if active_nav(request, url):
        html_classes.extend(["active", "btn-secondary"])
        aria_current = ' aria-current="page"'

    return mark_safe(
        f'<a class="{" ".join(html_classes)}"{aria_current} href="{url}">{_(text)}</a>'
    )


@register.simple_tag
def dropdown_item(request, url_name, text):
    return nav_link(request, url_name, text, ["dropdown-item"])


@register.simple_tag
def nav_login(request, text="Login", button=False):
    """Navigation login button

    Args:
        request (Request): Request object submitted by template
        text (str, optional): Text to be shown in button. Defaults to "Login".
        button (bool, optional): Is this to be styled as a button or as a link. Defaults to False.

    Returns:
        SafeText: HTML form
    """
    url = reverse("login")
    return nav_next(request, url, text, button)


@register.simple_tag
def nav_signup(request, text="Sign up", button=False):
    """Navigation sign up button

    Args:
        request (Request): Request object submitted by template
        text (str, optional): Text to be shown in button. Defaults to "Login".
        button (bool, optional): Is this to be styled as a button or as a link. Defaults to False.

    Returns:
        SafeText: HTML form
    """
    url = reverse("web:participant-signup")
    return nav_next(request, url, text, button)


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


@register.filter(name="studies_tab_selected")
def studies_tab_selected(value):
    for tab in value:
        if tab.data["selected"]:
            return tab.data["value"]
