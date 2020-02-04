import csv
import datetime
import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import json
import zipfile
from io import BytesIO, StringIO
from typing import NamedTuple
from enum import IntEnum

import boto3
import docker
import requests
from celery.utils.log import get_task_logger
from django.conf import settings
from django.core.files import File
from django.core.paginator import Paginator
from django.utils import timezone
from google.cloud import storage as gc_storage

from exp.utils import csv_dict_output_and_writer
from project import storages
from project.celery import app
from studies.helpers import send_mail
from studies.experiment_builder import EmberFrameplayerBuilder


logger = get_task_logger(__name__)
logger.setLevel(logging.DEBUG)

S3_RESOURCE = boto3.resource("s3")

DOCKER_CLIENT = docker.from_env()

# setup a stream handler for capturing logs for db logging
log_buffer = StringIO()
handler = logging.StreamHandler(log_buffer)

handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


@app.task(bind=True, max_retries=10, retry_backoff=10)
def ember_build_and_gcp_deploy(self, study_uuid, researcher_uuid, preview=True):
    """Celery task to build experiments.

    Build an experiment with docker, and persist the built results in the
    deployments volume.

    :param self: Task. This is a celery/kombu convention.
    :param study_uuid: String.
    :param researcher_uuid: String.
    :param preview: Boolean. Is this study build a preview?
    """

    fp_builder = EmberFrameplayerBuilder(
        study_uuid=study_uuid,
        researcher_uuid=researcher_uuid,
        is_preview=preview,
        logger=logger,
    )

    build_successful = fp_builder.build()

    if not build_successful:
        self.retry(countdown=30)


def cleanup_old_directories(root_path, older_than):
    if not older_than:
        older_than = timezone.now() - timezone.timedelta(days=1)
    else:
        assert (
            type(older_than) == timezone.datetime
        ), "older_than must be an instance of datetime"

    with os.scandir(root_path) as sd:
        for entry in sd:
            if entry.is_dir() and entry.stat().st_mtime < time.mktime(
                older_than.timetuple()
            ):
                logger.debug(f"Deleting {entry.path}...")
                shutil.rmtree(entry.path)


@app.task
def cleanup_builds(older_than=None):
    logger.debug("Cleaning up builds...")
    deployments = os.path.join(settings.EMBER_BUILD_ROOT_PATH, "deployments")
    cleanup_old_directories(deployments, older_than)


@app.task
def cleanup_checkouts(older_than=None):
    logger.debug("Cleaning up checkouts...")
    checkouts = os.path.join(settings.EMBER_BUILD_ROOT_PATH, "checkouts")
    cleanup_old_directories(checkouts, older_than)


@app.task
def cleanup_docker_images():
    logger.debug("Cleaning up docker images...")
    images = subprocess.run(
        ["docker", "images", "--quiet", "--filter", "dangling=true"],
        stdout=subprocess.PIPE,
    )
    for image in images.stdout.splitlines():
        subprocess.run(["docker", "rmi", "--force", image])


@app.task(bind=True, max_retries=10, retry_backoff=10)
def build_zipfile_of_videos(
    self, filename, study_uuid, orderby, match, requesting_user_uuid, consent=False
):
    from studies.models import Study
    from accounts.models import User

    study = Study.objects.get(uuid=study_uuid)
    requesting_user = User.objects.get(uuid=requesting_user_uuid)
    videos = study.consent_videos if consent else study.videos_for_consented_responses

    m = hashlib.sha256()

    for video in videos:
        m.update(video.full_name.encode("utf-8"))
    # create a sha256 of the included filenames
    sha = m.hexdigest()
    # use that sha in the filename
    zip_filename = f"{filename}_{sha}.zip"
    # get the gc client
    gs_client = gc_storage.client.Client(project=settings.GS_PROJECT_ID)
    # get the bucket
    gs_private_bucket = gs_client.get_bucket(settings.GS_PRIVATE_BUCKET_NAME)
    # instantiate a blob for the file
    gs_blob = gc_storage.blob.Blob(
        zip_filename, gs_private_bucket, chunk_size=256 * 1024 * 1024
    )  # 256mb

    # if the file exists short circuit and send the email with a 30m link
    if not gs_blob.exists():
        # if it doesn't exist build the zipfile
        with tempfile.TemporaryDirectory() as temp_directory:
            zip_file_path = os.path.join(temp_directory, zip_filename)
            with zipfile.ZipFile(zip_file_path, "w") as zf:
                for video in videos:
                    temporary_file_path = os.path.join(temp_directory, video.full_name)
                    file_response = requests.get(video.download_url, stream=True)
                    with open(temporary_file_path, mode="w+b") as local_file:
                        for chunk in file_response.iter_content(8192):
                            local_file.write(chunk)
                    zf.write(temporary_file_path, video.full_name)
                    os.remove(temporary_file_path)

            # upload the zip to GoogleCloudStorage
            gs_blob.upload_from_filename(zip_file_path)

    # then send the email with a 30m link
    signed_url = gs_blob.generate_signed_url(
        int(time.time() + datetime.timedelta(minutes=30).seconds)
    )
    # send an email with the signed url and return
    email_context = dict(
        signed_url=signed_url,
        user=requesting_user,
        videos=videos,
        zip_filename=zip_filename,
    )
    send_mail(
        "download_zip",
        "Your video archive has been created",
        settings.EMAIL_FROM_ADDRESS,
        bcc=[requesting_user.username],
        from_email=settings.EMAIL_FROM_ADDRESS,
        **email_context,
    )


