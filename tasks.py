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
import os
import platform
import shutil
from pathlib import Path

from invoke import run, task

HOSTNAME = "localhost"
PLATFORM = platform.system()
MESSAGE_FAILED = 'failed to install. Please, use "invoke task_name --verbose" to check out the stderr and stdout responses.'
MESSAGE_OK = "successfully installed"
MESSAGE_WRONG_PLATFORM = "Unsupported Platform. Only Ubuntu (16.04+), Debian (9+), Mac OS. Your system is {}".format(
    platform.platform()
)
MESSAGE_ALREADY_INSTALLED = "already installed"


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
        c.run(f"echo -e '\a Serving at https://{HOSTNAME}:8000\a'", hide=False)
        c.run(
            f"python -u manage.py runsslserver --certificate {certificate} --key {key}",
            hide=False,
        )
    else:
        c.run(f"echo -e '\a Serving at http://{HOSTNAME}:8000\a'", hide=False)
        c.run("python -u manage.py runserver", hide=False)


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


@task
def poetry_install(c):
    """Install current versions of python packages using 'poetry install'

    Args:
        c (Context): Context-aware API wrapper & state-passing object.
    """
    c.run("poetry install")


@task
def remove_db(c):
    """Remove existing postgres instance from Docker.

    Args:
        c (Context): Context-aware API wrapper & state-passing object.
    """
    c.run("docker stop lookit-postgres")
    c.run("docker rm lookit-postgres")


@task
def create_db(c):
    """Create postgres container in Docker.

    Args:
        c (Context): Context-aware API wrapper & state-passing object.
    """
    c.run(
        """
        docker run \
            --name lookit-postgres \
            -d \
            -e POSTGRES_HOST_AUTH_METHOD="trust" \
            -e POSTGRES_DB="lookit" \
            -p 5432:5432 \
            postgres:9.6
        """
    )


@task
def migrate_db(c):
    """Postgresql invoke task.

    Runs django db migrations.

    Args:
        c (obj): Context-aware API wrapper & state-passing object.
    """
    c.run("python -u manage.py migrate")


@task
def reset_db(c, sql_file=None):
    """Remove, create, and populate Postgres container in Docker.

    Args:
        c (Context): Context-aware API wrapper & state-passing object.
        sql_file (String, optional): SQL file from existing Postgres database. Defaults to None.
    """
    poetry_install(c)
    remove_db(c)
    create_db(c)
    c.run("sleep 3")
    if sql_file:
        c.run(
            f'cat "{sql_file}" | docker exec -i lookit-postgres psql -U postgres -d lookit'
        )
    migrate_db(c)


@task(dotenv, migrate_db, ssl_certificate, pre_commit_hooks)
def setup(_):
    """Setup invoke task.

    This func runs the tasks specified in the task decorator.

    Args:
        c (obj): Context-aware API wrapper & state-passing object.
    """
