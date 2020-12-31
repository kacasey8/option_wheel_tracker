$(document).ready(function () {
  const table = $('#option_detail_table').DataTable();
  const columnNames = [];
  table.columns().every( function () {        
    columnNames.push(this.header().innerHTML);
  });
  const returnIndex = columnNames.indexOf('Annualized Rate Of Return');
  const oddsIndex = columnNames.indexOf('Odds In The Money %');
  table
    .order( [ returnIndex, 'desc' ] )
    .draw();
   
  // Event listener to the two range filtering inputs to redraw on input
  $('#min_itm').keyup( function() {
    table.draw();
  } );

  $.fn.dataTable.ext.search.push(
    function( settings, data, dataIndex ) {
      var min = parseInt( $('#min_itm').val(), 10 );
      var odds_in_the_money = parseFloat( data[oddsIndex] ) || 0;
      if (isNaN(min) || (odds_in_the_money > min)) {
        return true;
      }
      return false;
    }
  );
  $('#min_itm').val("70");
  table.draw();
});