""" invoke tasks for local development. 

tasks.py is a set of invoke tasks for automatically installing and configuring all the dependencies necessary
for local development.

Example:
    invoke task_name

    where task_name can be rabbitmq, celery, or any other dependencies that is represented by a func

Requirement:
    invoke library 

Attributes:
    PLATFORM (str): holds OS details of the working env. ex: 'Linux'
    MESSAGE_FAILED (str): holds the message that displays when a package fails to install
    MESSAGE_WRONG_PLATFORM (str): holds a message that displays when the OS being used is not supported by the tasks. 
    MESSAGE_ALREADY_INSTALLED (str): holds a message that displays when the package is already available in the system.
    SERVE_CELERY (str): holds a command that serves celery
    SERVE_HTTPS_SERVER (str): holds a command that serves securely the django web application (HTTPS) 
    SERVE_HTTP_SERVER (str): holds a command that serces django web application (HTTP)
    SERVE_NGROK (str): holds a command that serves ngrok
    BASE_DIR (str): holds the path to the current working directory
    PATH_TO_CERTS (str): holds the path to certificates used to serve the django application securely.

"""
import os
import platform

import semantic_version
from invoke import run, task

PLATFORM = platform.system()
MESSAGE_FAILED = 'failed to install. Please, use "invoke task_name --verbose" to check out the stderr and stdout responses.'
MESSAGE_OK = "successfully installed"
MESSAGE_WRONG_PLATFORM = "Unsupported Platform. Only Ubuntu (16.04+), Debian (9+), Mac OS. Your system is {}".format(
    platform.platform()
)
MESSAGE_ALREADY_INSTALLED = "already installed"
SERVE_CELERY = "celery worker --app=project --loglevel=INFO -Q builds,email,cleanup"
SERVE_HTTPS_SERVER = "python manage.py runsslserver --certificate certs/local_lookit.mit.edu.pem --key certs/local_lookit.mit.edu-key.pem"
SERVE_HTTP_SERVER = "python manage.py runserver"
SERVE_NGROK = "ngrok http https://localhost:8000"
BASE_DIR = os.getcwd()
PATH_TO_CERTS = os.path.join(BASE_DIR, "certs")

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
def system_setup(c, verbose=False):
    """System-setup invoke task.
    
    This func installs pipenv, brew, docutils, and celery.
    This func also sets the debug to True in a local setting file for serving locally.

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
        invoke system-setup or invoke system-setup --verbose

    """

    run("echo '*** SYSTEM SETUP ***'")
    run("echo 'Installing & Configuring local settings'")

    # installing linuxbrew
    if PLATFORM == "Linux":
        run(
            'sh -c "$(curl -fsSL https://raw.githubusercontent.com/Linuxbrew/install/master/install.sh)"',
            hide=not verbose,
            warn=True,
        )
        run(
            "test -d ~/.linuxbrew && eval $(~/.linuxbrew/bin/brew shellenv)",
            hide=not verbose,
            warn=True,
        )
        run(
            "test -d /home/linuxbrew/.linuxbrew && eval \$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)",
            hide=not verbose,
            warn=True,
        )
        run(
            'test -r ~/.bash_profile && echo "eval \$($(brew --prefix)/bin/brew shellenv)" >>~/.bash_profile',
            hide=not verbose,
            warn=True,
        )
        run(
            'echo "eval $($(brew --prefix)/bin/brew shellenv)"',
            hide=not verbose,
            warn=True,
        )
        run(
            "sudo apt-get install build-essential curl git", hide=not verbose, warn=True
        )
        if run("command -v brew", hide=not verbose, warn=True).ok:
            run('echo "===> brew {}"'.format(MESSAGE_OK))
        else:
            run('echo "===> brew {}"'.format(MESSAGE_FAILED))


    # creating a local setting file
    if run("test -f .env", warn=True).ok:
        run(
            "echo '===> Settings file .env already exists; not overwriting. Check that .env contains any necessary values from env_dist.'"
        )
    else:
        run(
            "cp env_dist .env && echo '===> Created local settings file .env based on env-dist'"
        )


