"""Custom Widgets for Study views.

Toggle Widget stolen shamelessly from https://blog.ihfazh.com/django-custom-widget-with-3-examples.html and modified
forthwith to support multiple checkboxes.
"""
from bitfield.forms import BitFieldCheckboxSelectMultiple
from django import forms


class ToggleWidget(BitFieldCheckboxSelectMultiple):
    class Media:
        css = {
            "all": (
                "https://gitcdn.github.io/bootstrap-toggle/2.2.2/css/bootstrap-toggle.min.css",
            )
        }
        js = (
            "https://gitcdn.github.io/bootstrap-toggle/2.2.2/js/bootstrap-toggle.min.js",
        )

    def __init__(self, attrs=None, *args, **kwargs):
        attrs = attrs or {}

        default_options = {"toggle": "toggle", "offstyle": "danger"}
        options = kwargs.get("options", {})
        default_options.update(options)
        for key, val in default_options.items():
            attrs["data-" + key] = val

        super().__init__(attrs)
