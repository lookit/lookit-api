const RESET = "reset",
    CONSENT_PENDING = "pending",
    CONSENT_APPROVAL = "accepted",
    CONSENT_REJECTION = "rejected",
    RESPONSE_KEY_VALUE_STORE = JSON.parse(document.querySelector("#response-key-value-store").innerText),
    COMMENTS_CACHE = {};

$(document).ready(function () {
    /*
     Initialize important elements. $-prepended elements indicate jQuery element.
     */
    // Element Members.
    const $videoElement = $("#video-under-consideration"),
        $videoSource = $videoElement.find("source"),
        $videoManager = $("#video-manager"),
        $videoPreviousButton = $videoManager.find("#nav-video-previous"),
        $videoNextButton = $videoManager.find("#nav-video-next"),
        $currentVideoInfo = $("#current-video-information"),
        $currentSurveyConsentInfo = $("#current-survey-consent-information"),
        $responseComments = $("#response-commentary"),
        $responseStatusFilter = $("#response-status-filters"),
        $listOfResponses = $("#list-of-responses"),
        $consentRulingForm = $("#consent-ruling-form"),
        $approvalsCountBadge = $(".approvals-count"),
        $rejectionsCountBadge = $(".rejections-count"),
        $pendingCountBadge = $(".pending-count"),
        $commentsHiddenInput = $consentRulingForm.find("input[name='comments']"),
        $resetChoicesButton = $consentRulingForm.find("#reset-choices"),
        $responseDataSection = $("#response-info-container"),
        $generalHeader = $responseDataSection.find("table#general thead tr"),
        $generalRow = $responseDataSection.find("table#general tbody tr"),
        $participantRow = $responseDataSection.find("table#participant tbody tr"),
        $childRow = $responseDataSection.find("table#child tbody tr");

    // Lazily initialized closures (mutable members).
    let currentlyConsideredVideos,
        currentVideoListIndex,
        numberedVideoButtons,
        $currentlySelectedResponse; // jQuery container for response li.

    /*
     Call functions to set components to initial state.
    */
    applyFilterParametersToResponseList(CONSENT_PENDING);
    $('[data-toggle="tooltip"]').tooltip();

    applyFilterParametersToResponseList($responseStatusFilter.val());

    /*
     "Controller methods" - using closures to mimic class-like behavior.
     */
    function updateBadges() {
        $approvalsCountBadge.text($(`.consent-ruling[name=${CONSENT_APPROVAL}]`).length);
        $rejectionsCountBadge.text($(`.consent-ruling[name=${CONSENT_REJECTION}]`).length);
        $pendingCountBadge.text($(`.consent-ruling[name=${CONSENT_PENDING}]`).length);
    }

    function saveComments() {
        let currentText = $responseComments.val();
        if (currentText && $currentlySelectedResponse) {
            COMMENTS_CACHE[$currentlySelectedResponse.data("id")] = $responseComments.val();
        }
    }

    function retrieveComments() {
        $responseComments.val(COMMENTS_CACHE[$currentlySelectedResponse.data("id")] || "");
    }

    function applyFilterParametersToResponseList(stateToToggle) {
        let $responseOptions = $listOfResponses.find(".response-option"),
            $toShow = $responseOptions.filter(`.${stateToToggle}`),
            $toHide = $responseOptions.not(`.${stateToToggle}`);

        $toShow.show();
        $toHide.hide();

        // Start out with no response selected
        $currentVideoInfo.text("Please select a response from the list on the left.");
        $currentVideoInfo.parent().removeClass("bg-danger bg-warning");
        $videoElement.css("visibility", "hidden");
        $responseComments.addClass("d-none");
        $currentSurveyConsentInfo.addClass("d-none");
    }

    function handleRulingActions($button, $responseListItem, responseData) {
        let responseId = responseData["id"],
            responseRulingHiddenInputId = "consent-ruling-" + responseId,
            hiddenInputAttrs = { id: responseRulingHiddenInputId, type: "hidden" },
            $hiddenInput = $consentRulingForm.find("#" + responseRulingHiddenInputId),
            $optionList = $button.closest("ul"),
            $resetButton = $optionList.find(".consent-judgment[data-action=reset]"),
            $responseActor = $optionList.siblings("button"),
            action = $button.data("action");

        // First, change the UI signaling in the pending list.
        switch (action) {
            case RESET:
                $responseListItem.removeClass(
                    "list-group-item-danger list-group-item-success list-group-item-warning");
                // if already pending, just break out early after updating badges.
                $hiddenInput.remove();
                $resetButton.hide();
                // Gross but whatever - jquery's .text() blows out the other sibling DOM.
                $responseActor.contents()[0].textContent = responseData["originalStatus"] + " ";
                updateBadges();
                return;
            case CONSENT_APPROVAL:
                $responseListItem.removeClass("list-group-item-danger list-group-item-warning");
                $responseListItem.addClass("list-group-item-success");
                hiddenInputAttrs["name"] = CONSENT_APPROVAL;
                break;
            case CONSENT_REJECTION:
                $responseListItem.removeClass("list-group-item-success list-group-item-warning");
                $responseListItem.addClass("list-group-item-danger");
                hiddenInputAttrs["name"] = CONSENT_REJECTION;
                break;
            case CONSENT_PENDING:
                $responseListItem.removeClass("list-group-item-danger list-group-item-success");
                $responseListItem.addClass("list-group-item-warning");
                hiddenInputAttrs["name"] = CONSENT_PENDING;
                break;
        }

        // Now, either change or add the hidden form input.
        if ($hiddenInput.length) {
            $hiddenInput.attr("name", hiddenInputAttrs["name"]);
        } else {  // If it's not there, create a new one...
            hiddenInputAttrs["value"] = responseId;
            $consentRulingForm.append($("<input />", hiddenInputAttrs).addClass("consent-ruling"));
        }

        // ... Finally, update the UI with whatever approval state was changed.
        $resetButton.show();
        $responseActor.contents()[0].textContent = action + " ";
        updateBadges();
    }


    function updateVideoContainer(responseData) {
        // 1) Clear the current container
        $videoPreviousButton.nextUntil($videoNextButton).remove();
        $currentSurveyConsentInfo.parent().removeClass("bg-warning");

        currentlyConsideredVideos = responseData["videos"];
        currentVideoListIndex = 0;

        // 2) Reset video buttons.
        numberedVideoButtons = []; // Empty out current set of buttons.
        currentlyConsideredVideos.forEach((videoObject, index) => {
            videoObject["pointer"] = index;
            let $numberedVideoButton = $("<li></li>").data(videoObject);
            $numberedVideoButton.append(
                $('<a class="page-link" ></a>').text(index + 1)
            );
            numberedVideoButtons.push($numberedVideoButton);
        });
        $videoPreviousButton.after(numberedVideoButtons);

        if (currentlyConsideredVideos.length) { // Auto-set first video.
            let awsUrl = currentlyConsideredVideos[0]["aws_url"];
            $videoElement.css("visibility", "visible");
            $videoSource.attr("src", awsUrl);
            numberedVideoButtons[0].addClass("active");
            $videoElement.trigger("load").trigger("play");
        } else {
            $videoElement.css("visibility", "hidden");
            $currentVideoInfo.text("No video found for this response.");
            $currentVideoInfo.parent().addClass("bg-warning");
        }
    }

    function updateResponseDataSection(responseData) {
        let details = responseData["details"];

        $generalHeader.empty();
        $generalRow.empty();
        $generalHeader.append(Array.from(Object.keys(details["general"]), val => $(`<th>${val.split('_').map((s) => s.charAt(0).toUpperCase() + s.substring(1)).join(' ')}</th>`)));
        $generalRow.append(Array.from(Object.values(details["general"]), val => $(`<td>${val}</td>`)));

        $participantRow.empty();
        $participantRow.append(Array.from(Object.values(details["participant"]), val => $(`<td>${val}</td>`)));

        $childRow.empty();
        $childRow.append(Array.from(Object.values(details["child"]), val => $(`<td>${val}</td>`)));
    }

    function updateSurveyConsentFlag(responseElement) {

        // Show a survey-consent message if this response has a survey-consent frame
        if (responseElement.find('#survey-consent-msg').length > 0) {
            $currentSurveyConsentInfo.parent().addClass("bg-warning");
            $currentSurveyConsentInfo.removeClass("d-none");
        } else {
            // Hide the survey-consent message
            $currentSurveyConsentInfo.addClass("d-none");
        }
    }

    /*
     EVENT LISTENERS.
     XXX: Lots of manual event delegation, to account for constantly-updating elements.
     */
    $responseStatusFilter.on("change", function (event) {
        applyFilterParametersToResponseList($responseStatusFilter.val());
    });

    $listOfResponses.on("click", ".response-option", function (event) {

        // UI Signal - we're paying attention to this video.
        if ($currentlySelectedResponse) { // If we've got something, deselect it.
            $currentlySelectedResponse.removeClass("active");
            $videoElement.trigger("pause");
        }

        // Keep these in order for now, figure out a clean way to factor this out later.
        saveComments();
        $currentlySelectedResponse = $(this);
        retrieveComments();
        $responseComments.removeClass("d-none");

        $currentlySelectedResponse.addClass("active");

        let $target = $(event.target);
        let responseData = $currentlySelectedResponse.data();

        // If it's consent or approval, deal with it.
        if ($target.is(".dropdown-menu .consent-judgment")) {
            handleRulingActions($target, $currentlySelectedResponse, responseData);
        } else { // Update the video container with nav buttons.
            let responseObjects = RESPONSE_KEY_VALUE_STORE[responseData["id"]];
            updateVideoContainer(responseObjects);
            updateResponseDataSection(responseObjects);
            updateSurveyConsentFlag($currentlySelectedResponse);
        }
    });

    $videoManager.on("click", "li", function (event) {
        // Early exit if there's less than two videos.
        if (!currentlyConsideredVideos || currentlyConsideredVideos.length < 2) {
            return;
        }

        // Otherwise, get started.
        let $videoNavButton = $(this),
            navId = $videoNavButton.attr("id"),
            length = currentlyConsideredVideos.length,
            videoData, awsUrl;

        numberedVideoButtons.forEach($button => $button.removeClass("active"));

        if (navId === "nav-video-previous") {
            currentVideoListIndex -= 1;
            currentVideoListIndex %= length; // rotate backward,
            videoData = currentlyConsideredVideos[currentVideoListIndex];
        } else if (navId === "nav-video-next") {
            currentVideoListIndex += 1;
            currentVideoListIndex %= length; // rotate forward,
            videoData = currentlyConsideredVideos[currentVideoListIndex];
        } else {
            videoData = $videoNavButton.data(); // or get the actual index from the element data.
            currentVideoListIndex = videoData["pointer"];
        }

        // Mark currently active video.
        numberedVideoButtons[currentVideoListIndex].addClass("active");

        awsUrl = videoData["aws_url"];
        $videoSource.attr("src", awsUrl);
        $videoElement.trigger("load").trigger("play");
    });

    $consentRulingForm.submit(function (event) {
        // Create comments JSON and append to form.
        saveComments();
        $commentsHiddenInput.val(JSON.stringify(COMMENTS_CACHE));
    });

    $resetChoicesButton.on("click", function () {
        $listOfResponses.find(".response-option").removeClass(
            "list-group-item-danger list-group-item-success list-group-item-warning");
        $consentRulingForm.find("input.consent-ruling").remove();
        updateBadges();
    });

    $videoSource.on("error", function (event) {
        if ($videoSource.attr("src").length) {
            $currentVideoInfo.text("The video is not loading; the link probably timed out. Try refreshing this page.");
            $currentVideoInfo.parent().addClass("bg-danger")
        } else {
            $currentVideoInfo.text("Please select a response from the list on the left.");
        }
    });

    $videoElement.on("canplay", function () {
        let currentVideo = currentlyConsideredVideos[currentVideoListIndex],
            timeString = new Date(parseInt(currentVideo["filename"].split("_")[4])).toLocaleString();
        $currentVideoInfo.text("Processed: " + timeString);
        // Remove the danger/warning class on the parent div, unless this response has a survey-consent frame warning
        let responseElement = $('.response-option.active');
        if (responseElement && responseElement.find('#survey-consent-msg').length == 0) {
            $currentVideoInfo.parent().removeClass("bg-danger bg-warning");
        }
    });
});
