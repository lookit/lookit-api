import csv
import datetime
import io
import json

from django.db.models import Prefetch, QuerySet
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, reverse
from django.views.generic.detail import SingleObjectMixin
from guardian.mixins import PermissionRequiredMixin
from guardian.shortcuts import get_objects_for_user

import attachment_helpers
from accounts.models import Child, User
from exp.views.mixins import ExperimenterLoginRequiredMixin
from studies.models import Response, Study


# PREFETCH = Response.objects.filter(completed_consent_frame=True)
# CHILDREN_WITH_USERS = Child.objects.select_related("user")
WITH_PREFETCHED_RESPONSES = Study.objects.prefetch_related("responses", "videos")


def flatten_dict(d):
    """Flatten a dictionary where values may be other dictionaries

	The dictionary returned will have keys created by joining higher- to lower-level keys with dots. e.g. if the original dict d is
	{'a': {'x':3, 'y':4}, 'b':{'z':5}, 'c':{} }
	then the dict returned will be
	{'a.x':3, 'a.y': 4, 'b.z':5}

	Note that if a key is mapped to an empty dict or list, NO key in the returned dict is created for this key.

	Also note that values may be overwritten if there is conflicting dot notation in the input dictionary, e.g. {'a': {'x': 3}, 'a.x': 4}.
	"""
    # http://codereview.stackexchange.com/a/21035

    def expand(key, value):
        if isinstance(value, list):
            value = {i: v for (i, v) in enumerate(value)}
        if isinstance(value, dict):
            return [
                (str(key) + "." + str(k), v) for k, v in flatten_dict(value).items()
            ]
        else:
            return [(key, value)]

    items = [item for k, v in d.items() for item in expand(k, v)]

    return dict(items)


def merge_dicts(d1, d2):
    d1_copy = d1.copy()
    d1_copy.update(d2)
    return d1_copy

def round_age(age_in_days):
    if age_in_days <= 360:
        return round(age_in_days/10) * 10
    else:
        return round(age_in_days/30) * 30

