from invoke import task, run 
import platform 
import os 

PLATFORM=platform.system()
MESSAGE_FAILED="failed to install. Please, use \"invoke task_name --verbose\" to check out the stderr and stdout responses."
MESSAGE_OK="successfully installed"
MESSAGE_WRONG_PLATFORM="Unsupported Platform. Only Ubuntu (16.04+), Debian (9+), Mac OS. Your system is {}".format(platform.platform())
MESSAGE_ALREADY_INSTALLED="already installed"
SERVE_CELERY="celery worker --app=project --loglevel=INFO -Q builds,email,cleanup"
SERVE_HTTPS_SERVER="python manage.py runsslserver --certificate certs/local_lookit.mit.edu.pem --key certs/local_lookit.mit.edu-key.pem"
SERVE_HTTP_SERVER="python manage.py runserver"
SERVE_NGROK="ngrok http 80"
BASE_DIR=os.getcwd()
PATH_TO_CERTS=os.path.join(BASE_DIR, 'certs')


@task
def system_setup(c,verbose=False):
    """

    Install pipenv, brew, docutils, and celery
    usage: invoke system-setup or invoke system-setup --verbose

    """

    run("echo '*** SYSTEM SETUP ***'")
    run("echo 'Installing pipenv, brew, and docutils'")
    packages=("pipenv", "docutils", "celery")

    for package in packages:

        if (run("pip install {}".format(package), hide=not verbose, warn=True).ok):

            run("echo \"===>{} {}\"".format(package, MESSAGE_OK))

        else:

            run("echo \"===>{} {}\"".format(package, MESSAGE_FAILED))

    #installing linuxbrew
    if PLATFORM=="Linux": 
        run("sh -c \"$(curl -fsSL https://raw.githubusercontent.com/Linuxbrew/install/master/install.sh)\"", hide= not verbose, warn=True) 
        run("test -d ~/.linuxbrew && eval $(~/.linuxbrew/bin/brew shellenv)", hide=not verbose, warn=True)
        run("test -d /home/linuxbrew/.linuxbrew && eval \$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)", hide=not verbose, warn=True)
        run("test -r ~/.bash_profile && echo \"eval \$($(brew --prefix)/bin/brew shellenv)\" >>~/.bash_profile", hide= not verbose, warn=True)
        run("echo \"eval $($(brew --prefix)/bin/brew shellenv)\"", hide=not verbose, warn=True)
        run("sudo apt-get install build-essential curl git", hide= not verbose, warn=True)
        if (run("command -v brew", hide=not verbose, warn=True).ok):
            run("echo \"===>brew {}\"".format(MESSAGE_OK))
        else:
            run("echo \"===>brew {}\"".format(MESSAGE_FAILED))

    if PLATFORM=="Darwin":
        if (run('command -v cask ', hide=not verbose, warn=True).ok):
            run("echo \"===>Cask {}\"".format(MESSAGE_ALREADY_INSTALLED))
        else:
            if (run("brew install cask").ok):
                run("echo \"===>Cask {}\"".format(MESSAGE_OK))
            else:
                run("echo \"===>Cask {}\"".format(MESSAGE_FAILED))

@task
def install_dependencies(c, verbose= False):
    """

    Install all the dependencies of the API
    usage: invoke install-dependencies or invoke install-dependencies --verbose

    """

    run("echo '***INSTALLING ALL DEPENDENCIES***'")
    packages=('',"django-sslserver")
    for package in packages:

        if (run("pipenv install {}".format(package), hide=not verbose, warn=True).ok):
            run("echo \"===>{} {}\"".format(package, MESSAGE_OK))
        else:
            run("echo \"===>{} {}\"".format(package, MESSAGE_FAILED))

