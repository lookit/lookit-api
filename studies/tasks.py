import logging
import os
import re
import shutil
import subprocess
import time
import tempfile
import hashlib
import datetime
import zipfile
from io import BytesIO, StringIO

import requests
from django.conf import settings
from django.core.files import File
from django.utils import timezone
from google.cloud import storage as gc_storage

from project import storages
from project.celery import app
from studies.helpers import send_mail
import attachment_helpers

from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)
logger.setLevel(logging.DEBUG)

# setup a stream handler for capturing logs for db logging
log_buffer = StringIO()
handler = logging.StreamHandler(log_buffer)

handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


def get_repo_path(full_repo_path):
    return re.search('https://github.com/(.*)', full_repo_path).group(1).rstrip('/')


def get_branch_sha(repo_url, branch):
    logger.debug(f'Getting {branch} sha for {repo_url}...')
    api_url = f'https://api.github.com/repos/{get_repo_path(repo_url)}/git/refs'
    logger.debug(f'Making API request to {api_url}...')
    response = requests.get(api_url)
    sha = list(filter(lambda datum: datum['ref'] == f'refs/heads/{branch}', response.json()))[0]['object']['sha']
    logger.debug(f'Got sha of {sha}')
    return sha


def unzip_file(file, destination_folder):
    """
    Github puts all files into a f`{repo_name}_{sha}`/ directory.
    This strips off the top-level directory and uses the destination_folder
    in it's place.
    """
    logger.debug(f'Unzipping into {destination_folder}...')
    os.makedirs(destination_folder, mode=0o777, exist_ok=True)
    with zipfile.ZipFile(BytesIO(file)) as zip_file:
        for member in zip_file.infolist():
            if member.is_dir():
                os.makedirs(os.path.join(destination_folder, member.filename.partition('/')[-1]), mode=0o777, exist_ok=True)
                continue
            with open(os.path.join(destination_folder, member.filename.partition('/')[-1]), 'wb') as outfile:
                outfile.write(zip_file.read(member))


def deploy_to_remote(local_path, storage):
    """Wrapper for remote file deployments.

    If we have a Google Cloud Storage client, we should leverage batching capability.
    """
    # TODO: Threaded implementation of multi-upload, given that the GCS API backend
    # doesn't actually support batched MIME requests :(
    _upload_in_serial(local_path, storage)


def _upload_in_serial(local_path, storage):
    """Inner worker function for storage uploads in serial."""
    for root_directory, dirs, files in os.walk(local_path, topdown=True):
        for filename in files:
            full_path = os.path.join(root_directory, filename)
            with open(full_path, mode='rb') as f:
                remote_path = full_path.split('../ember_build/deployments/')[1]
                logger.debug(f'Uploading {full_path} to {storage.location}/{remote_path}...')
                storage.save(remote_path, File(f))


def download_repos(addons_repo_url, addons_sha=None, player_sha=None):
    if addons_sha is None or not re.match('([a-f0-9]{40})', addons_sha):
        addons_sha = get_branch_sha(addons_repo_url, settings.EMBER_ADDONS_BRANCH)
    if player_sha is None or not re.match('([a-f0-9]{40})', player_sha):
        player_sha = get_branch_sha(settings.EMBER_EXP_PLAYER_REPO, settings.EMBER_EXP_PLAYER_BRANCH)

    repo_destination_folder = f'{player_sha}_{addons_sha}'
    local_repo_destination_folder = os.path.join('./ember_build/checkouts/', repo_destination_folder)

    if os.path.isdir(local_repo_destination_folder):
        logger.debug(f'Found directory {local_repo_destination_folder}')
        return (repo_destination_folder, addons_sha, player_sha)

    addons_zip_path = f'{addons_repo_url}/archive/{addons_sha}.zip'
    player_zip_path = f'{settings.EMBER_EXP_PLAYER_REPO}/archive/{player_sha}.zip'

    logger.debug(f'Downloading {player_zip_path}...')
    unzip_file(requests.get(player_zip_path).content, local_repo_destination_folder)
    logger.debug(f'Downloading {addons_zip_path}...')
    unzip_file(requests.get(addons_zip_path).content, os.path.join(local_repo_destination_folder, 'lib'))

    return (repo_destination_folder, addons_sha, player_sha)


