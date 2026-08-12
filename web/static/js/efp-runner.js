// Get global variables from html
const DATA = document.currentScript.dataset;

// Show the generator function field only if use_generator is checked.
function updateProtocolDisplay() {
    const generator = document.querySelector('[for=id_generator]').parentNode;
    const structure = document.querySelector('[for=id_structure]').parentNode;

    // hide js validation error list
    document.querySelector('.js-validation').classList.add('d-none');

    if (document.querySelector('#id_use_generator:checked')) {
        generator.classList.remove('d-none');
        structure.classList.add('d-none');
    } else {
        generator.classList.add('d-none');
        structure.classList.remove('d-none');
    }
}

// The SHA the server last validated: what was saved, or what was rejected
// by the last save attempt. Once this field has any other value, the error shown
// for the field is no longer relevant.
const SHA_FIELD = document.querySelector('#id_last_known_player_sha');
const SUBMITTED_SHA = SHA_FIELD.value;

// django_bootstrap5 marks a field that failed validation with is-invalid:
// this is how we can tell whether the page was re-rendered after a rejected save
// (versus when the page first loads with a version that was already saved)
function shaFieldHasServerError() {
    return SHA_FIELD.classList.contains('is-invalid');
}

// Hide the form validation/save error once the researcher edits the version, so it can't sit there
// contradicting the live warning below it (otherwise it stays until the next form submission).
function clearStaleServerError() {
    if (!shaFieldHasServerError() || SHA_FIELD.value === SUBMITTED_SHA) {
        return;
    }

    const fieldMessages = [...SHA_FIELD.parentNode.querySelectorAll('.invalid-feedback')];
    const staleText = new Set(fieldMessages.map(message => message.textContent.trim()));

    SHA_FIELD.classList.remove('is-invalid');
    fieldMessages.forEach(message => message.remove());

    // The summary above the form repeats every field's errors, so remove only the lines
    // matching this SHA field - errors on the structure or generator fields still stand.
    document.querySelectorAll('ul.list-unstyled.text-danger').forEach(summary => {
        summary.querySelectorAll('li').forEach(line => {
            if (staleText.has(line.textContent.trim())) {
                line.remove();
            }
        });
        if (!summary.querySelector('li')) {
            summary.remove();
        }
    });
}

