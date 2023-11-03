from typing import Callable, Dict, List, NamedTuple, Union

from accounts.utils import hash_demographic_id, hash_id, hash_participant_id
from exp.utils import round_age, round_ages_from_birthdays
from studies.models import Response


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
        id="response__eligibility",
        description=(
            "List of eligibility codes (defined in Lookit docs), separated by spaces. Can be either 'Eligible' or "
            "one or more of: 'Ineligible_TooYoung'/'Ineligible_TooOld', 'Ineligible_CriteriaExpression', 'Ineligible_Participation'."
        ),
        extractor=lambda resp: resp.eligibility,
        name="Eligibility",
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
        id="demographic__number_of_guardians",
        description="Response to 'How many parents/guardians do your children live with?' - 1, 2, 3> [3 or more], varies",
        extractor=lambda resp: resp["demographic_snapshot__number_of_guardians"],
        name="Number of guardians",
    ),
    ResponseDataColumn(
        id="demographic__us_race_ethnicity_identification",
        description=(
            "Comma-separated list of all values checked for question 'What category(ies) does your family "
            "identify as?', from list:  White; Hispanic, Latino, or Spanish origin; Black or African American; "
            "Asian; American Indian or Alaska Native; Middle Eastern or North African; Native Hawaiian or "
            "Other Pacific Islander; Another race, ethnicity, or origin"
        ),
        extractor=lambda resp: resp[
            "demographic_snapshot__us_race_ethnicity_identification"
        ],
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
