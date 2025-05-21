from django.contrib.staticfiles.storage import ManifestFilesMixin
from storages.backends.gcloud import GoogleCloudStorage


class LookitGoogleCloudStorage(GoogleCloudStorage):
    """Overrides to compensate for the fact that we're proxying requests through nginx's proxypass."""

    def _normalize_name(self, name):
        return super()._normalize_name(name.lower())

    def url(self, name):
        """Override for the URL getter function.

        Since we're proxying requests through nginx's proxy_pass to GCS, we can avoid blob
        creation and the signed url generation that might happen otherwise (see parent implementation for details).
        """
        name = self._normalize_name(name)
        return f"/{name.lstrip('/')}"


class LookitStaticStorage(ManifestFilesMixin, LookitGoogleCloudStorage):
    pass


class LookitMediaStorage(LookitGoogleCloudStorage):
    pass


class LookitExperimentStorage(LookitGoogleCloudStorage):
    # location = settings.EXPERIMENT_LOCATION
    pass


class LowercaseGoogleCloudStorage(GoogleCloudStorage):
    def get_available_name(self, name, max_length=None):
        return super().get_available_name(name.lower(), max_length)