// Loose match on the repo URL, so that e.g. a trailing slash or a .git suffix doesn't
// exempt a study from the warning. This is just meant to be a flag/warning 
// (studies/helpers.py is_default_player_repo is what actually decides).
function isDefaultRepo(repoUrl) {
    // Dropp the scheme rather than rewriting http to https, and split on "/"
    // rather than matching a trailing-slash pattern, which keeps every step here linear
    // (an anchored quantifier like /(\.git)?\/*$/ backtracks over a run of slashes).
    const normalize = url => {
        const withoutScheme = url.trim().toLowerCase()
            .replace(/^https?:\/\//, '')
            .replace(/^www\./, '');
        const path = withoutScheme.split('/').filter(Boolean).join('/');
        return path.endsWith('.git') ? path.slice(0, -'.git'.length) : path;
    };
    return Boolean(DATA.defaultRepo) && normalize(repoUrl) === normalize(DATA.defaultRepo);
}

function updateCommitDescription() {
    const httpRequest = new XMLHttpRequest();


    const commitUpdateInfo = document.querySelector('#commit-update-info');
    const commitDescription = document.querySelector('#commit-description');
    const commitDetails = document.querySelector('#commit-details');
    const noVersionSelected = document.querySelector('#no-version-selected');
    const updateButton = document.querySelector('#update-button');
    const deprecationWarning = document.querySelector('#version-deprecated-warning');

    const playerSha = SHA_FIELD.value.trim();
    const playerRepoUrl = document.querySelector('#id_player_repo_url').value.trim();

    // Hide commit info cards
    commitUpdateInfo.classList.add('d-none');
    commitDescription.classList.add('d-none');

    // Hide the deprecation warning until a commit comes back old, so that an unanswered or failed request does not leave a stale warning behind from the previous SHA in the field.
    deprecationWarning.classList.add('d-none');

    httpRequest.onreadystatechange = () => {

        if (httpRequest.readyState === XMLHttpRequest.DONE) {
            if (httpRequest.status === 200) {
                const response = JSON.parse(httpRequest.responseText);
                const sha = commitDescription.querySelector('.sha');
                const date = commitDescription.querySelector('.date');
                const name = commitDescription.querySelector('.name');
                const message = commitDescription.querySelector('.message');
                const files = commitDescription.querySelector('.files');

                sha.innerHTML = response.sha;
                sha.href = response.html_url;
                date.innerHTML = response.commit.author.date;
                name.innerHTML = response.commit.author.name;

                // Wrap each line of the message in a paragraph element
                message.innerHTML = response.commit.message
                    .split('\n').map(e => `<p>${e}</p>`)
                    .join('');

                // Wrap each file name in a div element and add the file url
                files.innerHTML = response.files
                    .map(e => `<div>${e.status}: <a href = "${e.blob_url}"> ${e.filename}</a></div>`)
                    .join('');

                // show commit description card and update button, and hide the 'no version selected' message
                commitDetails.classList.remove('d-none');
                noVersionSelected.classList.add('d-none');
                updateButton.classList.remove('d-none');
                commitDescription.classList.remove('d-none');

                // Skip the warning while the server error is up (shaFieldHasServerError), since the two say the same thing
                // about the same SHA. If the form validation error was removed, then we can show a live warning based
                // on the current value.
                // Committer date, not the author date shown above it: the author date
                // survives a rebase, so it can be much older than the version itself.
                // studies/helpers.py get_commit_datetime gates on the same field.
                if (DATA.minCommitDate && !shaFieldHasServerError()
                    && isDefaultRepo(playerRepoUrl)
                    && new Date(response.commit.committer.date) < new Date(DATA.minCommitDate)) {
                    deprecationWarning.classList.remove('d-none');
                }
            }
        }
    };

    if (playerSha && playerRepoUrl) {
        const githubApiUrl = `${playerRepoUrl}/commits/${playerSha}`.replace('github.com', 'api.github.com/repos');
        httpRequest.open("GET", githubApiUrl, true);
        httpRequest.send();
    } else if (!playerSha) {
        // If the commit field is blank then show the 'no version selected' message and description card, but
        // hide any commit details and the update button.
        // (Don't try to figure out which commit is latest since that is settled by the server when the form is saved, not here.)
        commitDetails.classList.add('d-none');
        noVersionSelected.classList.remove('d-none');
        updateButton.classList.add('d-none');
        commitDescription.classList.remove('d-none');
    }
}

function updateCommitUpdateInfo(event) {
    event.preventDefault();
    const httpRequest = new XMLHttpRequest();
    httpRequest.onreadystatechange = () => {
        if (httpRequest.readyState === XMLHttpRequest.DONE) {
            if (httpRequest.status === 200) {
                const response = JSON.parse(httpRequest.responseText);
                const commitUpdateInfo = document.querySelector('#commit-update-info');
                const infoRows = commitUpdateInfo.querySelector('.card-body .container');

                // Clear elements from list
                while (infoRows.childNodes.length > 2) {
                    infoRows.removeChild(infoRows.lastChild);
                }

                response.map(e => {
                    const row = document.createElement('div');
                    const date = document.createElement('div');
                    const message = document.createElement('div');
                    const sha = document.createElement('div');

                    row.classList.add('row', 'pb-3');
                    date.classList.add('col-2');
                    [message, sha].forEach(e => e.classList.add('col'));

                    date.innerHTML = e.commit.author.date;
                    message.innerHTML = e.commit.message;
                    sha.innerHTML = e.sha;

                    row.append(date);
                    row.append(message);
                    row.append(sha);
                    infoRows.append(row);
                });
                commitUpdateInfo.classList.remove('d-none');
            }
        }
    };


    const currentCommitDate = document.querySelector('#commit-description .date').innerHTML;
    const playerRepoUrl = document.querySelector('#id_player_repo_url').value;
    if (playerRepoUrl && currentCommitDate) {
        const githubApiUrl = `${playerRepoUrl}/commits?since=${currentCommitDate}&sha=${DATA.branch}`.replace('github.com', 'api.github.com/repos');
        httpRequest.open("GET", githubApiUrl, true);
        httpRequest.send();
    }
}

function updateLastPlayerSha() {
    const form = document.querySelector('form#experiment_runner_form');

    if (!form.last_known_player_sha.value) {
        const playerRepoUrl = document.querySelector('#id_player_repo_url').value;
        const githubApiUrl = `${playerRepoUrl}/commits?sha=${DATA.branch}`.replace('github.com', 'api.github.com/repos');
        const httpRequest = new XMLHttpRequest();
        httpRequest.onreadystatechange = () => {
            if (httpRequest.readyState === XMLHttpRequest.DONE) {
                if (httpRequest.status === 200) {
                    const response = JSON.parse(httpRequest.responseText);
                    form.last_known_player_sha.value = response[0].sha;
                    updateCommitDescription();
                }
            }
        };
        httpRequest.open("GET", githubApiUrl, true);
        httpRequest.send();
    }
}

function validateGenerator(event) {
    const generator = document.querySelector('#id_generator');
    const use_generator = document.querySelector('#id_use_generator');

    if (use_generator.checked) {
        jsValidation(event, generator);
    }
}

/**
 * Page load
 */
updateProtocolDisplay();
updateCommitDescription();
updateLastPlayerSha();

/**
 * Event Listeners
 */
document.querySelector('#id_use_generator').addEventListener("click", updateProtocolDisplay);
document.querySelector('#update-button').addEventListener("click", updateCommitUpdateInfo);
// Use "input" event rather than "keyup" so that it is triggered by pasting a SHA from the context menu. 
// Clearing runs first so that updateCommitDescription sees that any validation errors are
// already gone and is free to warn about whatever version was typed instead.
SHA_FIELD.addEventListener('input', clearStaleServerError);
SHA_FIELD.addEventListener('input', updateCommitDescription);
document.querySelector('form#experiment_runner_form').addEventListener('submit', validateGenerator);