@app.task(bind=True, max_retries=10, retry_backoff=10)
def build_framedata_dict(self, filename, study_uuid, requesting_user_uuid):
    from studies.models import Study
    from accounts.models import User

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
            "eventType": "Descriptor for this event; determines what other data is available. Global event 'exitEarly' records cases where the participant attempted to exit the study early by closing the tab/window or pressing F1 or ctrl-X. RESEARCHER: INSERT DESCRIPTIONS OF PARTICULAR EVENTTYPES USED IN YOUR STUDY. (Note: you can find a list of events recorded by each frame in the frame documentation at https://lookit.github.io/ember-lookit-frameplayer, under the Events header.)",
            "exitType": "Used in the global event exitEarly. Only value stored at this point is 'browserNavigationAttempt'",
            "lastPageSeen": "Used in the global event exitEarly. Index of the frame the participant was on before exit attempt.",
            "pipeId": "Recorded by any event in a video-capture-equipped frame. Internal video ID used by Pipe service; only useful for troubleshooting in rare cases.",
            "streamTime": "Recorded by any event in a video-capture-equipped frame. Indicates time within webcam video (videoId) to nearest 0.1 second. If recording has not started yet, may be 0 or null.",
            "timestamp": "Recorded by all events. Timestamp of event in format e.g. 2019-11-07T17:14:43.626Z",
            "videoId": "Recorded by any event in a video-capture-equipped frame. Filename (without .mp4 extension) of video currently being recorded.",
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

        return output.getvalue()

    requesting_user = User.objects.get(uuid=requesting_user_uuid)
    study = Study.objects.get(uuid=study_uuid)
    responses = (
        study.consented_responses.order_by("id")
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

    # make filename for this request unique by adding timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    csv_filename = f"{filename}_{timestamp}.zip"  # TODO

    # get the gc client
    gs_client = gc_storage.client.Client(project=settings.GS_PROJECT_ID)
    # get the bucket
    gs_private_bucket = gs_client.get_bucket(settings.GS_PRIVATE_BUCKET_NAME)
    # instantiate a blob for the file
    gs_blob = gc_storage.blob.Blob(
        csv_filename, gs_private_bucket, chunk_size=256 * 1024 * 1024
    )  # 256mb

    header_list = [
        "column",
        "description",
        "possible_frame_id",
        "frame_description",
        "possible_key",
        "key_description",
    ]

    # if the file exists short circuit and send the email
    if not gs_blob.exists():
        # if it doesn't exist build the file
        with tempfile.TemporaryDirectory() as temp_directory:
            file_path = os.path.join(temp_directory, csv_filename)
            with open(file_path, "w") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    quoting=csv.QUOTE_NONNUMERIC,
                    fieldnames=header_list,
                    restval="",
                    extrasaction="ignore",
                )
                writer.writeheader()
                build_framedata_dict_csv(writer, responses)

            # upload the csv to GoogleCloudStorage
            gs_blob.upload_from_filename(file_path)

    # then send the email with a 24h link
    signed_url = gs_blob.generate_signed_url(
        int(time.time() + datetime.timedelta(hours=24).seconds)
    )
    # send an email with the signed url and return
    email_context = dict(
        signed_url=signed_url, user=requesting_user, csv_filename=csv_filename
    )
    send_mail(
        "download_framedata_dict",
        "Your frame data dictionary has been created",
        settings.EMAIL_FROM_ADDRESS,
        bcc=[requesting_user.username],
        from_email=settings.EMAIL_FROM_ADDRESS,
        **email_context,
    )


@app.task(bind=True)
def delete_video_from_cloud(task, s3_video_name):
    """Delete videos in S3.

    Meant to have a delay of about 7 days.
    """
    S3_RESOURCE.Object(settings.BUCKET_NAME, s3_video_name).delete()
