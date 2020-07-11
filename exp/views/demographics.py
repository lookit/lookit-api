import json

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.views import generic

from accounts.utils import hash_demographic_id, hash_participant_id
from exp.utils import (
    RESPONSE_PAGE_SIZE,
    csv_dict_output_and_writer,
    round_ages_from_birthdays,
    study_name_for_files,
)
from exp.views.mixins import (
    CanViewStudyResponsesMixin,
    SingleObjectParsimoniousQueryMixin,
)
from studies.models import Study


class StudyDemographics(
    CanViewStudyResponsesMixin, SingleObjectParsimoniousQueryMixin, generic.DetailView
):
    """
    StudyDemographics view shows participant demographic snapshots associated
    with each response to the study
    """

    template_name = "studies/study_demographics.html"
    queryset = Study.objects.all()

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.  Study results
        are paginated.
        """
        context = super().get_context_data(**kwargs)
        context["n_responses"] = (
            context["study"].responses_for_researcher(self.request.user).count()
        )
        return context

    def get_demographic_headers(self, optional_header_ids=None):
        if optional_header_ids == None:
            optional_header_ids = []
        optional_header_ids_to_columns = {"globalparent": "participant_global_id"}
        all_headers = self.get_csv_demographic_row_and_headers()["headers"]
        selected_headers = [
            optional_header_ids_to_columns[id]
            for id in optional_header_ids
            if id in optional_header_ids_to_columns
        ]
        optional_headers = optional_header_ids_to_columns.values()
        return [
            h for h in all_headers if h not in optional_headers or h in selected_headers
        ]

    def get_response_values_for_demographics(self, study):
        return (
            study.responses_for_researcher(self.request.user)
            .order_by("id")
            .select_related("child", "child__user", "study", "demographic_snapshot")
            .values(
                "uuid",
                "date_created",
                "child__user__uuid",
                "study__uuid",
                "study__salt",
                "study__hash_digits",
                "demographic_snapshot__uuid",
                "demographic_snapshot__created_at",
                "demographic_snapshot__number_of_children",
                "demographic_snapshot__child_birthdays",
                "demographic_snapshot__languages_spoken_at_home",
                "demographic_snapshot__number_of_guardians",
                "demographic_snapshot__number_of_guardians_explanation",
                "demographic_snapshot__race_identification",
                "demographic_snapshot__age",
                "demographic_snapshot__gender",
                "demographic_snapshot__education_level",
                "demographic_snapshot__spouse_education_level",
                "demographic_snapshot__annual_income",
                "demographic_snapshot__number_of_books",
                "demographic_snapshot__additional_comments",
                "demographic_snapshot__country",
                "demographic_snapshot__state",
                "demographic_snapshot__density",
                "demographic_snapshot__lookit_referrer",
                "demographic_snapshot__extra",
            )
        )

    def get_csv_demographic_row_and_headers(self, resp=None):
        """
        Returns dict with headers, row data dict, and description dict for csv participant data associated with a
        response
        """

        all_row_data = [
            (
                "response_uuid",
                str(resp["uuid"]) if resp else "",
                (
                    "Primary unique identifier for response. Can be used to match demographic data to response data "
                    "and video filenames; must be redacted prior to publication if videos are also published."
                ),
            ),
            (
                "participant_global_id",
                str(resp["child__user__uuid"]) if resp else "",
                (
                    "Unique identifier for family account associated with this response. Will be the same for multiple "
                    "responses from a child and for siblings, and across different studies. MUST BE REDACTED FOR "
                    "PUBLICATION because this allows identification of families across different published studies, "
                    "which may have unintended privacy consequences. Researchers can use this ID to match participants "
                    "across studies (subject to their own IRB review), but would need to generate their own random "
                    "participant IDs for publication in that case. Use participant_hashed_id as a publication-safe "
                    "alternative if only analyzing data from one Lookit study."
                ),
            ),
            (
                "participant_hashed_id",
                hash_participant_id(resp) if resp else "",
                (
                    "Identifier for family account associated with this response. Will be the same for multiple "
                    "responses from a child and for siblings, but is unique to this study. This may be published "
                    "directly."
                ),
            ),
            (
                "demographic_hashed_id",
                hash_demographic_id(resp) if resp else "",
                (
                    "Identifier for this demographic snapshot. Changes upon updates to the demographic form, "
                    "so may vary within the same participant across responses."
                ),
            ),
            (
                "demographic_date_created",
                str(resp["demographic_snapshot__created_at"]) if resp else "",
                (
                    "Timestamp of creation of the demographic snapshot associated with this response, in format e.g. "
                    "2019-10-02 21:39:03.713283+00:00"
                ),
            ),
            (
                "demographic_number_of_children",
                resp["demographic_snapshot__number_of_children"] if resp else "",
                "Response to 'How many children do you have?'; options 0-10 or >10 (More than 10)",
            ),
            (
                "demographic_child_rounded_ages",
                round_ages_from_birthdays(
                    resp["demographic_snapshot__child_birthdays"], resp["date_created"]
                )
                if resp
                else "",
                (
                    "List of rounded ages based on child birthdays entered in demographic form (not based on children "
                    "registered). Ages are at time of response for this row, in days, rounded to nearest 10 for ages "
                    "under 1 year and nearest 30 otherwise. In format e.g. [60, 390]"
                ),
            ),
            (
                "demographic_languages_spoken_at_home",
                resp["demographic_snapshot__languages_spoken_at_home"] if resp else "",
                "Freeform response to 'What language(s) does your family speak at home?'",
            ),
            (
                "demographic_number_of_guardians",
                resp["demographic_snapshot__number_of_guardians"] if resp else "",
                "Response to 'How many parents/guardians do your children live with?' - 1, 2, 3> [3 or more], varies",
            ),
            (
                "demographic_number_of_guardians_explanation",
                resp["demographic_snapshot__number_of_guardians_explanation"]
                if resp
                else "",
                (
                    "Freeform response to 'If the answer varies due to shared custody arrangements or travel, please "
                    "enter the number of parents/guardians your children are usually living with or explain.'"
                ),
            ),
            (
                "demographic_race_identification",
                resp["demographic_snapshot__race_identification"] if resp else "",
                (
                    "Comma-separated list of all values checked for question 'What category(ies) does your family "
                    "identify as?', from list:  White; Hispanic, Latino, or Spanish origin; Black or African American; "
                    "Asian; American Indian or Alaska Native; Middle Eastern or North African; Native Hawaiian or "
                    "Other Pacific Islander; Another race, ethnicity, or origin"
                ),
            ),
            (
                "demographic_age",
                resp["demographic_snapshot__age"] if resp else "",
                (
                    "Parent's response to question 'What is your age?'; options are <18, 18-21, 22-24, 25-29, 30-34, "
                    "35-39, 40-44, 45-49, 50s, 60s, >70"
                ),
            ),
            (
                "demographic_gender",
                resp["demographic_snapshot__gender"] if resp else "",
                (
                    "Parent's response to question 'What is your gender?'; options are m [male], f [female], o "
                    "[other], na [prefer not to answer]"
                ),
            ),
            (
                "demographic_education_level",
                resp["demographic_snapshot__education_level"] if resp else "",
                (
                    "Parent's response to question 'What is the highest level of education you've completed?'; options "
                    "are some [some or attending high school], hs [high school diploma or GED], col [some or attending "
                    "college], assoc [2-year college degree], bach [4-year college degree], grad [some or attending "
                    "graduate or professional school], prof [graduate or professional degree]"
                ),
            ),
            (
                "demographic_spouse_education_level",
                resp["demographic_snapshot__spouse_education_level"] if resp else "",
                (
                    "Parent's response to question 'What is the highest level of education your spouse has "
                    "completed?'; options are some [some or attending high school], hs [high school diploma or GED], "
                    "col [some or attending college], assoc [2-year college degree], bach [4-year college degree], "
                    "grad [some or attending graduate or professional school], prof [graduate or professional degree], "
                    "na [not applicable - no spouse or partner]"
                ),
            ),
            (
                "demographic_annual_income",
                resp["demographic_snapshot__annual_income"] if resp else "",
                (
                    "Parent's response to question 'What is your approximate family yearly income (in US dollars)?'; "
                    "options are 0, 5000, 10000, 15000, 20000-19000 in increments of 10000, >200000, or na [prefer not "
                    "to answer]"
                ),
            ),
            (
                "demographic_number_of_books",
                resp["demographic_snapshot__number_of_books"] if resp else "",
                "Parent's response to question 'About how many children's books are there in your home?'; integer",
            ),
            (
                "demographic_additional_comments",
                resp["demographic_snapshot__additional_comments"] if resp else "",
                "Parent's freeform response to question 'Anything else you'd like us to know?'",
            ),
            (
                "demographic_country",
                resp["demographic_snapshot__country"] if resp else "",
                "Parent's response to question 'What country do you live in?'; 2-letter country code",
            ),
            (
                "demographic_state",
                resp["demographic_snapshot__state"] if resp else "",
                (
                    "Parent's response to question 'What state do you live in?' if country is US; 2-letter state "
                    "abbreviation"
                ),
            ),
            (
                "demographic_density",
                resp["demographic_snapshot__density"] if resp else "",
                (
                    "Parent's response to question 'How would you describe the area where you live?'; options are "
                    "urban, suburban, rural"
                ),
            ),
            (
                "demographic_lookit_referrer",
                resp["demographic_snapshot__lookit_referrer"] if resp else "",
                "Parent's freeform response to question 'How did you hear about Lookit?'",
            ),
        ]

        headers = [name for (name, val, desc) in all_row_data]
        row_data_with_headers = {name: val for (name, val, desc) in all_row_data}
        field_descriptions = {name: desc for (name, val, desc) in all_row_data}

        return {
            "headers": headers,
            "descriptions": field_descriptions,
            "dict": row_data_with_headers,
        }


class StudyDemographicsJSON(StudyDemographics):
    """
    Hitting this URL downloads all participant demographics in JSON format.
    """

    def build_demographic_json(self, responses, optional_headers=None):
        """
        Builds a JSON representation of demographic snapshots for download
        """
        json_responses = []
        if optional_headers == None:
            optional_headers = []
        paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                json_responses.append(
                    json.dumps(
                        {
                            "response": {"uuid": str(resp["uuid"])},
                            "participant": {
                                "global_id": str(resp["child__user__uuid"])
                                if "globalparent" in optional_headers
                                else "",
                                "hashed_id": hash_participant_id(resp),
                            },
                            "demographic_snapshot": {
                                "hashed_id": hash_demographic_id(resp),
                                "date_created": str(
                                    resp["demographic_snapshot__created_at"]
                                ),
                                "number_of_children": resp[
                                    "demographic_snapshot__number_of_children"
                                ],
                                "child_rounded_ages": round_ages_from_birthdays(
                                    resp["demographic_snapshot__child_birthdays"],
                                    resp["date_created"],
                                ),
                                "languages_spoken_at_home": resp[
                                    "demographic_snapshot__languages_spoken_at_home"
                                ],
                                "number_of_guardians": resp[
                                    "demographic_snapshot__number_of_guardians"
                                ],
                                "number_of_guardians_explanation": resp[
                                    "demographic_snapshot__number_of_guardians_explanation"
                                ],
                                "race_identification": resp[
                                    "demographic_snapshot__race_identification"
                                ],
                                "age": resp["demographic_snapshot__age"],
                                "gender": resp["demographic_snapshot__gender"],
                                "education_level": resp[
                                    "demographic_snapshot__education_level"
                                ],
                                "spouse_education_level": resp[
                                    "demographic_snapshot__spouse_education_level"
                                ],
                                "annual_income": resp[
                                    "demographic_snapshot__annual_income"
                                ],
                                "number_of_books": resp[
                                    "demographic_snapshot__number_of_books"
                                ],
                                "additional_comments": resp[
                                    "demographic_snapshot__additional_comments"
                                ],
                                "country": resp["demographic_snapshot__country"],
                                "state": resp["demographic_snapshot__state"],
                                "density": resp["demographic_snapshot__density"],
                                "lookit_referrer": resp[
                                    "demographic_snapshot__lookit_referrer"
                                ],
                                "extra": resp["demographic_snapshot__extra"],
                            },
                        },
                        indent=4,
                    )
                )
        return json_responses

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = self.get_response_values_for_demographics(study)
        header_options = self.request.GET.getlist("demooptions")
        cleaned_data = ", ".join(self.build_demographic_json(responses, header_options))
        filename = "{}_{}.json".format(
            study_name_for_files(study.name), "all-demographic-snapshots"
        )
        response = HttpResponse(cleaned_data, content_type="text/json")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyDemographicsCSV(StudyDemographics):
    """
    Hitting this URL downloads all participant demographics in CSV format.
    """

    def build_all_demographic_csv(self, responses, optional_header_ids=None):
        """
        Builds CSV file contents for all participant data
        """

        participant_list = []
        these_headers = self.get_demographic_headers(optional_header_ids)

        paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                row_data = self.get_csv_demographic_row_and_headers(resp)["dict"]
                # Add any new headers from this session
                participant_list.append(row_data)

        output, writer = csv_dict_output_and_writer(these_headers)
        writer.writerows(participant_list)
        return output.getvalue()

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = self.get_response_values_for_demographics(study)
        header_options = self.request.GET.getlist("demooptions")
        cleaned_data = self.build_all_demographic_csv(responses, header_options)
        filename = "{}_{}.csv".format(
            study_name_for_files(study.name), "all-demographic-snapshots"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyDemographicsDictCSV(StudyDemographics):
    """
    Hitting this URL downloads a data dictionary for participant demographics in in CSV format.
    Does not depend on any actual data.
    """

    def build_all_demographic_dict_csv(self, optional_header_ids=None):
        """
        Builds CSV file contents for all participant data dictionary
        """

        descriptions = self.get_csv_demographic_row_and_headers()["descriptions"]
        these_headers = self.get_demographic_headers(optional_header_ids)
        all_descriptions = [
            {"column": key, "description": val}
            for (key, val) in descriptions.items()
            if key in these_headers
        ]
        output, writer = csv_dict_output_and_writer(["column", "description"])
        writer.writerows(all_descriptions)
        return output.getvalue()

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        header_options = self.request.GET.getlist("demooptions")
        cleaned_data = self.build_all_demographic_dict_csv(header_options)
        filename = "{}_{}.csv".format(
            study_name_for_files(study.name), "all-demographic-snapshots-dict"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response
