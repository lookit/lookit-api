function jsValidation(event, generator) {
    const jshint_config = { "esversion": 6, "sub": true };
    const jsValidation = document.querySelector('.js-validation');

    // if jshint comes back with errors (false)
    if (!JSHINT(generator.value, jshint_config)) {
        // Show errors element
        jsValidation.classList.remove('d-none');

        // Remove existing errors
        document.querySelectorAll('.js-validation ol').forEach(el => el.remove());

        // Don't submit the form and scroll to top of page.
        event.preventDefault();
        window.scrollTo(0, 0);

        // Add errors to the list
        JSHINT.errors.map(({ line, reason }) => {
            const errorEl = document.createElement('ol');
            errorEl.innerHTML = `${line}: ${reason}`;
            jsValidation.appendChild(errorEl);
        });
    } else {
        jsValidation.classList.add('d-none');
    }
}
