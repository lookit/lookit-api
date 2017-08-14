import io
import csv
import json
import datetime
from guardian.shortcuts import get_objects_for_user
from guardian.mixins import PermissionRequiredMixin
from django.shortcuts import redirect

from studies.models import Study
from exp.views.mixins import ExperimenterLoginRequiredMixin
import get_study_attachments

class StudyResponsesMixin(ExperimenterLoginRequiredMixin, PermissionRequiredMixin, object):
    """
    Mixin with shared items for StudyResponsesList, StudyResponsesAll, and
    StudyAttachments Views
    """
    model = Study
    permission_required = 'studies.can_view_study_responses'
    raise_exception = True

    def convert_to_string(self, object):
        if isinstance(object, datetime.date):
            return object.__str__()
        return object

    def build_responses(self, responses):
        """
        Builds the JSON response data for the researcher to download
        """
        json_responses = []
        for resp in responses:
            latest_dem = resp.demographic_snapshot
            json_responses.append(json.dumps({
                'sequence': resp.sequence,
                'conditions': resp.conditions,
                'exp_data': resp.exp_data,
                'participant_id': resp.child.user.id,
                'global_event_timings': resp.global_event_timings,
                'child_id': resp.child.id,
                'completed': resp.completed,
                'study_id': resp.study.id,
                'response_id': resp.id,
                'participant': {
                    "participant_id": resp.child.user.id,
                    "demographics_info": {
                        "demographic_id": latest_dem.id,
                        "number_of_children": latest_dem.number_of_children,
                        "child_birthdays": latest_dem.child_birthdays,
                        "languages_spoken_at_home": latest_dem.languages_spoken_at_home,
                        "number_of_guardians": latest_dem.number_of_guardians,
                        "number_of_guardians_explanation": latest_dem.number_of_guardians_explanation,
                        "race_identification": latest_dem.race_identification,
                        "age": latest_dem.age,
                        "gender": latest_dem.gender,
                        "education_level": latest_dem.gender,
                        "spouse_education_level": latest_dem.spouse_education_level,
                        "annual_income": latest_dem.annual_income,
                        "number_of_books": latest_dem.number_of_books,
                        "additional_comments": latest_dem.additional_comments,
                        "country": latest_dem.country.name,
                        "state": latest_dem.state,
                        "density": latest_dem.density,
                        "extra": latest_dem.extra
                    }
                }}, indent=4, default = self.convert_to_string))
        return json_responses

    def csv_output_and_writer(self):
        output = io.StringIO()
        return output, csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)

    def csv_row_data(self, resp):
        """
        Builds individual row for csv responses
        """
        latest_dem = resp.demographic_snapshot
        return [resp.sequence, resp.conditions, resp.exp_data, resp.child.user.id,
            resp.global_event_timings, resp.child.id, resp.completed, resp.study.id, resp.id,
            resp.demographic_snapshot.id, latest_dem.number_of_children, [self.convert_to_string(birthday) for birthday in latest_dem.child_birthdays],
            latest_dem.languages_spoken_at_home, latest_dem.number_of_guardians, latest_dem.number_of_guardians_explanation,
            latest_dem.race_identification, latest_dem.age, latest_dem.gender, latest_dem.education_level, latest_dem.spouse_education_level,
            latest_dem.annual_income, latest_dem.number_of_books, latest_dem.additional_comments, latest_dem.country.name,
            latest_dem.state, latest_dem.density, latest_dem.extra
        ]

    def get_csv_headers(self):
        """
        Returns header row for csv data
        """
        return ['sequence', 'conditions', 'exp_data', 'participant_id', 'global_event_timings',
            'child_id', 'completed', 'study_id', 'response_id', 'demographic_id', 'number_of_children',
            'child_birthdays', 'languages_spoken_at_home', 'number_of_guardians', 'number_of_guardians_explanation',
            'race_identification', 'age', 'gender', 'education_level', 'spouse_education_level', 'annual_income',
            'number_of_books', 'additional_comments', 'country', 'state', 'density', 'extra']

    def post(self, request, *args, **kwargs):
        '''
        Downloads study video
        '''
        attachment = self.request.POST.get('attachment')
        if attachment:
            download_url = get_study_attachments.get_download_url(attachment)
            return redirect(download_url)

        return HttpResponseRedirect(reverse('exp:study-responses-list', kwargs=dict(pk=self.get_object().pk)))