@task 
def pygraphviz(c, verbose=False):
    """

    Install graphyviz & pygraphviz 
    usage: invoke pygraphviz or invoke pygraphviz --verbose

    """

    if PLATFORM=="Linux":
        #Installing graphviz
        if(run("sudo apt-get update && sudo apt-get install graphviz", hide= not verbose, warn=True).ok):
            run("echo \"Graphyviz {}\"".format(MESSAGE_OK))
        else:
            run("echo \"Graphyviz {}\"".format(MESSAGE_FAILED))
        #Installing pygraphviz
        if (run("sudo pip3 install pygraphviz --install-option='--include-path=/usr/include/graphviz' --install-option='--library-path=/usr/lib/graphviz/'", hide=not verbose, warn=True).ok):
            run("echo \"===>pygraphyviz {}\"".format(MESSAGE_OK))
        else:
            run("echo \"===>pygraphyviz {}\"".format(MESSAGE_FAILED))

    elif PLATFORM=="Darwin":
        if (run("sudo pip install pygraphviz --install-option='--include-path=/usr/include/graphviz' --install-option='--library-path=/usr/lib/graphviz/'", hide= not verbose, warn=True).ok):
            run("echo \"===>pygraphyviz {}\"".format(MESSAGE_OK))
        else:
            run("echo \"===>pygraphyviz {}\"".format(MESSAGE_FAILED))
    else:
        run("echo {}".format(MESSAGE_WRONG_PLATFORM))

@task
def rabbitmq(c, verbose=False):
    """

    Install rabbitmq, create users, and queues for the API
    usage: invoke rabbitmq or invoke rabbitmq --verbose

    """

    run("echo '***INSTALLING RabbitMq***'")
    if PLATFORM=="Linux":
        #Rabbimq requires recent versions of erlang, which may not be available in the Debian and ubuntu distributions
        run("curl -fsSL https://github.com/rabbitmq/signing-keys/releases/download/2.0/rabbitmq-release-signing-key.asc | apt-key add -", hide=verbose, warn=True)
        run("apt-get update && apt-get install apt-transport-https", hide= not verbose, warn=True)
        res=str(run("cat /etc/os-release", hide= not verbose, warn=True))
        if "stretch" in res:
            run("echo 'deb http://dl.bintray.com/rabbitmq-erlang/debian stretch erlang-22.x' > /etc/apt/sources.list.d/bintray.erlang.list", hide=not verbose)
            run("echo 'deb https://dl.bintray.com/rabbitmq/debian stretch main' > /etc/apt/sources.list.d/bintray.rabbitmq.list", hide=not verbose)
        elif "bionic" in res:
            run("echo 'deb http://dl.bintray.com/rabbitmq-erlang/debian bionic erlang-22.x' > /etc/apt/sources.list.d/bintray.erlang.list", hide=not verbose)
            run("echo 'deb https://dl.bintray.com/rabbitmq/debian bionic main' > /etc/apt/sources.list.d/bintray.rabbitmq.list", hide=not verbose)
        elif "xenial" in res:
            run("echo 'deb http://dl.bintray.com/rabbitmq-erlang/debian xenial erlang-22.x' > /etc/apt/sources.list.d/bintray.erlang.list", hide=not verbose)
            run("echo 'deb https://dl.bintray.com/rabbitmq/debian xenial main' > /etc/apt/sources.list.d/bintray.rabbitmq.list", hide=not verbose)
        elif "buster" in res:
            run("echo 'deb http://dl.bintray.com/rabbitmq-erlang/debian buster erlang-22.x' > /etc/apt/sources.list.d/bintray.erlang.list", hide=not verbose)
            run("echo 'deb https://dl.bintray.com/rabbitmq/debian buster main' > /etc/apt/sources.list.d/bintray.rabbitmq.list", hide=not verbose)
        else:
            run("echo {}".format(MESSAGE_WRONG_PLATFORM))

        run("apt-get update -y && apt-get install -y erlang-base \
            erlang-asn1 erlang-crypto erlang-eldap erlang-ftp erlang-inets \
            erlang-mnesia erlang-os-mon erlang-parsetools erlang-public-key \
            erlang-runtime-tools erlang-snmp erlang-ssl \
            erlang-syntax-tools erlang-tftp erlang-tools erlang-xmerl", warn=True, hide= not verbose)
        #Installing rabbitmq from packagecloud
        run("apt-get update -y && apt-get install rabbitmq-server -y --fix-missing", hide= not verbose, warn=True)
        #Starting rabbitmq and creating administrators
        run("sudo service rabbitmq-server start", warn=True, hide= not verbose) 
        run("sudo rabbitmqctl add_user lookit-admin admin", warn=True, hide= not verbose)
        run("sudo rabbitmqctl set_user_tags lookit-admin administrator", warn=True, hide=not verbose)
        run("sudo rabbitmqctl set_permissions -p / lookit-admin '.*' '.*' '.*'", warn=True, hide=not verbose)
        run("sudo rabbitmq-plugins enable rabbitmq_management", warn=True, hide=not verbose)
        #Download rabbitmqadmin and authorize x permission
        run("cd /usr/bin/ && curl -O https://raw.githubusercontent.com/rabbitmq/rabbitmq-management/v3.7.17/bin/rabbitmqadmin", warn=True, hide=not verbose)
        run("sudo chmod +x /usr/bin/rabbitmqadmin ", warn=True, hide=not verbose )
        run("sudo chown -R rabbitmq:rabbitmq /var/lib/rabbitmq/", warn=True, hide=not verbose)
        run("sudo rabbitmqadmin declare queue  --vhost=/ name=email", warn=True, hide=not verbose)
        run("sudo rabbitmqadmin declare queue  --vhost=/ name=builds", warn=True, hide=not verbose)
        if (run("rabbitmqadmin list queues", warn=True, hide=not verbose).ok):
            run("echo \"===>Rabbitmq {}\"".format(MESSAGE_OK))
        else:
            run("echo \"===>Rabbitmq {}\"".format(MESSAGE_FAILED)) 

    elif PLATFORM=="Darwin":
        if run("command -v rabbitmqctl",hide= not verbose, warn=True):
            run("echo '===>RabbitMq {}'".format(MESSAGE_ALREADY_INSTALLED))
        else:
            if (run("brew install rabbitmq").ok):
                run("echo \"===>Rabbitmq {}\"".format(MESSAGE_OK))
            else:
                run("echo \"===>Rabbitmq {}\"".format(MESSAGE_FAILED))
        run("sudo rabbitmqctl add_user lookit-admin admin", warn=True, hide=not verbose)
        run("sudo rabbitmqctl set_user_tags lookit-admin administrator", warn=True, hide=not verbose)
        run("sudo rabbitmqctl set_permissions -p / lookit-admin '.*' '.*' '.*'", warn=True, hide=not verbose)
        run("sudo brew services stop rabbitmq-server.service", warn=True, hide=not verbose)
        run("sudo brew services start rabbitmq-server.service", warn=True, hide=not verbose)
        run("sudo brew services enable rabbitmq-server.service", warn=True, hide=not verbose)
        run("sudo rabbitmq-plugins enable rabbitmq_management", warn=True, hide=not verbose)
        run("sudo chown -R rabbitmq:rabbitmq /var/lib/rabbitmq/", warn=True, hide=not verbose)
        run("sudo rabbitmqadmin declare queue  --vhost=/ name=email", warn=True, hide=not verbose)
        run("sudo rabbitmqadmin declare queue  --vhost=/ name=builds", warn=True, hide=not verbose)
        run("sudo rabbitmqadmin list queues", warn=True, hide=not verbose)
    else:
        run("echo {}".format(MESSAGE_WRONG_PLATFORM))
   