@task
def pygraphviz(c, verbose=False):
    """Pygraphviz invoke task.

    This func installs graphyviz & pygraphviz.

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
        invoke pygraphviz or invoke pygraphviz --verbose

    """

    if PLATFORM == "Linux":
        # Installing pygraphviz
        if run("sudo pip install pygraphviz", hide=not verbose, warn=True).ok:
            run('echo "===> pygraphviz {}"'.format(MESSAGE_OK))
        else:
            run('echo "===> pygraphviz {}"'.format(MESSAGE_FAILED))

    elif PLATFORM == "Darwin":

        # Pygraphviz on Darwin usually fails to locate graphviz to solve the issue,
        # the install-option flag is used to include the path.

        if run(
            "sudo pip install pygraphviz --install-option='--include-path=/usr/include/graphviz' --install-option='--library-path=/usr/lib/graphviz/'",
            hide=not verbose,
            warn=True,
        ).ok:
            run('echo "===> pygraphviz {}"'.format(MESSAGE_OK))
        else:
            run('echo "===> pygraphviz {}"'.format(MESSAGE_FAILED))
    else:
        run("echo {}".format(MESSAGE_WRONG_PLATFORM))


@task
def rabbitmq(c, verbose=False):
    """Rabbitmq invoke task.

    This func installs rabbitmq and creates users and queues for the API.

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
        invoke rabbitmq or invoke rabbitmq --verbose

    """

    run("echo '*** INSTALLING RabbitMQ ***'")
    if PLATFORM == "Linux":
        # Rabbimq requires recent versions of erlang, which may not be available in the Debian and ubuntu distributions
        run(
            "sudo curl -fsSL https://github.com/rabbitmq/signing-keys/releases/download/2.0/rabbitmq-release-signing-key.asc | sudo apt-key add -",
            hide=not verbose,
            warn=True,
        )
        run(
            "sudo apt-get update && sudo apt-get install apt-transport-https",
            hide=not verbose,
            warn=True,
        )
        res = str(run("cat /etc/os-release", hide=not verbose, warn=True))
        if "stretch" in res:
            run(
                "sudo echo 'deb http://dl.bintray.com/rabbitmq-erlang/debian stretch erlang-22.x' > /etc/apt/sources.list.d/bintray.erlang.list",
                hide=not verbose,
                warn=True,
            )
            run(
                "sudo echo 'deb https://dl.bintray.com/rabbitmq/debian stretch main' > /etc/apt/sources.list.d/bintray.rabbitmq.list",
                hide=not verbose,
                warn=True,
            )
        elif "bionic" in res:
            run(
                "sudo echo 'deb http://dl.bintray.com/rabbitmq-erlang/debian bionic erlang-22.x' > sudo su /etc/apt/sources.list.d/bintray.erlang.list",
                hide=not verbose,
                warn=True,
            )
            run(
                "sudo su echo 'deb https://dl.bintray.com/rabbitmq/debian bionic main' > /etc/apt/sources.list.d/bintray.rabbitmq.list",
                hide=not verbose,
                warn=True,
            )
        elif "xenial" in res:
            run(
                "sudo su echo 'deb http://dl.bintray.com/rabbitmq-erlang/debian xenial erlang-22.x' > /etc/apt/sources.list.d/bintray.erlang.list",
                hide=not verbose,
                warn=True,
            )
            run(
                "sudo su echo 'deb https://dl.bintray.com/rabbitmq/debian xenial main' > /etc/apt/sources.list.d/bintray.rabbitmq.list",
                hide=not verbose,
                warn=True,
            )
        elif "buster" in res:
            run(
                "sudo echo 'deb http://dl.bintray.com/rabbitmq-erlang/debian buster erlang-22.x' > /etc/apt/sources.list.d/bintray.erlang.list",
                hide=not verbose,
                warn=True,
            )
            run(
                "sudo echo 'deb https://dl.bintray.com/rabbitmq/debian buster main' > /etc/apt/sources.list.d/bintray.rabbitmq.list",
                hide=not verbose,
                warn=True,
            )
        else:
            run("echo {}".format(MESSAGE_WRONG_PLATFORM))
        if run(
            "sudo apt-get update -y && sudo apt-get install -y erlang-base \
            erlang-asn1 erlang-crypto erlang-eldap erlang-ftp erlang-inets \
            erlang-mnesia erlang-os-mon erlang-parsetools erlang-public-key \
            erlang-runtime-tools erlang-snmp erlang-ssl \
            erlang-syntax-tools erlang-tftp erlang-tools erlang-xmerl",
            warn=True,
            hide=not verbose,
        ).ok:
            run('echo "===> erlang {}"'.format(MESSAGE_OK))
        else:
            run(
                'echo "Warning: Attempt to update Erlang failed. RabbitMQ has a requirement version of Erlang. Please, check and install it manually."'
            )

        # Installing rabbitmq from packagecloud
        run(
            "sudo apt-get update -y && sudo apt-get install rabbitmq-server -y --fix-missing",
            hide=not verbose,
            warn=True,
        )
        # Starting rabbitmq and creating administrators
        run("sudo service rabbitmq-server start", warn=True, hide=not verbose)
        run("sudo rabbitmqctl add_user lookit-admin admin", warn=True, hide=not verbose)
        run(
            "sudo rabbitmqctl set_user_tags lookit-admin administrator",
            warn=True,
            hide=not verbose,
        )
        run(
            "sudo rabbitmqctl set_permissions -p / lookit-admin '.*' '.*' '.*'",
            warn=True,
            hide=not verbose,
        )
        run(
            "sudo rabbitmq-plugins enable rabbitmq_management",
            warn=True,
            hide=not verbose,
        )
        # Download rabbitmqadmin and authorize x permission
        run(
            "cd /usr/bin/ && curl -O https://raw.githubusercontent.com/rabbitmq/rabbitmq-management/v3.7.17/bin/rabbitmqadmin",
            warn=True,
            hide=not verbose,
        )
        run("sudo chmod +x /usr/bin/rabbitmqadmin ", warn=True, hide=not verbose)
        run(
            "sudo chown -R rabbitmq:rabbitmq /var/lib/rabbitmq/",
            warn=True,
            hide=not verbose,
        )
        run(
            "sudo rabbitmqadmin declare queue  --vhost=/ name=email",
            warn=True,
            hide=not verbose,
        )
        run(
            "sudo rabbitmqadmin declare queue  --vhost=/ name=builds",
            warn=True,
            hide=not verbose,
        )
        run(
            "sudo rabbitmqadmin declare queue  --vhost=/ name=cleanup",
            warn=True,
            hide=not verbose,
        )
        if run("rabbitmqadmin list queues", warn=True, hide=not verbose).ok:
            run('echo "===> rabbitmq {}"'.format(MESSAGE_OK))
        else:
            run('echo "===> rabbitmq {}"'.format(MESSAGE_FAILED))

    elif PLATFORM == "Darwin":
        if run("command -v rabbitmqctl", hide=not verbose, warn=True):
            run("echo '===> RabbitMQ {}'".format(MESSAGE_ALREADY_INSTALLED))
        else:
            if run("brew install rabbitmq").ok:
                run('echo "===> RabbitMQ {}"'.format(MESSAGE_OK))
            else:
                run('echo "===> RabbitMQ {}"'.format(MESSAGE_FAILED))
        run("sudo rabbitmq server", warn=True, hide=not verbose)
        run("sudo rabbitmqctl add_user lookit-admin admin", warn=True, hide=not verbose)
        run(
            "sudo rabbitmqctl set_user_tags lookit-admin administrator",
            warn=True,
            hide=not verbose,
        )
        run(
            "sudo rabbitmqctl set_permissions -p / lookit-admin '.*' '.*' '.*'",
            warn=True,
            hide=not verbose,
        )
        run(
            "sudo brew services stop rabbitmq-server.service",
            warn=True,
            hide=not verbose,
        )
        run(
            "sudo brew services start rabbitmq-server.service",
            warn=True,
            hide=not verbose,
        )
        run(
            "sudo brew services enable rabbitmq-server.service",
            warn=True,
            hide=not verbose,
        )
        run(
            "sudo rabbitmq-plugins enable rabbitmq_management",
            warn=True,
            hide=not verbose,
        )
        run(
            "sudo chown -R rabbitmq:rabbitmq /var/lib/rabbitmq/",
            warn=True,
            hide=not verbose,
        )
        run(
            "sudo rabbitmqadmin declare queue  --vhost=/ name=email",
            warn=True,
            hide=not verbose,
        )
        run(
            "sudo rabbitmqadmin declare queue  --vhost=/ name=builds",
            warn=True,
            hide=not verbose,
        )
        run(
            "sudo rabbitmqadmin declare queue  --vhost=/ name=cleanup",
            warn=True,
            hide=not verbose,
        )
        run("sudo rabbitmqadmin list queues", warn=True, hide=not verbose)
    else:
        run("echo {}".format(MESSAGE_WRONG_PLATFORM))


