import logging
import os
import re
import time
import zipfile
from io import BytesIO

import requests
from django.conf import settings
from django.utils import timezone

from studies.models import Study

logger = logging.getLogger()


#   - pull the study model instance
#   - check to see if it is simple or advanced
#   - simple:
#       - save sha of current head of ember experimenter to study model instance
#       - save sha of current head of ember addons to study model instance
#       - create a build directory based on the uuid of the study and a timestamp
#       - create package.json referencing those as dependencies
#       - use yarn or npm to install dependencies
#       - ember-build to create a packagable application
#       - zip up packaged application
#       - delete temporary build directory
#       - create folder on s3 bucket
#       - transfer files to folder on s3 bucket
#       - save the url of the s3 bucket folder in study model instance
#       - send notification that deployment is completed
#   - advanced:
#       - user uploads a file with experiment
#       - file is saved in temporary location
#       - file is extracted to a temporary location
#       - create folder on s3 bucket
#       - transfer files to folder on s3 bucket
#       - delete temporary build directory
#       - save the url of the s3 bucket folder in the study model instance
#       - send notification that deployment is complete
#   - preview
#       - create a random build folder name based on the uuid of the study and a timestamp
#       - Do the deployment steps without copying to s3
#       - launch a new browser window at proxy view that requires login to the url of the temporary build folder
#       - task to clean up the temporary build folders nightly, weekly, monthly?

def get_repo_path(full_repo_path):
    return re.search('https://github.com/(.*)', full_repo_path).group(1)


def get_master_sha(repo_url):
    api_url = f'https://api.github.com/repos/{get_repo_path(repo_url)}/git/refs'
    response = requests.get(api_url)
    return response.json()[0]['object']['sha']


def unzip_file(file, destination_folder):
    """
    Github puts all files into a f`{repo_name}_{sha}`/ directory.
    This strips off the top-level directory and uses the destination_folder
    in it's place.
    """
    os.makedirs(destination_folder, mode=0o777, exist_ok=True)
    with zipfile.ZipFile(BytesIO(file)) as zip_file:
        for member in zip_file.infolist():
            if member.is_dir():
                os.makedirs(os.path.join(destination_folder, member.filename.partition('/')[-1]), mode=0o777, exist_ok=True)
                continue
            with open(os.path.join(destination_folder, member.filename.partition('/')[-1]), 'wb') as outfile:
                outfile.write(zip_file.read(member))


def deploy_to_remote(folder_name):
    pass


def download_repos(addons_sha=None, player_sha=None):
    if addons_sha is None or not re.match('([a-f0-9]{40})', addons_sha):
        addons_sha = get_master_sha(settings.EMBER_ADDONS_REPO)
    if player_sha is None or not re.match('([a-f0-9]{40})', player_sha):
        player_sha = get_master_sha(settings.EMBER_EXP_PLAYER_REPO)

    repo_destination_folder = f'./{player_sha}_{addons_sha}/'

    if os.path.isdir(repo_destination_folder):
        return repo_destination_folder

    addons_zip_path = f'{settings.EMBER_ADDONS_REPO}/archive/{addons_sha}.zip'
    player_zip_path = f'{settings.EMBER_EXP_PLAYER_REPO}/archive/{player_sha}.zip'

    unzip_file(requests.get(player_zip_path).content, repo_destination_folder)
    unzip_file(requests.get(addons_zip_path).content, os.path.join(repo_destination_folder, 'lib'))

    return repo_destination_folder


def build_experiment(study_uuid, preview=True):
    now = timezone.now()
    try:
        study = Study.objects.get(uuid=study_uuid)
    except Study.DoesNotExist as ex:
        logger.error(f'Study with uuid {study_uuid} does not exist. {ex}')
        raise
    player_destination_folder = f'./{study_uuid}_{time.mktime(now.timetuple())}'

    player_sha = getattr(study, 'last_known_player_sha', None)
    addons_sha = getattr(study, 'last_known_addons_sha', None)

    repo_destination_folder = download_repos(addons_sha=addons_sha, player_sha=player_sha)

    commands = [
        # args                                   # cwd
        (['yarn', 'install', '--pure-lockfile'], repo_destination_folder),
        (['bower', 'install'], repo_destination_folder),
        (['yarn', 'install', '--pure-lockfile'], os.path.join(repo_destination_folder, 'lib')),
        (['bower', 'install'], os.path.join(repo_destination_folder, 'lib')),
        # (['ls', '-l'], os.path.join(repo_destination_folder, 'lib')),
        (['cp', 'VideoRecorder.swf', os.path.join(repo_destination_folder, 'public')], os.path.abspath(os.path.join(os.path.curdir, 'studies/player_files'))),
        (['cp', 'environment', os.path.join(repo_destination_folder, 'public', '.env')], os.path.abspath(os.path.curdir)),
    ]
    while ret_code == 0:
        arguments, cwd = commands.pop()
        logger.debug(f'Started {' '.join(arguments)} on {cwd}')
        ret_code = subprocess.run(arguments, cwd=cwd)
        logger.debug(f'Finished {' '.join(arguments)} on {cwd}')

    # cd repo_destination_folder
    # yarn install --pure-lockfile
    # bower install
    # cd repo_destination_folder/lib/exp-player
    # yarn install --pure-lockfile
    # bower install
    # cp VideoRecorder.swf repo_destination_folder/public
    # cp .env into repo_destination_folder
    # ember build?


def cleanup_builds(older_than=None):
    if not older_than:
        older_than = timezone.now() - timezone.timedelta(days=1)
    pass
