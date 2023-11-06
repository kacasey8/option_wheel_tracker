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

  updateChartData();

  function updateChartData () {
    const showNegativeProfits = $('#show_negative_profits').is(":checked");
    const showAllYears = $('#show_all_years').is(":checked");
    let profitData = profit_per_day.sort();
    let collateralData = collateral_on_the_line_per_day.sort();
    if (!showAllYears) {
      // filter to the max year in the data
      const years = profitData.map(x => (new Date(x[0])).getFullYear());
      const maxYear = Math.max(...years);
      profitData = profitData.filter(x => (new Date(x[0])).getFullYear() === maxYear);
      collateralData = collateralData.filter(x => (new Date(x[0])).getFullYear() === maxYear);
    }

    const collateral_data = collateralData.sort().map((x => {
      return {
        t: new Date(x[0]),
        y: x[1]
      }
    }));
    myChart.data.datasets[0].data = collateral_data;

    const profit_data = profitData.map((x => {
      return {
        t: new Date(x[0]),
        y: showNegativeProfits ? x[1]: Math.max(0, x[1])
      }
    }));
    myChart.data.datasets[1].data = profit_data;
    myChart.update();
  }

  $('#show_negative_profits').change( function() {
    updateChartData();
  });

  $('#show_all_years').change( function() {
    updateChartData();
  });

});
