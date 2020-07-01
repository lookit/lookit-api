import io
import json
import types
import zipfile
from typing import NamedTuple, Union

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, reverse
from django.views import generic

import attachment_helpers
from accounts.utils import (
    hash_child_id,
    hash_demographic_id,
    hash_id,
    hash_participant_id,
)
from exp.mixins.paginator_mixin import PaginatorMixin
from exp.utils import (
    RESPONSE_PAGE_SIZE,
    csv_dict_output_and_writer,
    flatten_dict,
    round_age,
    round_ages_from_birthdays,
    study_name_for_files,
)
from exp.views.mixins import (
    ExperimenterLoginRequiredMixin,
    SingleObjectParsimoniousQueryMixin,
)
from studies.models import Feedback, Study
from studies.permissions import StudyPermission
from studies.queries import (
    get_consent_statistics,
    get_responses_with_current_rulings_and_videos,
)
from studies.tasks import build_framedata_dict, build_zipfile_of_videos

# ------- Helper functions for response downloads ----------------------------------------


class ResponseDataColumn(NamedTuple):
    id: str  # unique key to identify data; used as CSV column header. In format object.field_name
    description: str  # Description for data dictionary
    extractor: types.LambdaType  # Function to extract value from response instance
    optional: bool = False  # is a column the user checks a box to include?
    name: str = ""  # used in template form for optional columns
    include_by_default: bool = False  # whether to initially check checkbox for field
    identifiable: bool = False  # used to determine filename signaling


