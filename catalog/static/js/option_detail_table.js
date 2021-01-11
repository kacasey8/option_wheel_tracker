$(document).ready(function () {
  const table = $('#option_detail_table').DataTable();
  const columnNames = [];
  table.columns().every( function () {        
    columnNames.push(this.header().innerHTML);
  });
  const annualizedReturnIndex = columnNames.indexOf('Annualized Rate Of Return');
  const wheelTotalReturnIndex = columnNames.indexOf('Wheel Total Max Return %');
  let oddsIndex = columnNames.indexOf('Odds Out Of The Money %');
  if (oddsIndex === -1) {
    oddsIndex = columnNames.indexOf('Odds Lose Stock');
  }
  table
    .order( [ annualizedReturnIndex, 'desc' ] )
    .draw();

  $.fn.dataTable.ext.search.push(
    function( settings, data, dataIndex ) {
      const min = parseInt( $('#min_otm').val() || $('#min_itm_call').val() , 10 );
      const oddsNoStock = parseFloat( data[oddsIndex] ) || 0;
      if ($('#avoid_negative_returns').is(":checked")) {
        // remove the % at the end with slice
        const wheelTotalMaxReturnRate = parseFloat(data[wheelTotalReturnIndex].slice(0, -1)) || 0;
        if (wheelTotalMaxReturnRate < 0) {
          return false;
        }
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
  $('#min_itm_call').val("40");
  table.draw();
});