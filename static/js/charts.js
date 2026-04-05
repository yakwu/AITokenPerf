function renderPercentilesChart(container, p) {
  const metrics = Object.keys(p);
  if (!metrics.length) return;

  const pctKeys = ['P50', 'P95', 'P99', 'P99.5', 'Max'];
  const pctColors = {
    'P50':   { bg: '#3B7DD633', border: '#3B7DD6' },
    'P95':   { bg: '#F59E3B33', border: '#F59E3B' },
    'P99':   { bg: '#E85D2633', border: '#E85D26' },
    'P99.5': { bg: '#D63B3B33', border: '#D63B3B' },
    'Max':   { bg: '#8B5CF633', border: '#8B5CF6' },
  };

  metrics.forEach(metric => {
    const vals = p[metric];
    if (!vals) return;

    const isMs = (vals.Max || 0) < 1;
    const cardId = `chart_${metric}_${Date.now()}_${Math.random().toString(36).slice(2,6)}`;

    const card = document.createElement('div');
    card.className = 'chart-card';
    card.innerHTML = `<div class="chart-card-title">${metric} ${infoIcon(metric)}</div><div class="chart-container"><canvas id="${cardId}"></canvas></div>`;
    container.appendChild(card);

    const canvas = document.getElementById(cardId);

    const datasets = [{
      data: pctKeys.map(k => isMs ? (vals[k] || 0) * 1000 : (vals[k] || 0)),
      backgroundColor: pctKeys.map(k => pctColors[k].bg),
      borderColor: pctKeys.map(k => pctColors[k].border),
      borderWidth: 2,
      borderRadius: 6,
    }];

    new Chart(canvas, {
      type: 'bar',
      data: { labels: pctKeys, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => {
                const v = ctx.parsed.y;
                return isMs ? v.toFixed(1) + ' ms' : fmtTime(v);
              }
            }
          }
        },
        scales: {
          y: {
            grid: { color: '#F0EEE9' },
            beginAtZero: true,
            ticks: {
              font: { family: "'JetBrains Mono'", size: 11 },
              callback: v => isMs ? v.toFixed(0) + 'ms' : fmtTime(v),
            }
          },
          x: {
            grid: { display: false },
            ticks: { font: { family: "'JetBrains Mono'", size: 11 } }
          }
        }
      }
    });
  });
}