@task
def postgresql(c, verbose=False):
    """Postgresql invoke task.
    
    This func installs postgresql, create the database of the API and create required tables. 

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
        invoke postgresql or invoke postgresql --verbose

    """
    run("echo '*** INSTALLING Postgresql ***'")
    if PLATFORM == "Linux":
        if run("command -v psql", warn=True, hide=not verbose):
            run("echo '===> postgresql {}'".format(MESSAGE_ALREADY_INSTALLED))

        else:
            if run(
                "apt-get update && apt-get install postgresql",
                warn=True,
                hide=not verbose,
            ).ok:
                run('echo "===> postgresql {}"'.format(MESSAGE_OK))
            else:
                run('echo "===> postgres {}"'.format(MESSAGE_FAILED))
        if run("service postgresql start", warn=True, hide=not verbose).ok:
            run('echo "=====> postgresql successfully started!"')
        else:
            run('echo "=====> postgresql failed to start!"')
        res = run("createdb lookit", warn=True, hide=not verbose)
        if res.exited == 0:
            run('echo "Database Successfully created!"')
        else:
            run('echo "Database already existed"')
        if run("python manage.py migrate", warn=True, hide=not verbose).ok:
            run('echo "====> Migrated Django models to lookit db"')
        else:
            run('echo "====> Migration failed"')
    elif PLATFORM == "Darwin":
        if run("python manage.py migrate", warn=True, hide=not verbose).ok:
            run('echo "====> Migrated Django models to lookit db"')
        else:
            run('echo "====> Migration failed"')
    else:
        run("echo {}".format(MESSAGE_WRONG_PLATFORM))


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
    run("echo '*** Setting HTTPS for local development ***'")
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
            run('echo "certificates successfully created at {}/certs"'.format(BASE_DIR))
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
                    os.getcwd()
                )
            )
        else:
            run('echo "=====> certificates {}"'.format(MESSAGE_FAILED))
    else:
        run("echo {}".format(MESSAGE_WRONG_PLATFORM))


