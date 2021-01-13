$(document).ready(function () {
  const ctx = $('#profit_collateral_chart').get(0).getContext("2d");
  console.log(collateral_on_the_line_per_day)
  const data = collateral_on_the_line_per_day.sort().map((elem => {
    return {
      t: new Date(elem[0]),
      y: new Date(elem[1])
    }
  }));

  const myChart = new Chart(ctx, {
    type: 'line',
    data: {
      datasets: [{
        label: 'Collateral',
        data: data,
        backgroundColor: [
          'rgba(255, 99, 132, 0.2)'
        ],
        borderWidth: 1,
        spanGaps: true
      }]
    },
    options: {
      scales: {
        xAxes: [{
          type: 'time'
        }]
      }
    }
  });
});