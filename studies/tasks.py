import csv
import datetime
import hashlib
import logging
import os
import random
import secrets
import shutil
import tempfile
import time
import zipfile
from collections import Counter
from io import StringIO
from itertools import starmap
from operator import attrgetter, itemgetter
from typing import Generator, NamedTuple

import boto3
import docker
import requests
from celery.utils.log import get_task_logger
from django.conf import settings
from django.db import connection
from django.utils import timezone
from google.cloud import storage as gc_storage
from more_itertools import chunked, first, flatten, groupby_transform, map_reduce

from accounts.models import Child, Message, User
from accounts.queries import get_child_eligibility_for_study
from project.celery import app
from studies.experiment_builder import EmberFrameplayerBuilder
from studies.helpers import send_mail
from studies.permissions import StudyPermission

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


MESSAGE_TARGET_QUERY = """
WITH message_targets AS ( -- all valid user-child-study triplets
    SELECT DISTINCT ac.user_id,
                    ac.id as child_id,
                    ss.study_id
    FROM accounts_child ac
             INNER JOIN accounts_user au on au.id = ac.user_id
             CROSS JOIN (
        SELECT id AS study_id
        FROM studies_study
        WHERE state = 'active'
          AND public = true
    ) ss
    WHERE au.is_active = true
      AND ac.deleted = false
      AND au.email_new_studies = true
        EXCEPT (
        SELECT DISTINCT ac.user_id,
                        sr.child_id,
                        sr.study_id
        FROM studies_response sr
                 INNER JOIN accounts_child ac on sr.child_id = ac.id
                 INNER JOIN studies_studytype sst on sr.study_type_id = sst.id
        WHERE (sr.completed_consent_frame = true AND sst."name" = 'Ember Frame Player (default)')
	            OR (sst."name" = 'External')
    )
),
     latest_study_notifications_for_children AS (
         SELECT amr.user_id,
                amcoi.child_id,
                am.related_study_id,
                MAX(am.email_sent_timestamp) as latest_sent_time
         FROM accounts_message am
                  INNER JOIN accounts_message_children_of_interest amcoi on am.id = amcoi.message_id
                  INNER JOIN accounts_message_recipients amr on am.id = amr.message_id
         WHERE (amr.user_id, amcoi.child_id, am.related_study_id) IN (SELECT * FROM message_targets)
         GROUP BY amr.user_id, amcoi.child_id, am.related_study_id
     )
SELECT mt.user_id,
       mt.child_id,
       mt.study_id
FROM message_targets mt
         LEFT OUTER JOIN latest_study_notifications_for_children lsnfc
                         ON lsnfc.user_id = mt.user_id
                             AND lsnfc.child_id = mt.child_id
                             AND lsnfc.related_study_id = mt.study_id
WHERE lsnfc.latest_sent_time IS NULL
ORDER BY mt.user_id, mt.child_id, mt.study_id;
"""
MAX_EMAILS_PER_STUDY = 50


class MessageTarget(NamedTuple):
    user_id: int
    child_id: int
    study_id: int


def potential_message_targets(page_size: int = 2000):
    """Enable us to stream from the database."""
    with connection.cursor() as cursor:
        cursor.execute(MESSAGE_TARGET_QUERY)
        while page := cursor.fetchmany(page_size):
            yield from starmap(MessageTarget, page)


def _grouped_by_user(potential_targets):
    """Groups users with their child-study notification pairs.

    Note: Depends on sorted output (hence the ORDER BY in SQL) See:
    https://more-itertools.readthedocs.io/en/stable/api.html#more_itertools.groupby_transform
    """
    get_user_id = attrgetter("user_id")
    get_child_study_pair = attrgetter("child_id", "study_id")
    yield from (
        (
            user_id,
            tuple(pair),
        )  # Apparently, valuefunc gets wrapped to return a map object?
        for user_id, pair in groupby_transform(
            potential_targets, keyfunc=get_user_id, valuefunc=get_child_study_pair
        )
    )


def _deserialized(user_grouped_targets, number_of_parents: int = 100):
    """Fill out groups with real models.

    In prod, we have about 1.42 children per parent, so limiting it to 100 parents or so
    at a time should be fine.
    """
    from studies.models import Study

    # Cache studies entirely upfront; let the generator hold on to them.
    study_cache = {
        study.id: study
        for study in Study.objects.filter(state="active", public=True).select_related(
            "lab"
        )
    }

    # Go in batches sized by number of parents, fetch parents and children in one SELECT
    # query (each) before yielding deserialized groups.
    for group_list in chunked(user_grouped_targets, n=number_of_parents):
        user_cache = {
            user.id: user
            for user in User.objects.filter(id__in=[group[0] for group in group_list])
        }
        child_cache = {
            child.id: child
            for child in Child.objects.filter(
                id__in=flatten(list(map(first, group[1])) for group in group_list)
            )
        }

        for user_id, child_study_pairs in group_list:
            yield (
                user_cache.get(user_id),
                [
                    (child_cache.get(child_id), study_cache.get(study_id))
                    for child_id, study_id in child_study_pairs
                ],
            )


