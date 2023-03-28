// Date Range UI for "Date Sent" column filter
$('input[name="daterange"]').daterangepicker({
    ranges: {
        'Today': [moment().startOf('day'), moment()],
        'Yesterday': [moment().subtract(1, 'day').startOf('day'), moment().subtract(1, 'days').endOf('day')],
        'Last 7 Days': [moment().subtract(6, 'days'), moment()],
        'Last 30 Days': [moment().subtract(29, 'days'), moment()],
        'This Month': [moment().startOf('month'), moment().endOf('month')],
        'Last Month': [moment().subtract(1, 'month').startOf('month'), moment().subtract(1, 'month').endOf('month')],
        'Last Year': [moment().subtract(1, 'year')]
    },
    timePicker: true,
    locale: {
        format: 'M/DD/YY hh:mm:ss A'
    },
    startDate: moment().subtract(3, 'years'),
    endDate: moment(),
})

// Add search for "Date Sent" column filter
$.fn.dataTable.ext.search.push(
    function (_settings, data, _dataIndex) {
        const target = new moment(data[3]);
        const [start, end] = $('#dateRangeFilter').val().split(' - ').map(value => { return new moment(value) });
        return target.isSameOrAfter(start) && target.isSameOrBefore(end);
    }
);

// Datatable init/config
const table = $("#previousMessagesTable").DataTable({
    order: [[3, 'desc']], // Sort on "Date sent" column
    columnDefs: [
        { visible: false, targets: 4 }, // Hide body column
        { className: "column-text-search", targets: [0, 1, 2] }, // add class to text search columns
        { className: "dt-nowrap", "targets": 3 }, // don't wrap "Date sent" column
        { type: "date", targets: 3 } // set type for "Date Sent" column

    ],
    initComplete: function () {
        // Apply the text search to the first three columns
        this.api()
            .columns(".column-text-search")
            .every(function () {
                const that = this;
                $('input', this.footer()).on('keyup change clear', function () {
                    if (that.search() !== this.value) {
                        that.search(this.value).draw();
                    }
                });
            });
    },
});

// Redraw table on setting "Date Sent" column filter
$('#dateRangeFilter').on('keyup change clear', function () {
    table.draw();
});

// Show email body when row is clicked
$('#previousMessagesTable tbody').on('click', 'tr', function () {
    const tr = $(this).closest('tr');
    const row = table.row(tr);

    if (row.child.isShown()) {
        // This row is already open - close it
        row.child.hide();
        tr.removeClass('shown');
    } else {
        // Open this row
        console.log(row.data()[4])
        // format email body data
        const rowData = row.data()[4].split("\n").map(s => `<p>${s}</p>`).join('');
        row.child(rowData).show();
        // Add bs5 classes for style
        row.child().addClass('bg-light small m-3');
        tr.addClass('shown');
    }
});

// Select2 init/config on recipients field
$('#id_recipients').select2({
    placeholder: "Select Email Recipients",
});

// 
document.querySelectorAll("#recipientFilter input").forEach(el =>
    el.addEventListener("click", event => {
        $('#id_recipients').val(null).trigger('change');  // Clear recipients field

        // Show appropriate message for filter selected
        document.querySelectorAll(".msg").forEach(el => el.classList.add('d-none'));
        document.querySelectorAll(`.msg.${event.target.dataset.filter}`).forEach(el => el.classList.remove('d-none'));

        // Disable recipient if they've opted out of email type
        document.querySelectorAll(`#id_recipients option:disabled`).forEach(el => el.disabled = false);
        document.querySelectorAll(`#id_recipients option:not([data-${event.target.dataset.filter}=""])`).forEach(el => el.disabled = true);

    })
);
// Initial recipient filter click on page load
document.querySelector("#recipientFilter input:checked").click();

// Summernot init/config for email body field
$('#id_body').summernote({
    codeviewFilter: false, // Prevent XSS
    codeviewIframeFilter: true, // Prevent XSS
    placeholder: 'Write email contents here.',
    tabsize: 2,
    height: 150,
});