response_columns = [
    ResponseDataColumn(
        id="response__id",
        description="Short ID for this response",
        extractor=lambda resp: str(resp.id),
    ),
    ResponseDataColumn(
        id="response__uuid",
        description="Unique identifier for response. Can be used to match data to video filenames.",
        extractor=lambda resp: str(resp.uuid),
    ),
    ResponseDataColumn(
        id="response__date_created",
        description="Timestamp for when participant began session, in format e.g. 2019-11-07 17:13:38.702958+00:00",
        extractor=lambda resp: str(resp.date_created),
    ),
    ResponseDataColumn(
        id="response__completed",
        description=(
            "Whether the participant submitted the exit survey; depending on study criteria, this may not align "
            "with whether the session is considered complete. E.g., participant may have left early but submitted "
            "exit survey, or may have completed all test trials but not exit survey."
        ),
        extractor=lambda resp: resp.completed,
    ),
    ResponseDataColumn(
        id="response__withdrawn",
        description=(
            "Whether the participant withdrew permission for viewing/use of study video beyond consent video. If "
            "true, video will not be available and must not be used."
        ),
        extractor=lambda resp: resp.withdrawn,
    ),
    ResponseDataColumn(
        id="response__parent_feedback",
        description=(
            "Freeform parent feedback entered into the exit survey, if any. This field may incidentally contain "
            "identifying or sensitive information depending on what parents say, so it should be scrubbed or "
            "omitted from published data."
        ),
        extractor=lambda resp: resp.parent_feedback,
    ),
    ResponseDataColumn(
        id="response__birthdate_difference",
        description=(
            "Difference between birthdate entered in exit survey, if any, and birthdate of registered child "
            "participating. Positive values mean that the birthdate from the exit survey is LATER. Blank if "
            "no birthdate available from the exit survey."
        ),
        extractor=lambda resp: resp.birthdate_difference,
    ),
    ResponseDataColumn(
        id="response__video_privacy",
        description=(
            "Privacy level for videos selected during the exit survey, if the parent completed the exit survey. "
            "Possible levels are 'private' (only people listed on your IRB protocol can view), 'scientific' "
            "(can share for scientific/educational purposes), and 'publicity' (can also share for publicity). "
            "In no cases may videos be shared for commercial purposes. If this is missing (e.g., family stopped "
            "just after the consent form and did not complete the exit survey), you must treat the video as "
            "private."
        ),
        extractor=lambda resp: resp.privacy,
    ),
    ResponseDataColumn(
        id="response__databrary",
        description=(
            "Whether the parent agreed to share video data on Databrary - 'yes' or 'no'. If missing, you must "
            "treat the video as if 'no' were selected. If 'yes', the video privacy selections also apply to "
            "authorized Databrary users."
        ),
        extractor=lambda resp: resp.databrary,
    ),
    ResponseDataColumn(
        id="response__is_preview",
        description=(
            "Whether this response was generated by a researcher previewing the experiment. Preview data should "
            "not be used in any actual analyses."
        ),
        extractor=lambda resp: resp.is_preview,
    ),
    ResponseDataColumn(
        id="consent__ruling",
        description=(
            "Most recent consent video ruling: one of 'accepted' (consent has been reviewed and judged to indidate "
            "informed consent), 'rejected' (consent has been reviewed and judged not to indicate informed "
            "consent -- e.g., video missing or parent did not read statement), or 'pending' (no current judgement, "
            "e.g. has not been reviewed yet or waiting on parent email response')"
        ),
        extractor=lambda resp: resp.most_recent_ruling,
    ),
    ResponseDataColumn(
        id="consent__arbiter",
        description="Name associated with researcher account that made the most recent consent ruling",
        extractor=lambda resp: resp.most_recent_ruling_arbiter,
    ),
    ResponseDataColumn(
        id="consent__time",
        description="Timestamp of most recent consent ruling, format e.g. 2019-12-09 20:40",
        extractor=lambda resp: resp.most_recent_ruling_date,
    ),
    ResponseDataColumn(
        id="consent__comment",
        description=(
            "Comment associated with most recent consent ruling (may be used to track e.g. any cases where consent "
            "was confirmed by email)"
        ),
        extractor=lambda resp: resp.most_recent_ruling_comment,
    ),
    ResponseDataColumn(
        id="consent__time",
        description="Timestamp of most recent consent ruling, format e.g. 2019-12-09 20:40",
        extractor=lambda resp: resp.most_recent_ruling_date,
    ),
    ResponseDataColumn(
        id="study__uuid",
        description="Unique identifier of study associated with this response. Same for all responses to a given Lookit study.",
        extractor=lambda resp: str(resp.study.uuid),
    ),
    ResponseDataColumn(
        id="participant__global_id",
        description=(
            "Unique identifier for family account associated with this response. Will be the same for multiple "
            "responses from a child and for siblings, and across different studies. MUST BE REDACTED FOR "
            "PUBLICATION because this allows identification of families across different published studies, which "
            "may have unintended privacy consequences. Researchers can use this ID to match participants across "
            "studies (subject to their own IRB review), but would need to generate their own random participant "
            "IDs for publication in that case. Use participant_hashed_id as a publication-safe alternative if "
            "only analyzing data from one Lookit study."
        ),
        extractor=lambda resp: str(resp.child.user.uuid),
        optional=True,
        name="Parent global ID",
        include_by_default=False,
        identifiable=True,
    ),
    ResponseDataColumn(
        id="participant__hashed_id",
        description=(
            "Identifier for family account associated with this response. Will be the same for multiple responses "
            "from a child and for siblings, but is unique to this study. This may be published directly."
        ),
        extractor=lambda resp: hash_id(
            resp.child.user.uuid,
            resp.study.uuid,
            resp.study.salt,
            resp.study.hash_digits,
        ),
    ),
    ResponseDataColumn(
        id="participant__nickname",
        description=(
            "Nickname associated with the family account for this response - generally the mom or dad's name. "
            "Must be redacted for publication."
        ),
        extractor=lambda resp: resp.child.user.nickname,
        optional=True,
        name="Parent name",
        include_by_default=False,
        identifiable=True,
    ),
    ResponseDataColumn(
        id="child__global_id",
        description=(
            "Primary unique identifier for the child associated with this response. Will be the same for multiple "
            "responses from one child, even across different Lookit studies. MUST BE REDACTED FOR PUBLICATION "
            "because this allows identification of children across different published studies, which may have "
            "unintended privacy consequences. Researchers can use this ID to match participants across studies "
            "(subject to their own IRB review), but would need to generate their own random participant IDs for "
            "publication in that case. Use child_hashed_id as a publication-safe alternative if only analyzing "
            "data from one Lookit study."
        ),
        extractor=lambda resp: str(resp.child.uuid),
        optional=True,
        name="Child global ID",
        include_by_default=False,
        identifiable=True,
    ),
    ResponseDataColumn(
        id="child__hashed_id",
        description=(
            "Identifier for child associated with this response. Will be the same for multiple responses from a "
            "child, but is unique to this study. This may be published directly."
        ),
        extractor=lambda resp: hash_id(
            resp.child.uuid, resp.study.uuid, resp.study.salt, resp.study.hash_digits
        ),
    ),
    ResponseDataColumn(
        id="child__name",
        description=(
            "Nickname for the child associated with this response. Not necessarily a real name (we encourage "
            "initials, nicknames, etc. if parents aren't comfortable providing a name) but must be redacted for "
            "publication of data."
        ),
        extractor=lambda resp: resp.child.given_name,
        optional=True,
        name="Child name",
        include_by_default=False,
        identifiable=True,
    ),
    ResponseDataColumn(
        id="child__birthday",
        description=(
            "Birthdate of child associated with this response. Must be redacted for publication of data (switch to "
            "age at time of participation; either use rounded age, jitter the age, or redact timestamps of "
            "participation)."
        ),
        extractor=lambda resp: resp.child.birthday,
        optional=True,
        name="Birthdate",
        include_by_default=False,
        identifiable=True,
    ),
    ResponseDataColumn(
        id="child__age_in_days",
        description=(
            "Age in days at time of response of child associated with this response, exact. This can be used in "
            "conjunction with timestamps to calculate the child's birthdate, so must be jittered or redacted prior "
            "to publication unless no timestamp information is shared."
        ),
        extractor=lambda resp: (resp.date_created.date() - resp.child.birthday).days,
        optional=True,
        name="Age in days",
        include_by_default=False,
        identifiable=True,
    ),
    ResponseDataColumn(
        id="child__age_rounded",
        description=(
            "Age in days at time of response of child associated with this response, rounded to the nearest 10 "
            "days if under 1 year old and to the nearest 30 days if over 1 year old. May be published; however, if "
            "you have more than a few sessions per participant it would be possible to infer the exact age in days "
            "(and therefore birthdate) with some effort. In this case you might consider directly jittering "
            "birthdates."
        ),
        extractor=lambda resp: str(
            round_age(int((resp.date_created.date() - resp.child.birthday).days))
        )
        if (resp.date_created and resp.child.birthday)
        else "",
        optional=True,
        name="Rounded age",
        include_by_default=True,
        identifiable=False,
    ),
    ResponseDataColumn(
        id="child__gender",
        description=(
            "Parent-identified gender of child, one of 'm' (male), 'f' (female), 'o' (other), or 'na' (prefer not "
            "to answer)"
        ),
        extractor=lambda resp: resp.child.gender,
        optional=True,
        name="Child gender",
        include_by_default=True,
        identifiable=False,
    ),
    ResponseDataColumn(
        id="child__age_at_birth",
        description=(
            "Gestational age at birth in weeks. One of '40 or more weeks', '39 weeks' through '24 weeks', "
            "'Under 24 weeks', or 'Not sure or prefer not to answer'"
        ),
        extractor=lambda resp: resp.child.age_at_birth,
        optional=True,
        name="Child gestational age",
        include_by_default=True,
        identifiable=False,
    ),
    ResponseDataColumn(
        id="child__language_list",
        description="List of languages spoken (using language codes in Lookit docs), separated by spaces",
        extractor=lambda resp: resp.child.language_list,
        optional=True,
        name="Child languages",
        include_by_default=True,
        identifiable=False,
    ),
    ResponseDataColumn(
        id="child__condition_list",
        description="List of child characteristics (using condition/characteristic codes in Lookit docs), separated by spaces",
        extractor=lambda resp: resp.child.condition_list,
        optional=True,
        name="Child conditions",
        include_by_default=True,
        identifiable=False,
    ),
    ResponseDataColumn(
        id="child__additional_information",
        description=(
            "Free response 'anything else you'd like us to know' field on child registration form for child "
            "associated with this response. Should be redacted or reviewed prior to publication as it may include "
            "names or other identifying information."
        ),
        extractor=lambda resp: resp.child.additional_information,
        optional=True,
        name="Child additional information",
        include_by_default=True,
        identifiable=True,
    ),
    ResponseDataColumn(
        id="response__sequence",
        description=(
            "Each response_sequence.N field (response_sequence.0, response_sequence.1, etc.) gives the ID of the "
            "Nth frame displayed during the session associated with this response. Responses may have different "
            "sequences due to randomization or if a participant leaves early."
        ),
        extractor=lambda resp: resp.sequence,
    ),
    ResponseDataColumn(  # TODO: this may be the only tricky one to import to json
        id="response__conditions",
        description=(
            "RESEARCHERS: EXPAND THIS SECTION BASED ON YOUR INDIVIDUAL STUDY. Each set of "
            "response_conditions.N.(...) fields give information about condition assignment during a particular "
            "frame of this study. response_conditions.0.frameName is the frame ID (corresponding to a value in "
            "response_sequence) where the randomization occured. Additional fields such as "
            "response_conditions.0.conditionNum depend on the specific randomizer frames used in this study."
        ),
        extractor=lambda resp: [
            {**{"frameName": cond_frame}, **conds}
            for (cond_frame, conds) in resp.conditions.items()
        ],
    ),
]