class StudyResponsesMixin(
    SingleObjectMixin, ExperimenterLoginRequiredMixin, PermissionRequiredMixin
):
    """
	Mixin with shared items for StudyResponsesList, StudyResponsesAll, and StudyAttachments Views.

	TODO: deprecate this beast
	"""

    queryset = WITH_PREFETCHED_RESPONSES
    permission_required = "studies.can_view_study_responses"
    raise_exception = True

    def convert_to_string(self, object):
        if isinstance(object, datetime.date):
            return object.__str__()
        return object
        
    def round_ages_from_birthdays(self, child_birthdays, date_created):
        return [round_age((date_created.date() - birthdate).days) for birthdate in child_birthdays]

    def build_participant_data(self, responses):
        json_responses = []
        for resp in responses:
            latest_dem = resp.demographic_snapshot
            json_responses.append(
                json.dumps(
                    {
                        "response": {"id": resp.id, "uuid": str(resp.uuid)},
                        "participant": {
                            "id": resp.child.user_id,
                            "uuid": str(resp.child.user.uuid),
                            "nickname": resp.child.user.nickname,
                        },
                        "demographic_snapshot": {
                            "demographic_id": latest_dem.id,
                            "uuid": str(latest_dem.uuid),
                            "date_created": str(latest_dem.created_at),
                            "number_of_children": latest_dem.number_of_children,
                            "child_rounded_ages": self.round_ages_from_birthdays(latest_dem.child_birthdays, latest_dem.created_at),
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
                            "lookit_referrer": latest_dem.lookit_referrer,
                            "extra": latest_dem.extra,
                        },
                    },
                    indent=4,
                    default=self.convert_to_string,
                )
            )
        return json_responses

    def build_csv_participant_row_data(self, resp):
        """
		Returns row of csv participant data
		"""
        latest_dem = resp.demographic_snapshot

        return [
            resp.id,
            str(resp.uuid),
            resp.child.user_id,
            str(resp.child.user.uuid),
            resp.child.user.nickname,
            latest_dem.id,
            str(latest_dem.uuid),
            str(latest_dem.created_at),
            latest_dem.number_of_children,
            self.round_ages_from_birthdays(latest_dem.child_birthdays, latest_dem.created_at),
            latest_dem.languages_spoken_at_home,
            latest_dem.number_of_guardians,
            latest_dem.number_of_guardians_explanation,
            latest_dem.race_identification,
            latest_dem.age,
            latest_dem.gender,
            latest_dem.education_level,
            latest_dem.spouse_education_level,
            latest_dem.annual_income,
            latest_dem.number_of_books,
            latest_dem.additional_comments,
            latest_dem.country.name,
            latest_dem.state,
            latest_dem.density,
            latest_dem.lookit_referrer,
            latest_dem.extra,
        ]

    def get_csv_participant_headers(self):
        """
		Returns header row for csv participant data
		"""
        return [
            "response_id",
            "response_uuid",
            "participant_id",
            "participant_uuid",
            "participant_nickname",
            "demographic_id",
            "demographic_uuid",
            "demographic_date_created",
            "demographic_number_of_children",
            "demographic_child_rounded_ages",
            "demographic_languages_spoken_at_home",
            "demographic_number_of_guardians",
            "demographic_number_of_guardians_explanation",
            "demographic_race_identification",
            "demographic_age",
            "demographic_gender",
            "demographic_education_level",
            "demographic_spouse_education_level",
            "demographic_annual_income",
            "demographic_number_of_books",
            "demographic_additional_comments",
            "demographic_country",
            "demographic_state",
            "demographic_density",
            "demographic_lookit_referrer",
            "demographic_extra",
        ]

    def build_responses(self, responses, optional_headers=[]):
        """
		Builds the JSON response data for the researcher to download
		"""
        json_responses = []
        for resp in responses:
            age_in_days = (resp.date_created.date() - resp.child.birthday).days
            json_responses.append(
                {
                    "response": {
                        "id": resp.id,
                        "uuid": str(resp.uuid),
                        "sequence": resp.sequence,
                        "conditions": resp.conditions,
                        "exp_data": resp.exp_data,
                        "global_event_timings": resp.global_event_timings,
                        "completed": resp.completed,
                        "date_created": str(resp.date_created),
                        "withdrawn": resp.withdrawn,
                    },
                    "study": {"id": resp.study.id, "uuid": str(resp.study.uuid)},
                    "participant": {
                        "id": resp.child.user_id,
                        "uuid": str(resp.child.user.uuid),
                        "nickname": resp.child.user.nickname if "parent" in optional_headers else "",
                    },
                    "child": {
                        "id": resp.child.id,
                        "uuid": str(resp.child.uuid),
                        "name": resp.child.given_name if "name" in optional_headers else "",
                        "birthday": resp.child.birthday if "birthday" in optional_headers else "",
                        "age_in_days": age_in_days if "exact" in optional_headers else "",
                        "age_rounded": str(round_age(int(age_in_days))) if "rounded" in optional_headers else "",
                        "gender": resp.child.gender if "gender" in optional_headers else "",
                        "language_list": resp.child.language_list if "languages" in optional_headers else "",
                        "condition_list": resp.child.condition_list if "conditions" in optional_headers else "",
                        "age_at_birth": resp.child.age_at_birth if "gestage" in optional_headers else "",
                        "additional_information": resp.child.additional_information if "addl" in optional_headers else "",
                    },
                    "consent": resp.current_consent_details,
                }
            )
        return json_responses

    def csv_output_and_writer(self):
        output = io.StringIO()
        return output, csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)

    def csv_dict_output_and_writer(self, headerList):
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            quoting=csv.QUOTE_NONNUMERIC,
            fieldnames=headerList,
            restval="",
            extrasaction="ignore",
        )
        writer.writeheader()
        return output, writer

    def study_name_for_files(self, studyname):
        return "".join([c if c.isalnum() else "-" for c in studyname])

    def get_csv_headers_and_row_data(self, resp={}):
    
        age_in_days = (resp.date_created.date() - resp.child.birthday).days if resp else ""

        all_row_data = [
            ("response_id", resp.id if resp else "", "Short ID for this response"),
            (
                "response_uuid",
                str(resp.uuid) if resp else "",
                "Primary unique identifier for response, can be used to match to video filenames",
            ),
            (
                "response_date_created",
                str(resp.date_created) if resp else "",
                "Timestamp for when participant began session, in format e.g. 2019-11-07 17:13:38.702958+00:00",
            ),
            (
                "response_completed",
                resp.completed if resp else "",
                "Whether the participant submitted the exit survey; depending on study criteria, this may not align with whether the session is considered complete. E.g., participant may have left early but submitted exit survey, or may have completed all test trials but not exit survey.",
            ),
            (
                "response_withdrawn",
                resp.withdrawn if resp else "",
                "Whether the participant withdrew permission for viewing/use of study video beyond consent video. If true, video will not be available and must not be used.",
            ),
            (
                "response_consent_ruling",
                resp.most_recent_ruling if resp else "",
                "Most recent consent video ruling: one of 'accepted' (consent has been reviewed and judged to indidate informed consent), 'rejected' (consent has been reviewed and judged not to indicate informed consent -- e.g., video missing or parent did not read statement), or 'pending' (no current judgement, e.g. has not been reviewed yet or waiting on parent email response')",
            ),
            (
                "response_consent_arbiter",
                resp.most_recent_ruling_arbiter if resp else "",
                "Name associated with researcher account that made the most recent consent ruling",
            ),
            (
                "response_consent_time",
                resp.most_recent_ruling_date if resp else "",
                "Timestamp of most recent consent ruling, format e.g. 2019-12-09 20:40",
            ),
            (
                "response_consent_comment",
                resp.most_recent_ruling_comment if resp else "",
                "Comment associated with most recent consent ruling (may be used to track e.g. any cases where consent was confirmed by email)",
            ),
            (
                "study_id",
                resp.study.id if resp else "",
                "Short ID of study associated with this response. Same for all responses to a given Lookit study.",
            ),
            (
                "study_uuid",
                str(resp.study.uuid) if resp else "",
                "Primary unique identifier of study associated with this response. Same for all responses to a given Lookit study.",
            ),
            (
                "participant_id",
                resp.child.user_id if resp else "",
                "Short ID for the family account associated with this response. Will be the same for multiple responses from a child and for siblings.",
            ),
            (
                "participant_uuid",
                str(resp.child.user.uuid) if resp else "",
                "Primary unique identifier for family account associated with this response. Will be the same for multiple responses from a child and for siblings.",
            ),
            (
                "participant_nickname",
                resp.child.user.nickname if resp else "",
                "Nickname associated with the family account for this response - generally the mom or dad's name",
            ),
            (
                "child_id",
                resp.child.id if resp else "",
                "Short ID for the child associated with this response. Will be the same for multiple responses from one child.",
            ),
            (
                "child_uuid",
                str(resp.child.uuid) if resp else "",
                "Primary unique identifier for the child associated with this response. Will be the same for multiple responses from one child.",
            ),
            (
                "child_name",
                resp.child.given_name if resp else "",
                "Nickname for the child associated with this response. Not necessarily a real name (we encourage initials, nicknames, etc. if parents aren't comfortable providing a name) but should be redacted for publication of data.",
            ),
            (
                "child_birthday",
                resp.child.birthday if resp else "",
                "Birthdate of child associated with this response. Must be redacted for publication of data (switch to age at time of participation, and either round/jitter or redact timestamps of participation).",
            ),
            (
                "child_age_in_days",
                age_in_days,
                "Age in days at time of response of child associated with this response, exact. This can be used in conjunction with timestamps to calculate the child's birthdate, so should be redacted prior to publication unless no timestamp information is shared.",
            ),
            (
                "child_age_rounded",
                str(round_age(int(age_in_days))) if age_in_days else "",
                "Age in days at time of response of child associated with this response, rounded to the nearest 10 days if under 1 year old and to the nearest 30 days if over 1 year old. May be published; however, if you have more than a few sessions per participant it would be possible to infer the exact age in days (and therefore birthdate) with some effort. In this case you might consider directly jittering birthdates.",
            ),
            (
                "child_gender",
                resp.child.gender if resp else "",
                "Parent-identified gender of child, one of 'm' (male), 'f' (female), 'o' (other), or 'na' (prefer not to answer)",
            ),
            (
                "child_age_at_birth",
                resp.child.age_at_birth if resp else "",
                "Gestational age at birth in weeks. One of '40 or more weeks', '39 weeks' through '24 weeks', 'Under 24 weeks', or 'Not sure or prefer not to answer'",
            ),
            (
                "child_language_list",
                resp.child.language_list if resp else "",
                "List of languages spoken (using language codes in Lookit docs), separated by spaces",
            ),
            (
                "child_condition_list",
                resp.child.condition_list if resp else "",
                "List of child characteristics (using condition/characteristic codes in Lookit docs), separated by spaces",
            ),
            (
                "child_additional_information",
                resp.child.additional_information if resp else "",
                "Free response 'anything else you'd like us to know' field on child registration form for child associated with this response. Should be redacted or reviewed prior to publication as it may include names or other identifying information.",
            ),
            (
                "response_sequence",
                resp.sequence if resp else [],
                "Each response_sequence.N field (response_sequence.0, response_sequence.1, etc.) gives the ID of the Nth frame displayed during the session associated with this response. Responses may have different sequences due to randomization or if a participant leaves early.",
            ),
            (
                "response_conditions",
                [
                    merge_dicts({"frameName": condFrame}, conds)
                    for (condFrame, conds) in resp.conditions.items()
                ]
                if resp
                else [],
                "RESEARCHERS: EXPAND THIS SECTION BASED ON YOUR INDIVIDUAL STUDY. Each set of response_conditions.N.(...) fields give information about condition assignment during a particular frame of this study. response_conditions.0.frameName is the frame ID (corresponding to a value in response_sequence) where the randomization occured. Additional fields such as response_conditions.0.conditionNum depend on the specific randomizer frames used in this study.",
            ),
        ]

        headers_ordered = [name for (name, val, desc) in all_row_data][0:-2]

        field_descriptions = {name: desc for (name, val, desc) in all_row_data}

        row_data_with_headers = flatten_dict(
            {name: val for (name, val, desc) in all_row_data}
        )

        return {
            "headers": headers_ordered,
            "descriptions": field_descriptions,
            "dict": row_data_with_headers,
        }

    def get_frame_data(self, resp):

        frame_data_dicts = []

        # First add all of the global event timings as events with frame_id "global"
        for (iEvent, event) in enumerate(resp.global_event_timings):
            for (key, value) in event.items():
                frame_data_dicts.append(
                    {
                        "child_uuid": str(resp.child.uuid),
                        "response_uuid": str(resp.uuid),
                        "frame_id": "global",
                        "key": key,
                        "event_number": str(iEvent),
                        "value": value,
                    }
                )

        # Next add all data in exp_data
        event_prefix = "eventTimings."
        for (frame_id, frame_data) in resp.exp_data.items():
            for (key, value) in flatten_dict(frame_data).items():
                # Process event data separately and include event_number within frame
                if key.startswith(event_prefix):
                    key_pieces = key.split(".")
                    frame_data_dicts.append(
                        {
                            "child_uuid": str(resp.child.uuid),
                            "response_uuid": str(resp.uuid),
                            "frame_id": frame_id,
                            "key": ".".join(key_pieces[2:]),
                            "event_number": str(key_pieces[1]),
                            "value": value,
                        }
                    )
                # omit frameType values from CSV
                elif key == "frameType": 
                    continue
                # Omit empty generatedProperties values from CSV
                elif key == "generatedProperties" and not (value):
                    continue
                # For all other data, create a regular entry with frame_id and no event #
                else:
                    frame_data_dicts.append(
                        {
                            "child_uuid": str(resp.child.uuid),
                            "response_uuid": str(resp.uuid),
                            "frame_id": frame_id,
                            "key": key,
                            "event_number": "",
                            "value": value,
                        }
                    )

        headers = [
            (
                "response_uuid",
                "Unique identifier for this response; can be matched to summary data and video filenames",
            ),
            (
                "child_uuid",
                "Unique identifier for the child associated with this response; can be matched to summary data",
            ),
            (
                "frame_id",
                "Identifier for the particular frame responsible for this data; matches up to an element in the response_sequence in the summary data file",
            ),
            (
                "event_number",
                "Index of the event responsible for this data, if this is an event. Indexes start from 0 within each frame (and within global data) within each response.",
            ),
            (
                "key",
                "Label for a piece of data collected during this frame - for example, 'formData.child_favorite_animal'",
            ),
            (
                "value",
                "Value of the data associated with this key (of the indexed event if applicable) - for example, 'giraffe'",
            ),
        ]

        return {
            "data": frame_data_dicts,
            "data_headers": [header for (header, description) in headers],
            "header_descriptions": headers,
        }
    
    age_data_options = [
        {"id": "rounded", "name": "Rounded age", "column": "child_age_rounded", "default": True}, 
        {"id": "exact", "name": "Age in days", "column": "child_age_in_days"}, 
        {"id": "birthday", "name": "Birthdate", "column": "child_birthday"},
    ]
    child_data_options = [
        {"id": "name", "name": "Child name", "column": "child_name"}, 
        {"id": "gender", "name": "Child gender", "column": "child_gender", "default": True}, 
        {"id": "gestage", "name": "Child gestational age", "column": "child_age_at_birth"}, 
        {"id": "conditions", "name": "Child conditions", "column": "child_characteristics", "default": True}, 
        {"id": "languages", "name": "Child languages", "column": "child_languages", "default": True}, 
        {"id": "addl", "name": "Child additional info", "column": "child_additional_information"}, 
        {"id": "parent", "name": "Parent name", "column": "participant_nickname"}, 
    ]
    
    identifiable_data_options = ["exact", "birthday", "name", "addl", "parent"]
    
    all_optional_header_keys = [option["id"] for option in age_data_options + child_data_options]
    
    def get_headers(self, optional_headers_selected_ids, all_headers_available):
        standard_headers = self.get_csv_headers_and_row_data()["headers"]
        optional_headers = [option["column"] for option in self.age_data_options + self.child_data_options]
        selected_headers = [option["column"] for option in self.age_data_options + self.child_data_options if option["id"] in optional_headers_selected_ids]
        standard_headers_selected_only = [header for header in standard_headers if header not in optional_headers or header in selected_headers]
        ordered_headers = standard_headers_selected_only + sorted(list(all_headers_available - set(standard_headers)))
        return ordered_headers

        
    def build_summary_csv(self, responses, optional_headers_selected_ids):
        """
		Builds CSV file contents for overview of all responses
		"""

        headers = set()
        session_list = []

        for resp in responses:
            row_data = self.get_csv_headers_and_row_data(resp)["dict"]
            # Add any new headers from this session
            headers = headers | set(row_data.keys())
            session_list.append(row_data)

        headerList = self.get_headers(optional_headers_selected_ids, headers)
        output, writer = self.csv_dict_output_and_writer(headerList)
        writer.writerows(session_list)
        return output.getvalue()    

    def build_framedata_csv(self, responses):
        """
		Builds CSV file contents for frame-level data from all responses
		"""

        all_frame_data = []

        for resp in responses:
            this_resp_data = self.get_frame_data(resp)
            headers = this_resp_data["data_headers"]
            all_frame_data.extend(this_resp_data["data"])

        output, writer = self.csv_dict_output_and_writer(headers)
        writer.writerows(all_frame_data)
        return output.getvalue()

    def build_framedata_dict_csv(self, responses):

        all_frame_data = []

        for resp in responses:
            this_resp_data = self.get_frame_data(resp)
            all_frame_data.extend(this_resp_data["data"])

        # Start with general descriptions of high-level headers (child_id, response_id, etc.)
        header_descriptions = this_resp_data["header_descriptions"]
        frame_data_dict_entries = [
            {"column": header, "description": description}
            for (header, description) in header_descriptions
        ]

        frame_data_dict_entries.append(
            {
                "possible_frame_id": "global",
                "frame_description": "Data not associated with a particular frame",
            }
        )

        # Add placeholders to describe each frame type
        unique_frame_ids = sorted(
            list(
                set(
                    d["frame_id"].partition("-")[2]
                    for d in all_frame_data
                    if not (d["frame_id"] == "global")
                )
            )
        )
        for frame_id in unique_frame_ids:
            frame_data_dict_entries.append(
                {
                    "possible_frame_id": "*-" + frame_id,
                    "frame_description": "RESEARCHER: INSERT FRAME DESCRIPTION",
                }
            )
            unique_frame_keys = sorted(
                list(
                    set(
                        [
                            d["key"]
                            for d in all_frame_data
                            if d["frame_id"].partition("-")[2] == frame_id
                            and d["event_number"] == ""
                        ]
                    )
                )
            )
            for k in unique_frame_keys:
                frame_data_dict_entries.append(
                    {
                        "possible_frame_id": "*-" + frame_id,
                        "possible_key": k,
                        "key_description": "RESEARCHER: INSERT DESCRIPTION OF WHAT THIS KEY MEANS IN THIS FRAME",
                    }
                )

        event_keys = sorted(
            list(set([d["key"] for d in all_frame_data if d["event_number"] != ""]))
        )
        event_key_stock_descriptions = {
            "eventType": "Descriptor for this event; determines what other data is available. Global event 'exitEarly' records cases where the participant attempted to exit the study early by closing the tab/window or pressing F1 or ctrl-X. RESEARCHER: INSERT DESCRIPTIONS OF PARTICULAR EVENTTYPES USED IN YOUR STUDY. (Note: you can find a list of events recorded by each frame in the frame documentation at https://lookit.github.io/ember-lookit-frameplayer, under the Events header.)",
            "exitType": "Used in the global event exitEarly. Only value stored at this point is 'browserNavigationAttempt'",
            "lastPageSeen": "Used in the global event exitEarly. Index of the frame the participant was on before exit attempt.",
            "pipeId": "Recorded by any event in a video-capture-equipped frame. Internal video ID used by Pipe service; only useful for troubleshooting in rare cases.",
            "streamTime": "Recorded by any event in a video-capture-equipped frame. Indicates time within webcam video (videoId) to nearest 0.1 second. If recording has not started yet, may be 0 or null.",
            "timestamp": "Recorded by all events. Timestamp of event in format e.g. 2019-11-07T17:14:43.626Z",
            "videoId": "Recorded by any event in a video-capture-equipped frame. Filename (without .mp4 extension) of video currently being recorded.",
        }
        for k in event_keys:
            frame_data_dict_entries.append(
                {
                    "possible_frame_id": "any (event data)",
                    "possible_key": k,
                    "key_description": event_key_stock_descriptions.get(
                        k, "RESEARCHER: INSERT DESCRIPTION OF WHAT THIS EVENT KEY MEANS"
                    ),
                }
            )

        output, writer = self.csv_dict_output_and_writer(
            [
                "column",
                "description",
                "possible_frame_id",
                "frame_description",
                "possible_key",
                "key_description",
            ]
        )
        writer.writerows(frame_data_dict_entries)
        return output.getvalue()

    def post(self, request, *args, **kwargs):
        """
		Downloads a single study video.
		"""
        attachment_id = self.request.POST.get("attachment")
        if attachment_id:
            download_url = self.get_object().videos.get(pk=attachment_id).download_url
            return redirect(download_url)

        return HttpResponseRedirect(
            reverse("exp:study-responses-list", kwargs=dict(pk=self.get_object().pk))
        )
