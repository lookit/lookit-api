from guardian.mixins import LoginRequiredMixin
from django.conf import settings
from studies.models import StudyType


class ExperimenterLoginRequiredMixin(LoginRequiredMixin):
    login_url = settings.EXPERIMENTER_LOGIN_URL

class StudyTypeMixin():

    def extract_type_metadata(self):
        """
        Pull the metadata related to the selected StudyType from the POST request
        """
        study_type = StudyType.objects.get(id=self.request.POST.get('study_type'))
        type_fields = study_type.configuration['metadata']['fields']
        metadata = {}
        for key in type_fields:
            metadata[key] = self.request.POST.get(key, None)
        return metadata
