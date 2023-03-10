$(".selectable-participant").first().addClass('selected');
let currentResponseId = $(".selectable-participant").first().data("response-id");
showResponse(1);
showFeedbackList(currentResponseId);
$('form.download [name=response_id]').val(currentResponseId);
showAttachments(1);

$('.selectable-participant').click(function () {
    // Shows selected individual's response data
    var id = $(this)[0].id;
    var index = extractIdNumber(id);
    $('.selectable-participant').removeClass('selected');
    $('#' + id).addClass('selected');
    showResponse(index);
    showAttachments(index);
    var responseId = $(this).data("response-id");
    $('form.download [name=response_id]').val(responseId);
    showFeedbackList(responseId);
});

function showAttachments(index) {
    $('.response-attachments').hide();
    $('#resp-attachment-' + index).show();
}

function showFeedbackList(responseId) {
    $('.feedback-list').hide();
    $('form.feedback [name=response_id]').val(responseId);
    $(`#feedback-list-for-${responseId}`).show();
}

function extractIdNumber(id) {
    return id.split('-').slice(-1)[0];
}

function showResponse(index) {
    // Shows individual response summary
    $('.response-summary').hide();
    $('#response-summary-' + index).show();
}
