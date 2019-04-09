from django.conf import settings
from storages.backends.gcloud import GoogleCloudStorage
from storages.utils import clean_name


# class LocationPrefixedPublicGoogleCloudStorage(GoogleCloudStorage):
#     location = None
#
#     def _normalize_name(self, name):
#         if self.location:
#             return super()._normalize_name(safe_join(self.location, name))
#         return super()._normalize_name(name.lower())
#
#     def url(self, name):
#         """
#         The parent implementation calls GoogleCloudStorage on every request
#         once for oauth and again to get the file. Since we're proxying requests
#         through nginx's proxy_pass to GoogleCloudStorage we don't need their url
#         nonsense or to use the actual domain or bucket name.
#         """
#         name = self._normalize_name(clean_name(name))
#         return f"/{name.lstrip('/')}"
#
#
# class LowercaseNameMixin(GoogleCloudStorage):
#     def _normalize_name(self, name):
#         return super()._normalize_name(name.lower())


class LookitGoogleCloudStorage(GoogleCloudStorage):
    """Overrides to compensate for the fact that we're proxying requests through nginx's proxypass."""

    def _normalize_name(self, name):
        return super()._normalize_name(name.lower())

    def url(self, name):
        """
        The parent implementation calls GoogleCloudStorage on every request
        once for oauth and again to get the file. Since we're proxying requests
        through nginx's proxy_pass to GoogleCloudStorage we don't need their url
        nonsense or to use the actual domain or bucket name.
        """
        name = self._normalize_name(name)
        return f"/{name.lstrip('/')}"


class LookitStaticStorage(LookitGoogleCloudStorage):
    location = settings.STATICFILES_LOCATION


class LookitMediaStorage(LookitGoogleCloudStorage):
    location = settings.MEDIAFILES_LOCATION


class LookitExperimentStorage(LookitGoogleCloudStorage):
    location = settings.EXPERIMENT_LOCATION


class LookitPreviewExperimentStorage(LookitGoogleCloudStorage):
    location = settings.PREVIEW_EXPERIMENT_LOCATION
