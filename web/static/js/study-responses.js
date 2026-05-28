const hasMaxResponses = document.getElementById('tallyConfirmModal') !== null;
const isExternal = document.getElementById('filter-exit-status') === null;

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
    flashCard(document.getElementById('selected-response-card'));
    flashCard(document.getElementById(`response-summary-${index}`));
    flashCard(document.getElementById(`response-status-container-${index}`));
});

// Scroll to the response-status-container when clicking the tally status cell (first column)
if (hasMaxResponses) {
    $('#individualResponsesTable').on('click', 'tbody tr td:first-child', function () {
        const row = $(this).closest('tr');
        const index = extractIdNumber(row[0].id);
        const container = document.getElementById(`response-status-container-${index}`);
        if (container) {
            container.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
}

if (hasMaxResponses) document.getElementById('tallyConfirmModal').addEventListener('show.bs.modal', function (event) {
    const button = event.relatedTarget;
    const responseId = button.dataset.responseId;
    const responseIndex = button.dataset.responseIndex;
    const checkbox = document.getElementById(`tallied-checkbox-${responseIndex}`);
    const currentlyTallied = checkbox ? checkbox.checked : false;
    const newValue = !currentlyTallied;

    const statusWord = currentlyTallied ? 'tallied' : 'not tallied';
    const actionWord = currentlyTallied ? 'untally' : 'tally';
    let additional_text = '<div></div>';
    if (currentlyTallied) {
        // additional text if changing tallied to untallied
        additional_text = '<div class="text-muted mt-3">Responses should be tallied if:<ul><li>The correct child participated</li><li>The child was eligible for the study</li><li>The family participated in good faith (not a confirmed scammer)</li></ul>This is true even if you are not able to use this response in your analysis, for instance because the child was fussy or there were technical problems.';
        if (isExternal) {
            additional_text += '<br><br>For external studies, you may un-tally a response if, in this response session, the family:<ul><li>Did not complete the study (asynchronous studies)</li><li>Did not schedule a time to participate (synchronous studies)</li></ul>';
        }
        additional_text += '</div>';
    }
    document.getElementById('tallyConfirmModalLabel').textContent =
        `Change tallied status of response ${responseId}`;
    document.getElementById('tallyConfirmModalBody').innerHTML =
        `<div class="fs-5 text-center">This response is currently <strong>${statusWord}</strong>.<br>Are you sure you want to <strong>${actionWord}</strong> it?</div>` + additional_text;

    const updateBtn = document.getElementById('tallyConfirmModalUpdateBtn');
    updateBtn.dataset.pendingResponseId = responseId;
    updateBtn.dataset.pendingResponseIndex = responseIndex;
    updateBtn.dataset.pendingValue = newValue;
});

if (hasMaxResponses) document.getElementById('tallyConfirmModalUpdateBtn').addEventListener('click', function () {
    const responseId = this.dataset.pendingResponseId;
    const responseIndex = this.dataset.pendingResponseIndex;
    const newValue = this.dataset.pendingValue === 'true';

    bootstrap.Modal.getInstance(document.getElementById('tallyConfirmModal')).hide();

    const { token, url } = getCsrfTokenAndUrl();

    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': token
        },
        body: JSON.stringify({ responseId, field: 'is_tallied', value: newValue })
    })
        .then(response => {
            if (!response.ok) {
                return response.json().then(errorData => {
                    const errMsg = errorData?.error ??
                        `Request to update tallied status has failed for response ${responseId}.`;
                    throw new Error(errMsg);
                });
            }
            return response.json();
        })
        .then(data => {
            const checkbox = document.getElementById(`tallied-checkbox-${responseIndex}`);
            if (checkbox) {
                checkbox.checked = newValue;
                updateAJAXCellData(checkbox);
            }
            // Manually change the 'researcher override' value on the tally status card, as this info is only set on page load
            const researcher_override_row = document.getElementById(`resp-status-researcher-override-${responseId}`);
            if (newValue) {
                researcher_override_row.classList.add('list-group-item-success');
                researcher_override_row.querySelector('td.resp-status-value').innerHTML = 'Tallied';
            } else if (newValue === false) {
                researcher_override_row.classList.add('list-group-item-danger');
                researcher_override_row.querySelector('td.resp-status-value').innerHTML = 'Untallied';
            }
            // Update the tally status title via show response (which gets the tally/untally value via the checkbox for this response, which has been modified)
            showResponse(responseIndex);
            if (data.counts) {
                document.getElementById('count-tallied').textContent = data.counts.tallied;
                document.getElementById('count-untallied').textContent = data.counts.untallied;
                document.getElementById('count-preview').textContent = data.counts.preview;
                const approvedEl = document.getElementById('count-tallied-approved');
                const pendingEl = document.getElementById('count-tallied-pending');
                if (approvedEl) approvedEl.textContent = data.counts.tallied_approved;
                if (pendingEl) pendingEl.textContent = data.counts.tallied_pending;
            }
            const container = document.getElementById('is-tallied-toast-container');
            const toast = document.createElement('div');
            toast.className = `toast align-items-center border-0 ${newValue ? 'text-bg-success' : 'text-bg-secondary'}`;
            toast.setAttribute('role', 'status');
            toast.innerHTML = `<div class="d-flex">
                <div class="toast-body">${newValue ? `Response ${responseId} marked as tallied.` : `Response ${responseId} marked as not tallied.`}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>`;
            container.appendChild(toast);
            const bsToast = new bootstrap.Toast(toast, { delay: 5000 });
            toast.addEventListener('hidden.bs.toast', () => toast.remove());
            bsToast.show();
            if (data.message) showWarningToast(data.message);
            if (data.success) console.log(data.success);
        })
        .catch(error => {
            console.error(error);
            showErrorToast(error.message || 'Something went wrong. The tally status change failed.');
        });
});

