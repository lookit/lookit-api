function toggleOtherTextInput(e) {
    const otherTextInput = document.querySelector(`input[name=other_${e.name}]`)
    if (e.value === "Other") {
        otherTextInput.classList.remove('d-none')
        otherTextInput.disabled = false
    } else {
        otherTextInput.classList.add('d-none')
        otherTextInput.disabled = true
    }

}

let current_commit_date = "";
const $commit_description = $('#commit-description div.card-body');
const $update_info = $('#commit-update-info div.card-body');

function checkForUpdates(e) {
    e.preventDefault();
    let current_repo = $('#study-type-metadata input[name="player_repo_url"]').val().trim();
    const current_sha = $('#study-type-metadata input[name="last_known_player_sha"]').val().trim();
    current_repo = current_repo.replace('/\/$/', ''); //remove any trailing slash
    const commit_options_api_url = current_repo.replace('https://github.com/', 'https://api.github.com/repos/') + `/commits?since=${current_commit_date}`;

    $.ajax({
        url: commit_options_api_url,
        dataType: 'json'
    }).done(function (data) {
        if (data.length > 0) {
            // Commits returned are inclusive of the reference commit, 
            // which will be last (most recent first) if it's in master - 
            // don't list or count this one if so
            if (data[data.length - 1].sha == current_sha) {
                data = data.slice(0, -1);
            }
            const commits_since = $.map(data, function (c) { return `<tr><td>${c.commit.author.date.split('T')[0]}</td><td>${c.commit.message}</td><td>${c.sha}</td></tr>` }).join('');
            const commit_description = `<p>Since the version you are using, there have been updates to the master branch of ${current_repo}. Most recent commits:` +
                `<table><thead><tr><th>Date</th><th>Description</th><th>Commit SHA</th></tr></thead><tbody>${commits_since}</tbody></table>`
            $update_info.html(commit_description);
        } else {
            $update_info.html(`<p>Up to date!</p> <p>This is the most recent version of the master branch of ${current_repo}.</p>`);
        }
        $('#commit-update-info').show();
    }).fail(function () {
        const error_message = `<p> Error: unable to fetch versions for repo ${current_repo}. </p>`;
        $update_info.html(error_message);
        $('#commit-update-info').show();
    });
}

function processCommitData(data) {
    $('#update-button').prop('disabled', false);
    current_commit_date = data.commit.author.date;
    let files_changed_list = $.map(data.files, function (f) { return f.status + ': ' + f.filename });
    if (files_changed_list.length > 10) {
        files_changed_list = files_changed_list.slice(0, 10);
        files_changed_list.push('...');
    }
    if (data.commit.message.length > 1200) {
        data.commit.message = data.commit.message.slice(0, 1200) + "...";
    }
    const commit_description = `<p>Your study will use commit <a target="_blank" href="${data.html_url}">${data.sha}</a>:</p>` +
        `<table class="table"><tr><th scope="row">Date</th><td>${data.commit.author.date}</td></tr>` +
        `<tr><th scope="row">Author</th><td>${data.commit.author.name}</td></tr>` +
        `<tr><th scope="row">Message</th><td>${data.commit.message}</td></tr>` +
        `<tr><th scope="row">Files changed</th><td>${files_changed_list.join('<br>')}</td></tr></table>`
    $commit_description.html(commit_description);
}

function updateCommitInfo() {
    $('#commit-update-info').hide();
    $('#update-button').prop('disabled', true);
    $('#commit-description').hide();

    const has_player_repo_url = $('#study-type-metadata input[name="player_repo_url"]').length;
    const has_last_known_player_sha = $('#study-type-metadata input[name="last_known_player_sha"]').length;

    // Only does anything if we have the keys used by ember-lookit-frameplayer available (although potentially hidden).
    if (has_player_repo_url && has_last_known_player_sha) {
        let current_repo = $('#study-type-metadata input[name="player_repo_url"]').val().trim();
        $('#study-type-metadata input[name="player_repo_url"]').val(current_repo);
        const current_sha = $('#study-type-metadata input[name="last_known_player_sha"]').val().trim();
        $('#study-type-metadata input[name="last_known_player_sha"]').val(current_sha);
        current_repo = current_repo.replace('/\/$/', ''); //remove any trailing slash
        const commit_api_url = current_repo.replace('https://github.com/', 'https://api.github.com/repos/') + '/commits/' + current_sha;
        const repo_api_url = current_repo.replace('https://github.com/', 'https://api.github.com/repos/');

        $commit_description.html('Loading...');
        $('#commit-description').show();

        $.ajax({
            url: repo_api_url,
            dataType: 'json'
        }).done(function () {
            if (current_sha == "") {
                $commit_description.html(`Leave the version blank to build the experiment runner using the <a target="_blank" href="${current_repo}/commits">latest commit to the master branch</a> of ${current_repo}. This will be automatically filled in when you build the experiment runner.`);
            } else {
                $.ajax({
                    url: commit_api_url,
                    dataType: 'json'
                })
                    .done(processCommitData)
                    .fail(function () {
                        const error_message = `<p> Error: Version ${current_sha} not found! </p>` +
                            `<p>You can view a <a target="_blank" href="${current_repo}/commits/">list of available versions</a> and copy the 40-character "commit SHA" of the one you want to use by using the copy button.`;
                        $commit_description.html(error_message);
                    });
            }
        }).fail(function () {
            const error_message = `<p>Error: Nothing found at <a target="_blank" href="${current_repo}">${current_repo}</a>.`;
            $commit_description.html(error_message);
        });
    }
}

$('#commit-update-info').hide();
$('#update-button').prop('disabled', true);
$('#update-button').on('click', checkForUpdates);
// Only run update upon changes to the relevant keys, not other inputs for other player types
$('#study-type-metadata div.metadata-key input[name="last_known_player_sha"], #study-type-metadata div.metadata-key input[name="player_repo_url"]').on('change paste', updateCommitInfo);
updateCommitInfo();

// This is assuming that there are only radio buttons that have an other field. 
document.querySelectorAll("input[type=radio]")
    .forEach(e => e.addEventListener('click', ({ target }) => {
        toggleOtherTextInput(target)
    }))
document.querySelectorAll("input[type=radio]:checked").forEach(toggleOtherTextInput)