@task 
def postgresql(c, verbose=False):
    """

    Installs postgresql, create the database of the API and create the tables necessary
    usage: invoke postgresql or invoke postgresql --verbose

    """
    run("echo '***INSTALLING Postgresql***'")
    if PLATFORM=="Linux":
        if run("command -v psql", warn=True, hide= not verbose):
            run("echo '===>Postgresql {}'".format(MESSAGE_ALREADY_INSTALLED))

        else:
            if (run("apt-get update && apt-get install postgresql", warn=True, hide= not verbose).ok):
                run("echo \"===>Postgresql {}\"".format(MESSAGE_OK))
            else:
                run("echo \"===>Postgres {}\"".format(MESSAGE_FAILED))
        if (run("service postgresql start", warn=True, hide= not verbose).ok):
            run('echo "=====>Postgresql successfully started!"')
        else:
            run('echo "=====>Postgresql failed to start!"')
        res=run("createdb lookit", warn=True, hide=not verbose)
        if res.exited==0:
            run( 'echo "Database Successfully created!"')
        else:
            run('echo "Database already existed"')
        if (run("python manage.py migrate", warn=True, hide= not verbose).ok):
            run("echo \"====> Migrated Django models to lookit db\"")
        else:
            run("echo \"====> Migration failed\"") 
    elif PLATFORM=="Darwin":
        if run("command -v psql", warn=True, hide=not verbose):
            run("echo '===>Postgresql {}'".format(MESSAGE_ALREADY_INSTALLED))
        else:
            if (run("brew install postgresql", warn=True, hide= not verbose).ok):
                run("echo \"===>Postgresql {}\"".format(MESSAGE_OK))
            else:
                run("echo \"===>Postgresql {}\"".format(MESSAGE_FAILED))
        
        if (run("brew services start postgresql", warn=True, hide= not verbose).ok):
            run('echo "=====>Postgresql successfully started!"')
        else:
            run('echo "=====>Postgresql failed to start!"')
        res=run("createdb lookit", warn=True, hide=not verbose)
        if res.exited==0:
            run('echo "=====>Database \"lookit\" Successfully created!"')
        else:
            run('echo "=====>Database \"lookit\" already existed"')

        if (run("python manage.py migrate", warn=True, hide= not verbose).ok):
            run("echo \"====>Migrated Django models to lookit db\"")
        else:
            run("echo \"====>Migration failed\"")
    else:
        run("echo {}".format(MESSAGE_WRONG_PLATFORM))
    
