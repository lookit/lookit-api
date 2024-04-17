from collections import OrderedDict

import inflection
from rest_framework.settings import api_settings


def format_keys(obj, format_type=None):
    """
    Overwrites rest_framework_json_api/utils.py

    Does not recursively format dictionary keys. Only top level keys are formatted.

    :format_type: Either 'dasherize', 'camelize' or 'underscore'
    """
    if format_type is None:
        format_type = getattr(api_settings, "JSON_API_FORMAT_KEYS", False)

    if format_type in ("dasherize", "camelize", "underscore", "capitalize"):
        if isinstance(obj, dict):
            formatted = OrderedDict()
            for key, value in obj.items():
                if format_type == "dasherize":
                    # inflection can't dasherize camelCase
                    key = inflection.underscore(key)
                    formatted[inflection.dasherize(key)] = value
                elif format_type == "camelize":
                    formatted[inflection.camelize(key, False)] = value
                elif format_type == "capitalize":
                    formatted[inflection.camelize(key)] = value
                elif format_type == "underscore":
                    formatted[inflection.underscore(key)] = value
            return formatted
        if isinstance(obj, list):
            return [format_keys(item, format_type) for item in obj]
        else:
            return obj
    else:
        return obj
