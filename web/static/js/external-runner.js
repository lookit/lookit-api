const form = document.querySelector('form#experiment_runner_form');

function toggleScheduling() {
    const scheduled = form.querySelector('#id_scheduled');
    const scheduling = form.querySelector('#id_scheduling');
    const checked_scheduling = form.querySelector('input[name="scheduling"]:checked');
    if (scheduled.value === "Scheduled") {
        scheduling.parentNode.classList.remove('d-none');
    } else {
        scheduling.parentNode.classList.add('d-none');
        if (checked_scheduling) checked_scheduling.checked = false;
    }
}

function toggleOtherScheduling() {
    const scheduled = form.querySelector('#id_scheduled');
    const scheduling = form.querySelector('#id_scheduling');
    const otherScheduling = form.querySelector('#id_other_scheduling');
    if (scheduling.value === 'Other' && scheduled.value === "Scheduled") {
        otherScheduling.parentNode.classList.remove('d-none');
    } else {
        otherScheduling.parentNode.classList.add('d-none');
        otherScheduling.value = "";
    }
}

function toggleOtherStudyPlatform() {
    const studyPlatform = form.study_platform;
    const otherStudyPlatform = form.other_study_platform;
    if (studyPlatform.value === 'Other') {
        otherStudyPlatform.parentNode.classList.remove('d-none')
    } else {
        otherStudyPlatform.parentNode.classList.add('d-none');
        otherStudyPlatform.value = "";
    }
}

/***
 * Page load
 */
toggleScheduling();
toggleOtherScheduling();
toggleOtherStudyPlatform();

/***
 * Event listeners
 */
form.querySelector('#id_scheduled').addEventListener('click', () => {
    toggleScheduling();
    toggleOtherScheduling();
});
form.querySelector('#id_scheduling').addEventListener('change', toggleOtherScheduling);
form.querySelector('#id_study_platform').addEventListener('change', toggleOtherStudyPlatform);
