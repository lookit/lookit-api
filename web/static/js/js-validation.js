function jsValidation(event, generator) {
    const jshint_config = { "esversion": 6 }

    // Remove existing error list
    document.querySelector('.js-validation')?.remove();

    // if jshint comes back with errors (false)
    if (!JSHINT(generator.value, jshint_config)) {
        const breadcrumb = document.querySelector('nav.breadcrumb');
        const errorsList = document.createElement('ul')
        const errorsMsg = document.createElement('div');

        // Don't submit the form and scroll to top of page.
        event.preventDefault();
        window.scrollTo(0, 0);

        // Errors are red
        errorsList.classList.add('text-danger', 'js-validation');

        // Error message has some space around it
        errorsMsg.classList.add('my-3');

        // Add error message
        errorsMsg.appendChild(document.createTextNode('Generator javascript seems to be invalid.  Please edit and save again. If you reload this page, all changes will be lost.'))
        errorsList.appendChild(errorsMsg);

        // Add errors to the list
        JSHINT.errors.map(({ line, reason }) => {
            const errorEl = document.createElement('ol');
            errorEl.innerHTML = `${line}: ${reason}`;
            errorsList.appendChild(errorEl);
        })

        // Add list to page after breadcrumb
        breadcrumb.after(errorsList);
    }
}
