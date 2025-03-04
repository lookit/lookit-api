$(".selectable-response").first().addClass('selected');
let currentResponseId = $(".selectable-response").first().data("response-id");
showResponse(1);
updateInfoBox(1)
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
    updateInfoBox(index);
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
        { className: "column-text-search", targets: [1,2,3] }, // add class to text search columns
        { className: "dt-nowrap", "targets": 4 }, // don't wrap "Date" column
        { type: "date", targets: 4 } // set type for "Date" column
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

function updateInfoBox(index) {
  // Select table rows of response details table.
  const rows = document
    .querySelector(`#response-summary-${index}`)
    .querySelectorAll('table tbody tr');

  // construct parent ID
  const parentName = rows[13].children[1].textContent
    .toLowerCase()
    .split(" ")
    .map(el => ([...el]
      .filter(v => /[a-z\-]/.test(v)))
      .join(""))
    .join("-");
  const parentId = `${rows[12].children[1].textContent}-${parentName || "anonymous"}`;
  const parentUUID = rows[11].children[1].textContent
  
  // Recipient ID for sending message URL
  const url = new URL(document.querySelector('.contact-family').href);
  url.searchParams.set("recipient",parentUUID);

  // Short ID for child
  document.querySelector('.short-child-id').textContent =
    rows[15].children[1].textContent;

  // Create date for response with formatted date
  document.querySelector('.response-date').textContent = moment(
    rows[2].children[1].textContent
  ).format('M/D/YYYY h:m A');

  // Parent Feedback
  document.querySelector('.parent-feedback').textContent =
    rows[6].children[1].textContent;

  // Send message to family URL
  document.querySelector('.parent-id').textContent = parentId;
  document.querySelector('.contact-family').href = url.toString();
}