def get_response_headers(selected_headers, all_available_headers):
    """
    Select and order the appropriate headers to include in a file download.
    selected_headers is a list of headers to select from the optional header ids; all_available_headers is a set.
    Will put standard headers in the order defined in response_columns, then any remaining headers from
    all_available_headers. Optional headers not in selected_headers are removed.
    """
    unselected_optional_ids = [
        col.id
        for col in response_columns
        if col.optional and col.id not in selected_headers
    ]
    selected_standard_headers = [
        col.id
        for col in response_columns[0:-2]
        if col.id not in unselected_optional_ids
    ]
    return selected_standard_headers + sorted(
        list(
            all_available_headers
            - set(selected_standard_headers)
            - set(unselected_optional_ids)
        )
    )


def construct_response_dictionary(resp, optional_headers):
    resp_dict = {}
    for col in response_columns:
        if col.id in optional_headers or not col.optional:
            try:
                object_name, field_name = col.id.split("__")
                if object_name in resp_dict:
                    resp_dict[object_name][field_name] = col.extractor(resp)
                else:
                    resp_dict[object_name] = {field_name: col.extractor(resp)}
            except ValueError:
                resp_dict[col.id] = col.extractor(resp)
    return resp_dict


def build_responses_csv(responses, optional_headers_selected_ids):
    """
    Builds CSV file contents for overview of all responses.
    Note: this uses the actual response object rather than a dict returned by
    values() because we use several properties (which cannot be retrieved by
    values()):

     "withdrawn"
     "most_recent_ruling",
     "most_recent_ruling_arbiter",
     "most_recent_ruling_date",
     "most_recent_ruling_comment",
     "child__language_list",
     "child__condition_list"

    Iterating over the responses to fetch these properties would defeat the point
    so we just use the object.
    """

    headers = set()
    session_list = []

    paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
    for page_num in paginator.page_range:
        page_of_responses = paginator.page(page_num)
        for resp in page_of_responses:
            row_data = flatten_dict(
                {col.id: col.extractor(resp) for col in response_columns}
            )
            # Add any new headers from this session
            headers = headers | set(row_data.keys())
            session_list.append(row_data)

    header_list = get_response_headers(optional_headers_selected_ids, headers)
    output, writer = csv_dict_output_and_writer(header_list)
    writer.writerows(session_list)
    return output.getvalue()


def build_responses_json(responses, optional_headers=None):
    """
    Builds the JSON response data for the researcher to download
    """
    # Note: this uses the actual response object rather than a dict returned by
    # values() because we use several properties (which cannot be retrieved by
    # values()), e.g. withdrawn and child__language_list.
    json_responses = []
    if optional_headers is None:
        optional_headers = []
    paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
    for page_num in paginator.page_range:
        page_of_responses = paginator.page(page_num)
        for resp in page_of_responses:
            json_responses.append(construct_response_dictionary(resp, optional_headers))
    return json_responses


