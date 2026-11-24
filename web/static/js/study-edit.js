$(document).ready(function () {
    $("#save-button").click(function () {
        // Check the form before asking for confirmation. Otherwise the browser's
        // "required field" check only runs from the modal's Save button, where its
        // message is hidden behind the modal.
        const form = document.getElementById("study-details-form");
        if (!form.checkValidity()) {
            form.reportValidity();
            return;
        }
        $("#invalidate-build-warning").hide();
        $("#save-study-confirmation-body").show();
        let runner_type_changed = $("#id_study_type").data("previous") != $("#id_study_type").val();
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
        bootstrap.Modal.getOrCreateInstance(document.getElementById("save-study-confirmation")).show();
    });
});
