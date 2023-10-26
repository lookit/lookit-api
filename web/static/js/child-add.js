function getAge() {
    const day = document.getElementById('id_birthday_day').value
    const month = document.getElementById('id_birthday_month').value
    const year = document.getElementById('id_birthday_year').value
    const birthday = new Date(`${month}/${day}/${year}`);

    const years = moment().diff(birthday, 'years');
    if (years === 0) {
        const months = moment().diff(birthday, 'months');
        if (months === 0) {
            const days = moment().diff(birthday, 'days');
            return days === 1 ? days + " day" : days + " days";
        }
        return months === 1 ? months + " month" : months + " months";
    } else {
        return years === 1 ? years + " year" : years + " years";
    }
}

function createAgeText() {
    const birthdayWidget = document.querySelector('.birthday-widget');
    const p = document.createElement("p");
    p.setAttribute("id", "age_calc");
    p.setAttribute("class", "age_format");
    birthdayWidget.parentNode.insertBefore(p, birthdayWidget);
}


function updateAgeText() {
    const age = getAge();
    const p = document.getElementById("age_calc");
    p.textContent = `Age: ${age}`;
}

/***
 * Page Load
 */
createAgeText();

/**
 * Event Listeners
 */
document.querySelectorAll('#id_birthday_day, #id_birthday_month, #id_birthday_year').forEach(function (el) {
    el.addEventListener('change', updateAgeText)
});
