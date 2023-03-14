$(document).ready(function () {
    $('.text-warning').hide();
    $(".childDropdown").val("none");
});

function childSelected(selectElement) {
    var participateButton = document.getElementById('participate-button');
    if (selectElement.value === 'none') {
        participateButton.disabled = true;
        document.getElementById('too-old').style.display = 'none';
        document.getElementById('too-young').style.display = 'none';
        document.getElementById('criteria-not-met').style.display = 'none';
    } else {
        participateButton.disabled = false;
    }
    participateButton.value = selectElement.value;

    document.getElementById('too-old').style.display = 'none';
    document.getElementById('too-young').style.display = 'none';
    document.getElementById('criteria-not-met').style.display = 'none';
    let birthday = selectElement.selectedOptions[0].dataset["birthdate"],
        age = calculateAgeInDays(birthday),
        ineligibleBasedOnAge = ageCheck(age),
        ineligibleBasedOnCriteria = selectElement.selectedOptions[0].dataset["eligible"] === "False";

    if (ineligibleBasedOnAge > 0) { // Too old
        document.getElementById('too-old').style.display = 'inline-block';
    } else if (ineligibleBasedOnAge < 0 && !ineligibleBasedOnCriteria) { // Too young, but otherwise eligible
        document.getElementById('too-young').style.display = 'inline-block';
    } else if (ineligibleBasedOnCriteria) {
        document.getElementById('criteria-not-met').style.display = 'inline-block';
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
    // These are now hard-coded to avoid unpredictable behavior from moment.duration().asDays()
    // e.g. 1 year = 365 days, 1 month = 30 days, and 1 year + 1 month = 396 days.
    minDays = Number("{{study.min_age_days}}") + 30 * Number("{{study.min_age_months}}") + 365 * Number("{{study.min_age_years}}");
    maxDays = Number("{{study.max_age_days}}") + 30 * Number("{{study.max_age_months}}") + 365 * Number("{{study.max_age_years}}");

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
