function hideField(field) {
    $(`#id_${field}`).hide().prop('required', false);
    $(`#id_${field}`).parent('.form-group').hide(); // hide the parent form-group div
    $(`label[for=id_${field}]`).hide();
}

function showField(field) {
    $(`#id_${field}`).show();
    $(`#id_${field}`).parent('.form-group').show(); // show the parent form-group div
    $(`label[for=id_${field}]`).show();
}

// Show gender self describe when gener is "open response"
const $gender = $('#id_gender');
$gender.on('change', function () {
    if (this.value === 'o') {
        showField('gender_self_describe');
    } else {
        hideField('gender_self_describe');
        $('#id_gender_self_describe')[0].value = '';
    }
});
$gender.change();

// Show state field if US is selected in the country field.
const $country = $('#id_country');
$country.on('change', function () {
    // Show/hide state field based on USA or not
    if ($(this)[0].value === 'US') {
        showField('state');
    } else {
        hideField('state');
        $(`#id_state`)[0].value = '';
    }
});
$country.change();

// Show child birthdays field if child value is not zero or null.
const $numberOfChildren = $('#id_number_of_children');
$numberOfChildren.on('change', function () {
    if (this.value === "0" || this.value === '') {
        hideField('child_birthdays');
        $('.help-block').first().hide();
        $(`#id_child_birthdays`)[0].value = '';

    } else {
        showField('child_birthdays');
        $('.help-block').first().show();

    }
});
$numberOfChildren.change();

// Show guardian explanation if set number of guardians is "varies"
const $numberOfGuardians = $('#id_number_of_guardians');
$numberOfGuardians.on('change', function () {
    if (this.value === 'varies') {
        showField('guardians_explanation');
    } else {
        hideField('guardians_explanation');
        $('#id_guardians_explanation')[0].value = '';
    }
});
$numberOfGuardians.change();
