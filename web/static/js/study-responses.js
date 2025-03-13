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

function updateInfoBox(index) {
    // Select table rows of response details table.
    const rows = document
        .querySelector(`#response-summary-${index}`)
        ?.querySelectorAll('table tbody tr');

    if (!rows) return

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
    url.searchParams.set("recipient", parentUUID);

    // Short ID for child
    document.querySelector('.short-child-id').textContent =
        rows[15].children[1].textContent;

    // Create date for response with formatted date
    document.querySelector('.response-date').textContent = moment.utc(
        rows[2].children[1].textContent
    ).format('M/D/YYYY h:mm A z');

    // Parent Feedback
    document.querySelector('.parent-feedback').textContent =
        rows[6].children[1].textContent;

    // Send message to family URL
    document.querySelector('.parent-id').textContent = parentId;
    document.querySelector('.contact-family').href = url.toString();
}

// For updating the researcher-editable input elements in response table
function getCsrfTokenAndUrl() {
    const csrfTokenEl = document.querySelector('#csrftokenurl');
    const token = csrfTokenEl.value;
    const url = csrfTokenEl.dataset.updateUrl;
    return { token, url };
}

// Send the researcher-editable field/value to the server when the user changes those input elements
$('.researcher-editable').change(
    function (event) {
        const target = event.target;
        target.disabled = true;
        const currentResponseId = target.closest('tr').dataset.responseId;
        const fieldName = 'researcher_' + target.name.replace("-", "_");
        // The Star element's value is "on"/"off" but the database needs a boolean
        const fieldValue = (target.name == "star") ? target.checked : target.value;
        const data = {
            responseId: currentResponseId,
            field: fieldName,
            value: fieldValue
        };

        const { token, url } = getCsrfTokenAndUrl();

        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': token
            },
            body: JSON.stringify(data)
        })
            .then(response => {
                if (!response.ok) {
                    // If the response is not successful then parse the JSON for the error message and re-throw
                    return response.json().then(errorData => {
                        const errMsg = (errorData && errorData.error) ? errorData.error : "Request to update a response field has failed.";
                        throw new Error(errMsg);
                    });
                }
                return response.json();
            })
            .then(data => {
                target.disabled = false;
                updateAJAXCellData(target);
                if (data.success) console.log(data.success);
            })
            .catch(error => {
                // If the update fails, log the reason to the console and revert to the previous value by reloading the page.
                console.error(error);
                location.reload();
            });
    }
);

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

function showHideColumns() {
    // Elements containing links 
    const show_hide_columns = [{ col: 3, name: "Date" }, { col: 4, name: "Time Elapsed" }, { col: 5, name: "Exit Frame Status" }, { col: 6, name: "Payment Status" }, { col: 7, name: "Session Status" }, { col: 8, name: "Star" }]
    const hide_show_elements = show_hide_columns.map(el => {
        return `<a href class="toggle-vis" data-column="${el.col}">${el.name}</a>`
    })
    document.querySelector('.show-hide-cols').innerHTML = `Show/Hide: ${hide_show_elements.join(" | ")}`

    // Click event listener on the above links
    document.querySelectorAll('a.toggle-vis').forEach(el => {
        el.addEventListener('click', e => {
            e.preventDefault();
            const columnIdx = e.target.dataset.column;
            const column = resp_table.column(columnIdx);
            column.visible(!column.visible());
        });
    })

}

function filterText(table) {
    // Apply the text search to any column with the class "column-text-search"
    table.api()
        .columns(".column-text-search")
        .every(function () {
            let column = this;
            // Select input element for this column and apply search
            $('input', this.footer()).on('keyup change', function () {
                if (column.search() !== this.value) {
                    column.search(this.value).draw();
                }
            });
        });
}

function filterDropdown(table) {
    table.api()
        .columns(".column-dropdown-search")
        .every(function () {
            const column = this;
            $('select', this.footer()).on('change', function () {
                const text = this.options[this.selectedIndex].text
                if (column.search() !== text) {
                    column.search(text, { exact: true }).draw();
                }
            });
        });
}

function dateColRender(data, type) {
    switch (type) {
        case "display":
            const [date, time, amPm] = data.split(" ");
            return `<div>${date}</div><div>${time} ${amPm}</div>`;
        default:
            return data

    }
}

// Datatable init/config for responses table
const resp_table = $("#individualResponsesTable").DataTable({
    layout: {
        topStart: null,
        topEnd: null,
        top: ['pageLength',
            { features: [{ div: { className: 'show-hide-cols text-center mx-3' } }] },
            'search'],
    },
    order: [[3, 'desc']], // Sort on "Date" column
    columnDefs: [
        { className: "column-text-search", targets: [1, 2, 4] }, // add class to text search columns
        { className: "column-dropdown-search", targets: [5, 6, 7] }, // add class to dropdown search columns
        { orderData: 3, targets: [3, 4] }, // Sort "Time Elapsed" by "Date" column's data.
        { targets: 3, type: 'date', render: dateColRender}
    ],
    initComplete: function () {
        filterText(this);
        filterDropdown(this);
        showHideColumns();
    },
});

// Date Range UI and filter for "Date" column
setupDataTableDates("individualResponsesTable", 3, "dateRangeFilter");

function updateAJAXCellData(target) {
    const classes = target.classList
    const td = target.parentElement

    if (classes.contains("dropdown-cell")) {
        const text = target.options[target.selectedIndex].text;
        td.dataset.sort = text;
        td.dataset.filter = text;
    } else if (classes.contains("star-checkbox")) {
        td.querySelectorAll('.icon-star').forEach(el => {
            el.classList.toggle('icon-hidden')
        })
        td.dataset.sort = "False" == td.dataset.sort ? "True" : "False"
    }

    resp_table.rows().invalidate("dom").draw(false);
}
