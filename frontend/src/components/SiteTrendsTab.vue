<template>
  <div class="site-trends-tab">
    <!-- Controls Bar -->
    <div class="trends-controls">
      <span class="trends-label">历史趋势</span>
      <div class="radio-group-inline">
        <label v-for="opt in timeRangeOptions" :key="opt.label" class="radio-pill"
          :class="{ active: selectedTimeRange === opt.hours }" @click="changeTimeRange(opt.hours)" style="cursor:pointer">
          <span>{{ opt.label }}</span>
        </label>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="trends-loading">
      <div class="spinner"></div>
      <span>加载趋势数据...</span>
    </div>

    <template v-else>
      <!-- Summary Cards -->
      <div v-if="trendSummary.length > 0" class="trend-summary-cards">
        <div v-for="card in trendSummary" :key="card.label" class="trend-card">
          <div class="trend-card-label">{{ card.label }}</div>
          <div class="trend-card-value" :style="card.valueStyle">{{ card.value }}</div>
          <div class="trend-card-delta" :style="card.deltaStyle">{{ card.delta }}</div>
        </div>
      </div>

      <!-- Latency Chart Card -->
      <div class="chart-card">
        <div class="chart-card-title">延迟趋势 <span style="font-weight:400;color:var(--text-tertiary)">↓ 越低越好</span></div>
        <canvas v-show="trendData.length >= 1" ref="latencyCanvas" class="trend-canvas"></canvas>
        <div v-show="trendData.length < 1" class="trend-empty-canvas">暂无趋势数据，至少需要 1 次执行</div>
      </div>

      <!-- Quality Chart Card -->
      <div class="chart-card">
        <div class="chart-card-title">质量趋势 <span style="font-weight:400;color:var(--text-tertiary)">↑ 越高越好</span></div>
        <canvas v-show="trendData.length >= 1" ref="qualityCanvas" class="trend-canvas"></canvas>
        <div v-show="trendData.length < 1" class="trend-empty-canvas">暂无趋势数据，至少需要 1 次执行</div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { getSiteTrend } from '../api';
import { aggregateToFixedPoints } from '../utils/trendAggregator.js';
import { Chart, registerables } from 'chart.js';
Chart.register(...registerables);

const props = defineProps({
  profile: { type: Object, required: true },
});

// ---- State ----
const loading = ref(false);
const trendData = ref([]);
const trendSummary = ref([]);
const selectedTimeRange = ref(6);
const timeRangeOptions = [
  { label: '6h', hours: 6 },
  { label: '24h', hours: 24 },
  { label: '7d', hours: 168 },
];

const latencyCanvas = ref(null);
const qualityCanvas = ref(null);
let latencyChart = null;
let qualityChart = null;

