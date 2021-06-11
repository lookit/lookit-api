# Contributing to Lookit

We'd love for you to contribute to our source code and make Lookit even better than it is today!
Here are some guidelines we'd like you to follow:

* [Code of Conduct](#code-of-conduct)
* [Requests](#requests)
* [Developer Guidelines](#developer-guidelines)
    * [Local Development](#local-development)
    * [Outside Contributor Guidelines](#outside-contributors)
        * [Forking](#forking)
        * [Localization](#localization)
    * [Core Contributor Guidelines](#core-contributors)
        * [Releases](#releases)
* [Contact Us](#contact)

## Code of Conduct

As contributors and maintainers of the Lookit project, we pledge to respect everyone who contributes by posting 
issues, updating documentation, submitting pull requests, and providing feedback in comments.

Communication through any of Lookit's channels (Slack and Github) must be constructive and never resort 
to personal attacks, trolling, public or private harassment, insults, or other unprofessional conduct.

We promise to extend courtesy and respect to everyone involved in this project regardless of gender, 
gender identity, sexual orientation, disability, age, race, ethnicity, religion, or level of experience. 
We expect anyone contributing to the Lookit project to do the same.

If any member of the community violates this code of conduct, the maintainers of the Lookit project may 
take action, removing issues, comments, and PRs or blocking accounts as deemed appropriate.

## <a name="requests"></a> Questions, Bugs, and Features

### Got a Question or Problem?
For general questions about the platform, you should head over to our [Slack workspace][slack] - if you haven't joined
already, you can find out how to do so [here][slack-docs].

### Found an Issue or Bug?
If you find a bug in the source code, you can help us by [submitting an issue][bug-report]. Please follow the included 
template to ensure that we have as much relevant information as possible.

Even better, you can submit a Pull Request (see [forking](#forking) section) with a fix.

### Missing a Feature?
We have a process for getting new features into the roadmap. This process helps properly prioritize platform development
according to Lookit's vision and mission.

#### Phase 1: Definition and Discussion
If you're a *researcher*, you'll need to start here.
1. Check the [Feature Proposal Spreadsheet][feature-proposal] to see if something similar is already being discussed.
2. If you see your idea there, follow the link to the slack channel and join the discussion. 
3. If it's not there, go ahead and start a new discussion in the #feature-proposal channel in [Slack][slack].

Once the feature has been discussed and cleared for prioritization, the feature will move into the next phase.

#### Phase 2: Scoping and Implementation
If you're a *core contributor*, you can start here.
1. **Scoping** (Optional): Create a [Scoping][scoping-request] issue. You'll only need the narrative (justification) at 
   this point.
2. **Implementation**: Either convert your scoping issue to a Feature Request, or [make a new one][feature-request]
   with all the correct fields filled out. You should have implementation details and acceptance criteria from the
   prior scoping ticket.

## Developer Guidelines
We have several guidelines for contributing code, extending to both core and outside contributors. These rules help us 
streamline work and provide the best possible collaboration experience, so please follow them!

If you have a new idea or want to request an improvement to the current process, you can file a 
[developer issue here][developer-request].

## Local Development

### Setup
Follow the instructions laid out [here][lookit-setup-instructions].

### <a name="organization"></a> What's the high-level overview?
Conceptually speaking, "Lookit-API" is a misnomer. Lookit is *not actually one service*, it is three (3) processes that
act as (5) conceptually distinct systems/applications:
1. The Django web app/http API process, providing:
    - A web UI for researchers to design and manage experiments
    - A web UI for participants to discover experiments
    - An HTTP/JSON API consumed by built experiments
2. An offline Celery process (connected by message queue) that builds and deploys experiments (web archives)
3. An offline Celery process (connected by message queue) that sends emails and does some rudimentary cleanup

The processes listed above also has three major *in-network* service dependencies:
1. **Postgres** for relational data storage, used by all processes
2. **RabbitMQ** as a message queue to communicate between process #1 and the two offline task runner processes
3. **Docker** to provide a container environment for building experiments (used by process #2)

And as if that wasn't enough, three major *out of network* service dependencies:
1. **Amazon S3** for storing video
2. **Google Cloud Storage** for storing experiment web archives and other static files
3. [**Pipe**][pipe] to relay video streamed from experiments to Amazon S3

For the kicker, if you want to debug the video renaming webhook, you'll need to install and run `ngrok`, and [add
a new webhook target][pipe-add-webhook] in the Pipe web UI with the freshly generated URL. _Yikes_. Thankfully, you
won't need to do this that often. Still - depending on how much you want to set up and debug locally, you could 
potentially be running anywhere from 2-7 processes at once to support Lookit development.

### <a name="debugging"></a> OK this all sounds great - where do I point my debugger?

If you want to debug one of the processes, you can always use PDB or the new `breakpoint` builtin. Alternatively, if
you're using an IDE like PyCharm, you can set up handy debug profiles with neat conveniences like isolated environment
variables and push-button functionality.

If you just want to hack on the API or UIs, you only need to boot up Postgres and the web server (process #1):
```bash
# Confirm postgres is running in docker
poetry run invoke postgresql
poetry run ./manage.py runserver           
```
Note that this bare-minimum setup __won't__ allow you to kick off any offline tasks (i.e., sending emails and building
studies) from the UI. If you want to test offline jobs, you'll need to boot up RabbitMQ (needed for all offline tasks) 
and Docker (needed for experiment builds only); finally starting the celery worker itself to consume messages from the
message queue:
```bash
# Confirm that rabbitmq is running in docker
poetry run invoke celery-service
```

Serving with HTTPS will allow you to do two additional things:
1. Process videos with the Pipe webhook
2. Communicate with your locally served instance of ember-lookit-frameplayer (if you have configured it to serve in 
HTTPS - not default, but recommended).

To serve with HTTPS:
```bash
poetry run invoke server --https
```

### Outside Contributors
If you are _not_ on the Lookit core team, this section is for you!

#### Forking
While core contributors will work directly on the original repo, outside contributors will need to maintain their own 
fork of Lookit while working on new features for (or fixing bugs for) the platform. We recommend reading this handy
[guide on forking][forking-workflow-walkthrough] if you are not familiar with this workflow. GitHub's own [`hub` 
utility][hub-oss-contrib] will make your life a lot easier in this regard by abstracting over some of the steps; you 
can find the installation instructions [here][hub-install] (or, if you like to live on the cutting-edge, try out 
GitHub's [shiny new CLI][github-cli]).

One additional note: when you submit a PR, you'll want to target the `develop` branch.  It's the default branch and shouldn't cause you any further thought.

#### Localization
At the moment, we have very rudimentary i18n and l10n processes - nothing like the sophisticated pipeline you might see
at a big company. You'll first want to read [Django's documentation][django-i18n] on i18n and l10n to understand how 
Django apps deliver translated strings. In summary:

1. **Developers** will designate new strings for internationalization using `gettext` and `gettext_lazy` in code and
   `{% translate %}` tags in templates (currently, this is generally limited to _participant-facing_ strings). As their
   forks and/or feature branches are merged back into `develop`, these strings will become available for compilation
   into message files.
2. **Translators** will merge these upstream changes from `origin/develop` back into their respective forks.
    * `git fetch upstream && git merge upstream/develop` should be run frequently to surface new strings.
3. **Translators** will then run `./manage.py makemessages` to generate any necessary message snippets and their 
   containing `.po` files.
4. **Translators** will then fill in the requisite translations generated from the previous command, before committing
   and creating a PR.

As it's a system based on trust, translators will be notified ahead of time when the core team is about to cut a new
release. This way, they can get in any last-minute translations.


#### Releases
We deploy Lookit services on Google Kubernetes Engine; the CI/CD pipeline is defined over in the [Lookit Orchestrator 
repo][lookit-orchestrator]. A GitHub integration with GCP allows us to trigger builds upon commit to either the `master`
or `develop` branch; deploying to staging and production (respectively).

## Contact

Rico Rodriguez, Lead Software Engineer ([rrodrigu@mit.edu](mailto:rrodrigu@mit.edu))

Kim Scott, Lookit Project Head ([kimscott@mit.edu](mailto:kimscott@mit.edu))


[lookit-orchestrator]: https://github.com/lookit/lookit-orchestrator
[feature-proposal]: https://docs.google.com/spreadsheets/d/14JMz8bGFCfHVQ-Gfuvux4EjIj6LQlCMRlNewzidMdYs/edit?usp=sharing
[github]: https://github.com/lookit/lookit-api
[lookit-setup-instructions]: https://lookit.readthedocs.io/en/develop/install-django-project.html
[github-cli]: https://cli.github.com/
[bug-report]: https://github.com/lookit/lookit-api/issues/new?assignees=&labels=&template=bug_report.md&title=
[feature-request]: https://github.com/lookit/lookit-api/issues/new?assignees=&labels=&template=feature_request.md&title=
[scoping-request]: https://github.com/lookit/lookit-api/issues/new?assignees=&labels=Scoping&template=scoping.md&title=
[developer-request]: https://github.com/lookit/lookit-api/issues/new?assignees=&labels=Developer&template=developer-issue.md&title=
[slack]: https://lookit-mit.slack.com
[slack-docs]: https://lookit.readthedocs.io/en/develop/researchers-start-here.html#a-join-the-slack-workspace
[git-flow]: https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow
[git-flow-cheatsheet]: http://danielkummer.github.io/git-flow-cheatsheet/
[git-flow-avh]: https://github.com/petervanderdoes/gitflow-avh
[merge-methods-github]: https://docs.github.com/en/github/administering-a-repository/about-merge-methods-on-github
[forking-workflow-walkthrough]: https://gist.github.com/Chaser324/ce0505fbed06b947d962
[hub-oss-contrib]: https://hub.github.com/#contributor
[hub-install]: https://github.com/github/hub#installation
[git-flow-vanilla-equivalent]: https://gist.github.com/JamesMGreene/cdd0ac49f90c987e45ac
[pipe]: https://addpipe.com/
[pipe-add-webhook]: https://addpipe.com/webhooks
[django-i18n]: https://docs.djangoproject.com/en/dev/topics/i18n/

