$(document).ready(function () {
  const table = $('#option_detail_table').DataTable();
  const columnNames = [];
  table.columns().every( function () {        
    columnNames.push(this.header().innerHTML);
  });
  const returnIndex = columnNames.indexOf('Annualized Rate Of Return');
  let oddsIndex = columnNames.indexOf('Odds Out Of The Money %');
  if (oddsIndex === -1) {
    oddsIndex = columnNames.indexOf('Odds Lose Stock');
  }
  table
    .order( [ returnIndex, 'desc' ] )
    .draw();

  $.fn.dataTable.ext.search.push(
    function( settings, data, dataIndex ) {
      const min = parseInt( $('#min_otm').val() || $('#min_itm_call').val() , 10 );
      const oddsNoStock = parseFloat( data[oddsIndex] ) || 0;
      const returnRate = parseFloat(data[returnIndex].slice(0, -1)) || 1;
      if (returnRate < 1 && $('#avoid_negative_returns').is(":checked")) {
        return false;
      }
      if (isNaN(min) || (oddsNoStock > min)) {
        return true;
      }
      return false;
    }
  );
  // Event listener to the two range filtering inputs to redraw on input
  $('#min_otm').keyup( function() {
    table.draw();
  } );
  $('#min_otm').val("70");
  table.draw();
  $('#min_itm_call').keyup( function() {
    table.draw();
  } );
  $('#avoid_negative_returns').change( function() {
    table.draw();
  } );
  $('#min_itm_call').val("30");
  table.draw();
});