def _validated(deserialized_groups):
    """Yield only groups with targets that satisfy criteria for their respective studies."""
    for user, child_study_pairs in deserialized_groups:
        valid_message_targets = []
        for pair in child_study_pairs:
            child, study = pair
            eligible = get_child_eligibility_for_study(child, study)
            if eligible:
                valid_message_targets.append(pair)
        if valid_message_targets:
            yield user, valid_message_targets


def _segmented_by_study(validated_groups):
    for user, child_study_pairs in validated_groups:
        yield user, dict(map_reduce(child_study_pairs, itemgetter(1), itemgetter(0)))


def acquire_potential_announcement_email_targets() -> Generator:
    return _segmented_by_study(
        _validated(_deserialized(_grouped_by_user(potential_message_targets())))
    )


def limit_email_targets(
    potential_targets_segmented_by_study, max_emails_per_study
) -> Generator:
    """Reduces number of targets so users get <= 1 email and studies get <= max_emails_per_study.

    This is done AFTER deserializing to actual model objects so that we've already checked eligibility;
    otherwise we'd have to select a random sample of families to MAYBE email if they turn out to be
    eligible each time."""

    from studies.models import Study

    # Iterate through generator with actual models to build a list of IDs
    all_user_study_children_tuples = []
    for user, study_child_mapping in potential_targets_segmented_by_study:
        study, child_list = secrets.choice(list(study_child_mapping.items()))
        all_user_study_children_tuples.append(
            (user.id, study.id, [child.id for child in child_list])
        )

    # Randomly select the first <= N study-user pairs for each study. We don't want to just yield the first N per study
    # because then we'll always invite some families to participate first, others later
    random.shuffle(all_user_study_children_tuples)
    study_counts = Counter()
    email_user_study_children_tuples = []
    for (user_id, study_id, child_id_list) in all_user_study_children_tuples:
        if study_counts[study_id] >= max_emails_per_study:
            continue
        email_user_study_children_tuples.append((user_id, study_id, child_id_list))
        study_counts[study_id] += 1

    # Now fetch the actual objects again
    for (user_id, study_id, child_id_list) in email_user_study_children_tuples:
        yield (
            User.objects.get(id=user_id),
            Study.objects.get(id=study_id),
            [Child.objects.get(id=child_id) for child_id in child_id_list],
        )


@app.task
def send_announcement_emails():
    """Send study announcement emails to users with eligible children.

    We randomly choose one study (and set of eligible children) per family, per day
    in order to rate-limit the # of messages any parent gets in a given week. After
    the announcement email is sent, the message is saved down to the database and
    marked in a join table (`accounts_message_children_of_interest`) along with the
    targeted children such that those child-study pairs will be excluded from the next
    (daily) round of potential targets.
    """

    targets = limit_email_targets(
        acquire_potential_announcement_email_targets(), MAX_EMAILS_PER_STUDY
    )

    for user, study, child_list in targets:
        Message.send_announcement_email(user, study, child_list)


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
    DOCKER_CLIENT.images.prune(filters={"dangling": True})


@app.task
def cleanup_docker_containers():
    logger.debug("Cleaning up docker containers...")
    DOCKER_CLIENT.containers.prune()


@app.task(bind=True, max_retries=10, retry_backoff=10)
def build_zipfile_of_videos(
    self, filename, study_uuid, match, requesting_user_uuid, consent_only=False
):
    from accounts.models import User
    from studies.models import Study

    study = Study.objects.get(uuid=study_uuid)
    requesting_user = User.objects.get(uuid=requesting_user_uuid)

    video_qs = (
        study.consent_videos if consent_only else study.videos_for_consented_responses
    )

    if not requesting_user.has_study_perms(
        StudyPermission.READ_STUDY_RESPONSE_DATA, study
    ):
        video_qs = video_qs.filter(response__is_preview=True)
    if not requesting_user.has_study_perms(
        StudyPermission.READ_STUDY_PREVIEW_DATA, study
    ):
        video_qs = video_qs.filter(response__is_preview=False)

    if match:
        video_qs = video_qs.filter(full_name__contains=match)

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
                for video in video_qs:
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
        videos=video_qs,
        zip_filename=zip_filename,
    )
    send_mail(
        "download_zip",
        "Your video archive has been created",
        [requesting_user.username],
        from_email=settings.EMAIL_FROM_ADDRESS,
        **email_context,
    )


@app.task
def build_framedata_dict(filename, study_uuid, requesting_user_uuid):
    from accounts.models import User
    from exp.views.responses import build_framedata_dict_csv
    from studies.models import Study

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
        [requesting_user.username],
        from_email=settings.EMAIL_FROM_ADDRESS,
        **email_context,
    )


@app.task(bind=True)
def delete_video_from_cloud(task, s3_video_name):
    """Delete videos in S3.

    Meant to have a delay of about 7 days.
    """
    S3_RESOURCE.Object(settings.BUCKET_NAME, s3_video_name).delete()
