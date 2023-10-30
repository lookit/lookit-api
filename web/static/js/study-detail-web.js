$('.text-warning').hide();
$("#child-dropdown").val("none");
childSelected(document.getElementById('child-dropdown'));

function childSelected(selectElement) {
    var participateButton = document.getElementById('participate-button');
    if (selectElement.value === 'none') {
        participateButton.disabled = true;
        document.getElementById('too-old').classList.add('d-none');
        document.getElementById('too-young').classList.add('d-none');
        document.getElementById('criteria-not-met').classList.add('d-none');
    } else {
        participateButton.disabled = false;
    }
    participateButton.value = selectElement.value;

    document.getElementById('too-old').classList.add('d-none');
    document.getElementById('too-young').classList.add('d-none');
    document.getElementById('criteria-not-met').classList.add('d-none');
    let birthday = selectElement.selectedOptions[0].dataset["birthdate"];
    let age = calculateAgeInDays(birthday);
    let ineligibleBasedOnAge = ageCheck(age);
    let ineligibleBasedOnCriteriaExpression = selectElement.selectedOptions[0].dataset["eligibleCriteria"] === "False";
    let ineligibleBasedOnParticipation = selectElement.selectedOptions[0].dataset["eligibleParticipation"] === "False";

    if (ineligibleBasedOnAge > 0) { // Too old
        document.getElementById('too-old').classList.remove('d-none');
    } else if (ineligibleBasedOnAge < 0 && !(ineligibleBasedOnCriteriaExpression) && !(ineligibleBasedOnParticipation)) { // Too young, but otherwise eligible
        document.getElementById('too-young').classList.remove('d-none');
    } else if (ineligibleBasedOnCriteriaExpression || ineligibleBasedOnParticipation) {
        // Doesn't meet criteria from the criteria expression and/or the prior study participation requirements
        document.getElementById('criteria-not-met').classList.remove('d-none');
    }
}

function calculateAgeInDays(birthday) {
    // Warning: do NOT use moment.duration in the calculation of age! Use diffs
    // instead to get ACTUAL time difference, without passing through an 
    // approximation where each month is 30 days and each year is 365.
    return moment(moment()._d).diff(new Date(birthday), 'days');
}

function ageCheck(age) {
    // Adapted from experiment model in exp-addons
    var minDays;
    var maxDays;
    var study_age_criteria = document.getElementById('child-dropdown').dataset;
    // These are now hard-coded to avoid unpredictable behavior from moment.duration().asDays()
    // e.g. 1 year = 365 days, 1 month = 30 days, and 1 year + 1 month = 396 days.
    minDays = parseInt(study_age_criteria.studyMinAgeDays,10) + 30 * parseInt(study_age_criteria.studyMinAgeMonths,10) + 365 * parseInt(study_age_criteria.studyMinAgeYears,10);
    maxDays = parseInt(study_age_criteria.studyMaxAgeDays,10) + 30 * parseInt(study_age_criteria.studyMaxAgeMonths,10) + 365 * parseInt(study_age_criteria.studyMaxAgeYears,10);

    minDays = minDays || -1;
    maxDays = maxDays || Number.MAX_SAFE_INTEGER;

    if (age <= minDays) {
        return age - minDays;
    } else if (age >= maxDays) {
        return age - maxDays;
    } else {
        return 0;
    }
}
