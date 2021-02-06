$(document).ready(function () {
  const table = $('table.user_table').DataTable();
  const columnNames = [];
  table.columns().every( function () {        
    columnNames.push(this.header().innerHTML);
  });
  console.log(columnNames);
  const annualizedReturnIndex = columnNames.indexOf('Annualized Rate of Return');
  table
    .order( [ annualizedReturnIndex, 'desc' ] )
    .draw();
});