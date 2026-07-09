// Create event handlers
function validateExperiment(event) {
    const experiment = document.querySelector('#id_experiment');
    jsValidation(event, experiment);
};

function clearOrSelectAllPlugins(event) {
    const btn = event.currentTarget;
    const checked = btn.classList.contains('plugin-select-all');
    const fieldName = btn.id.replace(/-select-all$|-clear-all$/, '');
    document.querySelectorAll(`input[name="${fieldName}"]`).forEach(cb => cb.checked = checked);
}

// Set up event listeners
document.querySelector('form#experiment_runner_form').addEventListener('submit', validateExperiment);

document.querySelectorAll('.plugin-select-all, .plugin-clear-all').forEach(function (btn) {
    btn.addEventListener('click', clearOrSelectAllPlugins);
});

document.querySelectorAll('.collapse').forEach(function (collapseEl) {
    const btn = document.querySelector(`[data-bs-target="#${collapseEl.id}"]`);
    if (!btn) return;
    const icon = btn.querySelector('.collapse-icon');
    if (!icon) return;
    collapseEl.addEventListener('show.bs.collapse', () => icon.textContent = '▴');
    collapseEl.addEventListener('hide.bs.collapse', () => icon.textContent = '▾');
});
