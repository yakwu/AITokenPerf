<template>
  <div class="site-trends-tab">
    <!-- Controls Bar -->
    <div class="trends-controls">
      <!-- Metric Pills -->
      <div class="radio-group-inline">
        <label
          v-for="m in metricOptions"
          :key="m.key"
          class="radio-pill"
          :class="{ active: selectedMetric === m.key }"
          @click="selectedMetric = m.key"
        >
          <span>{{ m.label }}</span>
        </label>
      </div>

      <!-- Time Range Pills -->
      <div class="radio-group-inline">
        <label
          v-for="tr in timeRangeOptions"
          :key="tr.key"
          class="radio-pill"
          :class="{ active: selectedTimeRange === tr.key }"
          @click="changeTimeRange(tr.key)"
        >
          <span>{{ tr.label }}</span>
        </label>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="trends-loading">
      <div class="spinner"></div>
      <span>加载趋势数据...</span>
    </div>

    <!-- Empty -->
    <div v-else-if="chartDatasets.length === 0" class="trends-empty">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
      <div>暂无趋势数据</div>
      <div class="trends-empty-hint">执行测试后即可查看历史趋势</div>
    </div>

    <!-- Chart -->
    <div v-show="!loading && chartDatasets.length > 0" class="trends-chart-wrap">
      <canvas ref="chartCanvas"></canvas>
    </div>

    <!-- Anomaly Legend -->
    <div v-if="hasAnomalies && !loading" class="anomaly-legend">
      <span class="anomaly-dot"></span>
      <span class="anomaly-label">异常点</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { getResults } from '../api';
import { Chart, registerables } from 'chart.js';
Chart.register(...registerables);

const props = defineProps({
  profile: { type: Object, required: true },
});

// ---- Metric / Time Range ----
const metricOptions = [
  { key: 'ttft', label: 'TTFT', field: 'TTFT', unit: 's', higherBetter: false },
  { key: 'tpot', label: 'TPOT', field: 'TPOT', unit: 's', higherBetter: false },
  { key: 'tps', label: 'Token\u00B7s\u207B\u00B9', field: 'token_throughput_tps', unit: ' t/s', higherBetter: true },
  { key: 'success_rate', label: '成功率', field: 'success_rate', unit: '%', higherBetter: true },
];

const timeRangeOptions = [
  { key: '1h', label: '1h', hours: 1, bucketMs: 5 * 60 * 1000 },
  { key: '24h', label: '24h', hours: 24, bucketMs: 60 * 60 * 1000 },
  { key: '7d', label: '7d', hours: 168, bucketMs: 6 * 60 * 60 * 1000 },
  { key: '30d', label: '30d', hours: 720, bucketMs: 24 * 60 * 60 * 1000 },
];

const selectedMetric = ref('ttft');
const selectedTimeRange = ref('24h');
const loading = ref(false);
const rawResults = ref([]);
const chartCanvas = ref(null);
let chartInstance = null;

// ---- Model Color Palette ----
const MODEL_COLORS = [
  '#3B7DD6', '#E85D26', '#2D8B55', '#9333EA', '#D97706',
  '#0891B2', '#DB2777', '#4F46E5', '#059669', '#DC2626',
];

function modelColor(model, idx) {
  return MODEL_COLORS[idx % MODEL_COLORS.length];
}

// ---- Data Processing ----
const activeTimeRange = computed(() =>
  timeRangeOptions.find(t => t.key === selectedTimeRange.value)
);

const activeMetric = computed(() =>
  metricOptions.find(m => m.key === selectedMetric.value)
);

// Extract metric value from a result item
function extractMetric(item, metricKey) {
  switch (metricKey) {
    case 'ttft': return item.percentiles?.TTFT?.P50 ?? null;
    case 'tpot': return item.percentiles?.TPOT?.P50 ?? null;
    case 'tps': return item.summary?.token_throughput_tps ?? null;
    case 'success_rate': return item.summary?.success_rate ?? null;
    default: return null;
  }
}

