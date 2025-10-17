/* Fix for ace-editor. It thinks it's in the admin only */
(function (){
    if (window.jQuery !== undefined) {
        window.django = {
            'jQuery': window.jQuery
        };
    }
})();

$(document).ready(function() {
    $('form#study-details-form').submit(function() {
        $('#create-study-button').prop("disabled", "disabled");
    });
});
