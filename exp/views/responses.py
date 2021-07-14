import io
import json
import zipfile
from functools import cached_property
from typing import Callable, Dict, KeysView, List, NamedTuple, Set, Union

import requests
from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import ObjectDoesNotExist, SuspiciousOperation
from django.core.files import File
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.http import (
    FileResponse,
    HttpResponse,
    HttpResponseRedirect,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import redirect, reverse
from django.views import generic
from django.views.generic.base import View
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.list import MultipleObjectMixin

from accounts.utils import (
    hash_child_id,
    hash_demographic_id,
    hash_id,
    hash_participant_id,
)
from exp.utils import (
    RESPONSE_PAGE_SIZE,
    csv_dict_output_and_writer,
    csv_namedtuple_writer,
    flatten_dict,
    round_age,
    round_ages_from_birthdays,
    study_name_for_files,
)
from exp.views.mixins import (
    CanViewStudyResponsesMixin,
    ResearcherLoginRequiredMixin,
    SingleObjectFetchProtocol,
    StudyLookupMixin,
)
from studies.models import Feedback, Response, Study, Video
from studies.permissions import StudyPermission
from studies.queries import (
    get_consent_statistics,
    get_responses_with_current_rulings_and_videos,
)
from studies.tasks import build_framedata_dict, build_zipfile_of_videos


class ResponseDataColumn(NamedTuple):
    # id: Unique key to identify data. Used as CSV column header and any portion before __ is used to create a
    # sub-dictionary for JSON data.
    id: str
    description: str  # Description for data dictionary
    extractor: Callable[
        [Union[Response, Dict]], Union[str, List]
    ]  # Function to extract value from response instance or dict
    optional: bool = False  # is a column the user checks a box to include?
    name: str = ""  # used in template form for optional columns
    include_by_default: bool = False  # whether to initially check checkbox for field
    identifiable: bool = False  # used to determine filename signaling


# Columns for response downloads. Extractor functions expect Response instance
RESPONSE_COLUMNS = [
    ResponseDataColumn(
        id="response__id",
        description="Short ID for this response",
        extractor=lambda resp: str(resp.id),
        name="Response ID",
    ),
    ResponseDataColumn(
        id="response__uuid",
        description="Unique identifier for response. Can be used to match data to video filenames.",
        extractor=lambda resp: str(resp.uuid),
        name="Response UUID",
    ),
    ResponseDataColumn(
        id="response__date_created",
        description="Timestamp for when participant began session, in format e.g. 2019-11-07 17:13:38.702958+00:00",
        extractor=lambda resp: str(resp.date_created),
        name="Date created",
    ),
    ResponseDataColumn(
        id="response__completed",
        description=(
            "Whether the participant submitted the exit survey; depending on study criteria, this may not align "
            "with whether the session is considered complete. E.g., participant may have left early but submitted "
            "exit survey, or may have completed all test trials but not exit survey."
        ),
        extractor=lambda resp: resp.completed,
        name="Completed",
    ),
    ResponseDataColumn(
        id="response__withdrawn",
        description=(
            "Whether the participant withdrew permission for viewing/use of study video beyond consent video. If "
            "true, video will not be available and must not be used."
        ),
        extractor=lambda resp: resp.withdrawn,
        name="Withdrawn",
    ),
    ResponseDataColumn(
        id="response__parent_feedback",
        description=(
            "Freeform parent feedback entered into the exit survey, if any. This field may incidentally contain "
            "identifying or sensitive information depending on what parents say, so it should be scrubbed or "
            "omitted from published data."
        ),
        extractor=lambda resp: resp.parent_feedback,
        name="Parent feedback",
    ),
    ResponseDataColumn(
        id="response__birthdate_difference",
        description=(
            "Difference between birthdate entered in exit survey, if any, and birthdate of registered child "
            "participating. Positive values mean that the birthdate from the exit survey is LATER. Blank if "
            "no birthdate available from the exit survey."
        ),
        extractor=lambda resp: resp.birthdate_difference,
        name="Birthdate difference",
    ),
    ResponseDataColumn(
        id="response__video_privacy",
        description=(
            "Privacy level for videos selected during the exit survey, if the parent completed the exit survey. "
            "Possible levels are 'private' (only people listed on your IRB protocol can view), 'scientific' "
            "(can share for scientific/educational purposes), and 'public' (can also share for publicity). "
            "In no cases may videos be shared for commercial purposes. If this is missing (e.g., family stopped "
            "just after the consent form and did not complete the exit survey), you must treat the video as "
            "private."
        ),
        extractor=lambda resp: resp.privacy,
        name="Video privacy level",
    ),
    ResponseDataColumn(
        id="response__databrary",
        description=(
            "Whether the parent agreed to share video data on Databrary - 'yes' or 'no'. If missing, you must "
            "treat the video as if 'no' were selected. If 'yes', the video privacy selections also apply to "
            "authorized Databrary users."
        ),
        extractor=lambda resp: resp.databrary,
        name="Databrary sharing",
    ),
    ResponseDataColumn(
        id="response__is_preview",
        description=(
            "Whether this response was generated by a researcher previewing the experiment. Preview data should "
            "not be used in any actual analyses."
        ),
        extractor=lambda resp: resp.is_preview,
        name="Preview",
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
        name="Parent ID",
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
        name="Child ID",
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
        name="Response sequence",
    ),
    ResponseDataColumn(
        id="response__conditions",
        description=(
            "RESEARCHERS: EXPAND THIS SECTION BASED ON YOUR INDIVIDUAL STUDY. Each set of "
            "response_conditions.N.(...) fields give information about condition assignment during a particular "
            "frame of this study. response_conditions.0.frameName is the frame ID (corresponding to a value in "
            "response_sequence) where the randomization occurred. Additional fields such as "
            "response_conditions.0.conditionNum depend on the specific randomizer frames used in this study."
        ),
        extractor=lambda resp: [
            {**{"frameName": cond_frame}, **conds}
            for (cond_frame, conds) in resp.conditions.items()
        ],
    ),
]

# Columns for demographic data downloads. Extractor functions expect Response values dict,
# rather than instance.
DEMOGRAPHIC_COLUMNS = [
    ResponseDataColumn(
        id="response__uuid",
        description=(
            "Primary unique identifier for response. Can be used to match demographic data to response data "
            "and video filenames; must be redacted prior to publication if videos are also published."
        ),
        extractor=lambda resp: str(resp["uuid"]),
        name="Response UUID",
    ),
    ResponseDataColumn(
        id="participant__global_id",
        description=(
            "Unique identifier for family account associated with this response. Will be the same for multiple "
            "responses from a child and for siblings, and across different studies. MUST BE REDACTED FOR "
            "PUBLICATION because this allows identification of families across different published studies, "
            "which may have unintended privacy consequences. Researchers can use this ID to match participants "
            "across studies (subject to their own IRB review), but would need to generate their own random "
            "participant IDs for publication in that case. Use participant__hashed_id as a publication-safe "
            "alternative if only analyzing data from one Lookit study."
        ),
        extractor=lambda resp: str(resp["child__user__uuid"]),
        optional=True,
        name="Parent global ID",
        include_by_default=False,
        identifiable=True,
    ),
    ResponseDataColumn(
        id="participant__hashed_id",
        description=(
            "Identifier for family account associated with this response. Will be the same for multiple "
            "responses from a child and for siblings, but is unique to this study. This may be published "
            "directly."
        ),
        extractor=lambda resp: hash_participant_id(resp),
        name="Participant ID",
    ),
    ResponseDataColumn(
        id="demographic__hashed_id",
        description=(
            "Identifier for this demographic snapshot. Changes upon updates to the demographic form, "
            "so may vary within the same participant across responses."
        ),
        extractor=lambda resp: hash_demographic_id(resp),
        name="Demographic ID",
    ),
    ResponseDataColumn(
        id="demographic__date_created",
        description=(
            "Timestamp of creation of the demographic snapshot associated with this response, in format e.g. "
            "2019-10-02 21:39:03.713283+00:00"
        ),
        extractor=lambda resp: str(resp["demographic_snapshot__created_at"]),
        name="Date created",
    ),
    ResponseDataColumn(
        id="demographic__number_of_children",
        description="Response to 'How many children do you have?'; options 0-10 or >10 (More than 10)",
        extractor=lambda resp: resp["demographic_snapshot__number_of_children"],
        name="Number of children",
    ),
    ResponseDataColumn(
        id="demographic__child_rounded_ages",
        description=(
            "List of rounded ages based on child birthdays entered in demographic form (not based on children "
            "registered). Ages are at time of response for this row, in days, rounded to nearest 10 for ages "
            "under 1 year and nearest 30 otherwise. In format e.g. [60, 390]"
        ),
        extractor=lambda resp: round_ages_from_birthdays(
            resp["demographic_snapshot__child_birthdays"], resp["date_created"]
        ),
        name="Child ages rounded",
    ),
    ResponseDataColumn(
        id="demographic__languages_spoken_at_home",
        description="Freeform response to 'What language(s) does your family speak at home?'",
        extractor=lambda resp: resp["demographic_snapshot__languages_spoken_at_home"],
        name="Languages spoken at home",
    ),
    ResponseDataColumn(
        id="demographic__number_of_guardians",
        description="Response to 'How many parents/guardians do your children live with?' - 1, 2, 3> [3 or more], varies",
        extractor=lambda resp: resp["demographic_snapshot__number_of_guardians"],
        name="Number of guardians",
    ),
    ResponseDataColumn(
        id="demographic__number_of_guardians_explanation",
        description=(
            "Freeform response to 'If the answer varies due to shared custody arrangements or travel, please "
            "enter the number of parents/guardians your children are usually living with or explain.'"
        ),
        extractor=lambda resp: resp[
            "demographic_snapshot__number_of_guardians_explanation"
        ],
        name="Number of guardians explanation",
    ),
    ResponseDataColumn(
        id="demographic__race_identification",
        description=(
            "Comma-separated list of all values checked for question 'What category(ies) does your family "
            "identify as?', from list:  White; Hispanic, Latino, or Spanish origin; Black or African American; "
            "Asian; American Indian or Alaska Native; Middle Eastern or North African; Native Hawaiian or "
            "Other Pacific Islander; Another race, ethnicity, or origin"
        ),
        extractor=lambda resp: resp["demographic_snapshot__race_identification"],
        name="Race",
    ),
    ResponseDataColumn(
        id="demographic__parent_age",
        description=(
            "Parent's response to question 'What is your age?'; options are <18, 18-21, 22-24, 25-29, 30-34, "
            "35-39, 40-44, 45-49, 50s, 60s, >70"
        ),
        extractor=lambda resp: resp["demographic_snapshot__age"],
        name="Parent age",
    ),
    ResponseDataColumn(
        id="demographic__parent_gender",
        description=(
            "Parent's response to question 'What is your gender?'; options are m [male], f [female], o "
            "[other], na [prefer not to answer]"
        ),
        extractor=lambda resp: resp["demographic_snapshot__gender"],
        name="Parent age",
    ),
    ResponseDataColumn(
        id="demographic__education_level",
        description=(
            "Parent's response to question 'What is the highest level of education you've completed?'; options "
            "are some [some or attending high school], hs [high school diploma or GED], col [some or attending "
            "college], assoc [2-year college degree], bach [4-year college degree], grad [some or attending "
            "graduate or professional school], prof [graduate or professional degree]"
        ),
        extractor=lambda resp: resp["demographic_snapshot__education_level"],
        name="Parent education level",
    ),
    ResponseDataColumn(
        id="demographic__spouse_education_level",
        description=(
            "Parent's response to question 'What is the highest level of education your spouse has "
            "completed?'; options are some [some or attending high school], hs [high school diploma or GED], "
            "col [some or attending college], assoc [2-year college degree], bach [4-year college degree], "
            "grad [some or attending graduate or professional school], prof [graduate or professional degree], "
            "na [not applicable - no spouse or partner]"
        ),
        extractor=lambda resp: resp["demographic_snapshot__spouse_education_level"],
        name="Parent education level",
    ),
    ResponseDataColumn(
        id="demographic__annual_income",
        description=(
            "Parent's response to question 'What is your approximate family yearly income (in US dollars)?'; "
            "options are 0, 5000, 10000, 15000, 20000-19000 in increments of 10000, >200000, or na [prefer not "
            "to answer]"
        ),
        extractor=lambda resp: resp["demographic_snapshot__annual_income"],
        name="Annual income",
    ),
    ResponseDataColumn(
        id="demographic__number_of_books",
        description="Parent's response to question 'About how many children's books are there in your home?'; integer",
        extractor=lambda resp: resp["demographic_snapshot__number_of_books"],
        name="Number of books",
    ),
    ResponseDataColumn(
        id="demographic__additional_comments",
        description="Parent's freeform response to question 'Anything else you'd like us to know?'",
        extractor=lambda resp: resp["demographic_snapshot__additional_comments"],
        name="Additional comments",
    ),
    ResponseDataColumn(
        id="demographic__country",
        description="Parent's response to question 'What country do you live in?'; 2-letter country code",
        extractor=lambda resp: resp["demographic_snapshot__country"],
        name="Country code",
    ),
    ResponseDataColumn(
        id="demographic__state",
        description=(
            "Parent's response to question 'What state do you live in?' if country is US; 2-letter state "
            "abbreviation"
        ),
        extractor=lambda resp: resp["demographic_snapshot__state"],
        name="US State",
    ),
    ResponseDataColumn(
        id="demographic__density",
        description=(
            "Parent's response to question 'How would you describe the area where you live?'; options are "
            "urban, suburban, rural"
        ),
        extractor=lambda resp: resp["demographic_snapshot__density"],
        name="Density",
    ),
    ResponseDataColumn(
        id="demographic__lookit_referrer",
        description="Parent's freeform response to question 'How did you hear about Lookit?'",
        extractor=lambda resp: resp["demographic_snapshot__lookit_referrer"],
        name="How you heard about Lookit",
    ),
]

# Which headers from the response data summary should go in the child data downloads
CHILD_CSV_HEADERS = [
    col.id
    for col in RESPONSE_COLUMNS
    if col.id.startswith("child__") or col.id.startswith("participant__")
]

IDENTIFIABLE_DATA_HEADERS = {col.id for col in RESPONSE_COLUMNS if col.identifiable}


def get_response_headers(
    selected_header_ids: Union[Set, List],
    all_available_header_ids: Union[Set, KeysView],
) -> List:
    """Get ordered list of response headers for download.

    Select and order the appropriate headers to include in a file download, based on
    which optional headers are selected and which headers are available.

    Args:
        selected_header_ids: which optional headers to include (corresponding to id values in
            RESPONSE_COLUMNS). Headers that are specified as optional in RESPONSE_COLUMNS will
            only be included if listed in selected_header_ids.

        all_available_header_ids: all header ids we have data for. Any header ids that are in
            this set but not in RESPONSE_COLUMNS will be added to the end of the output list.

    Returns:
        List of headers to include, consisting of the following in order:
        1) Headers in RESPONSE_COLUMNS, in order, omitting any that are optional and were not selected
        2) Extra headers from all_available_header_ids not included in (1), in alpha order
    """
    unselected_optional_ids = {
        col.id
        for col in RESPONSE_COLUMNS
        if col.optional and col.id not in selected_header_ids
    }
    selected_standard_header_ids = [
        col.id
        for col in RESPONSE_COLUMNS[0:-2]
        if col.id not in unselected_optional_ids
    ]
    return selected_standard_header_ids + sorted(
        list(
            all_available_header_ids
            - set(selected_standard_header_ids)
            - unselected_optional_ids
        )
    )


def get_demographic_headers(selected_header_ids=None) -> List[str]:
    """Get ordered list of demographic headers for download.

    Args:
        selected_header_ids(set or list): which optional headers to include (corresponding
            to id values in DEMOGRAPHIC_COLUMNS).

    Returns:
        Ordered list of headers to include in download

        Headers are id values from DEMOGRAPHIC_COLUMNS in order, omitting any that are optional
        and were not included in selected_header_ids.
    """
    if selected_header_ids is None:
        selected_header_ids = {}
    return [
        col.id
        for col in DEMOGRAPHIC_COLUMNS
        if col.id in selected_header_ids or not col.optional
    ]


def construct_response_dictionary(
    resp, columns, optional_headers, include_exp_data=True
):
    if optional_headers is None:
        optional_headers = {}
    resp_dict = {}
    for col in columns:
        if col.id in optional_headers or not col.optional:
            try:
                object_name, field_name = col.id.split("__")
                if object_name in resp_dict:
                    resp_dict[object_name][field_name] = col.extractor(resp)
                else:
                    resp_dict[object_name] = {field_name: col.extractor(resp)}
            except ValueError:
                resp_dict[col.id] = col.extractor(resp)
    # Include exp_data field in dictionary?
    if include_exp_data:
        resp_dict["exp_data"] = resp.exp_data
    return resp_dict


class FrameDataRow(NamedTuple):
    response_uuid: str
    child_hashed_id: str
    frame_id: str
    event_number: str
    key: str
    value: str


FRAME_DATA_HEADER_DESCRIPTIONS = {
    "response_uuid": "Unique identifier for this response; can be matched to summary data and video filenames",
    "child_hashed_id": (
        "Hashed identifier for the child associated with this response; can be matched to summary data "
        "child_hashed_id. This random ID may be published directly; it is specific to this study. If you "
        "need to match children across multiple studies, use the child_global_id."
    ),
    "frame_id": (
        "Identifier for the particular frame responsible for this data; matches up to an element in the "
        "response_sequence in the summary data file"
    ),
    "event_number": (
        "Index of the event responsible for this data, if this is an event. Indexes start from 0 within each "
        "frame (and within global data) within each response. Blank for non-event data."
    ),
    "key": "Label for a piece of data collected during this frame - for example, 'formData.child_favorite_animal'",
    "value": "Value of the data associated with this key (of the indexed event if applicable) - for example, 'giraffe'",
}


def get_frame_data(resp: Union[Response, Dict]) -> List[FrameDataRow]:
    """Get list of data stored in response's exp_data and global_event_timings fields.

    Args:
        resp(Response or dict): response data to process. If dict, must contain fields
            child__uuid, study__uuid, study__salt, study__hash_digits, uuid, exp_data, and
            global_event_timings.

    Returns:
        List of FrameDataRows each representing a single piece of data from global_event_timings or
        exp_data. Descriptions of each field of the FrameDataRow are given in FRAME_DATA_HEADER_DESCRIPTIONS.
    """

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

    frame_data_tuples = []
    child_hashed_id = hash_id(
        resp["child__uuid"],
        resp["study__uuid"],
        resp["study__salt"],
        resp["study__hash_digits"],
    )

    # First add all of the global event timings as events with frame_id "global"
    for (iEvent, event) in enumerate(resp["global_event_timings"]):
        for (key, value) in event.items():
            frame_data_tuples.append(
                FrameDataRow(
                    child_hashed_id=child_hashed_id,
                    response_uuid=str(resp["uuid"]),
                    frame_id="global",
                    key=key,
                    event_number=str(iEvent),
                    value=value,
                )
            )

    # Next add all data in exp_data
    event_prefix = "eventTimings."
    for frame_id, frame_data in resp["exp_data"].items():
        for (key, value) in flatten_dict(frame_data).items():
            # Process event data separately and include event_number within frame
            if key.startswith(event_prefix):
                key_pieces = key.split(".")
                frame_data_tuples.append(
                    FrameDataRow(
                        child_hashed_id=child_hashed_id,
                        response_uuid=str(resp["uuid"]),
                        frame_id=frame_id,
                        key=".".join(key_pieces[2:]),
                        event_number=str(key_pieces[1]),
                        value=value,
                    )
                )
                # omit frameType values from CSV
            elif key == "frameType":
                continue
                # Omit the DOB from any exit survey
            elif key == "birthDate" and frame_data.get("frameType", None) == "EXIT":
                continue
                # Omit empty generatedProperties values from CSV
            elif key == "generatedProperties" and not value:
                continue
                # For all other data, create a regular entry with frame_id and no event #
            else:
                frame_data_tuples.append(
                    FrameDataRow(
                        child_hashed_id=child_hashed_id,
                        response_uuid=str(resp["uuid"]),
                        frame_id=frame_id,
                        key=key,
                        event_number="",
                        value=value,
                    )
                )

    return frame_data_tuples


def build_framedata_dict_csv(writer, responses):
    response_paginator = Paginator(responses, RESPONSE_PAGE_SIZE)
    unique_frame_ids = set()
    event_keys = set()
    unique_frame_keys_dict = {}

    for page_num in response_paginator.page_range:
        page_of_responses = response_paginator.page(page_num)
        for resp in page_of_responses:
            this_resp_data = get_frame_data(resp)
            these_ids = {
                d.frame_id.partition("-")[2]
                for d in this_resp_data
                if not d.frame_id == "global"
            }
            event_keys = event_keys | {
                d.key for d in this_resp_data if d.event_number != ""
            }
            unique_frame_ids = unique_frame_ids | these_ids
            for frame_id in these_ids:
                these_keys = {
                    d.key
                    for d in this_resp_data
                    if d.frame_id.partition("-")[2] == frame_id and d.event_number == ""
                }
                if frame_id in unique_frame_keys_dict:
                    unique_frame_keys_dict[frame_id] = (
                        unique_frame_keys_dict[frame_id] | these_keys
                    )
                else:
                    unique_frame_keys_dict[frame_id] = these_keys

    # Start with general descriptions of high-level headers (child_id, response_id, etc.)
    writer.writerows(
        [
            {"column": header, "description": description}
            for (header, description) in FRAME_DATA_HEADER_DESCRIPTIONS.items()
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
    output, writer = csv_namedtuple_writer(FrameDataRow)
    writer.writerows(this_resp_data)

    return output.getvalue()


class ResponseDownloadMixin(CanViewStudyResponsesMixin, MultipleObjectMixin):
    model = Response
    paginate_by = 10
    ordering = "id"

    def get_queryset(self):
        study = self.study
        return study.responses_for_researcher(self.request.user).order_by(
            self.get_ordering()
        )


class DemographicDownloadMixin(CanViewStudyResponsesMixin, MultipleObjectMixin):
    model = Response
    paginate_by = 10
    ordering = "id"

    def get_queryset(self):
        study = self.study
        return (
            study.responses_for_researcher(self.request.user)
            .order_by(self.get_ordering())
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


class StudyResponsesList(ResponseDownloadMixin, generic.ListView):
    """
    View to display a list of study responses.
    """

    template_name = "studies/study_responses.html"

    def get_ordering(self):
        """
        Determine sort field and order. Sorting on id actually sorts on child id, not response id.
        Sorting on status, actually sorts on 'completed' field, where we are alphabetizing
        "in progress" and "completed"
        """
        orderby = self.request.GET.get("sort", "id")
        return orderby.replace("id", "child__id").replace("status", "completed")

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .prefetch_related(
                "consent_rulings__arbiter",
                Prefetch(
                    "feedback",
                    queryset=Feedback.objects.select_related("researcher").order_by(
                        "-id"
                    ),
                ),
            )
        )

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.  Study results
        are paginated.
        """
        context = super().get_context_data(**kwargs)
        context["study"] = study = self.study
        paginated_responses = context["object_list"]
        columns_included_in_summary = [
            "response__id",
            "response__uuid",
            "response__date_created",
            "response__completed",
            "response__withdrawn",
            "response__parent_feedback",
            "response__birthdate_difference",
            "response__video_privacy",
            "response__databrary",
            "response__is_preview",
            "response__sequence",
            "participant__global_id",
            "participant__hashed_id",
            "participant__nickname",
            "child__global_id",
            "child__hashed_id",
            "child__name",
            "child__age_rounded",
            "child__gender",
            "child__age_at_birth",
            "child__language_list",
            "child__condition_list",
            "child__additional_information",
        ]

        columns_included_in_table = [
            "child__hashed_id",
            "response__uuid",
            "response__id",
            "response__status",
            "response__completed",
            "response__is_preview",
        ]
        response_data = []
        for resp in paginated_responses:
            # Info needed for table display of individual responses
            this_resp_data = {
                col.id: col.extractor(resp)
                for col in RESPONSE_COLUMNS
                if col.id in columns_included_in_table
            }
            # Exception - store actual date object for date created
            this_resp_data["response__date_created"] = resp.date_created
            # info needed for summary table shown at right
            this_resp_data["summary"] = [
                {
                    "name": col.name,
                    "value": col.extractor(resp),
                    "description": col.description,
                }
                for col in RESPONSE_COLUMNS
                if col.id in columns_included_in_summary
            ]
            this_resp_data["videos"] = resp.videos.values("pk", "full_name")
            for v in this_resp_data["videos"]:
                v["display_name"] = (
                    v["full_name"]
                    .replace("videoStream_{}_".format(study.uuid), "...")
                    .replace("_{}_".format(resp.uuid), "...")
                )
            response_data.append(this_resp_data)
        context["response_data"] = response_data
        context["data_options"] = [col for col in RESPONSE_COLUMNS if col.optional]
        context["can_view_regular_responses"] = self.request.user.has_study_perms(
            StudyPermission.READ_STUDY_RESPONSE_DATA, context["study"]
        )
        context["can_view_preview_responses"] = self.request.user.has_study_perms(
            StudyPermission.READ_STUDY_PREVIEW_DATA, context["study"]
        )
        context["can_edit_feedback"] = self.request.user.has_study_perms(
            StudyPermission.EDIT_STUDY_FEEDBACK, context["study"]
        )

        return context

    def build_video_display_name(self, study_uuid, response_uuid, vid_name):
        """
        Strips study_uuid and response_uuid out of video responses titles for better display.
        """
        return ". . ." + ". . .".join(
            vid_name.split(study_uuid + "_")[1].split("_" + response_uuid + "_")
        )


class StudySingleResponseDownload(ResponseDownloadMixin, View):
    """
    Download a single study response in the selected format with selected headers.
    """

    def get(self, *args, **kwargs):
        data_type = self.request.GET.get("data-type-selector", None)
        if data_type not in ["json", "csv", "framedata"]:
            raise SuspiciousOperation

        response_id = self.request.GET.get("response_id", None)
        try:
            resp = self.get_queryset().get(pk=response_id)
        except ObjectDoesNotExist:
            raise SuspiciousOperation

        study = self.study
        header_options = set(self.request.GET.getlist("data_options"))
        extension = "json" if data_type == "json" else "csv"
        filename = "{}_{}{}.{}".format(
            study_name_for_files(study.name),
            str(resp.uuid),
            "_frames"
            if data_type == "json"
            else "_identifiable"
            if IDENTIFIABLE_DATA_HEADERS & header_options
            else "",
            extension,
        )

        if data_type == "json":
            cleaned_data = json.dumps(
                construct_response_dictionary(resp, RESPONSE_COLUMNS, header_options),
                indent="\t",
                default=str,
            )
        elif data_type == "csv":
            row_data = flatten_dict(
                {col.id: col.extractor(resp) for col in RESPONSE_COLUMNS}
            )
            header_list = get_response_headers(header_options, row_data.keys())
            output, writer = csv_dict_output_and_writer(header_list)
            writer.writerow(row_data)
            cleaned_data = output.getvalue()
        elif data_type == "framedata":
            cleaned_data = build_single_response_framedata_csv(resp)
        else:
            raise SuspiciousOperation
        response = HttpResponse(cleaned_data, content_type="text/{}".format(extension))
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponseVideoAttachment(
    ResearcherLoginRequiredMixin, UserPassesTestMixin, StudyLookupMixin, View
):
    """
    View that redirects to a requested video for a study response.
    """

    raise_exception = True

    @cached_property
    def video(self):
        # Only select the video from consented videos for this study
        return self.study.videos_for_consented_responses.get(
            pk=self.kwargs.get("video")
        )

    def can_view_this_video(self):
        user = self.request.user
        study = self.study
        video = self.video

        return user.is_researcher and (
            (
                user.has_study_perms(StudyPermission.READ_STUDY_RESPONSE_DATA, study)
                and not video.response.is_preview
            )
            or (
                user.has_study_perms(StudyPermission.READ_STUDY_PREVIEW_DATA, study)
                and video.response.is_preview
            )
        )

    test_func = can_view_this_video

    def get(self, request, *args, **kwargs):
        video = self.video
        download_url = video.download_url

        if self.request.GET.get("mode") == "download":
            r = requests.get(download_url)
            response = FileResponse(
                File.open(io.BytesIO(r.content)),
                filename=video.filename,
                as_attachment=True,
            )
            return response

        return redirect(download_url)


class StudyResponseSubmitFeedback(StudyLookupMixin, UserPassesTestMixin, View):
    """
    View to create or edit response feedback.
    """

    def user_can_edit_feedback(self):
        user = self.request.user
        study = self.study
        # First check user has permission to be editing feedback from this study at all
        if not user.is_researcher and user.has_study_perms(
            StudyPermission.EDIT_STUDY_FEEDBACK, study
        ):
            return False
        # Check that the feedback_id (if given) is from this study
        feedback_id = self.request.POST.get("feedback_id", None)
        if feedback_id:
            try:
                feedback = Feedback.objects.get(id=feedback_id)
            except ObjectDoesNotExist:
                return False
            if feedback.response.study_id != study.pk:
                return False
        # Check that the response_id (if given) is from this study
        response_id = self.request.POST.get("response_id", None)
        if response_id:
            try:
                response = Response.objects.get(id=int(response_id))
            except ObjectDoesNotExist:
                return False
            if response.study_id != study.pk:
                return False
        return True

    test_func = user_can_edit_feedback

    def post(self, request, *args, **kwargs):
        """
        Create or edit feedback. Pass feedback_id to edit existing feedback, or response_id to create new
        feedback for that response.
        """
        form_data = self.request.POST
        user = self.request.user
        study = self.study

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
            reverse("exp:study-responses-list", kwargs=dict(pk=study.pk))
        )


class StudyResponsesConsentManager(
    ResearcherLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectFetchProtocol[Study],
    generic.DetailView,
):
    """Manage consent videos from here: approve or reject as evidence of informed consent."""

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

        # TODO: Use json_script template tag to create JSON that can be used in Javascript
        #       (see https://docs.djangoproject.com/en/3.0/ref/templates/builtins/#json-script)
        context["response_key_value_store"] = json.dumps(response_key_value_store)

        return context

    def post(self, request, *args, **kwargs):
        """This is where consent rulings are submitted."""
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
    CanViewStudyResponsesMixin, SingleObjectFetchProtocol[Study], generic.DetailView
):
    """
    StudyResponsesAll shows a variety of download options for response and child data
    from a given study. (It does not actually show any data.)
    """

    template_name = "studies/study_responses_all.html"
    queryset = Study.objects.all()
    http_method_names = ["get"]

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.
        """
        context = super().get_context_data(**kwargs)
        context["n_responses"] = (
            context["study"].responses_for_researcher(self.request.user).count()
        )
        context["data_options"] = [col for col in RESPONSE_COLUMNS if col.optional]
        context["can_delete_preview_data"] = self.request.user.has_study_perms(
            StudyPermission.DELETE_ALL_PREVIEW_DATA, context["study"]
        )
        context["can_view_regular_responses"] = self.request.user.has_study_perms(
            StudyPermission.READ_STUDY_RESPONSE_DATA, context["study"]
        )
        context["can_view_preview_responses"] = self.request.user.has_study_perms(
            StudyPermission.READ_STUDY_PREVIEW_DATA, context["study"]
        )
        return context


class StudyDeletePreviewResponses(
    ResearcherLoginRequiredMixin,
    UserPassesTestMixin,
    SingleObjectFetchProtocol[Study],
    SingleObjectMixin,
    View,
):
    queryset = Study.objects.all()

    def user_can_delete_preview_data(self):
        user = self.request.user
        study = self.get_object()
        return user.is_researcher and user.has_study_perms(
            StudyPermission.DELETE_ALL_PREVIEW_DATA, study
        )

    test_func = user_can_delete_preview_data

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
        return HttpResponseRedirect(
            reverse("exp:study-responses-all", kwargs={"pk": study.id})
        )


class StudyResponsesJSON(ResponseDownloadMixin, generic.list.ListView):
    """
    Hitting this URL downloads all study responses in JSON format.
    """

    # Smaller pagination because individual responses may be large and we don't want the json representing 100
    # responses in memory
    paginate_by = 1

    def make_chunk(self, paginator, page_num, header_options):
        chunk = ""
        if page_num == 1:
            chunk = "[\n"
        chunk += ",\n".join(
            json.dumps(
                construct_response_dictionary(resp, RESPONSE_COLUMNS, header_options),
                indent="\t",  # Use tab rather than spaces to make file smaller (ex. 60MB -> 25MB)
                default=str,
            )
            for resp in paginator.page(page_num)
        )
        if page_num == paginator.page_range[-1]:
            chunk += "\n]"
        else:
            chunk += ",\n"
        return chunk

    def render_to_response(self, context, **response_kwargs):
        paginator = context["paginator"]
        study = self.study
        header_options = set(self.request.GET.getlist("data_options"))
        filename = "{}_{}.json".format(
            study_name_for_files(study.name),
            "all-responses"
            + ("-identifiable" if IDENTIFIABLE_DATA_HEADERS & header_options else ""),
        )

        response = StreamingHttpResponse(
            (
                self.make_chunk(paginator, page_num, header_options)
                for page_num in paginator.page_range
            ),
            content_type="text/json",
        )
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponsesCSV(ResponseDownloadMixin, generic.list.ListView):
    """
    Hitting this URL downloads a summary of all study responses in CSV format.
    """

    def render_to_response(self, context, **response_kwargs):
        paginator = context["paginator"]
        study = self.study

        headers = set()
        session_list = []

        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                row_data = flatten_dict(
                    {col.id: col.extractor(resp) for col in RESPONSE_COLUMNS}
                )
                # Add any new headers from this session
                headers = headers | row_data.keys()
                session_list.append(row_data)
        header_options = set(self.request.GET.getlist("data_options"))
        header_list = get_response_headers(header_options, headers)
        output, writer = csv_dict_output_and_writer(header_list)
        writer.writerows(session_list)
        cleaned_data = output.getvalue()

        filename = "{}_{}.csv".format(
            study_name_for_files(study.name),
            "all-responses"
            + ("-identifiable" if IDENTIFIABLE_DATA_HEADERS & header_options else ""),
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponsesDictCSV(CanViewStudyResponsesMixin, View):
    """
    Hitting this URL downloads a data dictionary for the study response summary in CSV format. Does not depend on actual response data.
    """

    def build_summary_dict_csv(self, optional_headers_selected_ids):
        """
        Builds CSV file contents for data dictionary corresponding to the overview CSV
        """

        descriptions = {col.id: col.description for col in RESPONSE_COLUMNS}
        header_list = get_response_headers(
            optional_headers_selected_ids, descriptions.keys()
        )
        all_descriptions = [
            {"column": header, "description": descriptions[header]}
            for header in header_list
        ]
        output, writer = csv_dict_output_and_writer(["column", "description"])
        writer.writerows(all_descriptions)
        return output.getvalue()

    def get(self, request, *args, **kwargs):
        study = self.study
        header_options = self.request.GET.getlist("data_options")
        cleaned_data = self.build_summary_dict_csv(header_options)
        filename = "{}_{}.csv".format(
            study_name_for_files(study.name), "all-responses-dict"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyChildrenCSV(ResponseDownloadMixin, generic.list.ListView):
    """
    Hitting this URL downloads a summary of all children who participated in CSV format.
    """

    def render_to_response(self, context, **response_kwargs):
        paginator = context["paginator"]
        study = self.study

        child_list = []
        session_list = []

        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                row_data = flatten_dict(
                    {
                        col.id: col.extractor(resp)
                        for col in RESPONSE_COLUMNS
                        if col.id in CHILD_CSV_HEADERS
                    }
                )
                if row_data["child__global_id"] not in child_list:
                    child_list.append(row_data["child__global_id"])
                    session_list.append(row_data)

        output, writer = csv_dict_output_and_writer(CHILD_CSV_HEADERS)
        writer.writerows(session_list)
        cleaned_data = output.getvalue()

        filename = "{}_{}.csv".format(
            study_name_for_files(study.name), "all-children-identifiable"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyChildrenDictCSV(CanViewStudyResponsesMixin, View):
    """
    Hitting this URL downloads a data dictionary in CSV format for the summary of children who participated.
    Does not depend on actual response data.
    TODO: separate from response data mixin
    """

    def build_child_dict_csv(self):
        """
        Builds CSV file contents for data dictionary for overview of all child participants
        """

        all_descriptions = [
            {"column": col.id, "description": col.description}
            for col in RESPONSE_COLUMNS
            if col.id in CHILD_CSV_HEADERS
        ]
        output, writer = csv_dict_output_and_writer(["column", "description"])
        writer.writerows(all_descriptions)
        return output.getvalue()

    def get(self, request, *args, **kwargs):
        study = self.study
        cleaned_data = self.build_child_dict_csv()
        filename = "{}_{}.csv".format(
            study_name_for_files(study.name), "all-children-dict"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyResponsesFrameDataCSV(ResponseDownloadMixin, generic.list.ListView):
    """Hitting this URL downloads a ZIP file with frame data from one response per file in CSV format"""

    # TODO: with large files / many responses generation can take a while. Should generate asynchronously along
    # with the data dict.
    def render_to_response(self, context, **response_kwargs):
        paginator = context["paginator"]
        study = self.study

        zipped_file = io.BytesIO()  # import io
        with zipfile.ZipFile(zipped_file, "w", zipfile.ZIP_DEFLATED) as zipped:
            for page_num in paginator.page_range:
                page_of_responses = paginator.page(page_num)
                for resp in page_of_responses:
                    data = build_single_response_framedata_csv(resp)
                    filename = "{}_{}_{}.csv".format(
                        study_name_for_files(study.name), resp.uuid, "frames"
                    )
                    zipped.writestr(filename, data)

        zipped_file.seek(0)
        response = FileResponse(
            zipped_file,
            as_attachment=True,
            filename="{}_framedata_per_session.zip".format(
                study_name_for_files(study.name)
            ),
        )
        return response


class StudyResponsesFrameDataDictCSV(ResponseDownloadMixin, View):
    """
    Hitting this URL queues creation of a template data dictionary for frame-level data in CSV format.
    The file is put on GCP and a link is emailed to the user.
    """

    def get(self, request, *args, **kwargs):
        study = self.study
        filename = "{}_{}_{}".format(
            study_name_for_files(study.name), study.uuid, "all-frames-dict"
        )

        build_framedata_dict.delay(filename, study.uuid, self.request.user.uuid)
        messages.success(
            request,
            f"A frame data dictionary for {study.name} is being generated. You will be emailed a link when it's completed.",
        )
        return HttpResponseRedirect(
            reverse("exp:study-responses-all", kwargs=self.kwargs)
        )


class StudyDemographics(
    CanViewStudyResponsesMixin, SingleObjectFetchProtocol[Study], generic.DetailView
):
    """
    StudyDemographics view shows participant demographic snapshots associated
    with each response to the study
    """

    template_name = "studies/study_demographics.html"
    queryset = Study.objects.all()

    def get_context_data(self, **kwargs):
        """
        Adds information for displaying how many and which types of responses are available.
        """
        context = super().get_context_data(**kwargs)
        context["n_responses"] = (
            context["study"].responses_for_researcher(self.request.user).count()
        )
        context["can_view_regular_responses"] = self.request.user.has_study_perms(
            StudyPermission.READ_STUDY_RESPONSE_DATA, context["study"]
        )
        context["can_view_preview_responses"] = self.request.user.has_study_perms(
            StudyPermission.READ_STUDY_PREVIEW_DATA, context["study"]
        )
        return context


class StudyDemographicsJSON(DemographicDownloadMixin, generic.list.ListView):
    """
    Hitting this URL downloads all participant demographics in JSON format.
    """

    def render_to_response(self, context, **response_kwargs):
        study = self.study
        header_options = self.request.GET.getlist("demo_options")

        json_responses = []
        paginator = context["paginator"]
        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                json_responses.append(
                    json.dumps(
                        construct_response_dictionary(
                            resp,
                            DEMOGRAPHIC_COLUMNS,
                            header_options,
                            include_exp_data=False,
                        ),
                        indent="\t",
                        default=str,
                    )
                )
        cleaned_data = f"[ {', '.join(json_responses)} ]"
        filename = "{}_{}.json".format(
            study_name_for_files(study.name), "all-demographic-snapshots"
        )
        response = HttpResponse(cleaned_data, content_type="text/json")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyDemographicsCSV(DemographicDownloadMixin, generic.list.ListView):
    """
    Hitting this URL downloads all participant demographics in CSV format.
    """

    def render_to_response(self, context, **response_kwargs):
        study = self.study
        paginator = context["paginator"]
        header_options = set(self.request.GET.getlist("demo_options"))

        participant_list = []
        headers_for_download = get_demographic_headers(header_options)
        for page_num in paginator.page_range:
            page_of_responses = paginator.page(page_num)
            for resp in page_of_responses:
                row_data = {col.id: col.extractor(resp) for col in DEMOGRAPHIC_COLUMNS}
                participant_list.append(row_data)
        output, writer = csv_dict_output_and_writer(headers_for_download)
        writer.writerows(participant_list)
        cleaned_data = output.getvalue()

        filename = "{}_{}.csv".format(
            study_name_for_files(study.name), "all-demographic-snapshots"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyDemographicsDictCSV(DemographicDownloadMixin, generic.list.ListView):
    """
    Hitting this URL downloads a data dictionary for participant demographics in in CSV format.
    Does not depend on any actual data.
    """

    def render_to_response(self, context, **response_kwargs):
        header_options = set(self.request.GET.getlist("demo_options"))
        headers_for_download = get_demographic_headers(header_options)

        all_descriptions = [
            {"column": col.id, "description": col.description}
            for col in DEMOGRAPHIC_COLUMNS
            if col.id in headers_for_download
        ]
        output, writer = csv_dict_output_and_writer(["column", "description"])
        writer.writerows(all_descriptions)
        cleaned_data = output.getvalue()

        filename = "{}_{}.csv".format(
            study_name_for_files(self.study.name), "all-demographic-snapshots-dict"
        )
        response = HttpResponse(cleaned_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response


class StudyCollisionCheck(ResponseDownloadMixin, View):
    """
    Hitting this URL checks for collisions among all child and account hashed IDs, and returns a string describing
    any collisions (empty string if none).
    """

    def get(self, request, *args, **kwargs):
        study = self.study
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


class StudyAttachments(CanViewStudyResponsesMixin, generic.ListView):
    """
    StudyAttachments View shows video attachments for the study
    """

    template_name = "studies/study_attachments.html"
    model = Video
    paginate_by = 100

    def get_ordering(self):
        return self.request.GET.get("sort", "-created_at") or "-created_at"

    def get_queryset(self):
        """Fetches all consented videos this user has access to.

        Returns:
            QuerySet: all videos from this study where response has been marked as
            consented and response is of a type (preview/actual data) that user can view

        Todo:
            * use a helper (e.g. in queries) select_videos_for_user to fetch the
            appropriate videos here and in build_zipfile_of_videos - deferring for the moment
            to work out dependencies.
        """
        study = self.study
        videos = study.videos_for_consented_responses
        if not self.request.user.has_study_perms(
            StudyPermission.READ_STUDY_RESPONSE_DATA, study
        ):
            videos = videos.filter(response__is_preview=True)
        if not self.request.user.has_study_perms(
            StudyPermission.READ_STUDY_PREVIEW_DATA, study
        ):
            videos = videos.filter(response__is_preview=False)
        match = self.request.GET.get("match", "")
        if match:
            videos = videos.filter(full_name__icontains=match)
        return videos.order_by(self.get_ordering())

    def get_context_data(self, **kwargs):
        """
        In addition to the study, adds several items to the context dictionary.  Study results
        are paginated.
        """
        context = super().get_context_data(**kwargs)
        context["match"] = self.request.GET.get("match", "")
        context["study"] = self.study
        return context

    def post(self, request, *args, **kwargs):
        """
        Downloads study video
        """
        match = self.request.GET.get("match", "")
        study = self.study

        if self.request.POST.get("all-attachments"):
            build_zipfile_of_videos.delay(
                f"{study.uuid}_videos",
                study.uuid,
                match,
                self.request.user.uuid,
                consent_only=False,
            )
            messages.success(
                request,
                f"An archive of videos for {study.name} is being generated. You will be emailed a link when it's completed.",
            )

        if self.request.POST.get("all-consent-videos"):
            build_zipfile_of_videos.delay(
                f"{study.uuid}_consent_videos",
                study.uuid,
                match,
                self.request.user.uuid,
                consent_only=True,
            )
            messages.success(
                request,
                f"An archive of consent videos for {study.name} is being generated. You will be emailed a link when it's completed.",
            )

        return HttpResponseRedirect(
            reverse("exp:study-attachments", kwargs=self.kwargs)
        )
