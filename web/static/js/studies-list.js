const $form = $('form#studies_list_form');
const $hideStudiesCheckbox = $form.find('input:checkbox[name=hide_studies_we_have_done]')
const $checkboxes = $form.find('input:checkbox')
const $dropdownSelected = $form.find('select option:selected')

if ($dropdownSelected.val() === '') {
    $hideStudiesCheckbox.attr('disabled', true);
}

$form.on('reset', function (event) {
    resetForm(submitForm);
})

function resetForm(callbackFn) {
    $form.find('input:text').attr('value', '')
    $checkboxes.attr('checked', true);
    $hideStudiesCheckbox.attr('checked', false)
    $dropdownSelected.removeAttr('selected');
    callbackFn()
}

function submitForm() {
    $checkboxes.attr('disabled', false);
    $form.submit()
}

$('select, input:checkbox').on('change', submitForm)

// Set active tab based on which "tabs" radio button is checked.
const checked_radio = document.querySelector('input[name=study_list_tabs]:checked')
const active_tab = document.querySelector(`[data-value="${checked_radio.value}"] a`)
active_tab.classList.add('active')

// On click, update radio group 
document.querySelectorAll('[role=study_list_tabs]').forEach(function (tab) {
    tab.addEventListener('click', function (event) {
        event.preventDefault()
        const radio = document.querySelector(`[name="study_list_tabs"][value="${tab.dataset.value}"]`)
        if (!radio.hasAttribute('checked')) {
            radio.checked = true
            submitForm()
        }
    })
})