def build_docker_image(player_addons_concat_sha, ember_prepend_replacement_string, study_uuid):
    logger.debug(f'Running docker build...')
    return subprocess.run(
        [
            'docker',
            'build',
            '--pull',
            '--cache-from',
            f'ember_build:{player_addons_concat_sha}-{study_uuid}',
            '--build-arg',
            f'player_addons_concat_sha={player_addons_concat_sha}',
            '--build-arg',
            f'ember_prepend_replacement_string={ember_prepend_replacement_string}',
            '-t',
            f'ember_build:{player_addons_concat_sha}-{study_uuid}',
            '.'
        ],
        cwd=settings.EMBER_BUILD_ROOT_PATH,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        # check=True  # add back when we refactor this into multiple try blocks
    )


@app.task(bind=True, max_retries=10, retry_backoff=10)
def build_experiment(self, study_uuid, researcher_uuid, preview=True):
    """[12/20/18] Celery task to build experiments.

    Build an experiment with docker, and persist the built results in the
    deployments volume.

    :param self: Task. This is a celery/kombu convention.
    :param study_uuid: String.
    :param researcher_uuid: String.
    :param preview: Boolean. Is this study build a preview?
    """
    ex = None
    try:
        from studies.models import Study, StudyLog
        from accounts.models import User

        try:
            study = Study.objects.get(uuid=study_uuid)
        except Study.DoesNotExist as ex:
            logger.error(f'Study with uuid {study_uuid} does not exist. {ex}')
            raise

        try:
            researcher = User.objects.get(uuid=researcher_uuid)
        except User.DoesNotExist as ex:
            logger.error(f'User with uuid {researcher_uuid} does not exist. {ex}')
            raise

        destination_directory = f'{study_uuid}'

        player_sha = study.metadata.get('last_known_player_sha', None)
        addons_sha = study.metadata.get('last_known_addons_sha', None)
        addons_repo_url = study.metadata.get('addons_repo_url', settings.EMBER_ADDONS_REPO)
        logger.debug(f"Got {addons_repo_url} from {study.metadata.get('addons_repo_url')}")

        checkout_directory, addons_sha, player_sha = download_repos(
            addons_repo_url, addons_sha=addons_sha, player_sha=player_sha)

        if preview and player_sha is None and addons_sha is None:
            study.metadata['last_known_addons_sha'] = addons_sha
            study.metadata['last_known_player_sha'] = player_sha
            study.save()

        player_addons_concat_sha = f'{player_sha}_{addons_sha}'

        build_image_comp_process = build_docker_image(
            player_addons_concat_sha,
            re.escape(f"prepend: '/studies/{study_uuid}/'"),
            study_uuid
        )
        local_deployments_path = os.path.join(settings.EMBER_BUILD_ROOT_PATH, 'deployments')

        init_container_comp_process = subprocess.run(
            [
                'docker',
                'run',
                '--rm',  # Destroy container afterward, only keep volume output.
                '-e',
                f'STUDY_UUID={study_uuid}',
                '-v',
                f'{local_deployments_path}:/deployments',
                f'ember_build:{player_addons_concat_sha}-{study_uuid}',
                'bash',
                'build.sh'
            ],
            cwd=settings.EMBER_BUILD_ROOT_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # check=True  # Add back when we refactor this into multiple try blocks
        )

        if preview:
            # if they're previewing put things in the preview directory
            storage = storages.LookitPreviewExperimentStorage()
        else:
            # otherwise put them in the experiment directory
            storage = storages.LookitExperimentStorage()

        cloud_deployment_directory = os.path.join(local_deployments_path, destination_directory)

        deploy_to_remote(cloud_deployment_directory, storage)

        context = {
            'org_name': study.organization.name,
            'study_name': study.name,
            'study_id': study.pk,
            'study_uuid': str(study.uuid),
            'action': 'previewed' if preview else 'deployed'
        }
        send_mail.delay(
            'notify_admins_of_study_action',
            'Study Previewed' if preview else 'Study Deployed',
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(study.study_organization_admin_group.user_set.values_list('username', flat=True)),
            **context
        )
        send_mail.delay(
            'notify_researchers_of_deployment',
            'Study Previewed' if preview else 'Study Deployed',
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(study.study_admin_group.user_set.values_list('username', flat=True)),
            **context
        )
        if preview:
            study.previewed = True
        else:
            study.built = True

        study.save()
    except Exception as e:
        ex = e
        logger.error(e)
    finally:
        StudyLog.objects.create(
            study=study,
            action='preview' if preview else 'deploy',
            user=researcher,
            extra={
                # TODO: Shouldn't be "ember build" but instead "container build"
                'ember_build': str(init_container_comp_process.stdout),
                'image_build': str(build_image_comp_process.stdout),
                'ex': str(ex),
                'log': log_buffer.getvalue(),
            }
        )
        log_buffer.close()
    if ex:
        raise self.retry(exc=ex, countdown=30)


