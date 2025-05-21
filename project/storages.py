from storages.backends.gcloud import GoogleCloudStorage

from project import settings


class LowercaseGoogleCloudStorage(GoogleCloudStorage):
    def get_available_name(self, name, max_length=None):
        # Lowercase the file name and the additional text google adds when
        # there's a name collision.
        return super().get_available_name(name.lower(), max_length).lower()


class LookitExperimentStorage(LowercaseGoogleCloudStorage):
    location = settings.EXPERIMENT_LOCATION
