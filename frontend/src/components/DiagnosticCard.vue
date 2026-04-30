<template>
  <div class="diag-result-card" :class="{ 'diag-pending': status === 'pending' }">
    <!-- Category-based rendering (new) -->
    <template v-if="categories && categories.length">
      <!-- 渐变头部 -->
      <div class="diag-header" :class="'diag-header--' + (overallStatus || status)">
        <div class="diag-header-main">
          <div class="diag-header-status">
            {{ overallStatusLabel || diagStatusLabel(overallStatus || status) }}
          </div>
          <div v-if="confidence != null" class="diag-header-confidence">
            置信度 {{ (confidence * 100).toFixed(0) }}%
          </div>
        </div>
        <div class="diag-header-stats" v-if="categories && categories.length">
          <div class="diag-header-stat">
            <div class="diag-header-stat-value">{{ categories.length }}</div>
            <div class="diag-header-stat-label">类别</div>
          </div>
          <div class="diag-header-stat">
            <div class="diag-header-stat-value">{{ totalProbes }}</div>
            <div class="diag-header-stat-label">探针</div>
          </div>
        </div>
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

const totalProbes = computed(() => {
  if (!props.categories) return 0
  return props.categories.reduce((sum, cat) => sum + (cat.probes?.length || 0), 0)
})
</script>

<style scoped>
.diag-result-card {
  background: var(--surface-raised, var(--bg));
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  font-size: 12px;
}

/* 渐变头部 */
.diag-header {
  padding: 20px;
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  color: white;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.diag-header--passed {
  background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
}

.diag-header--warning {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
}

.diag-header--failed,
.diag-header--error {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
}

.diag-header-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.diag-header-status {
  font-size: 24px;
  font-weight: 700;
}

.diag-header-confidence {
  font-size: 13px;
  opacity: 0.9;
}

.diag-header-stats {
  display: flex;
  gap: 24px;
}

.diag-header-stat {
  text-align: center;
}

.diag-header-stat-value {
  font-size: 32px;
  font-weight: 700;
  line-height: 1;
}

.diag-header-stat-label {
  font-size: 11px;
  opacity: 0.9;
  margin-top: 4px;
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
