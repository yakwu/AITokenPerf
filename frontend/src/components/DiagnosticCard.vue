<template>
  <div class="diag-result-card" :class="{ 'diag-pending': status === 'pending' }">
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

    <!-- 类别状态网格 -->
    <div class="diag-categories-grid" v-if="categories && categories.length">
      <div
        v-for="cat in categories"
        :key="cat.category"
        class="diag-category-card"
        :class="{ 'diag-category-card--expanded': expandedCategories.has(cat.category) }"
        @click="toggleCategory(cat.category)"
      >
        <div class="diag-category-card-header">
          <div class="diag-category-dot" :style="{ background: categoryStatusColor(cat.status) }"></div>
          <div class="diag-category-name">{{ categoryLabel(cat.category) }}</div>
          <div class="diag-category-stats">
            {{ cat.probes?.filter(p => p.status === 'passed').length || 0 }}/{{ cat.probes?.length || 0 }} 通过
          </div>
        </div>
        <div class="diag-category-detail">
          <template v-if="cat.category === 'cache' && cat.summary?.hit_rate != null">
            命中率 {{ (cat.summary.hit_rate * 100).toFixed(0) }}%
          </template>
          <template v-else-if="cat.probes?.length">
            {{ (cat.probes.reduce((sum, p) => sum + (p.latency_ms || 0), 0) / 1000).toFixed(1) }}s
          </template>
        </div>
      </div>
    </div>

    <!-- 展开的探针详情 -->
    <div v-if="expandedCategories.size > 0" class="diag-probes-detail">
      <div v-for="cat in categories" :key="cat.category + '-detail'" v-show="expandedCategories.has(cat.category)">
        <div class="diag-probes-category-title">{{ categoryLabel(cat.category) }}</div>
        <div v-for="probe in (cat.probes || [])" :key="probe.name" class="diag-probe-row">
          <span class="diag-probe-name">{{ probeDisplayName(probe.name) }}</span>
          <span class="diag-probe-detail">{{ probe.detail || '' }}</span>
          <span class="diag-probe-latency">{{ probe.latency_ms ? (probe.latency_ms / 1000).toFixed(1) + 's' : '' }}</span>
          <span class="diag-probe-status" :class="'diag-probe-status--' + probe.status">
            {{ probe.status === 'passed' ? '✓' : '✗' }}
          </span>
        </div>
        <!-- 缓存特殊信息 -->
        <div v-if="cat.category === 'cache' && cat.summary?.hit_rate != null" class="diag-cache-summary">
          命中率: {{ (cat.summary.hit_rate * 100).toFixed(1) }}%
          <span v-if="cat.summary.prompt_cache_status"> · 状态: {{ cat.summary.prompt_cache_status }}</span>
        </div>
        <div v-if="cat.summary?.proxy_cache?.status === 'detected'" class="diag-proxy-warning">
          检测到代理层缓存干扰: {{ cat.summary.proxy_cache.evidence }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import {
  diagStatusLabel,
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

const expandedCategories = ref(new Set())

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

/* 类别状态网格 */
.diag-categories-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1px;
  background: var(--border);
  margin: 0;
}

.diag-category-card {
  background: var(--bg);
  padding: 16px;
  cursor: pointer;
  transition: background 0.15s;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.diag-category-card:hover {
  background: var(--surface-raised);
}

.diag-category-card--expanded {
  background: var(--surface-raised);
}

.diag-category-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.diag-category-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  flex-shrink: 0;
}

.diag-category-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.diag-category-stats {
  font-size: 12px;
  color: var(--text-secondary);
  margin-left: auto;
}

.diag-category-detail {
  font-size: 11px;
  color: var(--text-tertiary);
  padding-left: 26px;
}

/* 探针详情 */
.diag-probes-detail {
  border-top: 1px solid var(--border);
  padding: 16px;
}

.diag-probes-category-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.diag-probe-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 12px;
}

.diag-probe-name {
  min-width: 120px;
  color: var(--text-secondary);
  font-weight: 500;
}

.diag-probe-detail {
  flex: 1;
  color: var(--text-tertiary);
  font-size: 11px;
}

.diag-probe-latency {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-tertiary);
  min-width: 40px;
  text-align: right;
}

.diag-probe-status {
  font-weight: 600;
  font-size: 14px;
  min-width: 20px;
  text-align: center;
}

.diag-probe-status--passed {
  color: var(--success);
}

.diag-probe-status--failed {
  color: var(--danger);
}

.diag-cache-summary {
  margin-top: 12px;
  font-size: 11px;
  color: var(--text-secondary);
  padding: 8px 12px;
  background: var(--bg);
  border-radius: var(--radius);
}

.diag-proxy-warning {
  margin-top: 8px;
  font-size: 11px;
  color: var(--warning);
  padding: 8px 12px;
  background: var(--warning-bg, #fff8e1);
  border-radius: var(--radius);
}

/* 响应式 */
@media (max-width: 768px) {
  .diag-categories-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .diag-categories-grid {
    grid-template-columns: 1fr;
  }
}
</style>