def get_frame_data(resp):

    if type(resp) is not dict:
        resp = {
            "child__uuid": resp.child.uuid,
            "study__uuid": resp.study.uuid,
            "study__salt": resp.study.salt,
            "study__hash_digits": resp.study.hash_digits,
            "uuid": resp.uuid,
            "exp_data": resp.exp_data,
            "global_event_timings": resp.global_event_timings,
        }

    frame_data_dicts = []
    child_hashed_id = hash_id(
        resp["child__uuid"],
        resp["study__uuid"],
        resp["study__salt"],
        resp["study__hash_digits"],
    )

    # First add all of the global event timings as events with frame_id "global"
    for (iEvent, event) in enumerate(resp["global_event_timings"]):
        for (key, value) in event.items():
            frame_data_dicts.append(
                {
                    "child_hashed_id": child_hashed_id,
                    "response_uuid": str(resp["uuid"]),
                    "frame_id": "global",
                    "key": key,
                    "event_number": str(iEvent),
                    "value": value,
                }
            )

            # Next add all data in exp_data
    event_prefix = "eventTimings."
    for (frame_id, frame_data) in resp["exp_data"].items():
        for (key, value) in flatten_dict(frame_data).items():
            # Process event data separately and include event_number within frame
            if key.startswith(event_prefix):
                key_pieces = key.split(".")
                frame_data_dicts.append(
                    {
                        "child_hashed_id": child_hashed_id,
                        "response_uuid": str(resp["uuid"]),
                        "frame_id": frame_id,
                        "key": ".".join(key_pieces[2:]),
                        "event_number": str(key_pieces[1]),
                        "value": value,
                    }
                )
                # omit frameType values from CSV
            elif key == "frameType":
                continue
                # Omit the DOB from any exit survey
            elif key == "birthDate" and frame_data["frameType"] == "EXIT":
                continue
                # Omit empty generatedProperties values from CSV
            elif key == "generatedProperties" and not (value):
                continue
                # For all other data, create a regular entry with frame_id and no event #
            else:
                frame_data_dicts.append(
                    {
                        "child_hashed_id": child_hashed_id,
                        "response_uuid": str(resp["uuid"]),
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
            "child_hashed_id",
            (
                "Hashed identifier for the child associated with this response; can be matched to summary data "
                "child_hashed_id. This random ID may be published directly; it is specific to this study. If you "
                "need to match children across multiple studies, use the child_global_id."
            ),
        ),
        (
            "frame_id",
            (
                "Identifier for the particular frame responsible for this data; matches up to an element in the "
                "response_sequence in the summary data file"
            ),
        ),
        (
            "event_number",
            (
                "Index of the event responsible for this data, if this is an event. Indexes start from 0 within each "
                "frame (and within global data) within each response."
            ),
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


def build_framedata_dict_csv(writer, responses):

    response_paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
    unique_frame_ids = set()
    event_keys = set()
    unique_frame_keys_dict = {}

    for page_num in response_paginator.page_range:
        page_of_responses = response_paginator.page(page_num)
        for resp in page_of_responses:
            this_resp_data = get_frame_data(resp)["data"]
            these_ids = [
                d["frame_id"].partition("-")[2]
                for d in this_resp_data
                if not d["frame_id"] == "global"
            ]
            event_keys = event_keys | set(
                [d["key"] for d in this_resp_data if d["event_number"] != ""]
            )
            unique_frame_ids = unique_frame_ids | set(these_ids)
            for frame_id in these_ids:
                these_keys = set(
                    [
                        d["key"]
                        for d in this_resp_data
                        if d["frame_id"].partition("-")[2] == frame_id
                        and d["event_number"] == ""
                    ]
                )
                if frame_id in unique_frame_keys_dict:
                    unique_frame_keys_dict[frame_id] = (
                        unique_frame_keys_dict[frame_id] | these_keys
                    )
                else:
                    unique_frame_keys_dict[frame_id] = these_keys

    # Start with general descriptions of high-level headers (child_id, response_id, etc.)
    header_descriptions = get_frame_data(resp)["header_descriptions"]
    writer.writerows(
        [
            {"column": header, "description": description}
            for (header, description) in header_descriptions
        ]
    )
    writer.writerow(
        {
            "possible_frame_id": "global",
            "frame_description": "Data not associated with a particular frame",
        }
    )

    # Add placeholders to describe each frame type
    unique_frame_ids = sorted(list(unique_frame_ids))
    for frame_id in unique_frame_ids:
        writer.writerow(
            {
                "possible_frame_id": "*-" + frame_id,
                "frame_description": "RESEARCHER: INSERT FRAME DESCRIPTION",
            }
        )
        unique_frame_keys = sorted(list(unique_frame_keys_dict[frame_id]))
        for k in unique_frame_keys:
            writer.writerow(
                {
                    "possible_frame_id": "*-" + frame_id,
                    "possible_key": k,
                    "key_description": "RESEARCHER: INSERT DESCRIPTION OF WHAT THIS KEY MEANS IN THIS FRAME",
                }
            )

    event_keys = sorted(list(event_keys))
    event_key_stock_descriptions = {
        "eventType": (
            "Descriptor for this event; determines what other data is available. Global event 'exitEarly' records "
            "cases where the participant attempted to exit the study early by closing the tab/window or pressing F1 "
            "or ctrl-X. RESEARCHER: INSERT DESCRIPTIONS OF PARTICULAR EVENTTYPES USED IN YOUR STUDY. (Note: you can "
            "find a list of events recorded by each frame in the frame documentation at "
            "https://lookit.github.io/ember-lookit-frameplayer, under the Events header.)"
        ),
        "exitType": (
            "Used in the global event exitEarly. Only value stored at this point is 'browserNavigationAttempt'"
        ),
        "lastPageSeen": (
            "Used in the global event exitEarly. Index of the frame the participant was on before exit attempt."
        ),
        "pipeId": (
            "Recorded by any event in a video-capture-equipped frame. Internal video ID used by Pipe service; only "
            "useful for troubleshooting in rare cases."
        ),
        "streamTime": (
            "Recorded by any event in a video-capture-equipped frame. Indicates time within webcam "
            "video (videoId) to nearest 0.1 second. If recording has not started yet, may be 0 or null."
        ),
        "timestamp": "Recorded by all events. Timestamp of event in format e.g. 2019-11-07T17:14:43.626Z",
        "videoId": (
            "Recorded by any event in a video-capture-equipped frame. Filename (without .mp4 extension) of video "
            "currently being recorded."
        ),
    }
    for k in event_keys:
        writer.writerow(
            {
                "possible_frame_id": "any (event data)",
                "possible_key": k,
                "key_description": event_key_stock_descriptions.get(
                    k, "RESEARCHER: INSERT DESCRIPTION OF WHAT THIS EVENT KEY MEANS"
                ),
            }
        )


def build_single_response_framedata_csv(response):
    """
    Builds CSV file contents for frame-level data from a single response. Used for both
    building zip archive of all response data & offering individual-file downloads on individual responses view.
    """

    this_resp_data = get_frame_data(response)
    output, writer = csv_dict_output_and_writer(this_resp_data["data_headers"])
    writer.writerows(this_resp_data["data"])

    return output.getvalue()


# ------- End helper functions for response downloads ------------------------------------


class StudyResponsesList(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    PaginatorMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.DetailView,
):
    """
    View to acquire a list of study responses.
    """

    template_name = "studies/study_responses.html"
    queryset = Study.objects.all()
    raise_exception = True

    def user_can_see_study_responses(self):
        user = self.request.user
        study = self.get_object()
        method = self.request.method

        if not user.is_researcher:
            return False

        if method == "GET":
            return user.has_study_perms(
                StudyPermission.READ_STUDY_RESPONSE_DATA, study
            ) or user.has_study_perms(StudyPermission.READ_STUDY_PREVIEW_DATA, study)
        elif method == "POST":
            return user.has_study_perms(StudyPermission.EDIT_STUDY_FEEDBACK, study)

    test_func = user_can_see_study_responses

    def post(self, request, *args, **kwargs):
        """Currently, handles feedback form."""
        form_data = self.request.POST
        user = self.request.user

        # first, check the case for video download
        attachment_id = form_data.get("attachment")
        if attachment_id:
            download_url = self.get_object().videos.get(pk=attachment_id).download_url
            return redirect(download_url)

        feedback_id = form_data.get("feedback_id", None)
        comment = form_data.get("comment", "")

        if feedback_id:
            Feedback.objects.filter(id=feedback_id).update(comment=comment)
        else:
            response_id = int(form_data.get("response_id"))
            Feedback.objects.create(
                response_id=response_id, researcher=user, comment=comment
            )

        return HttpResponseRedirect(
            reverse("exp:study-responses-list", kwargs=dict(pk=self.get_object().pk))
        )

    def get_responses_orderby(self):
        """
        Determine sort field and order. Sorting on id actually sorts on user id, not response id.
        Sorting on status, actually sorts on 'completed' field, where we are alphabetizing
        "in progress" and "completed"
        """
        orderby = self.request.GET.get("sort", "id")
        reverse = "-" in orderby
        if "id" in orderby:
            orderby = "-child__id" if reverse else "child__id"
        if "status" in orderby:
            orderby = "completed" if reverse else "-completed"
        return orderby

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.  Study results
        are paginated.
        """
        context = super().get_context_data(**kwargs)
        page = self.request.GET.get("page", None)
        orderby = self.get_responses_orderby()

        responses = (
            context["study"]
            .responses_for_researcher(self.request.user)
            .prefetch_related(
                "consent_rulings__arbiter",
                Prefetch(
                    "feedback",
                    queryset=Feedback.objects.select_related("researcher").order_by(
                        "-id"
                    ),
                ),
            )
            .order_by(orderby)
        )
        paginated_responses = context["responses"] = self.paginated_queryset(
            responses, page, 10
        )

        minimal_optional_headers = [
            "rounded",
            "gender",
            "languages",
            "conditions",
            "gestage",
        ]
        context["response_data"] = build_responses_json(
            paginated_responses, minimal_optional_headers
        )
        context["csv_data"] = [
            build_responses_csv([resp], minimal_optional_headers)
            for resp in paginated_responses
        ]

        context["frame_data"] = [
            build_single_response_framedata_csv(resp) for resp in paginated_responses
        ]
        optional_header_ids = [col.id for col in response_columns if col.optional]
        context["response_data_full"] = build_responses_json(
            paginated_responses, optional_header_ids
        )
        context["csv_data_full"] = [
            build_responses_csv([resp], optional_header_ids)
            for resp in paginated_responses
        ]
        context["can_edit_feedback"] = self.request.user.has_study_perms(
            StudyPermission.EDIT_STUDY_FEEDBACK, context["study"]
        )
        return context

    def sort_attachments_by_response(self, responses):
        """
        Build a list of list of videos for each response
        """
        study = self.get_object()
        attachments = attachment_helpers.get_study_attachments(study)
        all_attachments = []
        for response in responses:
            uuid = str(response.uuid)
            att_list = []
            for attachment in attachments:
                if uuid in attachment.key:
                    att_list.append(
                        {
                            "key": attachment.key,
                            "display": self.build_video_display_name(
                                str(study.uuid), uuid, attachment.key
                            ),
                        }
                    )
            all_attachments.append(att_list)
        return all_attachments

    def build_video_display_name(self, study_uuid, response_uuid, vid_name):
        """
        Strips study_uuid and response_uuid out of video responses titles for better display.
        """
        return ". . ." + ". . .".join(
            vid_name.split(study_uuid + "_")[1].split("_" + response_uuid + "_")
        )


class StudyResponsesConsentManager(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.DetailView,
):
    """Manage videos from here."""

    template_name = "studies/study_responses_consent_ruling.html"
    queryset = Study.objects.all()
    raise_exception = True

    def user_can_code_consent(self):
        user = self.request.user
        study = self.get_object()
        return user.is_researcher and (
            user.has_study_perms(StudyPermission.CODE_STUDY_CONSENT, study)
            or user.has_study_perms(StudyPermission.CODE_STUDY_PREVIEW_CONSENT, study)
        )

    test_func = user_can_code_consent

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Need to prefetch our responses with consent-footage videos.
        study = context["study"]
        # TODO: technically should not grant access to consent videos for preview data unless has that perm
        # (or should clearly indicate that code_study_consent means preview + actual data)
        preview_only = not self.request.user.has_study_perms(
            StudyPermission.CODE_STUDY_CONSENT, study
        )
        responses = get_responses_with_current_rulings_and_videos(
            study.id, preview_only
        )

        context["loaded_responses"] = responses
        context["summary_statistics"] = get_consent_statistics(study.id, preview_only)

        # Using a map for arbitrarily structured data - lists and objects that we can't just trivially shove onto
        # data-* properties in HTML
        response_key_value_store = {}

        paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            # two jobs - generate statistics and populate k/v store.
            for response in page_of_responses:

                response_json = response_key_value_store[str(response["uuid"])] = {}

                response["uuid"] = str(response.pop("uuid"))
                response_json["videos"] = response.pop("videos")

                response_json["details"] = {
                    "general": {
                        "uuid": response["uuid"],
                        "global_event_timings": json.dumps(
                            response.pop("global_event_timings")
                        ),
                        "sequence": json.dumps(response.pop("sequence")),
                        "completed": json.dumps(response.pop("completed")),
                        "date_created": str(response["date_created"]),
                    },
                    "participant": {
                        "hashed_id": hash_participant_id(response),
                        "uuid": str(response.pop("child__user__uuid")),
                        "nickname": response.pop("child__user__nickname"),
                    },
                    "child": {
                        "hashed_id": hash_child_id(response),
                        "uuid": str(response.pop("child__uuid")),
                        "name": response.pop("child__given_name"),
                        "birthday": str(response.pop("child__birthday")),
                        "gender": response.pop("child__gender"),
                        "additional_information": response.pop(
                            "child__additional_information"
                        ),
                    },
                }

                # TODO: Upgrade to Django 2.x and use json_script.
        context["response_key_value_store"] = json.dumps(response_key_value_store)

        return context

    def post(self, request, *args, **kwargs):
        """This is where consent is submitted."""
        form_data = self.request.POST
        user = self.request.user
        study = self.get_object()
        preview_only = not self.request.user.has_study_perms(
            StudyPermission.CODE_STUDY_CONSENT, study
        )
        # Only allow any action on preview responses unless full perms
        responses = study.responses
        if preview_only:
            responses = responses.filter(is_preview=True)

        comments = json.loads(form_data.get("comments"))

        # We now accept pending rulings to reverse old reject/approve decisions.
        for ruling in ("accepted", "rejected", "pending"):
            judged_responses = responses.filter(uuid__in=form_data.getlist(ruling))
            for response in judged_responses:
                response.consent_rulings.create(
                    action=ruling,
                    arbiter=user,
                    comments=comments.pop(str(response.uuid), None),
                )
                response.save()

                # if there are any comments left over, these will count as new rulings that are the same as the last.
        if comments:
            for resp_uuid, comment in comments.items():
                response = responses.get(uuid=resp_uuid)
                response.consent_rulings.create(
                    action=response.most_recent_ruling, arbiter=user, comments=comment
                )

        return HttpResponseRedirect(
            reverse(
                "exp:study-responses-consent-manager",
                kwargs=dict(pk=self.get_object().pk),
            )
        )


class StudyResponsesAll(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.DetailView,
):
    """
    StudyResponsesAll shows a variety of download options for response and child data.
    """

    template_name = "studies/study_responses_all.html"
    queryset = Study.objects.all()
    raise_exception = True
    http_method_names = ["get", "post"]

    # Which headers from the response data summary should go in the child data downloads
    child_csv_headers = [
        col.id
        for col in response_columns
        if col.id.startswith("child__") or col.id.startswith("participant__")
    ]

    def user_can_see_study_responses(self):
        user = self.request.user
        study = self.get_object()
        method = self.request.method

        if not user.is_researcher:
            return False

        if method == "GET":
            return user.has_study_perms(
                StudyPermission.READ_STUDY_RESPONSE_DATA, study
            ) or user.has_study_perms(StudyPermission.READ_STUDY_PREVIEW_DATA, study)
        elif method == "POST":
            return user.has_study_perms(StudyPermission.DELETE_ALL_PREVIEW_DATA, study)
        else:
            # If we're not one of the two allowed methods this should be caught
            # earlier
            return False

    test_func = user_can_see_study_responses

    def valid_responses(self, study):
        return study.responses_for_researcher(self.request.user).order_by("id")

    def get_response_values_for_framedata(self, study):
        return (
            self.valid_responses(study)
            .select_related("child", "study")
            .values(
                "uuid",
                "exp_data",
                "child__uuid",
                "study__uuid",
                "study__salt",
                "study__hash_digits",
                "global_event_timings",
            )
        )

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.
        """
        context = super().get_context_data(**kwargs)
        context["n_responses"] = (
            context["study"].responses_for_researcher(self.request.user).count()
        )
        context["data_options"] = [col for col in response_columns if col.optional]
        context["can_delete_preview_data"] = self.request.user.has_study_perms(
            StudyPermission.DELETE_ALL_PREVIEW_DATA, context["study"]
        )
        return context

    def post(self, request, *args, **kwargs):
        """
        Post method on all responses view handles the  'delete all preview data' button.
        """
        study = self.get_object()
        # Note: delete all, not just consented!
        preview_responses = study.responses.filter(is_preview=True).prefetch_related(
            "videos", "responselog_set", "consent_rulings", "feedback"
        )
        paginator = Paginator(preview_responses, RESPONSE_PAGE_SIZE)
        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                # response logs, consent rulings, feedback, videos will all be deleted
                # via cascades - videos will be removed from S3 also on pre_delete hook
                resp.delete()
        return super().get(request, *args, **kwargs)


class StudyResponsesAllDownloadJSON(StudyResponsesAll):
    """
    Hitting this URL downloads all study responses in JSON format.
    """

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = self.valid_responses(study)
        header_options = self.request.GET.getlist("data_options")
        cleaned_data = json.dumps(
            build_responses_json(responses, header_options), indent=4, default=str
        )
        identifiable_data_headers = [
            col.id for col in response_columns if col.identifiable
        ]
        filename = "{}_{}.json".format(
            study_name_for_files(study.name),
            "all-responses"
            + (
                "-identifiable"
                if any(
                    [option in identifiable_data_headers for option in header_options]
                )
                else ""
            ),
        )
        response = HttpResponse(cleaned_data, content_type="text/json")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponsesSummaryDownloadCSV(StudyResponsesAll):
    """
    Hitting this URL downloads a summary of all study responses in CSV format.
    """

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        header_options = self.request.GET.getlist("data_options")
        responses = self.valid_responses(study)
        cleaned_data = build_responses_csv(responses, header_options)
        identifiable_data_headers = [
            col.id for col in response_columns if col.identifiable
        ]
        filename = "{}_{}.csv".format(
            study_name_for_files(study.name),
            "all-responses"
            + (
                "-identifiable"
                if any(
                    [option in identifiable_data_headers for option in header_options]
                )
                else ""
            ),
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponsesSummaryDictCSV(StudyResponsesAll):
    """
    Hitting this URL downloads a data dictionary for the study response summary in CSV format. Does not depend on actual response data.
    """

    def build_summary_dict_csv(self, optional_headers_selected_ids):
        """
        Builds CSV file contents for data dictionary corresponding to the overview CSV
        """

        descriptions = {col.id: col.description for col in response_columns}
        headerList = get_response_headers(
            optional_headers_selected_ids, descriptions.keys()
        )
        all_descriptions = [
            {"column": header, "description": descriptions[header]}
            for header in headerList
        ]
        output, writer = csv_dict_output_and_writer(["column", "description"])
        writer.writerows(all_descriptions)
        return output.getvalue()

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        header_options = self.request.GET.getlist("data_options")
        cleaned_data = self.build_summary_dict_csv(header_options)
        filename = "{}_{}.csv".format(
            study_name_for_files(study.name), "all-responses-dict"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyChildrenSummaryCSV(StudyResponsesAll):
    """
    Hitting this URL downloads a summary of all children who participated in CSV format.
    """

    def build_child_csv(self, responses):
        """
        Builds CSV file contents for overview of all child participants
        """

        child_list = []
        session_list = []

        paginator = Paginator(responses, RESPONSE_PAGE_SIZE)

        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                row_data = flatten_dict(
                    {
                        col.id: col.extractor(resp)
                        for col in response_columns
                        if col.id in self.child_csv_headers
                    }
                )
                if row_data["child__global_id"] not in child_list:
                    child_list.append(row_data["child__global_id"])
                    session_list.append(row_data)

        output, writer = csv_dict_output_and_writer(self.child_csv_headers)
        writer.writerows(session_list)
        return output.getvalue()

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = self.valid_responses(study)
        cleaned_data = self.build_child_csv(responses)
        filename = "{}_{}.csv".format(
            study_name_for_files(study.name), "all-children-identifiable"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyChildrenSummaryDictCSV(StudyResponsesAll):
    """
    Hitting this URL downloads a data dictionary in CSV format for the summary of children who participated.
    Does not depend on actual response data.
    """

    def build_child_dict_csv(self):
        """
        Builds CSV file contents for data dictionary for overview of all child participants
        """

        all_descriptions = [
            {"column": col.id, "description": col.description}
            for col in response_columns
            if col.id in self.child_csv_headers
        ]
        output, writer = csv_dict_output_and_writer(["column", "description"])
        writer.writerows(all_descriptions)
        return output.getvalue()

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        cleaned_data = self.build_child_dict_csv()
        filename = "{}_{}.csv".format(
            study_name_for_files(study.name), "all-children-dict"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponsesFrameDataCSV(StudyResponsesAll):
    """
    Hitting this URL downloads frame-level data from all study responses in CSV format
    """

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = self.get_response_values_for_framedata(study)
        paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
        headers = get_frame_data(responses[0])["data_headers"]
        output, writer = csv_dict_output_and_writer(headers)

        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                this_resp_data = get_frame_data(resp)
                writer.writerows(this_resp_data["data"])

        cleaned_data = output.getvalue()

        filename = "{}_{}.csv".format(study_name_for_files(study.name), "all-frames")
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponsesFrameDataIndividualCSV(StudyResponsesAll):
    """Hitting this URL downloads a ZIP file with frame data from one response per file in CSV format"""

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = self.get_response_values_for_framedata(study)
        paginator = Paginator(responses, RESPONSE_PAGE_SIZE)

        zipped_file = io.BytesIO()  # import io
        with zipfile.ZipFile(
            zipped_file, "w", zipfile.ZIP_DEFLATED
        ) as zipped:  # import zipfile

            for page_num in paginator.page_range:
                page_of_responses = paginator.page(page_num)
                for resp in page_of_responses:
                    data = build_single_response_framedata_csv(resp)
                    filename = "{}_{}_{}.csv".format(
                        study_name_for_files(study.name), resp["uuid"], "frames"
                    )
                    zipped.writestr(filename, data)

        zipped_file.seek(0)
        response = HttpResponse(zipped_file, content_type="application/octet-stream")
        response[
            "Content-Disposition"
        ] = 'attachment; filename="{}_framedata_per_session.zip"'.format(
            study_name_for_files(study.name)
        )
        return response


class StudyResponsesFrameDataDictCSV(StudyResponsesAll):
    """
    Hitting this URL queues creation of a template data dictionary for frame-level data in CSV format.
    The file is put on GCP and a link is emailed to the user.
    """

    def get(self, request, *args, **kwargs):

        study = self.get_object()
        filename = "{}_{}_{}".format(
            study_name_for_files(study.name), study.uuid, "all-frames-dict"
        )

        build_framedata_dict.delay(filename, study.uuid, self.request.user.uuid)
        messages.success(
            request,
            f"A frame data dictionary for {self.get_object().name} is being generated. You will be emailed a link when it's completed.",
        )
        return HttpResponseRedirect(
            reverse("exp:study-responses-all", kwargs=dict(pk=self.get_object().pk))
        )


class StudyDemographics(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.DetailView,
):
    """
    StudyDemographics view shows participant demographic snapshots associated
    with each response to the study
    """

    template_name = "studies/study_demographics.html"
    queryset = Study.objects.all()
    raise_exception = True

    def user_can_view_study_responses(self):
        user = self.request.user
        study = self.get_object()
        return user.is_researcher and (
            user.has_study_perms(StudyPermission.READ_STUDY_RESPONSE_DATA, study)
            or user.has_study_perms(StudyPermission.READ_STUDY_PREVIEW_DATA, study)
        )

    test_func = user_can_view_study_responses

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


class StudyDemographicsDownloadJSON(StudyDemographics):
    """
    Hitting this URL downloads all participant demographics in JSON format.
    """

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


class StudyDemographicsDownloadCSV(StudyDemographics):
    """
    Hitting this URL downloads all participant demographics in CSV format.
    """

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


class StudyDemographicsDownloadDictCSV(StudyDemographics):
    """
    Hitting this URL downloads a data dictionary for participant demographics in in CSV format.
    Does not depend on any actual data.
    """

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


class StudyCollisionCheck(StudyResponsesAll):
    """
    Hitting this URL checks for collisions among all child and account hashed IDs, and returns a string describing
    any collisions (empty string if none).
    """

    def get(self, request, *args, **kwargs):
        study = self.get_object()
        responses = (
            study.consented_responses.order_by("id")
            .select_related("child", "child__user", "study")
            .values(
                "uuid",
                "child__uuid",
                "child__user__uuid",
                "study__uuid",
                "study__salt",
                "study__hash_digits",
            )
        )
        child_dict = {}
        account_dict = {}
        collision_text = ""
        # Note: could also just check number of unique global vs. hashed IDs in full dataset;
        # only checking one-by-one for more informative output.

        paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                participant_hashed_id = hash_participant_id(resp)
                participant_global_id = resp["child__user__uuid"]
                child_hashed_id = hash_child_id(resp)
                child_global_id = resp["child__uuid"]

                if participant_hashed_id in account_dict:
                    if participant_global_id != account_dict[participant_hashed_id]:
                        collision_text += "Participant hashed ID {} ({}, {})\n".format(
                            participant_hashed_id,
                            account_dict[participant_hashed_id],
                            participant_global_id,
                        )
                else:
                    account_dict[participant_hashed_id] = participant_global_id

                if child_hashed_id in child_dict:
                    if child_global_id != child_dict[child_hashed_id]:
                        collision_text += "Child hashed ID {} ({}, {})<br>".format(
                            child_hashed_id,
                            child_dict[child_hashed_id],
                            child_global_id,
                        )
                else:
                    child_dict[child_hashed_id] = child_global_id
        return JsonResponse({"collisions": collision_text})


class StudyAttachments(
    ExperimenterLoginRequiredMixin,
    UserPassesTestMixin,
    PaginatorMixin,
    SingleObjectParsimoniousQueryMixin,
    generic.DetailView,
):
    """
    StudyAttachments View shows video attachments for the study
    """

    template_name = "studies/study_attachments.html"
    queryset = Study.objects.prefetch_related("responses", "videos")
    raise_exception = True

    def user_can_see_study_responses(self):
        user = self.request.user
        study = self.get_object()

        return user.is_researcher and (
            user.has_study_perms(StudyPermission.READ_STUDY_RESPONSE_DATA, study)
            or user.has_study_perms(StudyPermission.READ_STUDY_PREVIEW_DATA, study)
        )

    test_func = user_can_see_study_responses

    def get_consented_videos(self, study):
        """
        Fetches all consented videos this user has access to.
        TODO: use a helper (e.g. in queries) select_videos_for_user to fetch the appropriate videos here
        and in build_zipfile_of_videos - deferring for the moment to work out dependencies.
        """
        videos = study.videos_for_consented_responses
        if not self.request.user.has_study_perms(
            StudyPermission.READ_STUDY_RESPONSE_DATA, study
        ):
            videos = videos.filter(response__is_preview=True)
        if not self.request.user.has_study_perms(
            StudyPermission.READ_STUDY_PREVIEW_DATA, study
        ):
            videos = videos.filter(response__is_preview=False)
        return videos

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.  Study results
        are paginated.
        """
        context = super().get_context_data(**kwargs)
        orderby = self.request.GET.get("sort", "full_name")
        match = self.request.GET.get("match", "")
        videos = self.get_consented_videos(context["study"])
        if match:
            videos = videos.filter(full_name__icontains=match)
        if orderby:
            videos = videos.order_by(orderby)
        context["videos"] = videos
        context["match"] = match
        return context

    def post(self, request, *args, **kwargs):
        """
        Downloads study video
        """
        attachment_url = self.request.POST.get("attachment")
        match = self.request.GET.get("match", "")
        orderby = self.request.GET.get("sort", "id") or "id"

        if attachment_url:
            return redirect(attachment_url)

        if self.request.POST.get("all-attachments"):
            build_zipfile_of_videos.delay(
                f"{self.get_object().uuid}_all_attachments",
                self.get_object().uuid,
                orderby,
                match,
                self.request.user.uuid,
                consent_only=False,
            )
            messages.success(
                request,
                f"An archive of videos for {self.get_object().name} is being generated. You will be emailed a link when it's completed.",
            )

        if self.request.POST.get("all-consent-videos"):
            build_zipfile_of_videos.delay(
                f"{self.get_object().uuid}_all_consent",
                self.get_object().uuid,
                orderby,
                match,
                self.request.user.uuid,
                consent_only=True,
            )
            messages.success(
                request,
                f"An archive of consent videos for {self.get_object().name} is being generated. You will be emailed a link when it's completed.",
            )

        return HttpResponseRedirect(
            reverse("exp:study-attachments", kwargs=dict(pk=self.get_object().pk))
        )
