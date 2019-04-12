"""
Renderers
"""

from rest_framework_json_api.renderers import JSONRenderer


class JsonApiWithUuidRenderer(JSONRenderer):
    @classmethod
    def extract_attributes(cls, fields, resource):
        obj = super().extract_attributes(fields, resource)
        obj["pk"] = resource.get("pk")
        return obj

    @classmethod
    def build_json_resource_obj(
        cls, fields, resource, resource_instance, *args, **kwargs
    ):
        obj = super().build_json_resource_obj(
            fields, resource, resource_instance, *args, **kwargs
        )
        obj["id"] = str(resource_instance.uuid)
        return obj
