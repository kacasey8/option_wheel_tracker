$(document).ready(function () {
  const table = $('table.user_table').DataTable({
    "paging": false
  });
  const columnNames = [];
  table.columns().every( function () {        
    columnNames.push(this.header().innerHTML);
  });
  const annualizedReturnIndex = columnNames.indexOf('Annualized Rate of Return');
  table
    .order( [ annualizedReturnIndex, 'desc' ] )
    .draw();
});