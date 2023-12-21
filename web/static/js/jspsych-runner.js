function validateExperiment(event) {
    const experiment = document.querySelector('#id_experiment');
    jsValidation(event, experiment);
}

/**
 * Event Listeners
 */
document.querySelector('form').addEventListener('submit', validateExperiment);