// Parse timestamp string like "20260411_0930" to ms
function parseTimestamp(ts) {
  if (!ts) return 0;
  // Format: "YYYYMMDD_HHmm" or ISO
  if (ts.includes('_')) {
    const y = +ts.slice(0, 4), mo = +ts.slice(4, 6) - 1, d = +ts.slice(6, 8);
    const h = +ts.slice(9, 11), mi = +ts.slice(11, 13);
    return new Date(y, mo, d, h, mi).getTime();
  }
  return new Date(ts).getTime();
}

// Filter results for this site's profile
const filteredResults = computed(() => {
  const profileName = props.profile?.name;
  if (!profileName) return [];
  return rawResults.value.filter(r => r.config?.profile_name === profileName);
});

// Get unique model names sorted
const models = computed(() => {
  const set = new Set();
  for (const r of filteredResults.value) {
    if (r.config?.model) set.add(r.config.model);
  }
  return [...set].sort();
});

// Bucket and aggregate data per model
const chartDatasets = computed(() => {
  const tr = activeTimeRange.value;
  const metric = activeMetric.value;
  if (!tr || !metric || filteredResults.value.length === 0) return [];

  const now = Date.now();
  const rangeStart = now - tr.hours * 3600 * 1000;
  const bucketMs = tr.bucketMs;

  // Filter to time range
  const inRange = filteredResults.value.filter(r => {
    const ts = parseTimestamp(r.timestamp);
    return ts >= rangeStart && ts <= now;
  });

  if (inRange.length === 0) return [];

  // Group by model
  const modelMap = {};
  for (const r of inRange) {
    const m = r.config?.model || 'unknown';
    if (!modelMap[m]) modelMap[m] = [];
    modelMap[m].push(r);
  }

  // For each model, bucket and average
  const allBuckets = new Set();
  const modelBuckets = {};

  for (const model of Object.keys(modelMap)) {
    const runs = modelMap[model];
    const buckets = {};
    for (const r of runs) {
      const ts = parseTimestamp(r.timestamp);
      const bucketIdx = Math.floor((ts - rangeStart) / bucketMs);
      if (!buckets[bucketIdx]) buckets[bucketIdx] = [];
      buckets[bucketIdx].push(r);
      allBuckets.add(bucketIdx);
    }
    modelBuckets[model] = buckets;
  }

  // Create sorted bucket indices
  const sortedBuckets = [...allBuckets].sort((a, b) => a - b);

  // Detect anomalies: values > 2 standard deviations from mean
  const anomalyInfo = {};
  for (const model of Object.keys(modelMap)) {
    const vals = modelMap[model]
      .map(r => extractMetric(r, metric.key))
      .filter(v => v != null);
    if (vals.length < 5) { anomalyInfo[model] = null; continue; }
    const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
    const std = Math.sqrt(vals.reduce((a, b) => a + (b - mean) ** 2, 0) / vals.length);
    anomalyInfo[model] = { mean, std };
  }

  const datasets = [];
  const modelList = Object.keys(modelBuckets).sort();
  const labels = sortedBuckets.map(bIdx => {
    const midTs = rangeStart + (bIdx + 0.5) * bucketMs;
    return formatBucketLabel(midTs, tr.key);
  });

  for (let mi = 0; mi < modelList.length; mi++) {
    const model = modelList[mi];
    const buckets = modelBuckets[model];
    const color = modelColor(model, mi);

    const data = sortedBuckets.map(bIdx => {
      const items = buckets[bIdx];
      if (!items || items.length === 0) return null;
      const vals = items.map(r => extractMetric(r, metric.key)).filter(v => v != null);
      return vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    });

    // Detect anomaly points for this model
    const anomaly = anomalyInfo[model];
    const pointColors = data.map(v => {
      if (v == null || !anomaly) return color;
      const diff = Math.abs(v - anomaly.mean);
      if (diff > 2 * anomaly.std) return '#DC2626'; // red for anomaly
      return color;
    });
    const pointRadii = data.map(v => {
      if (v == null || !anomaly) return 2;
      const diff = Math.abs(v - anomaly.mean);
      return diff > 2 * anomaly.std ? 6 : 2;
    });

    datasets.push({
      label: model,
      data,
      borderColor: color,
      backgroundColor: color + '15',
      borderWidth: 2,
      pointRadius: pointRadii,
      pointBackgroundColor: pointColors,
      pointBorderColor: pointColors,
      pointHoverRadius: 5,
      tension: 0.3,
      fill: false,
      spanGaps: false,
    });
  }

  return { labels, datasets };
});

