$(document).ready(function () {
  const chart_item = $('#profit_collateral_chart').get(0);
  if (chart_item == null) {
    return;
  }
  const ctx = $('#profit_collateral_chart').get(0).getContext("2d");
  const collateral_data = collateral_on_the_line_per_day.sort().map((elem => {
    return {
      t: new Date(elem[0]),
      y: elem[1]
    }
  }));
  const profit_data = profit_per_day.sort().map((elem => {
    return {
      t: new Date(elem[0]),
      y: Math.max(0, elem[1])
    }
  }));

  const myChart = new Chart(ctx, {
    type: 'bar',
    data: {
      datasets: [
        {
          label: 'Collateral',
          data: collateral_data,
          backgroundColor: 'rgba(255, 99, 132)',
          borderWidth: 1,
          fill: true,
          yAxisID: 'A',
        },
        {
          label: 'Profit',
          data: profit_data,
          backgroundColor: 'rgba(159, 226, 191)',
          borderWidth: 1,
          fill: true,
          yAxisID: 'B',
        }
      ],
    },
    options: {
      scales: {
        xAxes: [{
          type: 'time',
          distribution: 'series',
          offset: true,
        }],
        yAxes: [{
          id: 'A',
          type: 'linear',
          position: 'left',
          label: 'a',
          ticks: {
            beginAtZero: true
          }
        }, {
          id: 'B',
          type: 'linear',
          position: 'right',
          ticks: {
            beginAtZero: true
          },
        }]
      }
    }
  });

  $('#show_negative_profits').change( function() {
    const showNegativeProfits = $('#show_negative_profits').is(":checked");
    const profit_data = profit_per_day.sort().map((elem => {
      return {
        t: new Date(elem[0]),
        y: showNegativeProfits ? elem[1]: Math.max(0, elem[1])
      }
    }));
    myChart.data.datasets[1].data = profit_data;
    myChart.update();
  });

});