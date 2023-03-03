// Show the generator function field only if use_generator is checked.
function updateGeneratorDisplay() {
    if ($('#id_use_generator:checked').length) {
        $('#generator-container').show();
    } else {
        $('#generator-container').hide();
    }
}

// Display an error if generator is not a valid JS function. Returns 0 if no errors, 1 if errors.
function validateGenerator(code) {

    const $errorToDisplay = $('<div id="clientside-generator-validation-message" class="form-text"></div>');
    const $generatorField = $('#id_generator').closest('.mb-4');
    $generatorField.removeClass('has-error');
    $('#clientside-generator-validation-message').remove();

    try {
        Function(code)();
        try {
            const generatorFn = Function('return ' + code)();
            if (typeof generatorFn !== 'function') {
                throw new Error();
            }
        } catch (error) {
            $errorToDisplay
                .text('Warning: Generator function does not evaluate to a single function. Generator will be disabled if this value is saved.')
                .insertBefore($generatorField.children().last());
            $generatorField.addClass('has-error');
            return 1;
        }
    } catch (error) {
        $errorToDisplay
            .text('Warning: Invalid Javascript. Generator will be disabled if this value is saved.')
            .insertBefore($generatorField.children().last());
        $generatorField.addClass('has-error');
        return 1;
    }
    return 0;
}

// Display an error if structure is not a valid JSON string. Returns 0 if no errors, 1 if errors.
function validateStructure(code) {
    const $errorToDisplay = $('<div id="clientside-protocol-validation-message" class="form-text"></div>');
    const $protocolField = $('#id_structure').closest('.mb-4');
    $protocolField.removeClass('has-error');
    $('#clientside-protocol-validation-message').remove();
    try {
        JSON.parse(code);
    } catch (error) {
        $errorToDisplay
            .text('Warning: Invalid JSON.')
            .insertBefore($protocolField.children().last());
        $protocolField.addClass('has-error');
        return 1;
    }
    return 0;
}

// Update a read-only field to display the calculated max age in days
function updateMaxAgeDaysDisplay() {
    $("#max_age_in_days_val").text(Number($("#id_max_age_years").val()) * 365 + Number($("#id_max_age_months").val()) * 30 + Number($("#id_max_age_days").val()))
}

// Update a read-only field to display the calculated min age in days
function updateMinAgeDaysDisplay() {
    $("#min_age_in_days_val").text(Number($("#id_min_age_years").val()) * 365 + Number($("#id_min_age_months").val()) * 30 + Number($("#id_min_age_days").val()))
}

function setExternal() {
    // hide frame player fields through css                
    document
        .querySelectorAll('#type-metadata-1, #structure-container, #generator-container, .use-generator.form-text')
        .forEach(e => e.classList.add('d-none'))
    // disable frame player metadata fields
    document
        .querySelectorAll("#type-metadata-1 input")
        .forEach(e => e.disabled=true)
    // enable external fields
    document
        .querySelectorAll("#type-metadata-2 input")
        .forEach(e => e.disabled=false)
    document.querySelector('#generator-container').classList.add('d-none')
    document.querySelector('#type-metadata-2').classList.remove('d-none')
}

function setFramePlayer() {
    // hide external fields through css
    document
        .querySelectorAll('#type-metadata-1, #structure-container, #generator-container, .use-generator.form-text')
        .forEach(e => e.classList.remove('d-none'))
    // enable frame player metadata fields
    document
        .querySelectorAll("#type-metadata-1 input")
        .forEach(e => e.disabled=false)
    // disable external fields
    document
        .querySelectorAll("#type-metadata-2 input")
        .forEach(e => e.disabled=true)
    document.querySelector('#generator-container').classList.remove('d-none')
    document.querySelector('#type-metadata-2').classList.add('d-none')
}

function updateStudyType (externalCheckbox) {
    externalCheckbox.checked ? setExternal() : setFramePlayer()
    updateScheduled()
}

function updateScheduled(){
    const external = document.querySelector('#id_external')
    const scheduled = document.querySelector('#id_scheduled')
    scheduled.disabled = !external.checked
}

function updateScheduling (scheduledCheckBox) {            
    const scheduling = document.querySelector("#id_scheduling").closest('.mb-4')
    if (!scheduledCheckBox.disabled && scheduledCheckBox.checked){
        scheduling.classList.remove("d-none")
    } else {
        scheduling.classList.add("d-none")
    }
}

