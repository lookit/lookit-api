""" invoke tasks for local development. 

tasks.py is a set of invoke tasks for automatically installing and configuring all the dependencies necessary
for local development.

Example:
    invoke task_name

    where task_name can be rabbitmq, celery, or any other dependencies that is represented by a func

Requirement:
    invoke library 

Attributes:
    HOSTNAME (str): This holds the value of the current hostname.  Usually 'localhost'.
    PLATFORM (str): holds OS details of the working env. ex: 'Linux'
    MESSAGE_FAILED (str): holds the message that displays when a package fails to install
    MESSAGE_WRONG_PLATFORM (str): holds a message that displays when the OS being used is not supported by the tasks. 
    MESSAGE_ALREADY_INSTALLED (str): holds a message that displays when the package is already available in the system.
"""
import json
import os
import platform
import shutil
from pathlib import Path

import semantic_version
from invoke import run, task

HOSTNAME = "localhost"
PLATFORM = platform.system()
MESSAGE_FAILED = 'failed to install. Please, use "invoke task_name --verbose" to check out the stderr and stdout responses.'
MESSAGE_OK = "successfully installed"
MESSAGE_WRONG_PLATFORM = "Unsupported Platform. Only Ubuntu (16.04+), Debian (9+), Mac OS. Your system is {}".format(
    platform.platform()
)
MESSAGE_ALREADY_INSTALLED = "already installed"

# Versioning
# - Segment
MAJOR = "major"
MINOR = "minor"
PATCH = "patch"
VERSION_TAGS = (MAJOR, MINOR, PATCH)
# - Pre-release
ALPHA = "alpha"
BETA = "beta"
RELEASE_CANDIDATE = "rc"
PRE_RELEASE_TAGS = (ALPHA, BETA, RELEASE_CANDIDATE)


@task
def dotenv(_):
    """Dotenv invoke task.

    Copies env_dist to .env if .env doesn't exist.

    Args:
        c (obj): Context-aware API wrapper & state-passing object.

    Returns:
        None.

    """
    if not Path(".env").exists():
        shutil.copy("env_dist", ".env")


@task
def rabbitmq(c):
    """Rabbitmq invoke task.

    This func creates users and queues for the API.

    Args:
        c (obj): Context-aware API wrapper & state-passing object.
    """
    # Get list of users and check if we've created our 'lookit-admin' yet.
    users = c.run("rabbitmqctl list_users --formatter json", hide="stdout").stdout
    users = json.loads(users)
    if not any(u["user"] == "lookit-admin" for u in users):
        c.run("rabbitmqctl add_user lookit-admin admin")

    c.run("rabbitmqctl set_user_tags lookit-admin administrator", hide="stdout")
    c.run("rabbitmqctl set_permissions -p / lookit-admin '.*' '.*' '.*'", hide="stdout")
    c.run("rabbitmq-plugins enable rabbitmq_management", hide="stdout")
    c.run("rabbitmqadmin declare queue  --vhost=/ name=email", hide="stdout")
    c.run("rabbitmqadmin declare queue  --vhost=/ name=builds", hide="stdout")
    c.run("rabbitmqadmin declare queue  --vhost=/ name=cleanup", hide="stdout")


@task
def postgresql(c):
    """Postgresql invoke task.

    Runs django db migrations. 

    Args:
        c (obj): Context-aware API wrapper & state-passing object.
    """
    c.run("python manage.py migrate", hide="stdout")


@task
def ssl_certificate(c, verbose=False):
    """Ssl-certificate invoke task. 

    this func sets up local https development env.

    Args:
        c (obj): Context-aware API wrapper & state-passing object.
        verbose (bool): states whether stdout should be printed.

    Returns:
        None.

        However, this func echoes MESSAGE_FAILED, MESSAGE_OK, or MESSAGE_ALREADY_INSTALLED
        depending on the state of the installation process.

    Note:
        For debugging purposes, set verbose (bool) to True to print the stdout responses for the run process.

    Usage:
        invoke ssl-certificate or invoke ssl-certificate --verbose

    """
    if PLATFORM == "Linux":
        if run("command -v mkcert", warn=True, hide=not verbose).ok:
            run('echo "===> mkcert {}"'.format(MESSAGE_ALREADY_INSTALLED))
        else:
            if run("brew install mkcert", warn=True, hide=not verbose).ok:
                run(
                    "apt-get update && apt install libnss3-tools",
                    warn=True,
                    hide=not verbose,
                )
                run("mkcert -install", warn=True, hide=not verbose)
                run('echo "===> mkcert {}"'.format(MESSAGE_OK))
            else:
                run('echo "===> mkcert {}"'.format(MESSAGE_FAILED))
        run("mkdir certs", warn=True, hide=not verbose)
        if run(
            "cd certs && mkcert local_lookit.mit.edu", warn=True, hide=not verbose
        ).ok:
            run(
                'echo "certificates successfully created at {}/certs"'.format(
                    Path.cwd()
                )
            )
        else:
            run('echo "certificates {}"'.format(MESSAGE_FAILED))
    elif PLATFORM == "Darwin":
        if run("command -v mkcert", warn=True, hide=not verbose).ok:
            run('echo "===> mkcert {}"'.format(MESSAGE_ALREADY_INSTALLED))
        else:
            if run("brew install mkcert", warn=True, hide=not verbose).ok:
                run("mkcert -install", warn=True, hide=not verbose)
                run('echo "===> mkcert {}"'.format(MESSAGE_OK))
            else:
                run('echo "===> mkcert {}"'.format(MESSAGE_FAILED))
        run("mkdir certs", warn=True, hide=not verbose)
        if run(
            "cd certs && mkcert local_lookit.mit.edu", warn=True, hide=not verbose
        ).ok:
            run(
                'echo "=====> certificates successfully created at {}/certs"'.format(
                    Path.cwd()
                )
            )
        else:
            run('echo "=====> certificates {}"'.format(MESSAGE_FAILED))
    else:
        run("echo {}".format(MESSAGE_WRONG_PLATFORM))


