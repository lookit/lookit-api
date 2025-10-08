function handleVideoRotation(event) {
    const button = event.target;
    const video = button.parentElement.children[0];

    // This actually works.
    // See: https://stackoverflow.com/questions/7742305/changing-the-order-of-elements
    video.appendChild(video.firstElementChild);
    button.querySelector('span.video-number').innerHTML = video.firstElementChild.dataset['index'];

    video.load();
}

document.querySelectorAll('button.next-video').forEach(el => el.addEventListener('click', handleVideoRotation));

// Set active tab based on which "tabs" radio button is checked.
const checked_radio = document.querySelector('input[name=past_studies_tabs]:checked')
const active_tab = document.querySelector(`[data-value="${checked_radio.value}"] a`)
active_tab.classList.add('active')

// On click, update radio group 
document.querySelectorAll('[role=past_studies_tabs]').forEach(function (tab) {
    tab.addEventListener('click', function (event) {
        event.preventDefault()
        const radio = document.querySelector(`[name="past_studies_tabs"][value="${tab.dataset.value}"]`)
        if (!radio.hasAttribute('checked')) {
            radio.checked = true
            document.querySelector('form#past-studies-tabs-form').submit()
        }
    })
})
