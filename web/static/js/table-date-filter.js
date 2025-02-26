// Helpers for filtering a datatables table with a "Date" column

const setupDataTableDates = (tableId, dateColumnIndex, dateFilterId) => {

    // Date Range UI for "Date" column filter
    $(`#${dateFilterId}`).daterangepicker({
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
            cancelLabel: 'Clear',
            format: 'M/DD/YY hh:mm:ss A'
        }
    })

    // Add search for "Date" column filter
    $.fn.dataTable.ext.search.push(
        function (_settings, data, _dataIndex) {
            const target = new moment(data[dateColumnIndex]);
            if (!$(`#${dateFilterId}`).val()) {
                return true;
            }
            const [start, end] = $(`#${dateFilterId}`).val().split(' - ').map(value => { return new moment(value) });
            if (!start.isValid() || !end || !end.isValid()) {
                return true;
            }
            return target.isSameOrAfter(start) && target.isSameOrBefore(end);
        }
    );

    // Redraw table on setting "Date" column filter
    $(`#${dateFilterId}`).on('keyup change clear', function () {
        // If the date range was fully deleted in the text input, clear the selected date range
        if ($(this).val() === '') {
            document.querySelector('div.drp-buttons button.cancelBtn')?.click();
        }
        $(`#${tableId}`).DataTable().draw();
    });

    // Clear date range filter on cancel
    $(`#${dateFilterId}`).on('cancel.daterangepicker', function(ev, picker) {
        $(`#${dateFilterId}`).val('');
        $(`#${tableId}`).DataTable().draw();
    });

    // Initialize with no date range filter
    $(`#${dateFilterId}`).val('');

}