$(document).ready(function() {
    // Do initial validation of structure, generator.
    validateStructure($('#id_structure').val());
    validateGenerator($('#id_generator').val());

    // When use_generator field changes, update whether generator field is displayed
    updateGeneratorDisplay();
    $('#id_use_generator').on('change', function() {
        updateGeneratorDisplay();
    });

    // Validate generator function upon closing its editor
    $("#generator-container .ace-overlay .save, #generator-container .ace-overlay .cancel").bind("click", function () {
        // data field 'editor' bound to editor but only while editor is open
        const code = $('#generator-container .ace-overlay').data('editor').getValue();
        validateGenerator(code);
    });

    // Validate structure function upon closing its editor
    $("#structure-container .ace-overlay .save, #generator-container .ace-overlay .cancel").bind("click", function () {
        // data field 'editor' bound to editor but only while editor is open
        const code = $('#structure-container .ace-overlay').data('editor').getValue();
        validateStructure(code);
    });

    // Use ctrl-S to close editor from either editor.
    $(".ace-overlay .edit").bind("click", function () {
        const $aceOverlay = $(this).closest('.ace-overlay')
        const editor = $aceOverlay.data('editor');
        editor.commands.addCommand({
            name: 'save',
            bindKey: {win: 'Ctrl-S', mac: 'Command-S'},
            exec: function() {
                $aceOverlay.find('.save').click();
                // Could also consider triggering save button on broader form
            },
            readOnly: false // should not apply in readOnly mode
        });
    });

    // Upon submit, unset use generator if generator function is invalid
    $("#create-study-button, #save-button").bind("click", function() {
        if (validateGenerator($('#id_generator').val())) {
            const $useGeneratorCheckbox = $('#id_use_generator');
            $useGeneratorCheckbox.prop("checked", false);
            $useGeneratorCheckbox[0].value = false;
        }
    });

    // Calculate the min/max age in day(s) upon page load & updates
    $("#id_min_age_years, #id_min_age_months, #id_min_age_days").change(updateMinAgeDaysDisplay);
    $("#id_max_age_years, #id_max_age_months, #id_max_age_days").change(updateMaxAgeDaysDisplay);
    updateMinAgeDaysDisplay();
    updateMaxAgeDaysDisplay();

    // Update study form based on study type
    const externalCheckbox = document.querySelector('#id_external')
    externalCheckbox.addEventListener('click', () => updateStudyType(externalCheckbox))
    updateStudyType(externalCheckbox)

    const scheduledCheckBox = document.querySelector("#id_scheduled")
    scheduledCheckBox.addEventListener('click', ()=>{
        updateScheduling(scheduledCheckBox)
    })
    updateScheduling(scheduledCheckBox)

    /*
        Priority current value
    */

    const priority = document.querySelector('#id_priority');
    const currentPriority = document.createElement('div');
    const priorityParent = priority.parentElement;
    const highest = document.createElement('span');
    const lowest = document.createElement('span');
    const helpBlock = priorityParent.querySelector('.form-text');

    // Add current priority element
    currentPriority.id = 'current-priority';
    priorityParent.insertBefore(currentPriority, priority);

    // Add priority labels
    highest.innerHTML = 'Highest';
    lowest.innerHTML = 'Lowest';
    highest.classList.add('priority-highest');
    priorityParent.insertBefore(lowest, helpBlock);
    priorityParent.insertBefore(highest, helpBlock);


    // Event listener to update current priority value
    priority.addEventListener('input', ()=>{currentPriority.innerHTML = `Current Priority: ${priority.value}`});

    // Call input event one time to populate current priority element
    priority.dispatchEvent(new Event('input'));

    /*
        Participation Selection 
    */

    const mustHaveList = document.createElement('ul');
    const mustNotHaveList = document.createElement('ul');
    const mustHave = document.querySelector('#id_must_have_participated');
    const mustNotHave = document.querySelector('#id_must_not_have_participated');
    const mustHaveDiv = document.createElement('div');
    const mustNotHaveDiv = document.createElement('div');

    // List headers
    mustHaveDiv.innerHTML = 'Participants must have participated in:';
    mustNotHaveDiv.innerHTML = 'Participants must NOT have participated in:';
    mustHave.parentElement.append(mustHaveDiv, mustHaveList);
    mustNotHave.parentElement.append(mustNotHaveDiv, mustNotHaveList);

    // Update list with current selection.  Hide header when list empty. 
    function showSelectedStudies(select, ul, div){
        const selection = select.querySelectorAll('option:checked');
        ul.children && [...ul.children].forEach(e=>e.remove());
        selection.forEach(e => {
            const li = document.createElement('li');
            li.innerHTML = e.innerHTML;
            ul.append(li);
        });
        ul.children.length ? div.classList.remove('d-none') : div.classList.add('d-none');
    }

    // Augment default mousedown event for multi select.  Option is selected when clicked and 
    // unselected when clicked again. 
    function toggleSelection(el){
        el.addEventListener('mousedown', (event) => {
            event.preventDefault();
            // Adjust selection when element has focus.
            if (document.activeElement === el.parentElement){
                el.selected = !el.selected
            }
            el.parentElement.focus();
        });
    }

    // add event listeners to select and options.
    mustHave.addEventListener('mousedown', ()=>{showSelectedStudies(mustHave, mustHaveList, mustHaveDiv);});
    mustNotHave.addEventListener('mousedown', ()=>{showSelectedStudies(mustNotHave, mustNotHaveList, mustNotHaveDiv);});
    [...mustHave.options, ...mustNotHave.options].forEach(el => toggleSelection(el));

    // Trigger mousedown to populate ui.
    mustHave.dispatchEvent(new Event('mousedown'));
    mustNotHave.dispatchEvent(new Event('mousedown'));
});