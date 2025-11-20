function validateExperiment(event) {
    const experiment = document.querySelector('#id_experiment');
    jsValidation(event, experiment);
}

/**
 * Event Listeners
 */
document.querySelector('form#experiment_runner_form').addEventListener('submit', validateExperiment);
