$(document).ready(function () {
  const table = $('#option_detail_table').DataTable();
  const columnNames = [];
  table.columns().every( function () {        
    columnNames.push(this.header().innerHTML);
  });
  const returnIndex = columnNames.indexOf('Annualized Rate Of Return');
  const oddsIndex = columnNames.indexOf('Odds Out Of The Money %');
  table
    .order( [ returnIndex, 'desc' ] )
    .draw();
   
  // Event listener to the two range filtering inputs to redraw on input
  $('#min_otm').keyup( function() {
    table.draw();
  } );

  $.fn.dataTable.ext.search.push(
    function( settings, data, dataIndex ) {
      var min = parseInt( $('#min_otm').val(), 10 );
      var odds_out_of_the_money = parseFloat( data[oddsIndex] ) || 0;
      if (isNaN(min) || (odds_out_of_the_money > min)) {
        return true;
      }
      return false;
    }
  );
  $('#min_otm').val("70");
  table.draw();
});