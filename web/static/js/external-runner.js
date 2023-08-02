function toggleScheduling() {
    const scheduled = document.forms[0].scheduled;
    const scheduling = document.querySelector('#id_scheduling');
    const checked_scheduling = document.querySelector('input[name="scheduling"]:checked')
    if (scheduled.checked) {
        scheduling.parentNode.classList.remove('d-none');
    } else {
        scheduling.parentNode.classList.add('d-none');
        checked_scheduling ? checked_scheduling.checked = false : null;
    }
}

function toggleOtherScheduling() {
    const scheduled = document.forms[0].scheduled;
    const scheduling = document.forms[0].scheduling;
    const otherScheduling = document.querySelector('#id_other_scheduling')
    if (scheduling.value === 'Other' && scheduled.checked) {
        otherScheduling.parentNode.classList.remove('d-none');
    } else {
        otherScheduling.parentNode.classList.add('d-none');
        otherScheduling.value = "";
    }
}

function toggleOtherStudyPlatform() {
    const studyPlatform = document.forms[0].study_platform;
    const otherStudyPlatform = document.forms[0].other_study_platform;

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
document.querySelector('#id_scheduled').addEventListener('click', () => {
    toggleScheduling();
    toggleOtherScheduling();
});
document.querySelector('#id_scheduling').addEventListener('change', toggleOtherScheduling);
document.querySelector('#id_study_platform').addEventListener('change', toggleOtherStudyPlatform);