// ---- Summary Cards ----
function renderTrendSummary() {
  const trend = trendData.value;
  if (!trend || trend.length === 0) { trendSummary.value = []; return; }

  const avgField = (fn) => {
    const vals = trend.map(fn).filter(v => v != null);
    return vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  };

  const aSucc = avgField(r => r.avg_success_rate);
  const aTps = avgField(r => r.avg_tps);
  const aTtft = avgField(r => r.avg_ttft_p50);
  const aTpot = avgField(r => r.avg_tpot_p50);

  // Trend delta: compare recent half vs earlier half
  const sorted = [...trend].sort((a, b) => (a.minute || '').localeCompare(b.minute || ''));
  const mid = Math.floor(sorted.length / 2);
  const recentHalf = sorted.slice(mid);
  const prevHalf = sorted.slice(0, mid);

  const avgHalf = (arr, fn) => {
    const vals = arr.map(fn).filter(v => v != null);
    return vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  };

  const pSucc = prevHalf.length > 0 ? avgHalf(prevHalf, r => r.avg_success_rate) : null;
  const pTps = prevHalf.length > 0 ? avgHalf(prevHalf, r => r.avg_tps) : null;
  const pTtft = prevHalf.length > 0 ? avgHalf(prevHalf, r => r.avg_ttft_p50) : null;
  const pTpot = prevHalf.length > 0 ? avgHalf(prevHalf, r => r.avg_tpot_p50) : null;

  function deltaStr(curr, prev, unit, higherIsBetter) {
    if (curr == null || prev == null) return { delta: '-', deltaStyle: '' };
    const diff = curr - prev;
    const absDiff = Math.abs(diff);
    const arrow = diff > 0 ? '↑' : diff < 0 ? '↓' : '→';
    const isGood = higherIsBetter ? diff >= 0 : diff <= 0;
    const color = diff === 0 ? 'color:var(--text-tertiary)' : isGood ? 'color:var(--success)' : 'color:var(--danger)';
    return { delta: `${arrow} ${absDiff.toFixed(1)}${unit}`, deltaStyle: color };
  }

  trendSummary.value = [
    { label: '成功率', value: aSucc != null ? aSucc.toFixed(1) + '%' : '-', valueStyle: aSucc >= 95 ? 'color:var(--success)' : aSucc >= 80 ? 'color:var(--warning)' : 'color:var(--danger)', ...deltaStr(aSucc, pSucc, '%', true) },
    { label: 'Token/s', value: aTps != null ? aTps.toFixed(0) + ' t/s' : '-', valueStyle: '', ...deltaStr(aTps, pTps, ' t/s', true) },
    { label: 'TTFT P50', value: aTtft != null ? aTtft.toFixed(2) + 's' : '-', valueStyle: aTtft <= 0.5 ? 'color:var(--success)' : aTtft <= 2 ? 'color:var(--warning)' : 'color:var(--danger)', ...deltaStr(aTtft, pTtft, 's', false) },
    { label: 'TPOT P50', value: aTpot != null ? aTpot.toFixed(3) + 's' : '-', valueStyle: aTpot <= 0.01 ? 'color:var(--success)' : aTpot <= 0.05 ? 'color:var(--warning)' : 'color:var(--danger)', ...deltaStr(aTpot, pTpot, 's', false) },
  ];
}

// ---- Data Fetching ----
async function fetchTrend() {
  const baseUrl = props.profile?.base_url;
  if (!baseUrl) return;

  loading.value = true;
  try {
    const data = await getSiteTrend(baseUrl, { hours: selectedTimeRange.value });
    trendData.value = data.trend || [];
  } catch {
    trendData.value = [];
  }
  loading.value = false;
  destroyCharts();
  await nextTick();
  renderTrendSummary();
  renderLatencyChart();
  renderQualityChart();
}

async function changeTimeRange(hours) {
  selectedTimeRange.value = hours;
  await fetchTrend();
}

// ---- Chart Rendering ----
function destroyCharts() {
  if (latencyChart) { latencyChart.destroy(); latencyChart = null; }
  if (qualityChart) { qualityChart.destroy(); qualityChart = null; }
}

function renderLatencyChart() {
  const trend = trendData.value;
  if (!trend || trend.length < 1) return;
  const canvas = latencyCanvas.value;
  if (!canvas) return;

  const { labels, items } = aggregateToFixedPoints(trend, 144);

  latencyChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'TTFT P50',
          data: items.map(r => r?.avg_ttft_p50 ?? null),
          borderColor: '#3B7DD6',
          backgroundColor: '#3B7DD618',
          borderWidth: 2,
          pointRadius: trend.length <= 50 ? 3 : 0,
          tension: 0.3,
          fill: true,
          spanGaps: false,
        },
        {
          label: 'TPOT P50',
          data: items.map(r => r?.avg_tpot_p50 ?? null),
          borderColor: '#E85D26',
          backgroundColor: '#E85D2618',
          borderWidth: 2,
          pointRadius: trend.length <= 50 ? 3 : 0,
          tension: 0.3,
          fill: true,
          spanGaps: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'top',
          labels: { font: { family: "'DM Sans'", size: 11 }, usePointStyle: true, pointStyle: 'circle', padding: 12 },
        },
        tooltip: {
          callbacks: {
            label: ctx => ctx.parsed.y != null ? `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(3)}s` : '',
          },
        },
      },
      scales: {
        y: {
          title: { display: true, text: 'Latency (s)', font: { size: 11 } },
          grid: { color: 'rgba(0,0,0,0.04)' },
          ticks: { font: { family: "'JetBrains Mono'", size: 10 }, callback: v => v.toFixed(2) + 's' },
          beginAtZero: true,
        },
        x: {
          grid: { display: false },
          ticks: { font: { family: "'JetBrains Mono'", size: 10 }, maxRotation: 45, autoSkip: true, maxTicksLimit: 20 },
        },
      },
    },
  });
}

