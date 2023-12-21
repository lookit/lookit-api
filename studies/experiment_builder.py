import inspect
import json
import os
import re
import zipfile
from io import BytesIO
from operator import attrgetter
from typing import NamedTuple, Sequence

import docker
import requests
from django.conf import settings
from django.core.files import File

from project import storages
from studies.helpers import send_mail

DOCKER_CLIENT = docker.from_env()


class DirectoryTargets(NamedTuple):
    checkouts: str
    deployments: str


class BuildLog(NamedTuple):
    stage: str
    success: bool
    logs: str

    def as_dict(self):
        return self._asdict()


class BuildError(Exception):
    """Base error for module"""


class ExperimentBuilder:
    """A robust class that helps us build arbitrary experiments."""

    DEFAULT_CONTEXT: dict

    build_logs: list
    build_stages: Sequence[str]
    build_context: dict

    def __init__(self, build_stages: Sequence = None, logger=None, **kwargs):
        """

        Args:
            build_stages: The sequence of build stages that you want.
        """
        self.build_logs = []
        self.build_stages = build_stages or self.build_stages
        self.build_context = {**(self.DEFAULT_CONTEXT or {}), **(kwargs or {})}
        self.logger = logger

    def build(self) -> bool:
        """The build method.

        Returns:
            A boolean indicating whether or not the build went to completion.
        """
        broken_stage = None
        for index, stage in enumerate(self.build_stages):
            try:
                self._do_stage(stage)
                self.logger.debug(f"Stage {index + 1}: {stage} successfully completed.")
            except BuildError as e:
                self.logger.debug(e)
                broken_stage = stage
                break

        log_finalizer = getattr(self, "finalize_build_log")

        if log_finalizer:
            log_finalizer(failure_stage=broken_stage)

        return not bool(broken_stage)

    def _do_stage(self, current_stage: str):
        """Performs the next stage of the build.

        Args:
            current_stage: A getter string. Can be dot formatted in case you have inner classes or nested callables of
                some other sort.

        Side Effects:
            Stores build context.

        Raises:
            BuildError: for when things go wrong.
        """
        stage_fn = attrgetter(current_stage)(self)
        args, varargs, kwargs = inspect.getargs(stage_fn.__code__)

        args = args[1:]  # Get rid of "self"
        try:
            if args:
                build_args = tuple(self.build_context[arg] for arg in args)
            else:
                build_args = tuple()
        except KeyError as e:
            raise BuildError(f"Missing build context: {e}")

        # Run function with build args, append to build log.
        try:
            stage_data = stage_fn(*build_args)
        except Exception as e:  # early exit
            stage_log = BuildLog(
                stage=current_stage,
                success=False,
                logs=f"Uncaught failure of type {type(e)}:\n{e}",
            )
            self.build_logs.append(stage_log.as_dict())
            raise BuildError(f"Failure at {current_stage}\nLogs:\n{stage_log.logs}.")

        if stage_data is None:
            stage_log = BuildLog(
                stage=current_stage, success=True, logs="No logs given."
            )
        elif isinstance(stage_data, dict):
            stage_data = {
                "stage": current_stage,
                "success": True,
                "logs": "No logs given.",
                **stage_data,  # Override defaults.
            }
            stage_log = BuildLog(**stage_data)
        elif isinstance(stage_data, (tuple, list)):
            stage_log = BuildLog(current_stage, *stage_data)
        else:
            raise BuildError(
                f"Unsupported return type for build stage: {type(stage_data)}"
            )

        self.build_logs.append(stage_log.as_dict())

        if not stage_log.success:
            raise BuildError(f"Failure at {current_stage}\nLogs:\n{stage_log.logs}.")


