from django.conf import settings

from storages.backends.gcloud import GoogleCloudStorage
from storages.utils import safe_join


class LocationPrefixedGoogleCloudStorage(GoogleCloudStorage):
    location = None

    def _normalize_name(self, name):
        if self.location:
            return super()._normalize_name(safe_join(self.location, name.lower()))
        return super()._normalize_name(name.lower())


class LookitStaticStorage(LocationPrefixedGoogleCloudStorage):
    location = settings.STATICFILES_LOCATION


class LookitMediaStorage(LocationPrefixedGoogleCloudStorage):
    location = settings.MEDIAFILES_LOCATION
