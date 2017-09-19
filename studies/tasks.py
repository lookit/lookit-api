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


def get_master_sha(repo_url):
    logger.debug(f'Getting master sha for {repo_url}...')
    api_url = f'https://api.github.com/repos/{get_repo_path(repo_url)}/git/refs'
    logger.debug(f'Making API request to {api_url}...')
    response = requests.get(api_url)
    sha = response.json()[0]['object']['sha']
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
    for root_directory, dirs, files in os.walk(local_path, topdown=True):
        for filename in files:
            full_path = os.path.join(root_directory, filename)
            with open(full_path, mode='rb') as f:
                remote_path = full_path.split('../ember_build/deployments/')[1]
                logger.debug(f'Uploading {full_path} to {storage.location}/{remote_path}...')
                storage.save(remote_path, File(f))


def download_repos(addons_repo_url, addons_sha=None, player_sha=None):
    if addons_sha is None or not re.match('([a-f0-9]{40})', addons_sha):
        addons_sha = get_master_sha(addons_repo_url)
    if player_sha is None or not re.match('([a-f0-9]{40})', player_sha):
        player_sha = get_master_sha(settings.EMBER_EXP_PLAYER_REPO)

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


def build_docker_image():
    # this is broken out so that it can be more complicated if it needs to be
    logger.debug(f'Running docker build...')
    return subprocess.run(
        [
            'docker',
            'build',
            '--pull',
            '--cache-from',
            'ember_build',
            '-t',
            'ember_build',
            '.'
        ],
        cwd=settings.EMBER_BUILD_ROOT_PATH,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )


@app.task(bind=True, max_retries=10, retry_backoff=10)
def build_experiment(self, study_uuid, researcher_uuid, preview=True):
    ex = None
    try:
        from studies.models import Study, StudyLog
        from accounts.models import User

        save_versions = preview
        now = timezone.now()
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

        if preview:
            current_state = study.state
            study.state = 'previewing'
            study.save()
            if player_sha is None and addons_sha is None:
                # if they're previewing and the sha's on their study aren't set
                # save the latest master sha of both repos
                save_versions = True

        checkout_directory, addons_sha, player_sha = download_repos(addons_repo_url, addons_sha=addons_sha, player_sha=player_sha)

        if save_versions:
            study.metadata['last_known_addons_sha'] = addons_sha
            study.metadata['last_known_player_sha'] = player_sha
            study.save()

        container_checkout_directory = os.path.join('/checkouts/', checkout_directory)
        container_destination_directory = os.path.join('/deployments/', destination_directory)

        build_image_comp_process = build_docker_image()
        local_checkout_path = os.path.join(settings.EMBER_BUILD_ROOT_PATH, 'checkouts')
        local_deployments_path = os.path.join(settings.EMBER_BUILD_ROOT_PATH, 'deployments')

        replacement_string = f"prepend: '/studies/{study_uuid}/'"
        recorder_replacement_string = f'/studies/{study_uuid}/VideoRecorder.swf'

        build_command = [
            'docker',
            'run',
            '--rm',
            '-e', f'CHECKOUT_DIR={container_checkout_directory}',
            '-e', f'REPLACEMENT={re.escape(replacement_string)}',
            '-e', f'RECORDER_REPLACEMENT={re.escape(recorder_replacement_string)}',
            '-e', f'STUDY_OUTPUT_DIR={container_destination_directory}',
            '-e', f"SENTRY_DSN={os.environ.get('SENTRY_DSN_JS', None)}",
            '-v', f'{local_checkout_path}:/checkouts',
            '-v', f'{local_deployments_path}:/deployments',
            'ember_build'
        ]

        logger.debug(f'Running build.sh for {container_checkout_directory}...')
        ember_build_comp_process = subprocess.run(
            build_command,
            cwd=settings.EMBER_BUILD_ROOT_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
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
        if not preview:
            study.state = 'active'
        else:
            study.previewed = True
            study.state = current_state

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
                'ember_build': str(ember_build_comp_process.stdout),
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


@app.task(bind=True, max_retries=10, retry_backoff=10)
def build_zipfile_of_videos(self, filename, study_uuid, orderby, match, requesting_user_uuid, consent=False):
    from studies.models import Study
    from accounts.models import User
    # get the study in question
    study = Study.objects.get(uuid=study_uuid)
    # get the user
    requesting_user = User.objects.get(uuid=requesting_user_uuid)
    # find the requested attachments
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
    gs_blob = gc_storage.blob.Blob(zip_filename, gs_private_bucket)

    # if the file exists short circuit and send the email with a 30m link
    if not gs_blob.exists():
        # if it doesn't exist build the zipfile
        with tempfile.TemporaryDirectory() as temp_directory:
            zip_file_path = os.path.join(temp_directory, zip_filename)
            zip = zipfile.ZipFile(zip_file_path, 'w')
            for attachment in attachments:
                temporary_file_path = os.path.join(temp_directory, attachment.key)
                file_response = requests.get(
                    attachment_helpers.get_download_url(attachment.key),
                    stream=True
                )
                local_file = open(temporary_file_path, mode='w+b')
                for chunk in file_response.iter_content(8192):
                    local_file.write(chunk)
                local_file.close()
                zip.write(temporary_file_path, attachment.key)
            zip.close()

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
