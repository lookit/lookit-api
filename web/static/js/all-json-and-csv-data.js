$('#check-for-collisions').click(function (e) {
    e.preventDefault(); // prevent page reload!
    $('#collision-indicator').html('Checking for collisions...');
    $.ajax({
        url: $('#check-for-collisions').attr('url'),
        type: 'get',
        dataType: 'json',
        success: function (data) {
            if (data.collisions.length) {
                $('#collision-indicator').html('WARNING: collision(s) detected for the following IDs. ' + data.collisions);
            } else {
                $('#collision-indicator').html('No collisions detected.');
            }
        },
        failure: function(data) { 
            $('#collision-indicator').html('Error detecting collisions.');

        }
    }); 
});
