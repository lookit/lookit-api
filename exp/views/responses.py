import io
import json
import zipfile
from functools import cached_property
from typing import Dict, KeysView, List, NamedTuple, Set, Text, Union

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

from accounts.utils import hash_child_id, hash_id, hash_participant_id
from exp.utils import (
    RESPONSE_PAGE_SIZE,
    csv_dict_output_and_writer,
    csv_namedtuple_writer,
    flatten_dict,
    study_name_for_files,
)
from exp.views.mixins import (
    CanViewStudyResponsesMixin,
    ResearcherLoginRequiredMixin,
    SingleObjectFetchProtocol,
    StudyLookupMixin,
)
from exp.views.responses_data import DEMOGRAPHIC_COLUMNS, RESPONSE_COLUMNS
from studies.models import Feedback, Response, Study, Video
from studies.permissions import StudyPermission
from studies.queries import (
    get_consent_statistics,
    get_responses_with_current_rulings_and_videos,
)
from studies.tasks import build_framedata_dict, build_zipfile_of_videos

CONTENT_TYPE = "text/csv"


# Which headers from the response data summary should go in the child data downloads
CHILD_CSV_HEADERS = [
    col.id
    for col in RESPONSE_COLUMNS
    if col.id.startswith("child__") or col.id.startswith("participant__")
]

IDENTIFIABLE_DATA_HEADERS = {col.id for col in RESPONSE_COLUMNS if col.identifiable}


def csv_filename(study: Study, *args) -> Text:
    """Generate CSV filename.

    Args:
        study (Study): Study model object

    Returns:
        Text: CSV filename
    """
    args = map(str, args)
    return f"{study_name_for_files(study.name)}_{'_'.join(args)}.csv"


def set_content_disposition(response: HttpResponse, filename: Text) -> None:
    """Set filename in response

    Args:
        response (HttpResponse): Respose object return from view
        filename (Text): The file's name
    """
    response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)


def study_responses_all(study: Study) -> HttpResponse:
    return redirect(reverse("exp:study-responses-all", kwargs={"pk": study.id}))


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
    for (i_event, event) in enumerate(resp["global_event_timings"]):
        for (key, value) in event.items():
            frame_data_tuples.append(
                FrameDataRow(
                    child_hashed_id=child_hashed_id,
                    response_uuid=str(resp["uuid"]),
                    frame_id="global",
                    key=key,
                    event_number=str(i_event),
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
                if d.frame_id != "global"
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

        columns_included_in_summary = study.columns_included_in_summary()

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

        if data_type == "json":
            filename_ending = "_frames"
        elif IDENTIFIABLE_DATA_HEADERS & header_options:
            filename_ending = "_identifiable"
        else:
            filename_ending = ""

        filename = "{}_{}{}.{}".format(
            study_name_for_files(study.name),
            str(resp.uuid),
            filename_ending,
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
        set_content_disposition(response, filename)
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

    def get(self, request, *args, **kwargs):
        if self.get_object().study_type.is_external:
            messages.error(request, "There is no consent manager for external studies.")
            return HttpResponseRedirect(reverse("exp:study-detail", kwargs=kwargs))
        else:
            return super().get(request, *args, **kwargs)


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

        return study_responses_all(study)


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
        set_content_disposition(response, filename)
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

        all_responses = "all-responses"
        if IDENTIFIABLE_DATA_HEADERS & header_options:
            all_responses += "-identifiable"

        filename = csv_filename(study, all_responses)
        response = HttpResponse(cleaned_data, content_type=CONTENT_TYPE)
        set_content_disposition(response, filename)
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
        filename = csv_filename(study, "all-responses-dict")
        response = HttpResponse(cleaned_data, content_type=CONTENT_TYPE)
        set_content_disposition(response, filename)
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

        filename = csv_filename(study, "all-children-identifiable")
        response = HttpResponse(cleaned_data, content_type=CONTENT_TYPE)
        set_content_disposition(response, filename)
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
        filename = csv_filename(study, "all-children-dict")
        response = HttpResponse(cleaned_data, content_type=CONTENT_TYPE)
        set_content_disposition(response, filename)
        return response


class StudyResponsesFrameDataCSV(ResponseDownloadMixin, generic.list.ListView):
    """Hitting this URL downloads a ZIP file with frame data from one response per file in CSV format"""

    # TODO: with large files / many responses generation can take a while. Should generate asynchronously along
    # with the data dict.
    def render_to_response(self, context, **response_kwargs):
        paginator = context["paginator"]
        study = self.study

        if study.study_type.is_external:
            messages.error(
                self.request, "Frame data is not available for External Studies."
            )

            return study_responses_all(study)

        zipped_file = io.BytesIO()
        with zipfile.ZipFile(zipped_file, "w", zipfile.ZIP_DEFLATED) as zipped:
            for page_num in paginator.page_range:
                page_of_responses = paginator.page(page_num)
                for resp in page_of_responses:
                    data = build_single_response_framedata_csv(resp)
                    filename = csv_filename(study, resp.uuid, "frames")
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

        if study.study_type.is_external:
            messages.error(
                request, "Frame data dictionary is not available for external studies"
            )
        else:
            filename = "{}_{}_{}".format(
                study_name_for_files(study.name), study.uuid, "all-frames-dict"
            )

            build_framedata_dict.delay(filename, study.uuid, self.request.user.uuid)
            messages.success(
                request,
                f"A frame data dictionary for {study.name} is being generated. You will be emailed a link when it's completed.",
            )

        return study_responses_all(study)


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
        set_content_disposition(response, filename)
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

        filename = csv_filename(study, "all-demographic-snapshots")
        response = HttpResponse(cleaned_data, content_type=CONTENT_TYPE)
        set_content_disposition(response, filename)
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

        filename = csv_filename(self.study, "all-demographic-snapshots-dict")
        response = HttpResponse(cleaned_data, content_type=CONTENT_TYPE)
        set_content_disposition(response, filename)
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
