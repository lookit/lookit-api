// Update the referral link when a different lab is chosen, and copy it on click.
document.querySelectorAll('.referral-lab-select').forEach((select) => {
    select.addEventListener('change', () => {
        document.querySelector(select.dataset.target).value = select.value;
    });
});

if (!window.referralClipboard) {
    window.referralClipboard = new Clipboard('.referral-copy-button'); // NOSONAR
    window.referralClipboard.on('success', (event) => {
        const button = event.trigger;
        button.textContent = 'Copied!';
        setTimeout(() => { button.textContent = 'Copy'; }, 2000);
    });
}
