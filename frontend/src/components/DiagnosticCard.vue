<template>
  <div class="diag-result-card" :class="{ 'diag-pending': status === 'pending' }">
    <!-- Category-based rendering (new) -->
    <template v-if="categories && categories.length">
      <!-- Overall bar -->
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">
        <span :style="'background:' + diagStatusColor(overallStatus || status) + ';color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600'">
          {{ overallStatusLabel || diagStatusLabel(overallStatus || status) }}
        </span>
        <span v-if="confidence != null" style="font-size:12px;color:var(--text-secondary)">置信度: <strong>{{ (confidence * 100).toFixed(0) }}%</strong></span>
      </div>

      <!-- Category sections -->
      <div v-for="cat in categories" :key="cat.category" class="diag-category-section" style="border:1px solid var(--border-subtle);border-radius:6px;margin-bottom:6px;overflow:hidden">
        <div class="diag-cat-header" @click="toggleCategory(cat.category)" style="display:flex;align-items:center;gap:8px;padding:8px 10px;cursor:pointer;user-select:none;font-size:12px">
          <span style="width:8px;height:8px;border-radius:50%;flex-shrink:0" :style="'background:' + categoryStatusColor(cat.status)"></span>
          <span style="font-weight:600">{{ categoryLabel(cat.category) }}</span>
          <span style="font-size:11px;color:var(--text-tertiary);margin-left:auto">{{ cat.probes?.length || 0 }} 个探针</span>
          <span style="font-size:9px;color:var(--text-tertiary)">{{ expandedCategories.has(cat.category) ? '▲' : '▼' }}</span>
        </div>
        <div v-if="expandedCategories.has(cat.category)" style="padding:0 10px 10px;border-top:1px solid var(--border-subtle)">
          <div v-for="probe in (cat.probes || [])" :key="probe.name" style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:12px;border-bottom:1px solid var(--border-subtle)">
            <span style="min-width:100px;color:var(--text-secondary)">{{ probeDisplayName(probe.name) }}</span>
            <span style="flex:1;font-size:11px;color:var(--text-tertiary)">{{ probe.detail || '' }}</span>
            <span style="font-family:var(--font-mono);font-size:11px;color:var(--text-tertiary)">{{ probe.latency_ms ? (probe.latency_ms / 1000).toFixed(1) + 's' : '' }}</span>
            <span :style="'font-weight:600;font-size:11px;color:' + (probe.status === 'passed' ? 'var(--success)' : 'var(--danger)')">
              {{ probe.status === 'passed' ? '✓' : '✗' }}
            </span>
          </div>
          <!-- Cache-specific summary -->
          <div v-if="cat.category === 'cache' && cat.summary?.hit_rate != null" style="margin-top:6px;font-size:11px;color:var(--text-secondary)">
            命中率: {{ (cat.summary.hit_rate * 100).toFixed(1) }}%
            <span v-if="cat.summary.prompt_cache_status"> · 状态: {{ cat.summary.prompt_cache_status }}</span>
          </div>
          <!-- Proxy warning -->
          <div v-if="cat.summary?.proxy_cache?.status === 'detected'" style="margin-top:4px;font-size:11px;color:var(--warning);padding:4px 6px;background:var(--warning-bg,#fff8e1);border-radius:4px">
            检测到代理层缓存干扰: {{ cat.summary.proxy_cache.evidence }}
          </div>
        </div>
      </div>
    </template>

    <!-- Legacy rendering (backward compatible) -->
    <template v-else>
      <!-- Status badge -->
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">
        <span :style="'background:' + diagStatusColor(status) + ';color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600'">
          {{ diagStatusLabel(status) }}
        </span>
        <span v-if="confidence != null" style="font-size:12px;color:var(--text-secondary)">置信度: <strong>{{ (confidence * 100).toFixed(0) }}%</strong></span>
      </div>

      <!-- Cache hit rate -->
      <div v-if="report?.cache_hit_rate != null" style="font-size:12px;color:var(--text-secondary);margin-bottom:8px">
        缓存命中率: <strong>{{ (report.cache_hit_rate * 100).toFixed(1) }}%</strong>
      </div>

      <!-- Proxy warning -->
      <div v-if="report?.proxy_cache_status === 'detected'" style="font-size:11px;color:var(--warning);padding:6px 8px;background:var(--warning-bg,#fff8e1);border-radius:4px;margin-bottom:8px">
        检测到代理层缓存干扰: {{ report.proxy_cache_evidence }}
      </div>

      <!-- Probe details -->
      <div v-if="report?.probes?.length" style="margin-top:8px">
        <div v-for="probe in report.probes" :key="probe.name" style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:12px;border-bottom:1px solid var(--border-subtle)">
          <span style="min-width:100px;color:var(--text-secondary)">{{ diagProbeLabel(probe.name) }}</span>
          <span style="flex:1;font-size:11px;color:var(--text-tertiary)">{{ probe.detail || '' }}</span>
          <span style="font-family:var(--font-mono);font-size:11px;color:var(--text-tertiary)">{{ probe.latency_ms ? (probe.latency_ms / 1000).toFixed(1) + 's' : '' }}</span>
          <span :style="'font-weight:600;font-size:11px;color:' + (probe.status === 'passed' ? 'var(--success)' : 'var(--danger)')">
            {{ probe.status === 'passed' ? '✓' : '✗' }}
          </span>
        </div>
      </div>

      <!-- Run tag -->
      <div v-if="report?.run_tag" style="margin-top:8px;font-size:10px;color:var(--text-tertiary)">
        运行标识: {{ report.run_tag }}
      </div>

      <!-- Response cache warning -->
      <div v-if="report?.response_cache_detected" style="margin-top:6px;font-size:11px;color:var(--warning);padding:4px 6px;background:var(--warning-bg,#fff8e1);border-radius:4px">
        检测到响应缓存: 完全相同的请求返回了缓存响应
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import {
  diagStatusColor,
  diagStatusLabel,
  diagStatusTooltip,
  diagProbeLabel,
  probeTokenColor,
  probeTokenCheck,
  categoryLabel,
  probeDisplayName,
  categoryStatusColor,
} from '../utils/diagnosticUtils.js'

const props = defineProps({
  report: { type: Object, default: null },
  status: { type: String, default: 'pending' },
  overallRisk: { type: String, default: '' },
  confidence: { type: Number, default: null },
  categories: { type: Array, default: null },
  overallStatus: { type: String, default: '' },
})

const expandedCategories = ref(new Set(['connectivity', 'streaming', 'context', 'tool_use', 'structured', 'cache']))

function toggleCategory(catId) {
  const s = new Set(expandedCategories.value)
  if (s.has(catId)) s.delete(catId); else s.add(catId)
  expandedCategories.value = s
}

const overallStatusLabel = computed(() => {
  if (!props.overallStatus) return ''
  const map = { passed: '全部通过', warning: '部分存疑', failed: '存在失败', error: '诊断出错' }
  return map[props.overallStatus] || props.overallStatus
})
</script>

<style scoped>
.diag-result-card {
  background: var(--surface-raised, var(--bg));
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px;
  font-size: 12px;
}

.diag-result-card.diag-pending {
  opacity: 0.5;
}

.diag-cat-header:hover {
  background: var(--border-subtle);
}

.diag-category-section:last-child {
  margin-bottom: 0;
}
</style>
