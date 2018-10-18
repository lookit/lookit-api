==================================
Guidelines for Contributors
==================================

Interested in helping write the code behind the Lookit platform?  Thanks for supporting open source science!  The Lookit project has three different code repos.  The content of this page applies to all of the repos: ``lookit-api`` (Lookit site), ``ember-lookit-frameplayer`` (system for displaying experiments), and ``exp-addons`` (specific frames, subrepo of ember-lookit-frameplayer).

This page describes the process any would-be contributor should plan to use.  We have included some beginner-friendly details in case you are new to open source projects.

At a high level, you should plan to make feature-specific branches off of the ``develop`` branch of a local copy of the code running on your own machine.  This will keep the codebase as clean as possible.  Before submitting a PR, merge in the most recent changes from the ``develop`` branch.  

Getting started
~~~~~~~~~~~~~~~~~~~

First create your own fork of lookit-api and/or ember-lookit-frameplayer. Then follow the directions for installation of lookit-api or ember-lookit-frameplayer. If you only want to change something about the Lookit site, without touching experiment functionality (for instance, to add a question to the demographic survey or change how studies are sorted), you will only need to run `lookit-api` and can follow the Django project installation steps. If you want to develop experiment frames or change how the experiment player works, you will need to follow the steps for local frame development, installing *both* `lookit-api` and `ember-lookit-frameplayer` and telling them how to talk to each other. Your changes, however, will likely be limited to the `exp-addons` repo or possibly `ember-lookit-frameplayer`.

Ignoring some files
~~~~~~~~~~~~~~~~~~~~

You may want to configure a global .gitignore on your machine and include your virtualenv(s) along with any files specific to your system.  A sample global .gitignore is available `here <https://gist.github.com/octocat/9257657>`_ -- you can tell git to globally ignore files specified in a .gitignore file via::

    git config --global core.excludesfile ~/path/to/your/.gitignore_global


Add your own feature and submit a Pull Request
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The following instructions describe how to submit a pull request to the `lookit-api`, `ember-lookit-frameplayer`, or `exp-addons` repos.  

Keep your commit history clean and merge process simple by following these steps before starting on any new feature.

One time only, add the repo as a remote to your fork, e.g., if you are contributing to `lookit-api` you would run a command like this:

SSH::

    git remote add upstream git@github.com:lookit/lookit-api.git

HTTPS::

    git remote add upstream https://github.com/lookit/lookit-api.git

Anytime a PR is merged or changes are pushed (or you're starting this process for the first time), you should run::

    git checkout develop
    git pull upstream develop

in order to make sure you are working with an up-to-date copy of the `develop` branch.

Once you have the most recent `develop` code, pick an issue (or create a new one) which your new feature will address and create a new branch off of `develop`.  Note: our project convention is to prepend `feature/` or `hotfix/` to the feature or issue name for a richer annotation of the commit history.  

If you want to create a new validation feature, for example, you might name it like this::

    git checkout -b feature/my-validation-feature

Now you can run `git branch` and should see an output like this::

    $ git branch
      develop
      master
    * feature/my-validation-feature

Proceed with writing code.  Commit frequently!  Focus on writing very clear, concise commit statements and plentiful comments.  If you have poor comments or zero tests, your PR will not be merged.

If you are aware of changes in the branch you forked from, rebase your branch from that changing branch (in our case that is `develop`) by running::

    git rebase develop
    
and then resolving all merge conflicts.

On `lookit-api`, you should then update dependencies like this::

    pip install -r requirements/defaults.txt
    python manage.py migrate
    python manage.py test
    
On `ember-lookit-frameplayer` and `exp-addons`, you should update dependencies using the package manager yarn as described in the `exp-addons` README file.

Next, push all your local changes to your own fork. You should push your code (making sure to replace `feature/my-validation-feature` with whatever your branch is actually called)::

    git push --set-upstream origin feature/my-validation-feature

When your branch is ready (e.g., has comments and tests), submit a Pull Request! To do this, go to GitHub, navigate to your fork (in this case the github extension should be /your-username/lookit-api), 
then click `new pull request`.   Change the base to `develop` and the compare to `feature/my-validation-feature`. Finally, click `Create pull request` and describe the changes you have made. Your pull request will be reviewed by Lookit staff; changes may be requested before changes are merged into the develop branch. To allow Lookit staff to add changes directly to your feature branch, follow the directions `here <https://help.github.com/articles/allowing-changes-to-a-pull-request-branch-created-from-a-fork/>`_.

IMPORTANT: WHEN YOUR PR IS ACCEPTED, stop using your branch right away (or delete it altogether).  New features (or enhanced versions of your existing feature) should be created on brand new branches (after pulling in all the fresh changes from ``develop``).


Editing the Lookit documentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Documentation for use of the Lookit platform (what you're reading now!), including *both* the Django site lookit-api and the Ember application ember-lookit-frameplayer used for the actual studies, lives in the lookit-api repo under ``/lookit-api/docs/source``.

The file ``index.rst`` contains the table of contents (look for ``toctree``). Documentation is written using `ReStructured Text (RST) markup <http://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html>`_. It is also possible to add Markdown (.md) files and have them included in the documentation, but for consistency we are trying to keep all documentation in .rst format. If you are more familiar with Markdown, you can convert between formats using `Pandoc <https://pandoc.org/>`_, e.g.::

    pandoc -o outputfile.rst inputfile.md

If you are making substantial changes, you will want to take a look at how those changes look locally by using Sphinx to build your own local copy of the documentation. To do this, first create another virtual environment and install the requirements for Sphinx there::

    /lookit-api $ virtualenv -p python3 denv
    /lookit-api $ source denv/bin/activate
    (denv) /lookit-api $ pip install -r docs/requirements.txt
    
You can then build the docs from within the ``docs`` directory::

    (denv) /lookit-api/docs $ make html

Navigate to ``docs/build/html/index.html`` from your favorite web browser to inspect the docs.

If you are *only* editing the documentation, please submit a PR to the ``lookit-api/current-docs`` branch rather than ``lookit-api/develop``. This allows us to do more casual and faster review of your changes, as merging them in will update the docs automatically served by
ReadTheDocs at https://lookit.readthedocs.io without triggering deployment of the staging server. (TODO: Eventually, yes, the docs can be in a separate repo or subrepo.)