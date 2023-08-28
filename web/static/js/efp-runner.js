// Show the generator function field only if use_generator is checked.
function updateGeneratorDisplay() {
    const generator = document.querySelector('[for=id_generator]').parentNode;
    document.querySelector('#id_use_generator:checked') ? generator.classList.remove('d-none') : generator.classList.add('d-none');
}

function updateCommitDescription() {
    const httpRequest = new XMLHttpRequest();


    const commitUpdateInfo = document.querySelector('#commit-update-info');
    const commitDescription = document.querySelector('#commit-description');

    // Hide commit info cards
    commitUpdateInfo.classList.add('d-none');
    commitDescription.classList.add('d-none');

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
                    .join('')

                // Wrap each file name in a div element and add the file url
                files.innerHTML = response.files
                    .map(e => `<div>${e.status}: <a href = "${e.blob_url}"> ${e.filename}</a></div>`)
                    .join('')

                // show commit description card
                commitDescription.classList.remove('d-none');
            }
        }
    };

    const playerSha = document.querySelector('#id_last_known_player_sha').value.trim();
    const playerRepoUrl = document.querySelector('#id_player_repo_url').value.trim();
    if (playerSha && playerRepoUrl) {
        const githubApiUrl = `${playerRepoUrl}/commits/${playerSha}`.replace('github.com', 'api.github.com/repos')
        httpRequest.open("GET", githubApiUrl, true);
        httpRequest.send();
    }
}

function updateCommitUpdateInfo() {
    const httpRequest = new XMLHttpRequest();
    httpRequest.onreadystatechange = () => {
        if (httpRequest.readyState === XMLHttpRequest.DONE) {
            if (httpRequest.status === 200) {
                const response = JSON.parse(httpRequest.responseText);
                const commitUpdateInfo = document.querySelector('#commit-update-info');
                const infoRows = commitUpdateInfo.querySelector('.card-body .container');

                // Clear elements from list
                while (infoRows.childNodes.length > 2) {
                    infoRows.removeChild(infoRows.lastChild)
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
                    infoRows.append(row)
                })
                commitUpdateInfo.classList.remove('d-none')
            }
        }
    }


    const currentCommitDate = document.querySelector('#commit-description .date').innerHTML;
    const playerRepoUrl = document.querySelector('#id_player_repo_url').value;
    if (playerRepoUrl && currentCommitDate) {
        const githubApiUrl = `${playerRepoUrl}/commits?since=${currentCommitDate}`.replace('github.com', 'api.github.com/repos')
        httpRequest.open("GET", githubApiUrl, true);
        httpRequest.send();
    }
}

function updateLastPlayerSha() {
    const form = document.forms[0];

    if (!form.last_known_player_sha.value) {
        const playerRepoUrl = document.querySelector('#id_player_repo_url').value;
        const githubApiUrl = `${playerRepoUrl}/commits`.replace('github.com', 'api.github.com/repos')
        const httpRequest = new XMLHttpRequest();
        httpRequest.onreadystatechange = () => {
            if (httpRequest.readyState === XMLHttpRequest.DONE) {
                if (httpRequest.status === 200) {
                    const response = JSON.parse(httpRequest.responseText);
                    form.last_known_player_sha.value = response[0].sha;
                    updateCommitDescription();
                }
            }
        }
        httpRequest.open("GET", githubApiUrl, true);
        httpRequest.send();
    }
}

/**
 * Page load
 */
updateGeneratorDisplay();
updateCommitDescription();
updateLastPlayerSha();

/**
 * Event Listeners
 */
document.querySelector('#id_use_generator').addEventListener("click", updateGeneratorDisplay);
document.querySelector('#update-button').addEventListener("click", (event) => {
    event.preventDefault();
    updateCommitUpdateInfo();
})
document.querySelector('#id_last_known_player_sha').addEventListener('keyup', updateCommitDescription);