function renderQualityChart() {
  const trend = trendData.value;
  if (!trend || trend.length < 1) return;
  const canvas = qualityCanvas.value;
  if (!canvas) return;

  const { labels, items } = aggregateToFixedPoints(trend, 144);
  const failureData = items.map(r => r?.avg_success_rate != null ? (100 - r.avg_success_rate) : null);

  qualityChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: '吞吐量 (t/s)',
          data: items.map(r => r?.avg_tps ?? null),
          borderColor: '#2D8B55',
          backgroundColor: '#2D8B5518',
          borderWidth: 2,
          pointRadius: trend.length <= 50 ? 3 : 0,
          tension: 0.3,
          fill: true,
          yAxisID: 'y',
          spanGaps: false,
        },
        {
          label: '失败率 (%)',
          data: failureData,
          borderColor: '#E85D26',
          backgroundColor: '#E85D2618',
          borderWidth: 2,
          pointRadius: trend.length <= 50 ? 3 : 0,
          tension: 0.3,
          fill: true,
          yAxisID: 'y1',
          borderDash: [5, 3],
          spanGaps: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'top',
          labels: { font: { family: "'DM Sans'", size: 11 }, usePointStyle: true, pointStyle: 'circle', padding: 12 },
        },
        tooltip: {
          callbacks: {
            label: ctx => {
              if (ctx.parsed.y == null) return '';
              if (ctx.dataset.yAxisID === 'y1') return `失败率: ${ctx.parsed.y.toFixed(1)}%`;
              return `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)} t/s`;
            },
          },
        },
      },
      scales: {
        y: {
          position: 'left',
          title: { display: true, text: 'Throughput (t/s)', font: { size: 11 } },
          grid: { color: 'rgba(0,0,0,0.04)' },
          ticks: { font: { family: "'JetBrains Mono'", size: 10 } },
          beginAtZero: true,
        },
        y1: {
          position: 'right',
          title: { display: true, text: '失败率 (%)', font: { size: 11 } },
          grid: { drawOnChartArea: false },
          ticks: { font: { family: "'JetBrains Mono'", size: 10 } },
          min: 0,
          max: 100,
        },
        x: {
          grid: { display: false },
          ticks: { font: { family: "'JetBrains Mono'", size: 10 }, maxRotation: 45, autoSkip: true, maxTicksLimit: 20 },
        },
      },
    },
  });
}

// ---- Lifecycle ----
onMounted(() => {
  fetchTrend();
});

onUnmounted(() => {
  destroyCharts();
});
</script>

<style scoped>
.site-trends-tab {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.trends-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.trends-label {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-secondary);
}

.trends-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--text-tertiary);
  gap: 12px;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ---- Summary Cards ---- */
.trend-summary-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.trend-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  text-align: center;
}

.trend-card-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

.trend-card-value {
  font-family: var(--font-mono);
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.2;
  margin-bottom: 4px;
}

.trend-card-delta {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
}

/* ---- Chart Cards ---- */
.chart-card {
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px;
  box-shadow: var(--shadow-sm);
}

.chart-card-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.trend-canvas {
  width: 100%;
  height: 200px;
  max-height: 200px;
}

.trend-empty-canvas {
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  font-size: 12px;
}

@media (max-width: 768px) {
  .trend-summary-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