// Check if any anomalies exist
const hasAnomalies = computed(() => {
  const cd = chartDatasets.value;
  if (!cd || !cd.datasets) return false;
  return cd.datasets.some(ds => {
    const pr = ds.pointRadius;
    return Array.isArray(pr) && pr.some(r => r > 2);
  });
});

function formatBucketLabel(tsMs, rangeKey) {
  const d = new Date(tsMs);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');

  switch (rangeKey) {
    case '1h': return `${hh}:${mi}`;
    case '24h': return `${hh}:${mi}`;
    case '7d': return `${mm}-${dd} ${hh}:00`;
    case '30d': return `${mm}-${dd}`;
    default: return `${mm}-${dd} ${hh}:${mi}`;
  }
}

// ---- Data Fetching ----
async function fetchResults() {
  loading.value = true;
  try {
    const data = await getResults({ limit: 500 });
    rawResults.value = data.items || data.results || [];
  } catch {
    rawResults.value = [];
  }
  loading.value = false;
}

async function changeTimeRange(key) {
  selectedTimeRange.value = key;
}

// ---- Chart Rendering ----
function destroyChart() {
  if (chartInstance) {
    chartInstance.destroy();
    chartInstance = null;
  }
}

function renderChart() {
  destroyChart();
  const canvas = chartCanvas.value;
  if (!canvas) return;
  const cd = chartDatasets.value;
  if (!cd || !cd.datasets || cd.datasets.length === 0) return;

  const metric = activeMetric.value;

  chartInstance = new Chart(canvas, {
    type: 'line',
    data: {
      labels: cd.labels,
      datasets: cd.datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: {
          position: 'top',
          labels: {
            font: { family: "'DM Sans'", size: 12 },
            usePointStyle: true,
            pointStyle: 'circle',
            padding: 16,
          },
        },
        tooltip: {
          callbacks: {
            label: ctx => {
              if (ctx.parsed.y == null) return '';
              const unit = metric.unit;
              const val = metric.key === 'success_rate'
                ? ctx.parsed.y.toFixed(1) + unit
                : ctx.parsed.y.toFixed(2) + unit;
              return `${ctx.dataset.label}: ${val}`;
            },
          },
        },
      },
      scales: {
        y: {
          title: {
            display: true,
            text: metric.key === 'success_rate' ? 'Success Rate (%)'
              : metric.key === 'tps' ? 'Throughput (t/s)'
              : `Latency (${metric.unit})`,
            font: { size: 11 },
          },
          grid: { color: 'var(--border, #F0EEE9)' },
          ticks: {
            font: { family: "'JetBrains Mono'", size: 10 },
            callback: v => {
              if (metric.key === 'success_rate') return v.toFixed(0) + '%';
              return v.toFixed(metric.key === 'tps' ? 0 : 1) + metric.unit;
            },
          },
          beginAtZero: metric.key !== 'ttft' && metric.key !== 'tpot',
        },
        x: {
          grid: { display: false },
          ticks: {
            font: { family: "'JetBrains Mono'", size: 10 },
            maxRotation: 45,
            autoSkip: true,
            maxTicksLimit: 20,
          },
        },
      },
    },
  });
}

// ---- Watchers ----
watch([selectedMetric, selectedTimeRange, chartDatasets], () => {
  nextTick(renderChart);
}, { deep: true });

// ---- Lifecycle ----
onMounted(() => {
  fetchResults();
});

onUnmounted(() => {
  destroyChart();
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

.trends-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--text-tertiary);
  gap: 8px;
  font-size: 14px;
}

.trends-empty-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

.trends-chart-wrap {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  height: 360px;
  overflow: hidden;
}

.anomaly-legend {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-tertiary);
  padding: 0 4px;
}

.anomaly-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #DC2626;
}

.anomaly-label {
  font-size: 11px;
}
</style>