@task
def ngrok(c, verbose=False):
    """Ngrok invoke task. 

    This func installs ngrok for Linux and Darwin platforms

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
        invoke ngrok or invoke ngrok --version 

    """
    run("echo '*** Installing Ngrok ***'")

    if PLATFORM == "Linux":
        if run("command -v ngrok", warn=True, hide=not verbose):
            run('echo "===> Ngrok {}"'.format(MESSAGE_ALREADY_INSTALLED))
        else:
            run("cd / && mkdir downloads", warn=True, hide=not verbose)
            run(
                "cd / && cd downloads && wget -cO ngrok.zip https://bin.equinox.io/c/4VmDzA7iaHb/ngrok-stable-linux-amd64.zip",
                warn=True,
                hide=not verbose,
            )
            run("cd / && cd downloads && unzip ngrok", warn=True, hide=not verbose)
            run("ln -s /downloads/ngrok /usr/bin/ngrok", warn=True, hide=not verbose)

            if run("ngrok", warn=True, hide=not verbose):
                run('echo "===> Ngrok {}"'.format(MESSAGE_OK))
            else:
                run('echo "===> Ngrok {}"'.format(MESSAGE_FAILED))

    elif PLATFORM == "Darwin":
        if run("command -v ngrok", hide=not verbose, warn=True).ok:
            run('echo "===> ngrok {}"'.format(MESSAGE_OK))
        else:
            run('echo "===> ngrok {}"'.format(MESSAGE_FAILED))

    else:
        run("echo {}".format(MESSAGE_WRONG_PLATFORM))


