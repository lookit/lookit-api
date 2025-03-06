$(".selectable-response").first().addClass('selected');
let currentResponseId = $(".selectable-response").first().data("response-id");
showResponse(1);
showFeedbackList(currentResponseId);
$('form.download [name=response_id]').val(currentResponseId);
showAttachments(1);

$('.selectable-response').click(function () {
    // Shows selected individual's response data
    const id = $(this)[0].id;
    const index = extractIdNumber(id);
    $('.selectable-response').removeClass('selected');
    $('#' + id).addClass('selected');
    showResponse(index);
    showAttachments(index);
    const responseId = $(this).data("response-id");
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

// Datatable init/config for responses table
const resp_table = $("#individualResponsesTable").DataTable({
    order: [[4, 'desc']], // Sort on "Date" column
    columnDefs: [
        // add class to text search columns
        { className: "column-text-search", targets: [1,2,3] }, 
        // For "Date" column, set type and don't wrap "Date" column. For "Time Elapsed" column, sort by "Date" column's data.
        { className: "dt-nowrap", type: "date", orderData: 4, targets: [4,5] }, 
    ],
    initComplete: function () {
        // Apply the text search to any column with the class "column-text-search"
        this.api()
            .columns(".column-text-search")
            .every(function () {
                let column = this;
                // Select input element for this column and apply search
                $('input', this.footer()).on('keyup change', function () {
                    if (column.search() !== this.value) {
                        column
                            .search(this.value)
                            .draw();
                        }
                    });
            });
    },
});

// Date Range UI and filter for "Date" column
setupDataTableDates("individualResponsesTable", 4, "dateRangeFilter");
