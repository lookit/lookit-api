$.fn.editable.defaults.mode = 'inline';

function cloneStudy() {
    document.getElementById('cloneForm').submit()
}

function onStateSelect(stateListItem) {
    let trigger = $(stateListItem).data()['trigger'],
        stateChangeForm = $('#study-state-modal'),
        stateChangeCommentsInput = stateChangeForm.find('textarea[name=comments-text]'),
        infoText = transitionHelpData[trigger];
    let commentsHelpText = commentsHelpData[trigger];

    switch (trigger) {
        case 'reject':
            stateChangeCommentsInput.attr('placeholder', 'List requested changes here');
            break;
        case 'resubmit':
            stateChangeCommentsInput.attr('placeholder', 'List changes here');
            break;
        case 'submit':
            stateChangeCommentsInput.attr('placeholder', 'Provide information about peer review and any nonstandard elements here');
            break;
        case 'approve':
            stateChangeCommentsInput.attr('placeholder', 'List approval comments here');
            break;
        default:
            stateChangeCommentsInput.hide();
    }

    let $additionalInfoSpan = stateChangeForm.find('#study-status-additional-information');
    $additionalInfoSpan.text(infoText);

    let $commentsHelpText = stateChangeForm.find('#study-comments-help-text');
    $commentsHelpText.text(commentsHelpText);

    stateChangeForm.find('input[name=trigger]').val(trigger);

    let $declarationsForm = stateChangeForm.find(".declarations");
    $declarationsForm.empty();
    if (trigger in declarations) {
        $declarationsForm.append(`
            <p>
                Please note here any elements of your study that require additional review (see Terms of Use):
            </p>
        `);
        for (let key in declarations[trigger]) {
            $declarationsForm.append(`
                <div class="checkbox">
                    <label>
                        <input type="checkbox" value="" name="${key}"/>
                        ${declarations[trigger][key]}
                    </label>
                </div>
        `)
        }
        $declarationsForm.append(`
        <p>
            If you checked any of the boxes above, please describe below:
        </p>
        <textarea class="form-control" rows="5" name="issues_description" placeholder="Describe declarations here"></textarea>
    `);
    }
}

$(document).ready(function () {
    let origin = window.location.origin;
    let privateLink = document.getElementById('private-study-link');
    let previewLink = document.getElementById('study-preview-link');
    if (privateLink && !privateLink.value.startsWith(origin)) {
        privateLink.value = origin + privateLink.value;
    }
    if (previewLink && !previewLink.value.startsWith(origin)) {
        previewLink.value = origin + previewLink.value;
    }

    if ("{{ match }}" !== '') {
        document.getElementById("search-organization").value = "{{ match }}";
    }
    $('.researcher_permissions').editable({
        source: [
            { value: 'study_preview', text: 'Preview' },
            { value: 'study_design', text: 'Design' },
            { value: 'study_analysis', text: 'Analysis' },
            { value: 'study_submission_processor', text: 'Submission processor' },
            { value: 'study_researcher', text: 'Researcher' },
            { value: 'study_manager', text: 'Manager' },
            { value: 'study_admin', text: 'Admin' },
        ],
        error: function (response, _newValue) {
            // If removing own permissions, direct to study detail page.
            if (response.status === 403) {
                window.location = window.location.href.replace('edit/', '');
            }
        },
        success: function (_response, newValue) {
            // On success, populate the success message with the permissions the user was given
            // and reveal the permission edit alert message.
            // This is necessary b/c we're using x-editable here. Page is not reloaded.
            $('#add-researcher-messages').hide()
            $('#permission-edit-text').append(' given ' + newValue + ' permissions for this study.');
            $('.disabledPermissionDisplay').hide()
            $('.permissionDisplay').show();
            // Shows success message
            $('#permission-edit').show();
        }
    }).on('click', function (event) {
        // When clicking on a researcher, prepopulate success message with researcher name.
        $('#permission-edit').hide();
        $('#permission-edit-text').text($(event.currentTarget).attr('data-id'));
    });


    new Clipboard('#copy-link-button'); // NOSONAR

    $('#private-study-link, #study-preview-link').attr('readonly', 'readonly');
    $('#copy-link-button').tooltip({
        title: "Copied!",
        trigger: "click",
        placement: "bottom",
    });
    $('.question-icon').tooltip({
        placement: "top",
    });
    $('body').on('hidden.bs.tooltip', function (e) {
        $(e.target).data("bs.tooltip").inState.click = false;
    });

    removeTooltip = function () {
        $('[data-toggle="tooltip"]').tooltip('hide');
    }
    $('form').submit(function () {
        $('#changeStatusButton').prop("disabled", "disabled");
    });
});