def cleanup_old_directories(root_path, older_than):
    if not older_than:
        older_than = timezone.now() - timezone.timedelta(days=1)
    else:
        assert type(older_than) == timezone.datetime, 'older_than must be an instance of datetime'

    with os.scandir(root_path) as sd:
        for entry in sd:
            if entry.is_dir() and entry.stat().st_mtime < time.mktime(older_than.timetuple()):
                logger.debug(f'Deleting {entry.path}...')
                shutil.rmtree(entry.path)


@app.task
def cleanup_builds(older_than=None):
    logger.debug('Cleaning up builds...')
    deployments = os.path.join(settings.EMBER_BUILD_ROOT_PATH, 'deployments')
    cleanup_old_directories(deployments, older_than)


@app.task
def cleanup_checkouts(older_than=None):
    logger.debug('Cleaning up checkouts...')
    checkouts = os.path.join(settings.EMBER_BUILD_ROOT_PATH, 'checkouts')
    cleanup_old_directories(checkouts, older_than)


@app.task
def cleanup_docker_images():
    logger.debug('Cleaning up docker images...')
    images = subprocess.run(['docker', 'images', '--quiet', '--filter', 'dangling=true'], stdout=subprocess.PIPE)
    for image in images.stdout.splitlines():
        subprocess.run(['docker', 'rmi', '--force', image])


@app.task(bind=True, max_retries=10, retry_backoff=10)
def build_zipfile_of_videos(self, filename, study_uuid, orderby, match, requesting_user_uuid, consent=False):
    from studies.models import Study
    from accounts.models import User
    # get the study in question
    study = Study.objects.get(uuid=study_uuid)
    # get the user
    requesting_user = User.objects.get(uuid=requesting_user_uuid)
    # find the requested attachments
    if consent:
        attachments = attachment_helpers.get_consent_videos(study.uuid)
    else:
        attachments = attachment_helpers.get_study_attachments(study, orderby, match)
    m = hashlib.sha256()
    for attachment in attachments:
        m.update(attachment.key.encode('utf-8'))
    # create a sha256 of the included filenames
    sha = m.hexdigest()
    # use that sha in the filename
    zip_filename = f'{filename}_{sha}.zip'
    # get the gc client
    gs_client = gc_storage.client.Client(project=settings.GS_PROJECT_ID)
    # get the bucket
    gs_private_bucket = gs_client.get_bucket(settings.GS_PRIVATE_BUCKET_NAME)
    # instantiate a blob for the file
    gs_blob = gc_storage.blob.Blob(zip_filename, gs_private_bucket, chunk_size=256*1024*1024)  # 256mb

    # if the file exists short circuit and send the email with a 30m link
    if not gs_blob.exists():
        # if it doesn't exist build the zipfile
        with tempfile.TemporaryDirectory() as temp_directory:
            zip_file_path = os.path.join(temp_directory, zip_filename)
            with zipfile.ZipFile(zip_file_path, 'w') as zip:
                for attachment in attachments:
                    temporary_file_path = os.path.join(temp_directory, attachment.key)
                    file_response = requests.get(
                        attachment_helpers.get_download_url(attachment.key),
                        stream=True
                    )
                    with open(temporary_file_path, mode='w+b') as local_file:
                        for chunk in file_response.iter_content(8192):
                            local_file.write(chunk)
                    zip.write(temporary_file_path, attachment.key)
                    os.remove(temporary_file_path)

            # upload the zip to GoogleCloudStorage
            gs_blob.upload_from_filename(zip_file_path)

    # then send the email with a 30m link
    signed_url = gs_blob.generate_signed_url(int(time.time() + datetime.timedelta(minutes=30).seconds))
    # send an email with the signed url and return
    context = dict(
        signed_url=signed_url,
        user=requesting_user,
        videos=attachments,
        zip_filename=zip_filename
    )
    send_mail(
        'download_zip',
        'Your video archive has been created',
        settings.EMAIL_FROM_ADDRESS,
        bcc=[requesting_user.username, ],
        from_email=settings.EMAIL_FROM_ADDRESS,
        **context
    )
