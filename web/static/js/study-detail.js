const data = document.currentScript.dataset;
const btnPrimaryClasses = data.btnPrimaryClasses;
const btnSecondaryClasses = data.btnSecondaryClasses;
const externalStudy = data.externalStudy === 'True'


$.fn.editable.defaults.mode = 'inline';

$.fn.editableform.buttons = `
<button type="submit" class="${btnPrimaryClasses}">&#x2713;</button>
<button type="button" class="${btnSecondaryClasses}">&#x2715;</button>
`

function formCheckbox(label, name) {
    return `
    <div class="checkbox" >
        <label>
            <input type="checkbox" value="" name="${name}" />
            ${label}
        </label>
    </div >
    `
}

function removeTooltip() {
    $('[data-toggle="tooltip"]').tooltip('hide');
}

function cloneStudy() {
    document.getElementById('cloneForm').submit()
}

function onStateSelect(stateListItem) {
    const trigger = $(stateListItem).data()['trigger'];
    const stateChangeForm = $('#studyStateModalForm');
    const stateChangeCommentsInput = stateChangeForm.find('textarea[name=comments-text]');
    const infoText = transitionHelpData[trigger];
    const commentsHelpText = commentsHelpData[trigger];

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

    if (commentsHelpText) {
        const $commentsHelpTextElem = stateChangeForm.find('#study-comments-help-text');
        $commentsHelpTextElem.append(commentsHelpText.split('\n').map(v => `<p>${v}</p>`).join(''));
    }

    stateChangeForm.find('input[name=trigger]').val(trigger);

    const $declarationsForm = stateChangeForm.find(".declarations");

    $declarationsForm.empty();

    if (trigger in declarations) {
        $declarationsForm.append('<p>Please note here any elements of your study that require additional review (see Terms of Use):</p>');

        /**
         * For this section of the form, we need two fields to be conditional 'collecting_data' 
         * and 'issue_consent'. 
         */
        const filteredDelarations = Object.keys(declarations[trigger])
            .filter((key) => key !== 'collecting_data')
            .filter((key) => !externalStudy || key !== 'issue_consent')
            .reduce((cur, key) => { return Object.assign(cur, { [key]: declarations[trigger][key] }) }, {});

        for (let key in filteredDelarations) {
            $declarationsForm.append(formCheckbox(declarations[trigger][key], key))
        }
        $declarationsForm.append(`
            <p class="pt-2">If you checked any of the boxes above, please describe below:</p>
            <textarea class="form-control" rows="5" name="issues_description" placeholder="Describe declarations here"></textarea>
            `);
    }

    /**
     * Update submit form when the study is external and, for right now, the trigger is 'submit'. 
     */
    if (externalStudy && trigger === 'submit') {
        const $collectingData = stateChangeForm.find('.collecting-data');
        $collectingData.append('<hr/><p>If you are submitting a study that is already actively collecting data from participants, check the box below:</p>');
        $collectingData.append(formCheckbox(declarations[trigger]['collecting_data'], 'collecting_data'));
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

// disable the study state dropdown and submit/save button to prevent another status change while the page reloads
$('form#studyStateModalForm').submit(function () {
    $('#changeStudyState').prop("disabled", "disabled");
    $('form#studyStateModalForm button').prop("disabled", "disabled");
});

$(function () {
    $('.copy-link-button').tooltip({
        title: "Copied!",
        trigger: "click",
        placement: "bottom",
    });
});