@task
def server(c, https=False):
    """Serving invoke task.

    This func serves django application server.

    Args:
        c (obj): Context-aware API wrapper & state-passing object.
        https (bool, optional): Use the ssl version of the local development server. Defaults to False.
    """
    certs_path = Path.cwd() / "certs"
    key = certs_path / "local_lookit.mit.edu-key.pem"
    certificate = certs_path / "local_lookit.mit.edu.pem"

    if https and os.listdir(certs_path):
        c.run(
            f"echo -e '\a Serving at https://{HOSTNAME}:8000\a'", hide=False,
        )
        c.run(
            f"python manage.py runsslserver --certificate {certificate} --key {key}",
            hide=False,
        )
    else:
        c.run(f"echo -e '\a Serving at http://{HOSTNAME}:8000\a'", hide=False)
        c.run("python manage.py runserver", hide=False)


@task
def ngrok_service(c):
    """Ngrok-service invoke task.

    This func serves ngrok.

    Args:
        c (obj): Context-aware API wrapper & state-passing object.
    """
    c.run(f"ngrok http https://{HOSTNAME}:8000")


@task
def celery_service(c):
    """Celery-service invoke task

    This func serves celery.

    Args:
        c (obj): Context-aware API wrapper & state-passing object.
    """
    c.run("celery worker --app=project --loglevel=INFO -Q builds,email,cleanup")


@task
def pre_commit_hooks(c):
    """Add pre-commit git hooks

    Args:
        c (Context): Context-aware API wrapper & state-passing object.
    """
    c.run("poetry run pre-commit install --install-hooks")


@task(dotenv, postgresql, rabbitmq, ssl_certificate, pre_commit_hooks)
def setup(_):
    """Setup invoke task.

    This func runs the tasks specified in the task decorator.

    Args:
        c (obj): Context-aware API wrapper & state-passing object.
    """
    pass


@task
def new_version(c, kind="", pre="", build="", dry_run=False):
    """Semantic Versioning automation.

    Leverages builder pattern afforded by `semantic_version.Version` objects.

    Args:
        c: Context-aware API wrapper & state-passing object.
        kind: What kind of version bump we're doing. Choices are as follows:
            `major`: use when public API changes
            `minor`: use when a new feature/enhancement is included
            `patch`: use when a bug is fixed or non-functional change is added
        pre: If this is a prerelease (release on dev), then the type should be provided here.
            `alpha`: Alpha; work in progress
            `beta`: Beta; ready for testing
            `rc`: Release Candidate; ready for final check up prior to deployment.
        build: If something has changed in the CI pipeline and we are attempting to trigger a new
            CI/CD run, you should run with this flag and pass a space-separated string of build
            information (you probably want to associate a commit with this, as well).
        dry_run: Defaults to False. Whether or not to write to the VERSION file.

    Returns:
        None

    Side Effects:
        Prints a newly updated version to stdout if `--dry-run` is false, and
        writes that version to the `VERSION` file in the root of the project.
    """
    with open("VERSION") as version_file:
        release_version = semantic_version.Version(version_file.read())

    # Simple version bumps are straightforward.
    if (kind := kind.lower()) and kind in VERSION_TAGS:
        release_version = getattr(release_version, f"next_{kind}")()

    # Pre-releases must proceed in order (alpha before beta, beta before release candidate)
    # and format of (kind: str, iteration: int) is enforced.
    elif (pre := pre.lower()) and pre in PRE_RELEASE_TAGS:
        previous_prerelease = release_version.prerelease
        # If there's current prerelease info, bump the associated number
        if previous_prerelease:
            # Assume (type, number) structure
            previous_pre, previous_iteration = previous_prerelease
            if pre == previous_pre:
                next_iteration = str(int(previous_iteration) + 1)
            elif PRE_RELEASE_TAGS.index(pre) > PRE_RELEASE_TAGS.index(previous_pre):
                next_iteration = "1"
            else:  # Invalid progression
                raise SystemExit("Pre-releases must proceed alpha -> beta -> rc")
        else:  # Otherwise, start at 1.
            next_iteration = "1"

        release_version.prerelease = (pre, next_iteration)

    # Build information just gets tacked on - it's information for pretty much developers
    # only, and as such can be arbitrary.
    elif build:
        release_version.build = tuple(build.split(" "))

    else:
        raise SystemExit("Must provide --kind, --pre, or --build.")

    release_output: str = str(release_version)

    if not dry_run:
        with open("VERSION", "w") as version_file:
            version_file.write(release_output)

    print(release_output)


@task
def coverage(c):
    """Generate test coverage data.

    Args:
        c (Context): Context-aware API wrapper & state-passing object.
    """
    c.run("poetry run coverage run --source='.' manage.py test")
    coverage_report(c)


@task
def coverage_report(c):
    """View basic CLI test coverage report.

    Args:
        c (Context): Context-aware API wrapper & state-passing object.
    """
    c.run("poetry run coverage report -i")
