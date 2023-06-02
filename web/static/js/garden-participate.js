document.getElementById('garden-studies-link').addEventListener('click', (e) => {
    e.preventDefault();
    e.stopImmediatePropagation();
    e.stopPropagation();
    window.location.href = e.target.href;
});
