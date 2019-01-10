from guardian.mixins import LoginRequiredMixin
from django.conf import settings
from studies.models import StudyType

import requests


class ExperimenterLoginRequiredMixin(LoginRequiredMixin):
    login_url = settings.EXPERIMENTER_LOGIN_URL


class StudyTypeMixin:

    def validate_and_store_metadata(self):
        study = self.get_object()
        study_type = StudyType.objects.get(id=self.request.POST.get('study_type'))
        metadata = self.extract_type_metadata(study_type=study_type)

        if VALIDATIONS.get(study_type, is_valid_ember_frame_player)(metadata):  # fix this switch later
            study.metadata = metadata
            return True
        else:
            return False

    def extract_type_metadata(self, study_type=None):
        """
        Pull the metadata related to the selected StudyType from the POST request
        """
        if not study_type:
            study_type = StudyType.objects.get(id=self.request.POST.get('study_type'))

        type_fields = study_type.configuration['metadata']['fields']

        metadata = {}

        for key in type_fields:
            metadata[key] = self.request.POST.get(key, None)

        return metadata


def is_valid_ember_frame_player(metadata):

    addons_repo_url = metadata.get('addons_repo_url', settings.EMBER_ADDONS_REPO)
    frameplayer_commit_sha = metadata.get('last_known_player_sha', '')
    addons_commit_sha = metadata.get('last_known_addons_sha', '')

    return (
        requests.get(addons_repo_url).ok and
        requests.get(f'{settings.EMBER_EXP_PLAYER_REPO}/commit/{frameplayer_commit_sha}').ok and
        requests.get(f'{settings.EMBER_ADDONS_REPO}/commit/{addons_commit_sha}').ok
    )


VALIDATIONS = {
    'foo': is_valid_ember_frame_player
}
