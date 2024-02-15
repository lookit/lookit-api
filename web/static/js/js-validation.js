function jsValidation(event, generator) {
    const jsValidation = document.querySelector('.js-validation');
    try {
        Babel.transform(generator.value, { presets: ["env"] });
        jsValidation.classList.add('d-none');
    } catch ({ message }) {
        // Remove existing errors
        document.querySelectorAll('.js-validation pre').forEach(el => el.remove());

        // Show errors element
        jsValidation.classList.remove('d-none');

        // Don't submit the form and scroll to top of page.
        event.preventDefault();
        window.scrollTo(0, 0);

        // Add error message
        const errorEl = document.createElement('pre');
        errorEl.innerHTML = message;
        jsValidation.appendChild(errorEl);
    }
}
