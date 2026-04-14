<template>
  <div class="connectivity-progress" v-if="running || result">
    <!-- 运行中：进度面板 -->
    <div class="progress-panel" :class="{ active: running }" v-show="running">
      <div class="card">
        <div class="card-header">
          <div class="card-title">连通性验证中...</div>
        </div>
        <div class="progress-bar-wrap">
          <div class="progress-bar" :style="barStyle"></div>
        </div>
        <div class="progress-stats">
          <div class="progress-stat">
            <div class="progress-stat-value">{{ progress.done }}</div>
            <div class="progress-stat-label">已完成</div>
          </div>
          <div class="progress-stat">
            <div class="progress-stat-value" style="color:var(--success)">{{ progress.success }}</div>
            <div class="progress-stat-label">成功</div>
          </div>
          <div class="progress-stat">
            <div class="progress-stat-value" style="color:var(--danger)">{{ progress.failed }}</div>
            <div class="progress-stat-label">失败</div>
          </div>
          <div class="progress-stat">
            <div class="progress-stat-value">{{ progress.elapsed + 's' }}</div>
            <div class="progress-stat-label">耗时</div>
          </div>
        </div>
        <div class="progress-log" ref="logRef">
          <div v-for="(log, i) in logs" :key="i" v-html="log"></div>
        </div>
      </div>
    </div>

    <!-- 完成后：结果指标卡片 -->
    <div class="connectivity-result" v-if="!running && result">
      <div class="card">
        <div class="card-header">
          <div class="card-title">
            <span v-if="!error" style="color:var(--success)">&#10003;</span>
            <span v-else style="color:var(--danger)">&#10007;</span>
            连通性验证{{ error ? '失败' : '通过' }}
          </div>
          <button class="btn btn-ghost btn-sm" @click="$emit('dismiss')">关闭</button>
        </div>
        <div class="connectivity-metrics" v-if="result.percentiles || result.summary">
          <div class="connectivity-metric">
            <span class="connectivity-metric-label">TTFT</span>
            <span class="connectivity-metric-value">{{ fmtTime(result.percentiles?.TTFT?.P50) }}</span>
          </div>
          <div class="connectivity-metric">
            <span class="connectivity-metric-label">TPOT</span>
            <span class="connectivity-metric-value">{{ fmtTime(result.percentiles?.TPOT?.P50) }}</span>
          </div>
          <div class="connectivity-metric">
            <span class="connectivity-metric-label">E2E</span>
            <span class="connectivity-metric-value">{{ fmtTime(result.percentiles?.E2E?.P50) }}</span>
          </div>
          <div class="connectivity-metric">
            <span class="connectivity-metric-label">Token/s</span>
            <span class="connectivity-metric-value">{{ fmtNum(result.summary?.token_throughput_tps, 0) }}</span>
          </div>
          <div class="connectivity-metric">
            <span class="connectivity-metric-label">成功率</span>
            <span class="connectivity-metric-value">{{ fmtPct(result.summary?.success_rate) }}</span>
          </div>
        </div>
        <div class="progress-log" v-if="logs.length" ref="logRef" style="margin-top:12px">
          <div v-for="(log, i) in logs" :key="i" v-html="log"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, watch, nextTick, ref } from 'vue';
import { fmtTime, fmtPct, fmtNum } from '../utils/formatters.js';

const props = defineProps({
  running: { type: Boolean, default: false },
  progress: { type: Object, default: () => ({ done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' }) },
  logs: { type: Array, default: () => [] },
  result: { type: Object, default: null },
  error: { type: String, default: null },
});

defineEmits(['dismiss']);

const logRef = ref(null);

const barStyle = computed(() => {
  const pct = props.progress.total > 0
    ? (props.progress.done / props.progress.total * 100).toFixed(1)
    : 0;
  return `width:${pct}%`;
});

watch(() => props.logs, () => {
  nextTick(() => {
    if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight;
  });
}, { deep: true });
</script>

<style scoped>
.connectivity-progress {
  margin-top: 16px;
}

.connectivity-result .card {
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px;
}

.connectivity-result .card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.connectivity-result .card-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 6px;
}

.connectivity-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
}

.connectivity-metric {
  display: flex;
  align-items: center;
  gap: 6px;
}

.connectivity-metric-label {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 600;
  text-transform: uppercase;
}

.connectivity-metric-value {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}
</style>
