==================================
Lookit Guidelines for Contributors
==================================

Interested in helping write the code behind the Lookit platform?  Thanks for supporting open source science!  The Lookit project has three different code repos.  The content of this page applies to all of the repos: `lookit-api` (Lookit site), `ember-lookit-frameplayer` (system for displaying experiments), and `exp-addons` (specific frames).

This page describes the process any would-be contributor should plan to use.  We have included some beginner-friendly details in case you are new to open source projects.

At a high level, you should plan to make feature-specific branches off of the `develop` branch of a local copy of the code running on your own machine.  This will keep the codebase as clean as possible.  Before submitting a PR, merge in the most recent changes from the `develop` branch.  

System dependencies
~~~~~~~~~~~~~~~~~~~

Runs on Python 3.6 w/ dependencies listed in `requirements/defaults.txt`

To run this project locally, fork and clone the repo, download the project dependencies, and set up a superuser on your local machine via these steps:

Fork and clone the repo
~~~~~~~~~~~~~~~~~~~~~~~

Fork the project on GitHub and git clone your fork, e.g.:

SSH::

    git clone <username>@github.com:<username>/<reponame>.git
    
HTTPS::

    git clone https://github.com/<username>/<reponame>.git

Start a `virtualenv`
~~~~~~~~~~~~~~~~~~~~

Make sure to start a virtual environment so that you have the expected project configuration.

You may want to configure a global .gitignore on your machine and include your virtualenv(s) along with any files specific to your system.  A sample global .gitignore is available here https://gist.github.com/octocat/9257657 -- you can tell git to globally ignore a .gitignore file via::

    git config --global core.excludesfile ~/path/to/your/.gitignore_global

Install dependencies
~~~~~~~~~~~~~~~~~~~~

Depending on whether you are contributing to `lookit-api`, `ember-lookit-frameplayer` or `exp-addons`, you will have different dependencies.  Please refer to the repo-specific installation instructions.

Lookit API: Add your own feature and submit a Pull Request
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The following instructions describe how to submit a pull request to the `lookit-api` codebase.  

Keep your commit history clean and merge process simple by following these steps before starting on any new feature.

One time only, add the repo as a remote to your fork, e.g., if you are contributing to `lookit-api` you would run a command like this::

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

Then resolve all merge conflicts and update dependencies like this::

    pip install -r requirements/defaults.txt
    python manage.py migrate
    python manage.py test

Next, push all your local changes to your own fork. You should push your code (making sure to replace `feature/my-validation-feature` with whatever your branch is actually called)::

    git push --set-upstream origin feature/my-validation-feature

When your branch is ready (e.g., has comments and tests), submit a Pull Request! To do this, go to GitHub, navigate to your fork (in this case the github extension should be /your-username/lookit-api),
then click `new pull request`.   Change the base to `develop` and the compare to `feature/my-validation-feature`. Finally, click `Create pull request`



IMPORTANT: WHEN YOUR PR IS ACCEPTED, stop using your branch right away (or delete it altogether).  New features (or enhanced versions of your existing feature) should be created on brand new branches (after pulling in all the fresh changes from `develop`).

Editing the Lookit API Documentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Lookit API project documentation lives in the following directory::

    /lookit-api/docs/source

The file `index.rst` contains the table of contents (look for `toctree`).  

If you'd like to use Sphinx to build the documentation locally, activate another virtual environment and install the requirements for Sphinx.

From inside the `lookit-api` folder::

    (denv) /lookit-api/$ pip install -r lookit-api/docs/requirements.txt
    (denv) /lookit-api/$ cd docs
    (denv) /lookit-api/docs$ make clean singlehtml

Navigate to the index.html file from your favorite browser to inspect the docs.
