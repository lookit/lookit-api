# Contributing to Lookit

We'd love for you to contribute to our source code and make Lookit even better than it is today!
Here are some guidelines we'd like you to follow:

* [Code of Conduct](#code-of-conduct)
* [Requests](#requests)
* [Developer Guidelines](#developer-guidelines)
    * [Local Development](#local-development)
    * [Source Control](#source-control)
    * [Localization](#localization)
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
Do not open issues for general support questions as we want to keep GitHub issues for bug reports
and feature requests. We have an existing process for diagnosing/triaging issues and generating new
feature requests from user input, and it starts with [Slack][slack].

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

### Local Development

#### Setup
Follow the instructions laid out [here][lookit-setup-instructions].

#### <a name="organization"></a> What's the high-level overview?
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

##### <a name="debugging"></a> OK this all sounds great - where do I point my debugger?

If you want to debug one of the processes, you can always use PDB or the new `breakpoint` builtin. Alternatively, if
you're using an IDE like PyCharm, you can set up handy debug profiles with neat conveniences like isolated environment
variables and push-button functionality.

If you just want to hack on the API or UIs, you only need to boot up Postgres and the web server (process #1):
```bash
brew services start postgresql  # Or `service postgresql start` if you're on linux
./manage.py runserver           # Alternatively, `python manage.py runserver`
```

If you you want to run with local HTTPS (allowing webhook processing of videos), you'll need `runserver_plus` installed
(should be in your virtual environment already if you ran `pipenv install --dev`) and a directory with cert files:
```bash
./manage.py runserver_plus --nopin --cert-file ${PATH_TO_YOUR_CERTFILE}
```

If you want to hack on experiment building, you'll need to boot up RabbitMQ and Docker first, and finally the celery 
worker itself:
```bash
open /Applications/Docker.app                                        # If you're on Linux, just `docker`
rabbitmq-server                                                      # You may need `sudo` for this
celery worker --app=project --loglevel=INFO -Q builds,email,cleanup
```

### Source Control

#### Workflow
We use a slightly modified [Git Flow][git-flow] process; as such, we highly recommend that contributors read this 
[Git Flow cheatsheet][git-flow-cheatsheet] to understand what each branch type is used for and how the workflow manages
multiple changes and releases in progress at once. In short: 

- There's a `master` branch and a `develop` branch; `master` reflects production code while `develop` is the staging
  area for new features and bugfixes
- Consequently, `feature` and `bugfix` branches derive from and merge back into `develop`
-  `release` branches are cut from `develop` to bundle features and bugfixes and package them into a release prior to 
   merging back into both `master` and `develop`. 

Taken together as a whole, this process enables development to continue apace in a CI/CD-enabled environment: releases
themselves do not "stop the world" in terms of integrating changes in the development process.

Once you've got the concepts down, it's recommended to either install [gitflow-avh][git-flow-avh] for conveniently 
automated branch management, or use [this cheat sheet][git-flow-vanilla-equivalent] as a reference for equivalent 
vanilla git commands.

There are a few additional practices we adhere to when contributing to Lookit:
1. **Rebase locally before publishing a feature or bugfix branch.** `git rebase -i develop` is your friend. A clean
   local commit history means that we can get away with *never* squashing on remote branches; thus preserving optimal
   behavior for commands like `git rerere` and `git blame`. In fact, commands like `git flow $MYFEATURE pull` already 
   execute `git pull --rebase` under the hood. Please do your part to keep our commit history clean and meaningful!
2. The flip side of #1: **do not *ever* try to rebase or amend commits that are already on a remote branch**. No force
   pushing, _ever_, unless you know _exactly_ what you are doing (if you know what you're doing, you probably don't need
   to force push!).
3. **Prepend Feature and Bugfix branches with the relevant issue ID**. For example, `feature/600-new-cool-thing` or 
   `bugfix/601-horrible-terrible-bug`. It's a small thing, but it helps us better understand what you're working on.
4. **Use Pull Requests after publishing feature/bugfix branches.** We use PRs for code review. Since our `origin` uses
   the default strategy of `--no-ff` merges ([configured][merge-methods-github] in GitHub), you can press the merge
   button or issue a local `git flow ... finish` without *ever* having to force push. 

#### Forking
While core contributors will work directly on the original repo, outside contributors will need to maintain their own 
fork of Lookit while working on new features for (or fixing bugs for) the platform. We recommend reading this handy
[guide on forking][forking-workflow-walkthrough] if you are not familiar with this workflow. GitHub's own [`hub` 
utility][hub-oss-contrib] will make your life a lot easier in this regard by abstracting over some of the steps; you 
can find the installation instructions [here][hub-install] (or, if you like to live on the cutting-edge, try out 
GitHub's [shiny new CLI][github-cli]).

#### Staying on the Command Line
If you have `hub` and `gitflow-avh` installed, you should be able to work entirely from the command line - even when
working with a PR of a published feature/bugfix branch.

You'll need to change a bit of `gitflow-avh`'s default `finish` behavior to push to remote branches:
```bash
git config --local gitflow.bugfix.finish.push yes
git config --local gitflow.feature.finish.push yes
git config --local gitflow.release.finish.push yes
```
This will enact proper Git Flow "finalizer" processes on remote branches (e.g. merging `release` branches back to 
`develop` and `master`, deleting old `feature` and `bugfix` branches). This way, you won't have to do manual (remote) 
branch cleanup with vanilla git commands, or have to remember to push tags.

Once that's done, you'll just do normal Git Flow process with one exception: after running a `git flow ... publish` 
command, you'll run `hub pull-request` and fill out a proper PR with your command line editor of choice.

Since GitHub considers a PR "Merged" as soon as the commits in the PR branch are also found in the target branch (so
long as the commits are not modified in any way - not a problem if you never rebase or amend remote commits!), you can 
just issue a `git flow ... finish` command to do the necessary merges, tag pushes, and branch cleanup.

### Localization
At the moment, we have very rudimentary i18n and l10n processes - nothing like the sophisticated pipeline you might see
at a big company. It's a system based on trust:

1. Code contributors and reviewers are trusted to enforce internationalization of strings where appropriate.
2. Translators are expected to keep their `feature` branches up-to-date with `develop`. 
3. Translators should keep their `.po` files up to date by running `./manage.py makemessages` whenever `develop` is 
   merged back into their `feature` branch. 
3. Translators will be notified ahead of time when releases are about to cut so that they can get in any last-minute 
   translations.

### Releases
We deploy Lookit services on Google Kubernetes Engine; the CI/CD pipeline is defined over in the [Lookit Orchestrator 
repo][lookit-orchestrator]. A GitHub integration with GCP allows us to trigger builds upon commit to either the `master`
or `develop` branch; deploying to staging and production (respectively).

As described above in the [source control section](#workflow), we use Git Flow methodology, and as such we leverage the
concept of `release` branches. These branches are based off of `develop` and meant to be a "cutoff point" for
new features and bugfixes. They are tightly controlled by the build master ([Rico Rodriguez](mailto:rrodrigu@mit.edu)), 
and should only ever add the following changes:

- Version Bumps (major and minor only)
- Changelog updates (manually authored)
- The occasional cherry-picked commit from a Localization branch.

#### How to Release

**If you want to do releases, it's critical that you carefully read the section below**.
The tooling we have put together enforces a strict adherence to Semantic Versioning. If you understand how Semantic
Versioning works, then the behavior of the tools will not confuse you. If you have trouble answering the question
"what is build metadata?", or articulating what constitutes a prerelease, then you will probably be baffled by the
restrictions on the workflow.

1. `git flow release start $(invoke new-release --kind "major")`
    - `invoke new-release` updates the VERSION file and echoes back the new version. There are three mutually exclusive
      options for `invoke new release`, each appropriate for a different situation during the release cycle.
        * `--kind`: `major`, `minor`, or `patch`. When creating a release branch, you'll be using this most often.
        * `--pre`: Rarely, after starting a release branch, you want to deploy it to the staging environment for QA.
          in this situation, you should **absolutely not call it in the context of the `git flow` tools**, since they
          automate a workflow of merging _all_ release branches back into master and develop at the same time. I cannot
          emphasize this enough - ***Do NOT, ever, under any circumstance, merge a prerelease branch into master!***
          Instead, do the remote merge with develop manually:
            - `invoke new-release --pre alpha`: Pre-releases proceed from *alpha*, to *beta*, to *rc* ("Release
            Candidate"). You can iterate on a prerelease by just calling the command again; it'll go from something like
            `1.2.1-beta.1` to `1.2.1-beta.2`. You can't go backwards - if you try to create a new alpha release after a
            beta, the tool will quit and print an error message.
            - `NEXT_LOOKIT_VERSION=$(<VERSION)`
            - `git checkout develop`
            - `git merge --no-ff release/$NEXT_LOOKIT_VERSION`
            - `git tag -a $(cat VERSION) && git push origin --tags`: Tag the commit as a prerelease.
            - `git push origin develop`: Push to remote and trigger the build.
        * `--build`: Sometimes, we'll need to fix or change something with the [CI/CD pipeline][lookit-orchestrator], in
          which case the likelihood is that you'll need to redeploy Lookit to re-initialize any environment variables
          passed in from configs and secrets. While it's true that you could run `kubectl rollout restart
          ${SOME_DEPLOYMENT}` to accomplish this, it's preferable here to annotate the commit history with valuable
          information about the evolution of the product. Ideally, you'll be able to enter the commit SHA for the
          updated version of [Lookit Orchestrator][lookit-orchestrator] that will be controlling your re-deployment.
2. Now you're in a new release branch with the changed `VERSION` file in your git staging area (uncommitted). You should
   make any changes you need to. Ideally, this is only additions to `CHANGELOG.md`.
3. `git flow release finish $(cat VERSION)` - this will execute a `--no-ff` merge on both develop and master branches,
   along with creating the appropriate tags both locally and remotely.

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