class EmberFrameplayerBuilder(ExperimentBuilder):
    """Builds Ember Frameplayer experiments."""

    DEFAULT_CONTEXT = {
        "local_paths": DirectoryTargets(
            checkouts=os.path.join(settings.EMBER_BUILD_ROOT_PATH, "checkouts"),
            deployments=os.path.join(settings.EMBER_BUILD_ROOT_PATH, "deployments"),
        ),
        "update_fields": [],
    }

    build_stages = (
        "get_study",
        "get_researcher",
        "get_player_sha",
        "build_docker_image",
        "get_container_directories",
        "run_docker_container",
        "deploy_study",
        "save_study_and_log_results",
    )

    def __init__(self, *args, **kwargs):
        kwargs["destination_directory"] = kwargs["study_uuid"]
        super().__init__(*args, **kwargs)

    def get_study(self, study_uuid):
        from studies.models import Study

        study = Study.objects.get(uuid=study_uuid)
        # Set this here (in addition to in view) in case re-trying
        study.is_building = True
        study.save(update_fields=["is_building"])
        self.build_context["study"] = study

    def get_researcher(self, researcher_uuid):
        from accounts.models import User

        self.build_context["researcher"] = User.objects.get(uuid=researcher_uuid)

    def get_player_sha(self, study):
        """Gets the player sha, if it's been explicitly declared. If not, mark metadata as an update field."""
        self.build_context["player_sha"] = player_sha = study.metadata.get(
            "last_known_player_sha", None
        )
        if not player_sha:  # We will technically be updating metadata here.
            self.build_context["update_fields"] += ["metadata"]

    def build_docker_image(self):
        image, _image_log_gen = DOCKER_CLIENT.images.build(
            path=settings.EMBER_BUILD_ROOT_PATH,
            pull=True,
            tag="ember_build",
            cache_from=["ember_build"],
        )
        self.build_context["docker_image"] = image

    def get_container_directories(self, study, study_uuid, player_sha):
        player_repo_url = study.metadata.get(
            "player_repo_url", settings.EMBER_EXP_PLAYER_REPO
        )

        # TODO: How can we make download repos more efficient?
        checkout_directory, player_sha = download_repos(
            player_repo_url, player_sha=player_sha
        )

        study.metadata["last_known_player_sha"] = player_sha

        container_checkout_directory = os.path.join("/checkouts/", checkout_directory)
        container_destination_directory = os.path.join("/deployments/", study_uuid)

        self.build_context["container_paths"] = DirectoryTargets(
            checkouts=container_checkout_directory,
            deployments=container_destination_directory,
        )

    def run_docker_container(self, container_paths, study_uuid, local_paths):
        stdout_and_stderr = DOCKER_CLIENT.containers.run(
            "ember_build",
            command="bash build.sh",
            auto_remove=True,
            environment={
                "CHECKOUT_DIR": container_paths.checkouts,
                "PREPEND_FINGERPRINT": f"/studies/{study_uuid}/",
                "STUDY_OUTPUT_DIR": container_paths.deployments,
                "SENTRY_DSN": os.environ.get("SENTRY_DSN_JS", None),
                "PIPE_ACCOUNT_HASH": os.environ.get("PIPE_ACCOUNT_HASH"),
                "PIPE_ENVIRONMENT": os.environ.get("PIPE_ENVIRONMENT"),
                "S3_REGION": os.environ.get("S3_REGION"),
                "S3_ACCESS_KEY_ID": os.environ.get("S3_ACCESS_KEY_ID"),
                "S3_SECRET_ACCESS_KEY": os.environ.get("S3_SECRET_ACCESS_KEY"),
                "S3_BUCKET": os.environ.get("S3_BUCKET"),
            },
            volumes={
                local_paths.checkouts: {"bind": "/checkouts", "mode": "ro"},
                local_paths.deployments: {"bind": "/deployments", "mode": "rw"},
            },
            stdout=True,
            stderr=True,
        )

        return {"success": True, "logs": stdout_and_stderr.decode("utf-8")}

    def deploy_study(self, local_paths, destination_directory):
        storage = storages.LookitExperimentStorage()

        cloud_deployment_directory = os.path.join(
            local_paths.deployments, destination_directory
        )

        deploy_to_remote(cloud_deployment_directory, storage)

    def save_study_and_log_results(self, study, update_fields):
        # Only update field for particular build, in case we have parallel builds running
        study.built = True
        study.is_building = False
        study.save(update_fields=update_fields + ["built", "is_building"])
        self.build_context["action"] = "deployed"

    def finalize_build_log(self, failure_stage=None):
        from studies.models import StudyLog

        study = self.build_context["study"]
        study.is_building = False
        study.save(update_fields=["is_building"])
        action = self.build_context.get("action", "failed to build")
        researcher = self.build_context["researcher"]
        logs = json.dumps(self.build_logs, indent=4, default=str)

        notify_involved_parties_of_build_status(
            study, failure_stage=failure_stage, log_output=logs
        )

        StudyLog.objects.create(study=study, action=action, user=researcher, extra=logs)


