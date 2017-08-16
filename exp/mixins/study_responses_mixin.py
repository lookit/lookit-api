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

class StudyResponsesMixin(ExperimenterLoginRequiredMixin, PermissionRequiredMixin):
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
                'response': {
                    'id': resp.id,
                    'sequence': resp.sequence,
                    'conditions': resp.conditions,
                    'exp_data': resp.exp_data,
                    'global_event_timings': resp.global_event_timings,
                    'completed': resp.completed,
                },
                'study': {
                    'id': resp.study.id
                },
                'participant': {
                    'id': resp.child.user_id,
                    'username': resp.child.user.given_name
                },
                'child': {
                    'id': resp.child.id,
                    'name': resp.child.given_name,
                    'birthday': resp.child.birthday,
                    'gender': resp.child.gender,
                    'age_at_birth': resp.child.age_at_birth,
                    'additional_information': resp.child.additional_information
                }}, indent=4, default = self.convert_to_string))
        return json_responses
# 'participant': {
#     "participant_id": resp.child.user.id,
#     "demographics_info": {
#         "demographic_id": latest_dem.id,
#         "number_of_children": latest_dem.number_of_children,
#         "child_birthdays": latest_dem.child_birthdays,
#         "languages_spoken_at_home": latest_dem.languages_spoken_at_home,
#         "number_of_guardians": latest_dem.number_of_guardians,
#         "number_of_guardians_explanation": latest_dem.number_of_guardians_explanation,
#         "race_identification": latest_dem.race_identification,
#         "age": latest_dem.age,
#         "gender": latest_dem.gender,
#         "education_level": latest_dem.gender,
#         "spouse_education_level": latest_dem.spouse_education_level,
#         "annual_income": latest_dem.annual_income,
#         "number_of_books": latest_dem.number_of_books,
#         "additional_comments": latest_dem.additional_comments,
#         "country": latest_dem.country.name,
#         "state": latest_dem.state,
#         "density": latest_dem.density,
#         "extra": latest_dem.extra
#     }
    # return [resp.sequence, resp.conditions, resp.exp_data, resp.child.user.id,
    #     resp.global_event_timings, resp.child.id, resp.completed, resp.study.id, resp.id,
    #     resp.demographic_snapshot.id, latest_dem.number_of_children, [self.convert_to_string(birthday) for birthday in latest_dem.child_birthdays],
    #     latest_dem.languages_spoken_at_home, latest_dem.number_of_guardians, latest_dem.number_of_guardians_explanation,
    #     latest_dem.race_identification, latest_dem.age, latest_dem.gender, latest_dem.education_level, latest_dem.spouse_education_level,
    #     latest_dem.annual_income, latest_dem.number_of_books, latest_dem.additional_comments, latest_dem.country.name,
    #     latest_dem.state, latest_dem.density, latest_dem.extra
    # ]
    # return [resp.sequence, resp.conditions, resp.exp_data, resp.child.user.id,
    #     resp.global_event_timings, resp.child.id, resp.completed, resp.study.id, resp.id,
    #     resp.demographic_snapshot.id, latest_dem.number_of_children, [self.convert_to_string(birthday) for birthday in latest_dem.child_birthdays],
    #     latest_dem.languages_spoken_at_home, latest_dem.number_of_guardians, latest_dem.number_of_guardians_explanation,
    #     latest_dem.race_identification, latest_dem.age, latest_dem.gender, latest_dem.education_level, latest_dem.spouse_education_level,
    #     latest_dem.annual_income, latest_dem.number_of_books, latest_dem.additional_comments, latest_dem.country.name,
    #     latest_dem.state, latest_dem.density, latest_dem.extra
    def csv_output_and_writer(self):
        output = io.StringIO()
        return output, csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)

    def csv_row_data(self, resp):
        """
        Builds individual row for csv responses
        """
        return [resp.id, resp.sequence, resp.conditions, resp.exp_data, resp.global_event_timings, resp.completed, resp.study.id,
            resp.child.user.id, resp.child.user.given_name, resp.child.id, resp.child.given_name, resp.child.birthday, resp.child.gender,
            resp.child.age_at_birth, resp.child.additional_information
        ]


    def get_csv_headers(self):
        """
        Returns header row for csv data
        """
        return ['response_id', 'response_sequence', 'response_conditions', 'response_exp_data', 'response_global_event_timings',
            'response_completed', 'study_id', 'participant_id', 'participant_username', 'child_id', 'child_name',
            'child_birthday', 'child_gender', 'child_age_at_birth', 'child_additional_information']

    def post(self, request, *args, **kwargs):
        '''
        Downloads study video
        '''
        attachment = self.request.POST.get('attachment')
        if attachment:
            download_url = get_study_attachments.get_download_url(attachment)
            return redirect(download_url)

        return HttpResponseRedirect(reverse('exp:study-responses-list', kwargs=dict(pk=self.get_object().pk)))
