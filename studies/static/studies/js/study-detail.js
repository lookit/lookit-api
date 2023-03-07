$.fn.editable.defaults.mode = 'inline';

$.fn.editableform.buttons = `
<button type="submit" class="btn btn-primary btn-sm editable-submit">&#x2713;</button>
<button type="button" class="btn btn-secondary btn-sm editable-cancel">&#x2715;</button>
`


function removeTooltip() {
    $('[data-toggle="tooltip"]').tooltip('hide');
}

function cloneStudy() {
    document.getElementById('cloneForm').submit()
}

function onStateSelect(stateListItem) {
    console.log("clocked");
    const trigger = $(stateListItem).data()['trigger'];
    const stateChangeForm = $('#studyStateModalForm');
    const stateChangeCommentsInput = stateChangeForm.find('textarea[name=comments-text]');
    const infoText = transitionHelpData[trigger];
    const commentsHelpText = commentsHelpData[trigger];


    console.log(trigger);

    stateChangeCommentsInput.show();

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

    const $additionalInfoSpan = stateChangeForm.find('#study-status-additional-information');
    $additionalInfoSpan.text(infoText);

    const $commentsHelpText = stateChangeForm.find('#study-comments-help-text');
    $commentsHelpText.text(commentsHelpText);

    stateChangeForm.find('input[name=trigger]').val(trigger);

    const $declarationsForm = stateChangeForm.find(".declarations");

    $declarationsForm.empty();

    if (trigger in declarations) {
        $declarationsForm.append(`
            <p>Please note here any elements of your study that require additional review(see Terms of Use):</p>
            `);
        for (let key in declarations[trigger]) {
            $declarationsForm.append(`
                <div class="checkbox" >
                    <label>
                        <input type="checkbox" value="" name="${key}" />
                        ${declarations[trigger][key]}
                    </label>
                </div >
                `)
        }
        $declarationsForm.append(`
            <p>If you checked any of the boxes above, please describe below:</p>
            <textarea class="form-control" rows="5" name="issues_description" placeholder="Describe declarations here"></textarea>
            `);
    }
}

const origin = window.location.origin;
const privateLink = document.getElementById('private-study-link');
const previewLink = document.getElementById('study-preview-link');
if (privateLink && !privateLink.value.startsWith(origin)) {
    privateLink.value = origin + privateLink.value;
}
if (previewLink && !previewLink.value.startsWith(origin)) {
    previewLink.value = origin + previewLink.value;
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
    ]
});

new Clipboard('.copy-link-button'); // NOSONAR

$('#private-study-link, #study-preview-link').attr('readonly', 'readonly');


$('form').submit(function () {
    $('#changeStatusButton').prop("disabled", "disabled");
});

$(function () {
    $('.copy-link-button').tooltip({
        title: "Copied!",
        trigger: "click",
        placement: "bottom",
    });
});
