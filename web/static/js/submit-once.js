// Prevent duplicate submissions (e.g. fast/double clicks) on any form marked with
// `data-submit-once`. After the first submit, this disables the submit button and
// swaps each button's icon for a spinner.
// Don't use this on forms where the user stays on the same page after submitting,
// e.g. file downloads, forms submitted via JS with fetch/preventDefault().
// Also don't use it if the server reads the submit button's name/value: disabled
// buttons are left out of the submitted form data.

// Form submit buttons don't need to have a '[type="submit"]' attribute, so we
// need to check the type property (button.type) instead.
const submitButtons = (form) =>
    [...form.querySelectorAll('button')].filter((button) => button.type === 'submit');

document.addEventListener('submit', (event) => {
    // Form that that the submit event was called on.
    const form = event.target;
    // The form needs to be tagged with data-submit-once, and make sure that no other
    // JS has called preventDefault on the submit event - ignore if either of these
    // is not the case.
    if (!form.matches('form[data-submit-once]') || event.defaultPrevented) {
        return;
    }
    // disable to prevent additional submissions and add a spinner
    form.setAttribute('aria-busy', 'true');
    submitButtons(form).forEach((button) => {
        // Leave buttons that other JS has already disabled alone, so that we don't
        // re-enable them on restore.
        if (button.disabled) {
            return;
        }
        button.disabled = true;
        button.dataset.submitOnceDisabled = '';
        // Mark the icons we hide so that only those are unhidden on restore. Skip icons
        // that are already hidden so they stay hidden.
        button
            .querySelectorAll('svg:not(.d-none)')
            .forEach((icon) => icon.classList.add('d-none', 'submit-once-hidden'));
        const spinner = document.createElement('span');
        spinner.className = 'spinner-border spinner-border-sm me-1 submit-once-spinner';
        spinner.setAttribute('aria-hidden', 'true');
        button.prepend(spinner);
    });
});

// Browsers may restore this page from the back/forward cache with the buttons
// still disabled, so reset them when the page loads from cache.
window.addEventListener('pageshow', (event) => {
    // Ignore this step if the page is not loaded from cache
    // (i.e. event persisted is false). However this is for clarity and for skipping
    // these steps when unnecessary - the outcome would be exactly the same if this check
    // were removed and the block below ran in all pageshow cases.
    if (!event.persisted) {
        return;
    }
    document.querySelectorAll('form[data-submit-once]').forEach((form) => {
        form.removeAttribute('aria-busy');
        form.querySelectorAll('button[data-submit-once-disabled]').forEach((button) => {
            button.disabled = false;
            delete button.dataset.submitOnceDisabled;
            button.querySelectorAll('.submit-once-spinner').forEach((spinner) => spinner.remove());
            button
                .querySelectorAll('.submit-once-hidden')
                .forEach((icon) => icon.classList.remove('d-none', 'submit-once-hidden'));
        });
    });
});
