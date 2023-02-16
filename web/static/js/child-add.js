
$('.datepicker').datepicker({
    changeMonth: true,
    changeYear: true,
    showButtonPanel: true,
    maxDate: 0,
    yearRange: "1900:+nn"
}).on('change', function () {
    const age = getAge(this);
    if (document.getElementById('age_calc')) {
        document.getElementById('age_calc').innerHTML = `Age: ${age}`;
    } else {
        const x = document.createElement("p");
        x.setAttribute("id", "age_calc");
        x.setAttribute("class", "age_format")
        const t = document.createTextNode(`Age: ${age}`);
        x.appendChild(t);
        document.getElementById("id_birthday").parentNode.insertBefore(x, document.getElementById("id_birthday"));
    }
});


function getAge(dateValue) {
    if (dateValue.value === '') {
        return '{% trans "Empty birthday" %} '
    }
    const years = moment().diff(new Date(dateValue.value), 'years');
    if (years === 0) {
        const months = moment().diff(new Date(dateValue.value), 'months');
        if (months === 0) {
            const days = moment().diff(new Date(dateValue.value), 'days');
            return days === 1 ? days + " day" : days + " days";
        }
        return months === 1 ? months + " month" : months + " months";
    } else {
        return years === 1 ? years + " year" : years + " years";
    }
}