function showWarningToast(message) {
    const container = document.getElementById('is-tallied-toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast align-items-center border-0 text-bg-warning';
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `<div class="d-flex">
        <div class="toast-body">${message}</div>
        <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
    </div>`;
    container.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast, { autohide: false });
    toast.addEventListener('hidden.bs.toast', () => toast.remove());
    bsToast.show();
}

function showErrorToast(message) {
    const container = document.getElementById('is-tallied-toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast align-items-center border-0 text-bg-danger';
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `<div class="d-flex">
        <div class="toast-body">${message}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
    </div>`;
    container.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast, { autohide: false });
    toast.addEventListener('hidden.bs.toast', () => toast.remove());
    bsToast.show();
}

function flashCard(el) {
    if (!el) return;
    el.classList.remove('card-highlight');
    el.getBoundingClientRect(); // force reflow so animation restarts
    el.classList.add('card-highlight');
    el.addEventListener('animationend', () => el.classList.remove('card-highlight'), { once: true });
}

function updateInfoBox(index) {
    // TO DO: fix this to remove the use of row/list indicies for getting info from summary table
    // Select table rows of response details table.
    const rows = document
        .querySelector(`#response-summary-${index}`)
        ?.querySelectorAll('table tbody tr');
    // Select row from responses table
    const selected_response = document.querySelector(`tr#response-${index}`);

    if (!rows || !selected_response) return

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

    // Response ID, child short ID, and date
    document.querySelector('.response-id').textContent =
        `Response ${selected_response.dataset.responseId}, `;
    document.querySelector('.short-child-id').textContent =
        `Child ${selected_response.children[1].textContent}`;
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

// Capture the current value of selects before the user changes them, so we can revert on failure
$('.researcher-editable').on('mousedown', function () {
    if (this.type !== 'checkbox') {
        this.dataset.previousValue = this.value;
    }
});

// Send the researcher-editable field/value to the server when the user changes those input elements
$('.researcher-editable').change(
    function (event) {
        const target = event.target;
        const previousValue = (target.type === 'checkbox') ? !target.checked : target.dataset.previousValue;
        target.disabled = true;
        const currentResponseId = target.closest('tr').dataset.responseId;
        const fieldName = target.dataset.field || ('researcher_' + target.name.replace("-", "_"));
        // Checkbox elements' values are "on"/"off" but the database needs a boolean
        const fieldValue = (target.type === "checkbox") ? target.checked : target.value;
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
                    // to send this to the .catch block.
                    return response.json().then(errorData => {
                        const errMsg = errorData?.error ?? `Request to update a response field has failed for response ${currentResponseId}.`;
                        throw new Error(errMsg);
                    });
                }
                return response.json();
            })
            .then(data => {
                target.disabled = false;
                updateAJAXCellData(target);
                if (data.success) console.log(data.success);
                if (fieldName === 'is_valid') {
                    const container = document.getElementById('is-valid-toast-container');
                    const toast = document.createElement('div');
                    toast.className = `toast align-items-center border-0 ${fieldValue ? 'text-bg-success' : 'text-bg-secondary'}`;
                    toast.setAttribute('role', 'status');
                    toast.innerHTML = `<div class="d-flex">
                        <div class="toast-body">${fieldValue ? `Response ${currentResponseId} marked as valid.` : `Response ${currentResponseId} marked as invalid.`}</div>
                        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                    </div>`;
                    container.appendChild(toast);
                    // or use { autohide: false } if we want the message to stay until manually dismissed
                    const bsToast = new bootstrap.Toast(toast, { delay: 5000 });
                    toast.addEventListener('hidden.bs.toast', () => toast.remove());
                    bsToast.show();
                }
            })
            .catch(error => {
                target.disabled = false;
                if (target.type === 'checkbox') {
                    target.checked = previousValue;
                } else {
                    target.value = previousValue;
                }
                console.error(error);
                showErrorToast(error.message || 'Something went wrong. The response update failed.');
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
    if (hasMaxResponses) {
        // Shows individual response tallied/untallied status container and sets title based on current tallied status
        $('.response-status-container').hide();
        $('#response-status-container-' + index).show();
        const resp_status = document.querySelector(`tr#response-${index}`).children[0].dataset.filter;
        document.querySelector('span#response-status-title-' + index).textContent = (resp_status == "Preview" || resp_status == "Untallied ✘") ? "Not tallied ✘" : "Tallied ✔";
    }
}

function showHideColumns() {
    // Elements containing links
    const show_hide_columns = isExternal
        ? [{ col: 3, name: "Date" }, { col: 4, name: "Time Elapsed" }, { col: 5, name: "Payment Status" }, { col: 6, name: "Session Status" }, { col: 7, name: "Star" }]
        : [{ col: 3, name: "Date" }, { col: 4, name: "Time Elapsed" }, { col: 5, name: "Exit Frame Status" }, { col: 6, name: "Payment Status" }, { col: 7, name: "Session Status" }, { col: 8, name: "Star" }]
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
    order: [[2, 'desc']], // Sort on "Response ID" column (most recent first). Sorting on Date doesn't work as expected.
    columnDefs: [
        { className: "column-text-search", targets: [1, 2, 4] }, // add class to text search columns
        { className: "column-dropdown-search", targets: isExternal ? [0, 5, 6, 7] : [0, 5, 6, 7, 8] }, // add class to dropdown search columns
        // This tells datatables to sort "Time Elapsed" and "Date" by "Response ID" column's data. Date sorting isn't working (it doesn't take the full timestamp into account). The right way to do this is to pass the full timestamp into the template and tell datatables how to parse and display it, but I couldn't get that to work (docs https://datatables.net/examples/datetime/.)
        { orderData: 2, targets: [2, 3, 4] },
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
            el.classList.toggle('icon-star-filled')
        })
        td.dataset.sort = "False" == td.dataset.sort ? "True" : "False"
        // JS uses unicode rather than HTML &# chars. &#9733; = \u2605, &#9734; = \u2606
        td.dataset.filter = target.checked ? "Starred \u2605" : "Unstarred \u2606"
    } else if (classes.contains("tallied-checkbox")) {
        td.dataset.sort = "False" == td.dataset.sort ? "True" : "False"
        // JS uses unicode rather than HTML &# chars. &#10004; = \u2714, &#10008; = \u2718
        td.dataset.filter = target.checked ? "Tallied \u2714" : "Untallied \u2718"
    }

    resp_table.rows().invalidate("dom").draw(false);
}
