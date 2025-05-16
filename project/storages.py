from django.conf import settings
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
    location = settings.STATICFILES_LOCATION


class LookitMediaStorage(LookitGoogleCloudStorage):
    location = settings.MEDIAFILES_LOCATION
    # See https://github.com/lookit/lookit-api/issues/570
    file_overwrite = False


class LookitExperimentStorage(LookitGoogleCloudStorage):
    location = settings.EXPERIMENT_LOCATION
