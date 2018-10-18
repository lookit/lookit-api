Installation: ember-lookit-frameplayer (Ember app)
==================================================

This is a small Ember application that allows both researchers to
preview an experiment and users to participate in an experiment. This is
meant to be used in conjunction with the `Lookit API Django
project <https://github.com/lookit/lookit-api>`__, which contains the
Experimenter and Lookit applications. The Django application will proxy
to these Ember routes for previewing/participating in an experiment. The
Ember routes will fetch the appropriate models and then pass them to the
exp-player component in the subrepo
`exp-addons <https://github.com/lookit/exp-addons>`__.

In order to run the frame player as it works on Lookit, you will need to
additionally install the Django app ``lookit-api`` and then follow the
local frame development instructions to make sure it communicates with
the Ember app. This way, for instance, an experiment frame will be able
to look up previous sessions a user has completed and use those for
longitudinal designs.

   Note: These instructions are for Mac OS. Installing on another OS?
   Please consider documenting the exact steps you take and submitting a
   PR to the lookit-api repo to update the documentation!

Prerequisites
-------------

You will need the following things properly installed on your computer.

-  `Git <http://git-scm.com/>`__
-  `Node.js <http://nodejs.org/>`__ (with NPM)
-  `Bower <http://bower.io/>`__
-  `Ember CLI <http://ember-cli.com/>`__
-  `PhantomJS <http://phantomjs.org/>`__

Get a local copy of the ember-lookit-frameplayer repo
-----------------------------------------------------

-  ``$ git clone https://github.com/lookit/ember-lookit-frameplayer.git``
-  ``$ cd lookit-api``
-  ``$ sh up.sh`` *Installs dependencies and run migrations*
-  ``$ python manage.py createsuperuser`` *Creates superuser locally
   (has all user permissions)*
-  ``$ touch project/settings/local.py`` Create a local settings file.
-  Add DEBUG = True to ``local.py`` and save. This is for local
   development only.
-  ``$ python manage.py runserver`` *Starts up server*

Installation
------------

Before beginning, you will need to install Yarn, a package manager (like
npm).

.. code:: bash

    git clone https://github.com/CenterForOpenScience/ember-lookit-frameplayer.git
    cd ember-lookit-frameplayer
    git submodule init
    git submodule update
    yarn install --pure-lockfile
    bower install

    cd lib/exp-player
    yarn install --pure-lockfile
    bower install

Create or open a file named ‘.env’ in the root of the
ember-lookit-frameplayer directory, and add the following entries to use
the Pipe WebRTC-based recorder: ``PIPE_ACCOUNT_HASH`` (reference to
account to send video to) and ``PIPE_ENVIRONMENT`` (which environment,
e.g. development, staging, or production). These are available upon
request if you need to use the actual Lookit environments. (If you are
doing a very large amount of local testing, we may ask that you set up
your own Pipe account.)

Running / Development
---------------------

-  ``ember serve``
-  Visit your app at http://localhost:4200.

If you are making changes to frame definitions in ``exp-addons``, you
will want to use ``yarn link`` as described in the ``exp-addons`` README
so your updated local code is used. If you change any dependencies,
should also use yarn to update the lockfile and commit it.

Code Generators
~~~~~~~~~~~~~~~

Make use of the many generators for code, try ``ember help generate``
for more details

Running Tests
~~~~~~~~~~~~~

-  ``ember test``
-  ``ember test --server``

Building
~~~~~~~~

-  ``ember build`` (development)
-  ``ember build --environment production`` (production)

Writing documentation of frames
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Documentation of individual exp-player components is automatically
generated using YUIDoc:

-  cd exp-player
-  yarn run docs

At the moment, this is a manual process: whatever files are in the top
level /docs/ folder of the master branch will be served via GitHub
pages. New documentation releases will require manually making a new
“release” to update the master branch, which can be done on request.