def get_repo_path(full_repo_path):
    return re.search("https://github.com/(.*)", full_repo_path).group(1).rstrip("/")


def get_branch_sha(repo_url, branch):
    api_url = f"https://api.github.com/repos/{get_repo_path(repo_url)}/git/refs/heads/{branch}"
    response = requests.get(api_url)
    sha = response.json()["object"]["sha"]
    return sha


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
                os.makedirs(
                    os.path.join(
                        destination_folder, member.filename.partition("/")[-1]
                    ),
                    mode=0o777,
                    exist_ok=True,
                )
                continue
            with open(
                os.path.join(destination_folder, member.filename.partition("/")[-1]),
                "wb",
            ) as outfile:
                outfile.write(zip_file.read(member))


def deploy_to_remote(local_path, storage):
    """Wrapper for remote file deployments.

    If we have a Google Cloud Storage client, we should leverage batching capability.
    """
    # TODO: Threaded implementation of multi-upload, given that the GCS API backend
    # doesn't actually support batched MIME requests :(
    _upload_in_serial(local_path, storage)


def _upload_in_serial(local_path, storage):
    """Inner worker function for storage uploads in serial.  This should be skipped when
    developing locally."""
    if not settings.DEBUG:
        for root_directory, dirs, files in os.walk(local_path, topdown=True):
            for filename in files:
                full_path = os.path.join(root_directory, filename)
                with open(full_path, mode="rb") as f:
                    remote_path = full_path.split("/ember_build/deployments/")[1]
                    storage.save(remote_path, File(f))


def download_repos(player_repo_url, player_sha=None):
    if player_sha is None or not re.match("([a-f0-9]{40})", player_sha):
        player_sha = get_branch_sha(player_repo_url, settings.EMBER_EXP_PLAYER_BRANCH)

    repo_destination_folder = f"{player_sha}"
    local_repo_destination_folder = os.path.join(
        "./ember_build/checkouts/", repo_destination_folder
    )

    if not os.path.isdir(local_repo_destination_folder):
        player_zip_path = f"{player_repo_url}/archive/{player_sha}.zip"
        unzip_file(requests.get(player_zip_path).content, local_repo_destination_folder)

    return repo_destination_folder, player_sha


def notify_involved_parties_of_build_status(study, failure_stage=None, log_output=None):
    lab = study.lab
    lab_name = lab.name if lab else None
    email_context = {
        "lab_name": lab_name,
        "study_name": study.name,
        "study_id": study.pk,
        "study_uuid": str(study.uuid),
    }

    success = failure_stage is None

    if success:
        email_context["action"] = "deployed"

        send_mail.delay(
            "notify_admins_of_study_action",
            "Study Deployed",
            settings.EMAIL_FROM_ADDRESS,
            bcc=list(study.admin_group.user_set.values_list("username", flat=True)),
            **email_context,
        )
        subject_line = "Experiment runner built"
        researcher_notification_template = "notify_researchers_of_deployment"
    else:
        email_context["failure_stage"] = failure_stage
        email_context["log_output"] = log_output
        subject_line = "Experiment runner failed to build."
        researcher_notification_template = "notify_researchers_of_build_failure"

    send_mail.delay(
        researcher_notification_template,
        subject_line,
        settings.EMAIL_FROM_ADDRESS,
        bcc=list(study.admin_group.user_set.values_list("username", flat=True)),
        **email_context,
    )