@task
def ssl_certificate(c, verbose=False):
    """

    Setup local https development env
    usage: invoke ssl-certificate or invoke ssl-certificate --verbose

    """
    run("echo '***Setting HTTPS for local development***'")
    if PLATFORM=="Linux":
        if (run("command -v mkcert", warn=True, hide=not verbose).ok):
            run("echo \"===>mkcert {}\"".format(MESSAGE_ALREADY_INSTALLED))
        else:
            if (run("brew install mkcert",warn=True, hide=not verbose).ok):
                run("apt-get update && apt install libnss3-tools", warn=True, hide=not verbose)
                run("mkcert -install", warn=True, hide=not verbose)
                run("echo \"===>mkcert {}\"".format(MESSAGE_OK))
            else:
                run("echo \"===>mkcert {}\"".format(MESSAGE_FAILED))
        run("mkdir certs", warn=True, hide=not verbose)
        if (run("cd certs && mkcert local_lookit.mit.edu", warn=True, hide=not verbose).ok):
            run("echo \"Certificates successfully created at {}/certs\"".format(BASE_DIR))
        else:
            run("echo \"Certificates {}\"".format(MESSAGE_FAILED))
    elif PLATFORM=="Darwin":
        if (run("command -v mkcert", warn=True, hide=not verbose).ok):
            run("echo \"===> mkcert {}\"".format(MESSAGE_ALREADY_INSTALLED))
        else:
            if (run("brew install mkcert",warn=True, hide=not verbose).ok):
                run("mkcert -install", warn=True, hide=not verbose)
                run("echo \"===>mkcert {}\"".format(MESSAGE_OK))
            else:
                run("echo \"===>mkcert {}\"".format(MESSAGE_FAILED))
        run("mkdir certs", warn=True, hide=not verbose)
        if (run("cd certs && mkcert local_lookit.mit.edu", warn=True, hide=not verbose).ok):
            run("echo \"=====>Certificates successfully created at {}/certs\"".format(os.getcwd()))
        else:
            run("echo \"=====>Certificates {}\"".format(MESSAGE_FAILED))
    else:
        run("echo {}".format(MESSAGE_WRONG_PLATFORM))

@task
def ngrok(c, verbose=False):
    """

    Installing ngrok for Linux and Darwin platforms
    usage: invoke ngrok or invoke ngrok --version 

    """
    run("echo '***Installing Ngrok***'")

    if PLATFORM=="Linux":
        if run("command -v ngrok", warn=True, hide=not verbose):
            run("echo \"===>Ngrok {}\"".format(MESSAGE_ALREADY_INSTALLED)) 
        else:
            run("cd / && mkdir downloads", warn=True, hide=not verbose)
            run("cd / && cd downloads && wget -cO ngrok.zip https://bin.equinox.io/c/4VmDzA7iaHb/ngrok-stable-linux-amd64.zip", warn=True, hide=not verbose)
            run("cd / && cd downloads && unzip ngrok", warn=True, hide=not verbose)
            run("ln -s /downloads/ngrok /usr/bin/ngrok", warn=True, hide=not verbose)

            if run("ngrok", warn=True, hide= not verbose):
                run("echo \"===>Ngrok {}\"".format(MESSAGE_OK))
            else:
                run("echo \"===>Ngrok {}\"".format(MESSAGE_FAILED))  
                
    elif PLATFORM=="Darwin":
        if (run('command -v ngrok', hide=not verbose,warn=True).ok):
            run("echo \"===>Ngrok {}\"".format(MESSAGE_OK))
        else:
            run("echo \"===>Ngrok {}\"".format(MESSAGE_FAILED))  

    else:
        run("echo {}".format(MESSAGE_WRONG_PLATFORM))