@task
def docker(c, verbose=False):
    """Docker invoke task.

    this func installs docker for both Ubuntu(Linux) and Darwin(MacOS/OSX)

    Args:
        c (obj): Context-aware API wrapper & state-passing object.
        verbose (bool): states whether stdout should be printed.

    Returns:
        None.

        However, this func echoes MESSAGE_FAILED, MESSAGE_OK, or MESSAGE_ALREADY_INSTALLED
        depending on the state of the installation process.

    Note:
        For debugging purposes, set verbose (bool) to True to print the stdout responses for the run process.

    usage: 
        invoke docker

    """

    if PLATFORM == "Linux":
        # Install Docker
        # Install key dependencies first
        if run("command -v docker", hide=not verbose, warn=True).ok:
            run('echo "===> docker {}"'.format(MESSAGE_ALREADY_INSTALLED))
        else:
            run(
                "apt-get install apt-transport-https ca-certificates curl gnupg2 software-properties-common",
                hide=not verbose,
                warn=True,
            )
            res = run("cat /etc/issue", hide=not verbose, warn=True)
            if "Debian" in str(res):
                run(
                    "curl -fsSL https://download.docker.com/linux/debian/gpg | apt-key add -",
                    hide=not verbose,
                    warn=True,
                )
                run("apt-key fingerprint 0EBFCD88", hide=not verbose, warn=True)
                run(
                    'add-apt-repository \
                    "deb [arch=amd64] https://download.docker.com/linux/debian \
                    $(lsb_release -cs) \
                    stable"',
                    hide=not verbose,
                    warn=True,
                )
                run(
                    "apt install docker-ce docker-ce-cli containerd.io",
                    hide=not verbose,
                    warn=True,
                )

                if run("docker", hide=not verbose, warn=True).ok:
                    run('echo "===> docker {}"'.format(MESSAGE_OK))
                else:
                    run('echo "===> docker {}"'.format(MESSAGE_FAILED))
            elif "Ubuntu" in str(res):
                run(
                    "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -",
                    hide=not verbose,
                    warn=True,
                )
                run("apt-key fingerprint 0EBFCD88", hide=not verbose, warn=True)
                run(
                    'add-apt-repository \
                    "deb [arch=amd64] https://download.docker.com/linux/debian \
                    $(lsb_release -cs) \
                    stable"',
                    hide=not verbose,
                    warn=True,
                )
                run("apt install docker-ce", hide=not verbose, warn=True)

                if run("docker", hide=not verbose, warn=True).ok:
                    run('echo "===> docker {}"'.format(MESSAGE_OK))
                else:
                    run('echo "===> docker {}"'.format(MESSAGE_FAILED))
            else:
                run("echo {}".format(MESSAGE_WRONG_PLATFORM))

    elif PLATFORM == "Darwin":
        pass
    else:
        run("echo {}".format(MESSAGE_WRONG_PLATFORM))


@task
def server(c):
    """Serving invoke task.

    This func serves django application server.
    
    Args:
        c (obj): Context-aware API wrapper & state-passing object.

    Returns:
        None.

    usage:
        invoke server

    """

    if os.listdir(PATH_TO_CERTS):
        run(
            "echo -e '\a Serving at https://localhost:8000\a'"
            + "&&"
            + SERVE_HTTPS_SERVER,
            hide=False,
        )
    else:
        run(
            "echo -e '\a Serving at http://localhost:8000\a'"
            + "&&"
            + SERVE_HTTP_SERVER,
            hide=False,
        )


@task
def ngrok_service(c):
    """Ngrok-service invoke task.

    This func serves ngrok.

    Args:
        c (obj): Context-aware API wrapper & state-passing object.

    Returns:
        None.

    Usage: 
        invoke ngrok_service

    """

    run(SERVE_NGROK)


@task
def celery_service(c):
    """Celery-service invoke task

    This func serves celery.

    Args:
        c (obj): Context-aware API wrapper & state-passing object.

    Returns:
        None.

    usage: 
        invoke celery 

    """
    run(SERVE_CELERY)


@task(
    system_setup,
    pygraphviz,
    rabbitmq,
    postgresql,
    ssl_certificate,
    docker,
    server,
)
def setup(c):
    """Setup invoke task.

    This func runs the tasks specified in the task decorator.

    Args:
        c (obj): Context-aware API wrapper & state-passing object.

    Returns:
        None.
    
    Note: 
        This func does not serve celery and ngrok. 

    usage: 
        invoke setup

    """
    pass


@task
def new_version(context, kind="", pre="", build="", dry_run=False):
    """Semantic Versioning automation.

    Leverages builder pattern afforded by `semantic_version.Version` objects.

    Args:
        context: Context-aware API wrapper & state-passing object.
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
