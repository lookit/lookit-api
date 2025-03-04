// Helpers for filtering a datatables table with a "Date" column

const setupDataTableDates = (tableId, dateColumnIndex, dateFilterId) => {

    const noneRange = '- None -';

    // Date Range UI for "Date" column filter
    $(`#${dateFilterId}`).daterangepicker({
        ranges: {
            [noneRange]: '',
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
    });

    // Add search for "Date" column filter
    $.fn.dataTable.ext.search.push(
        function (_settings, data, _dataIndex) {
            const target = new moment(data[dateColumnIndex]);
            // Return all rows if the date filter is empty
            if (!$(`#${dateFilterId}`).val()) {
                return true;
            }
            const [start, end] = $(`#${dateFilterId}`).val().split(' - ').map(value => { return new moment(value) });
            // Return all rows if the date filter is invalid
            if (!start.isValid() || !end || !end.isValid()) {
                return true;
            }
            return target.isSameOrAfter(start) && target.isSameOrBefore(end);
        }
    );

    const clearInputAndUpdateTable = () => {
        $(`#${dateFilterId}`).val('');
        $(`#${tableId}`).DataTable().draw();
    };

    const clearRangeSelection = () => {
        document.querySelector('div.daterangepicker div.drp-buttons button.cancelBtn')?.click();
    };

    // Redraw table on setting "Date" column filter
    $(`#${dateFilterId}`).on('keyup change clear', function () {
        // If the date range was fully deleted in the text input, clear the selected date range
        if ($(this).val() === '') {
            clearRangeSelection();
        }
        $(`#${tableId}`).DataTable().draw();
    });

    // Clear date range filter on cancel button click
    $(`#${dateFilterId}`).on('cancel.daterangepicker', function(ev, picker) {
        clearInputAndUpdateTable();
    });

    $(`#${dateFilterId}`).on('click', function() {
        // The "none" range should be selected when the date filter text box is empty
        if ($(`#${dateFilterId}`).val() === '') {
            $(`div.daterangepicker div.ranges li`).removeClass('active');
            $(`div.daterangepicker div.ranges li[data-range-key="${noneRange}"]`).addClass('active');
        }
        
    });

    // When an empty input box is clicked and then blurred (without selecting a new date range),
    // the input box should remain empty rather than being filled with the default range ("custom")
    $(`#${dateFilterId}`).on('blur', function() {
        if ($(`div.daterangepicker div.ranges li[data-range-key="${noneRange}"]`).hasClass('active')) {
            clearInputAndUpdateTable();
        }
    });

    // When the "none" range is clicked, clear the date range filter text and previously selected dates
    $(`div.daterangepicker div.ranges li[data-range-key="${noneRange}"]`).on('click', function(ev, picker) {
        if ($(`#${dateFilterId}`).val() !== '') {
            $(`#${dateFilterId}`).val('');
        }
        clearRangeSelection();
    });

    // Initialize with the "none" range filter selected rather than "custom"
    $(`div.daterangepicker div.ranges li[data-range-key="${noneRange}"]`).click();

}
