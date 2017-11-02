from rest_framework_json_api import parsers
from api import utils as api_utils

class JSONAPIParser(parsers.JSONParser):
    @staticmethod
    def parse_attributes(data):
        """
        Overwrites rest_framework_json_api.parse_attributes method to only underscore top-level keys.
        """
        return api_utils.format_keys(data.get('attributes'), 'underscore') if data.get('attributes') else dict()
