import io
import csv
import json
from guardian.shortcuts import get_objects_for_user
from guardian.mixins import PermissionRequiredMixin

from studies.models import Study
from exp.views.mixins import ExperimenterLoginRequiredMixin

class StudyResponsesMixin(ExperimenterLoginRequiredMixin, PermissionRequiredMixin, object):
    """
    Mixin with shared items for StudyResponsesList and StudyResponsesAll views
    """
    model = Study
    permission_required = 'studies.can_view_study_responses'
    raise_exception = True

    def build_responses(self, responses):
        """
        Builds the JSON response data for the researcher to download
        """
        return [json.dumps({
            'sequence': resp.sequence,
            'conditions': resp.conditions,
            'exp_data': resp.exp_data,
            'participant_id': resp.child.user.id,
            'global_event_timings': resp.global_event_timings,
            'child_id': resp.child.id,
            'completed': resp.completed,
            'study_id': resp.study.id,
            'response_id': resp.id,
            'demographic_id': resp.demographic_snapshot.id
            }, indent=4) for resp in responses]

    def csv_output_and_writer(self):
        output = io.StringIO()
        return output, csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)

    def csv_row_data(self, resp):
        """
        Builds individual row for csv responses
        """
        return [resp.sequence, resp.conditions, resp.exp_data, resp.child.user.id,
        resp.global_event_timings, resp.child.id, resp.completed, resp.study.id, resp.id,
        resp.demographic_snapshot.id]

    def get_csv_headers(self):
        """
        Returns header row for csv data
        """
        return ['sequence', 'conditions', 'exp_data', 'participant_id', 'global_event_timings',
            'child_id', 'completed', 'study_id', 'response_id', 'demographic_id']
