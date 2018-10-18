Installation: lookit-api (Django project)
=========================================

This is the codebase for Experimenter and Lookit, excluding the actual
studies themselves. Any functionality you see as a researcher or a
participant (e.g., signing up, adding a child, editing or deploying a
study, downloading data) is part of the ``lookit-api`` repo. The
Experimenter platform is the part of this project for designing and
administering research studies, meant for researchers. The Lookit
platform is participant-facing, where users can signup and take part in
studies. This project is built using Django and PostgreSQL. (The studies
themselves use Ember.js; see Ember portion of codebase,
`ember-lookit-frameplayer <https://github.com/CenterForOpenScience/ember-lookit-frameplayer>`__.),
It was initially developed by the `Center for Open
Science <https://cos.io/>`__.

If you install only the ``lookit-api`` project locally, you will be able
to edit any functionality that does not require actual study
participation. For instance, you could contribute an improvement to how
studies are displayed to participants or create a new CSV format for
downloading data as a researcher.

   Note: These instructions are for Mac OS. Installing on another OS?
   Please consider documenting the exact steps you take and submitting a
   PR to the lookit-api repo to update the documentation!

Prerequisites
~~~~~~~~~~~~~

-  Make sure you have python 3.6: ``$ python --version`` will check the
   version of your current default python installation. If you don’t
   have this, install from https://www.python.org/.
-  Make sure you have ``pip``. ``$ pip --version``
-  Create a virtual environment using python 3.6

   -  One way to do this:
   -  ``$  pip install virtualenv``
   -  ``$ virtualenv -p python3 envname``, *where ``envname`` is the
      name of your virtual environment.*
   -  ``$ source envname/bin/activate`` *Activates your virtual
      environment*

-  Install postgres

   -  make sure you have brew ``$ brew``
   -  ``$ brew install postgresql``
   -  ``$ brew services start postgres`` *Starts up postgres*
   -  ``$ createdb lookit`` *Creates lookit database*

Installation
~~~~~~~~~~~~

-  ``$ git clone https://github.com/lookit/lookit-api.git``
-  ``$ cd lookit-api``
-  ``$ sh up.sh`` *Installs dependencies and run migrations*
-  ``$ python manage.py createsuperuser`` *Creates superuser locally
   (has all user permissions)*
-  ``$ touch project/settings/local.py`` Create a local settings file.
-  Add DEBUG = True to ``local.py`` and save. This is for local
   development only.
-  ``$ python manage.py runserver`` *Starts up server*

Authentication
~~~~~~~~~~~~~~

OAuth authentication to OSF accounts, used for access to Experimenter,
currently does not work when running locally. You can create a local
participant account and log in using that to view participant-facing
functionality, or log in as your superuser at localhost:8000/admin and
then navigate to Experimenter. As your superuser, you can also use the
Admin app to edit other local users - e.g., to make users researchers vs
participants, in particular organizations, etc.

Handling video
~~~~~~~~~~~~~~

This project includes an incoming webhook handler for an event generated
by the Pipe video recording service when video is transferred to our S3
storage. This requires a webhook key for authentication. It can be
generated via our Pipe account and, for local testing, stored in
project/settings/local.py as ``PIPE_WEBHOOK_KEY``. However, Pipe will
continue to use the handler on the production/staging site unless you
edit the settings to send it somewhere else (e.g., using ngrok to send
to localhost for testing).

Common Issues
~~~~~~~~~~~~~

During the installation phase, when running ``sh up.sh``, you may see
the following:

::

   psql: FATAL:  role "postgres" does not exist

To fix, run something like the following from your home directory:

::

   $../../../usr/local/Cellar/postgresql/9.6.3/bin/createuser -s postgres

If your version of postgres is different than 9.6.3, replace with the
correct version above. Running this command should be a one-time thing.

.. raw:: html

   <hr>

You might also have issues with the installation of ``pygraphviz``, with
errors like

::

   running install
   Trying pkg-config
   Package libcgraph was not found in the pkg-config search path.
   Perhaps you should add the directory containing `libcgraph.pc'
   to the PKG_CONFIG_PATH environment variable
   No package 'libcgraph' found

or

::

   pygraphviz/graphviz_wrap.c:2954:10: fatal error: 'graphviz/cgraph.h' file not found
   #include "graphviz/cgraph.h"
          ^
   1 error generated.
   error: command 'clang' failed with exit status 1

To fix, try running something like:

::

   $ brew install graphviz
   $ pip install --install-option="--include-path=/usr/local/include" --install-option="--library-path=/usr/local/lib" pygraphviz

Then run ``sh up.sh again.``
