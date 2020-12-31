$(document).ready(function () {
  var table = $('#option_detail_table').DataTable();
  table
    .order( [ 5, 'desc' ] )
    .draw();
   
  // Event listener to the two range filtering inputs to redraw on input
  $('#min_itm').keyup( function() {
    table.draw();
  } );

  $.fn.dataTable.ext.search.push(
    function( settings, data, dataIndex ) {
      var min = parseInt( $('#min_itm').val(), 10 );
      var odds_in_the_money = parseFloat( data[3] ) || 0;
      if (isNaN(min) || (odds_in_the_money > min)) {
        return true;
      }
      return false;
    }
  );
  $('#min_itm').val("70");
  table.draw();
});