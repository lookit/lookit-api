// Update a read-only field to display the calculated max age in days
function updateMaxAgeDaysDisplay() {
    $("#max_age_in_days_val").text(Number($("#id_max_age_years").val()) * 365 + Number($("#id_max_age_months").val()) * 30 + Number($("#id_max_age_days").val()))
}

// Update a read-only field to display the calculated min age in days
function updateMinAgeDaysDisplay() {
    $("#min_age_in_days_val").text(Number($("#id_min_age_years").val()) * 365 + Number($("#id_min_age_months").val()) * 30 + Number($("#id_min_age_days").val()))
}











$(document).ready(function () {
    // Calculate the min/max age in day(s) upon page load & updates
    $("#id_min_age_years, #id_min_age_months, #id_min_age_days").change(updateMinAgeDaysDisplay);
    $("#id_max_age_years, #id_max_age_months, #id_max_age_days").change(updateMaxAgeDaysDisplay);
    updateMinAgeDaysDisplay();
    updateMaxAgeDaysDisplay();

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
    priority.addEventListener('input', () => { currentPriority.innerHTML = `Current Priority: ${priority.value}` });

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
    function showSelectedStudies(select, ul, div) {
        const selection = select.querySelectorAll('option:checked');
        ul.children && [...ul.children].forEach(e => e.remove());
        selection.forEach(e => {
            const li = document.createElement('li');
            li.innerHTML = e.innerHTML;
            ul.append(li);
        });
        ul.children.length ? div.classList.remove('d-none') : div.classList.add('d-none');
    }

    // Augment default mousedown event for multi select.  Option is selected when clicked and 
    // unselected when clicked again. 
    function toggleSelection(el) {
        el.addEventListener('mousedown', (event) => {
            event.preventDefault();
            // Adjust selection when element has focus.
            if (document.activeElement === el.parentElement) {
                el.selected = !el.selected
            }
            el.parentElement.focus();
        });
    }

    // add event listeners to select and options.
    mustHave.addEventListener('mousedown', () => { showSelectedStudies(mustHave, mustHaveList, mustHaveDiv); });
    mustNotHave.addEventListener('mousedown', () => { showSelectedStudies(mustNotHave, mustNotHaveList, mustNotHaveDiv); });
    [...mustHave.options, ...mustNotHave.options].forEach(el => toggleSelection(el));

    // Trigger mousedown to populate ui.
    mustHave.dispatchEvent(new Event('mousedown'));
    mustNotHave.dispatchEvent(new Event('mousedown'));

    /*
        Max Responses validation
    */
    const maxResponses = document.querySelector('#id_max_responses');
    if (maxResponses) {
        maxResponses.addEventListener('input', () => {
            // Remove non-numeric characters and leading zeros
            let value = maxResponses.value.replace(/[^0-9]/g, '').replace(/^0+/, '');
            // Ensure minimum value of 1 if not empty
            if (value !== '' && parseInt(value) < 1) {
                value = '1';
            }
            maxResponses.value = value;
        });
    }
});
