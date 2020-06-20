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
import zipfile
from io import StringIO

import boto3
import docker
import requests
from celery.utils.log import get_task_logger
from django.conf import settings
from django.utils import timezone
from google.cloud import storage as gc_storage

from project.celery import app
from studies.experiment_builder import EmberFrameplayerBuilder
from studies.helpers import send_mail

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
def ember_build_and_gcp_deploy(self, study_uuid, researcher_uuid):
    """Celery task to build experiments.

    Build an experiment with docker, and persist the built results in the
    deployments volume.

    :param self: Task. This is a celery/kombu convention.
    :param study_uuid: String.
    :param researcher_uuid: String.
    """

    fp_builder = EmberFrameplayerBuilder(
        study_uuid=study_uuid, researcher_uuid=researcher_uuid, logger=logger
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
    self, video_qs, filename, study_uuid, orderby, match, requesting_user_uuid
):
    from studies.models import Study
    from accounts.models import User

    study = Study.objects.get(uuid=study_uuid)
    requesting_user = User.objects.get(uuid=requesting_user_uuid)

    m = hashlib.sha256()

    for video in video_qs:
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


@app.task
def build_framedata_dict(filename, study_uuid, requesting_user_uuid):
    from studies.models import Study
    from accounts.models import User
    from exp.views.responses import build_framedata_dict_csv

    requesting_user = User.objects.get(uuid=requesting_user_uuid)
    study = Study.objects.get(uuid=study_uuid)
    response_qs = study.responses_for_researcher(requesting_user).order_by("id")
    responses = response_qs.select_related("child", "study").values(
        "uuid",
        "exp_data",
        "child__uuid",
        "study__uuid",
        "study__salt",
        "study__hash_digits",
        "global_event_timings",
    )

    # make filename for this request unique by adding timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    csv_filename = f"{filename}_{timestamp}.csv"

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
    signed_url = gs_blob.generate_signed_url(datetime.timedelta(hours=24))
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
