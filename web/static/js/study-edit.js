/* Fix for ace-editor. It thinks it's in the admin only */
(function (){
    if (window.jQuery !== undefined) {
        window.django = {
            'jQuery': window.jQuery
        };
    }
})();

$(document).ready(function() {
    $("#save-button").click(function () {
        $("#invalidate-build-warning").hide();
        $("#save-study-confirmation-body").show();
        var runner_type_changed = $("#id_study_type").data("previous") != $("#id_study_type").val();
        $("#study-type-metadata div.metadata-key").each(function (index, element) {
            runner_type_changed = runner_type_changed || $(element).data("previous") != $("input", element).val();
        });
        if (runner_type_changed) {
            $("#invalidate-build-warning").show();
        } else {
            let save_study_confirmation_empty = true;
            $("#save-study-confirmation-body")
            .children()
            .each(function () {
                if (!($(this).css("visibility") == "hidden" || $(this).css("display") == "none")) {
                    save_study_confirmation_empty = false;
                }
            });
            if (save_study_confirmation_empty) {
                $("#save-study-confirmation-body").hide();
            }
        }
    });
});