@task 
def docker(c, verbose=False):
    """

    Installing docker for both Ubuntu(Linux) and Darwin(MacOS/OSX)
    usage: invoke docker

    """

    if PLATFORM=="Linux":
        # Install Docker
        #Install key dependencies first
        if (run("command -v docker", hide= not verbose, warn=True).ok):
            run("echo \"===>Docker {}\"".format(MESSAGE_ALREADY_INSTALLED))
        else:
            run("apt-get install apt-transport-https ca-certificates curl gnupg2 software-properties-common",hide= not verbose, warn=True )
            res=run("cat /etc/issue", hide= not verbose, warn=True)
            if "Debian" in str(res):
                run("curl -fsSL https://download.docker.com/linux/debian/gpg | apt-key add -", hide= not verbose, warn=True )
                run("apt-key fingerprint 0EBFCD88", hide= not verbose, warn=True)
                run('add-apt-repository \
                    "deb [arch=amd64] https://download.docker.com/linux/debian \
                    $(lsb_release -cs) \
                    stable"', hide= not verbose, warn=True)
                run("apt install docker-ce docker-ce-cli containerd.io", hide= not verbose, warn=True)

                if (run("docker", hide= not verbose, warn=True).ok):
                    run("echo \"===>Docker {}\"".format(MESSAGE_OK))
                else:
                    run("echo \"===>Docker {}\"".format(MESSAGE_FAILED))
            elif "Ubuntu" in str(res):
                run("curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -", hide= not verbose, warn=True)
                run("apt-key fingerprint 0EBFCD88", hide= not verbose, warn=True)
                run('add-apt-repository \
                    "deb [arch=amd64] https://download.docker.com/linux/debian \
                    $(lsb_release -cs) \
                    stable"', hide= not verbose, warn=True)
                run("apt install docker-ce", hide= not verbose, warn=True)

                if (run("docker", hide= not verbose, warn=True).ok):
                    run("echo \"===>Docker {}\"".format(MESSAGE_OK))
                else:
                    run("echo \"===>Docker {}\"".format(MESSAGE_FAILED))
            else:
                run("echo {}".format(MESSAGE_WRONG_PLATFORM))

    elif PLATFORM=="Darwin":
        if (run('command -v docker', hide=not verbose,warn=True).ok):
            run("echo \"===>Docker {}\"".format(MESSAGE_ALREADY_INSTALLED)) 
        else:
            if(run("brew cask install docker", hide=not verbose, warn=True).ok):
                run("echo \"===>Docker {}\"".format(MESSAGE_OK))
            else:
                run("echo \"===>Docker {}\"".format(MESSAGE_FAILED))
        run("open /Applications/Docker.app")

    else:
        run("echo {}".format(MESSAGE_WRONG_PLATFORM))
     
@task 
def server(c):
    """

    serves django application server
    usage:invoke server

    """

    if os.listdir(PATH_TO_CERTS):
        run(SERVE_HTTPS_SERVER, hide=False)
    else:
        run(SERVE_HTTP_SERVER, hide=False)
    
@task
def ngrok_service(c):
    """

    Serves ngrok
    usage: invoke ngrok_service

    """
    run(SERVE_NGROK)

@task
def celery_service(c):
    """

    serves celery
    usage: invoke celery 

    """
    run(SERVE_CELERY)

@task
def serve(c):
    """

    Serves the django application, starts celery, and ngrok
    usage: invoke serve

    """

    if(os.listdir(PATH_TO_CERTS)):
        run(SERVE_HTTPS_SERVER + "&" + SERVE_NGROK + "&" + SERVE_CELERY)
    else:
        run(SERVE_HTTP_SERVER+"&" + SERVE_NGROK + "&" + SERVE_CELERY)

@task(system_setup, install_dependencies,pygraphviz, rabbitmq, postgresql, ssl_certificate, ngrok, docker)
def setup(c):
    pass

    