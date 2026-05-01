<template>
  <div class="diag-result-card" :class="{ 'diag-pending': status === 'pending', 'diag-result-card--compact': compact }">
    <!-- 分类诊断渲染 -->
    <template v-if="effectiveCategories && effectiveCategories.length">
      <!-- 渐变头部 -->
      <div class="diag-header" :class="'diag-header--' + (effectiveOverallStatus || status)">
        <div class="diag-header-main">
          <div class="diag-header-status">
            {{ overallStatusLabel || diagStatusLabel(effectiveOverallStatus || status) }}
          </div>
          <div v-if="confidence != null" class="diag-header-confidence">
            置信度 {{ (confidence * 100).toFixed(0) }}%
          </div>
        </div>
        <div class="diag-header-stats">
          <div class="diag-header-stat">
            <div class="diag-header-stat-value">{{ effectiveCategories.length }}</div>
            <div class="diag-header-stat-label">类别</div>
          </div>
          <div class="diag-header-stat">
            <div class="diag-header-stat-value">{{ totalProbes }}</div>
            <div class="diag-header-stat-label">探针</div>
          </div>
        </div>
      </div>

      <!-- 类别状态网格 -->
      <div class="diag-categories-grid">
        <div
          v-for="cat in effectiveCategories"
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

      <!-- 展开的探针详情：每个类别一个区块，探针是区块内的列表项 -->
      <div v-if="expandedCategories.size > 0" class="diag-probes-detail">
        <div
          v-for="cat in effectiveCategories"
          :key="cat.category + '-detail'"
          v-show="expandedCategories.has(cat.category)"
          class="diag-category-block"
        >
          <div class="diag-category-block-title">
            <span class="diag-category-block-dot" :style="{ background: categoryStatusColor(cat.status) }"></span>
            {{ categoryLabel(cat.category) }}
            <span class="diag-category-block-summary">
              {{ cat.probes?.filter(p => p.status === 'passed').length || 0 }}/{{ cat.probes?.length || 0 }} 通过
            </span>
          </div>
          <!-- 缓存摘要 -->
          <div v-if="cat.category === 'cache' && cat.summary?.hit_rate != null" class="diag-block-cache-info">
            命中率 {{ (cat.summary.hit_rate * 100).toFixed(0) }}%
            <span v-if="cat.summary.prompt_cache_status"> · {{ cat.summary.prompt_cache_status }}</span>
          </div>
          <!-- 代理缓存警告 -->
          <div v-if="cat.summary?.proxy_cache?.status === 'detected'" class="diag-proxy-warning">
            检测到代理层缓存干扰: {{ cat.summary.proxy_cache.evidence }}
          </div>
          <!-- 探针列表 -->
          <div class="diag-probe-list">
            <div
              v-for="probe in (cat.probes || [])"
              :key="probe.name"
              class="diag-probe-item"
              :class="{ 'diag-probe-item--fail': probe.status === 'failed' || probe.status === 'error' }"
            >
              <div class="diag-probe-item-main" @click="toggleProbe(probe.name)">
                <span class="diag-probe-badge" :class="'diag-probe-badge--' + probe.status">{{ probeStatusText(probe.status) }}</span>
                <span class="diag-probe-item-name">{{ probeDisplayName(probe.name) }}</span>
                <span class="diag-probe-item-desc" v-if="probe.detail">{{ probe.detail }}</span>
                <span class="diag-probe-item-latency" v-if="probe.latency_ms">{{ (probe.latency_ms / 1000).toFixed(2) }}s</span>
                <span class="diag-probe-item-expand">{{ expandedProbes.has(probe.name) ? '▾' : '▸' }}</span>
              </div>
              <div class="diag-probe-item-meta" v-if="probe.ttft_ms || probe.usage?.input_tokens || probe.usage?.output_tokens || probe.usage?.cache_read_input_tokens">
                <span v-if="probe.ttft_ms">TTFT {{ (probe.ttft_ms / 1000).toFixed(2) }}s</span>
                <span v-if="probe.usage?.input_tokens">输入 {{ probe.usage.input_tokens }}t</span>
                <span v-if="probe.usage?.output_tokens">输出 {{ probe.usage.output_tokens }}t</span>
                <span v-if="probe.usage?.cache_read_input_tokens" style="color:var(--success)">缓存读取 {{ probe.usage.cache_read_input_tokens }}t</span>
              </div>
              <!-- 展开详情 -->
              <div v-if="expandedProbes.has(probe.name)" class="diag-probe-item-detail">
                <div v-if="probe.error" class="diag-probe-section">
                  <div class="diag-probe-section-title" style="color:var(--danger)">错误信息</div>
                  <pre class="diag-probe-pre" style="color:var(--danger)">{{ probe.error }}</pre>
                </div>
                <div v-if="probe.request_preview" class="diag-probe-section">
                  <div class="diag-probe-section-title">请求内容</div>
                  <pre class="diag-probe-pre">{{ probe.request_preview }}</pre>
                </div>
                <div v-if="probe.response_preview" class="diag-probe-section">
                  <div class="diag-probe-section-title">响应内容</div>
                  <pre class="diag-probe-pre">{{ probe.response_preview }}</pre>
                </div>
                <div v-if="probe.raw_usage && Object.keys(probe.raw_usage).length" class="diag-probe-section">
                  <div class="diag-probe-section-title">原始 Usage</div>
                  <pre class="diag-probe-pre">{{ JSON.stringify(probe.raw_usage, null, 2) }}</pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Legacy 旧格式兼容 -->
    <template v-else>
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">
        <span :style="'background:' + probeStatusColor(status) + ';color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600'">
          {{ diagStatusLabel(status) }}
        </span>
        <span v-if="confidence != null" style="font-size:12px;color:var(--text-secondary)">置信度: <strong>{{ (confidence * 100).toFixed(0) }}%</strong></span>
      </div>
      <div v-if="report?.cache_hit_rate != null" style="font-size:12px;color:var(--text-secondary);margin-bottom:8px">
        缓存命中率: <strong>{{ (report.cache_hit_rate * 100).toFixed(1) }}%</strong>
      </div>
      <div v-if="report?.proxy_cache_status === 'detected'" style="font-size:11px;color:var(--warning);padding:6px 8px;background:var(--warning-bg,#fff8e1);border-radius:4px;margin-bottom:8px">
        检测到代理层缓存干扰: {{ report.proxy_cache_evidence }}
      </div>
      <div v-if="report?.probes?.length" style="margin-top:8px">
        <div v-for="probe in report.probes" :key="probe.name" style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:12px;border-bottom:1px solid var(--border-subtle)">
          <span style="min-width:100px;color:var(--text-secondary)">{{ probeDisplayName(probe.name) }}</span>
          <span style="flex:1;font-size:11px;color:var(--text-tertiary)">{{ probe.detail || '' }}</span>
          <span style="font-family:var(--font-mono);font-size:11px;color:var(--text-tertiary)">{{ probe.latency_ms ? (probe.latency_ms / 1000).toFixed(1) + 's' : '' }}</span>
          <span :style="'font-weight:600;font-size:11px;color:' + probeStatusColor(probe.status)">{{ probeStatusIcon(probe.status) }}</span>
        </div>
      </div>
      <div v-if="report?.run_tag" style="margin-top:8px;font-size:10px;color:var(--text-tertiary)">
        运行标识: {{ report.run_tag }}
      </div>
      <div v-if="report?.response_cache_detected" style="margin-top:6px;font-size:11px;color:var(--warning);padding:4px 6px;background:var(--warning-bg,#fff8e1);border-radius:4px">
        检测到响应缓存: 完全相同的请求返回了缓存响应
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import {
  diagStatusLabel,
  categoryLabel,
  probeDisplayName,
  categoryStatusColor,
} from '../utils/diagnosticUtils.js'

const props = defineProps({
  report: { type: Object, default: null },
  status: { type: String, default: 'pending' },
  confidence: { type: Number, default: null },
  categories: { type: Array, default: null },
  overallStatus: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})

const expandedCategories = ref(new Set())
const expandedProbes = ref(new Set())

const effectiveCategories = computed(() => {
  if (props.categories && props.categories.length) return props.categories
  if (props.report?.categories?.length) return props.report.categories
  return null
})

watch(effectiveCategories, (cats) => {
  if (cats && cats.length) {
    expandedCategories.value = new Set(cats.map(c => c.category))
  }
}, { immediate: true })

const effectiveOverallStatus = computed(() => {
  if (props.overallStatus) return props.overallStatus
  if (props.report?.overall_status) return props.report.overall_status
  return props.status
})

const overallStatusLabel = computed(() => {
  const s = effectiveOverallStatus.value
  if (!s) return ''
  const map = { passed: '全部通过', warning: '部分存疑', failed: '存在失败', error: '诊断出错' }
  return map[s] || s
})

const totalProbes = computed(() => {
  const cats = effectiveCategories.value
  if (!cats) return 0
  return cats.reduce((sum, cat) => sum + (cat.probes?.length || 0), 0)
})

function toggleCategory(catId) {
  const s = new Set(expandedCategories.value)
  if (s.has(catId)) s.delete(catId); else s.add(catId)
  expandedCategories.value = s
}

function toggleProbe(probeName) {
  const s = new Set(expandedProbes.value)
  if (s.has(probeName)) s.delete(probeName); else s.add(probeName)
  expandedProbes.value = s
}

function probeStatusColor(status) {
  if (status === 'passed') return 'var(--success)'
  if (status === 'failed' || status === 'error') return 'var(--danger)'
  if (status === 'warning' || status === 'inconclusive') return 'var(--warning)'
  return 'var(--text-tertiary)'
}

function probeStatusText(status) {
  if (status === 'passed') return '通过'
  if (status === 'failed') return '失败'
  if (status === 'error') return '错误'
  if (status === 'warning') return '警告'
  if (status === 'inconclusive') return '存疑'
  return '…'
}

function probeStatusIcon(status) {
  if (status === 'passed') return '✓'
  if (status === 'failed' || status === 'error') return '✗'
  if (status === 'warning') return '⚠'
  if (status === 'inconclusive') return '?'
  return '…'
}
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
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

@media (max-width: 768px) {
  .diag-probes-detail {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .diag-probes-detail {
    grid-template-columns: 1fr;
  }
}

/* 类别区块 */
.diag-category-block {
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  overflow: hidden;
}

.diag-category-block-title {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  background: var(--surface-raised, var(--bg-secondary));
  border-bottom: 1px solid var(--border-subtle);
}

.diag-category-block-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.diag-category-block-summary {
  margin-left: auto;
  font-size: 11px;
  font-weight: 400;
  color: var(--text-tertiary);
}

.diag-block-cache-info {
  padding: 6px 14px;
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--bg);
  border-bottom: 1px solid var(--border-subtle);
}

/* 探针列表 */
.diag-probe-list {
  display: flex;
  flex-direction: column;
}

.diag-probe-item {
  border-bottom: 1px solid var(--border-subtle);
  padding: 10px 14px;
}

.diag-probe-item:last-child {
  border-bottom: none;
}

.diag-probe-item--fail {
  background: var(--danger-bg, #fef2f2);
}

.diag-probe-item-main {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}

.diag-probe-item-main:hover .diag-probe-item-name {
  color: var(--accent);
}

.diag-probe-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  color: #fff;
  flex-shrink: 0;
}

.diag-probe-badge--passed { background: var(--success); }
.diag-probe-badge--warning { background: var(--warning); }
.diag-probe-badge--failed,
.diag-probe-badge--error { background: var(--danger); }
.diag-probe-badge--inconclusive { background: var(--text-tertiary); }

.diag-probe-item-name {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
}

.diag-probe-item-desc {
  font-size: 11px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.diag-probe-item-latency {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  flex-shrink: 0;
}

.diag-probe-item-expand {
  font-size: 10px;
  color: var(--text-tertiary);
  flex-shrink: 0;
  width: 14px;
  text-align: center;
}

.diag-probe-item-meta {
  display: flex;
  gap: 12px;
  padding: 4px 0 0 64px;
  font-size: 11px;
  color: var(--text-tertiary);
}

.diag-probe-item-detail {
  padding: 10px 0 0 64px;
}

.diag-probe-section {
  margin-top: 8px;
}

.diag-probe-section-title {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.diag-probe-pre {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--surface-raised, var(--bg));
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  padding: 8px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
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

/* 紧凑模式 */
.diag-result-card--compact .diag-header {
  padding: 10px 16px;
}

.diag-result-card--compact .diag-header-status {
  font-size: 14px;
}

.diag-result-card--compact .diag-header-confidence {
  font-size: 11px;
}

.diag-result-card--compact .diag-header-stats {
  gap: 14px;
}

.diag-result-card--compact .diag-header-stat-value {
  font-size: 20px;
}

.diag-result-card--compact .diag-header-stat-label {
  font-size: 10px;
}

.diag-result-card--compact .diag-category-card {
  padding: 10px 12px;
  gap: 4px;
}

.diag-result-card--compact .diag-category-name {
  font-size: 12px;
}

.diag-result-card--compact .diag-category-dot {
  width: 10px;
  height: 10px;
}

.diag-result-card--compact .diag-category-stats {
  font-size: 11px;
}

.diag-result-card--compact .diag-category-detail {
  font-size: 10px;
  padding-left: 18px;
}

.diag-result-card--compact .diag-probes-detail {
  padding: 10px;
  gap: 8px;
}

.diag-result-card--compact .diag-category-block-title {
  padding: 8px 12px;
  font-size: 12px;
}

.diag-result-card--compact .diag-probe-item {
  padding: 8px 12px;
}

.diag-result-card--compact .diag-probe-badge {
  font-size: 9px;
  padding: 1px 6px;
}

.diag-result-card--compact .diag-probe-item-name {
  font-size: 12px;
}

.diag-result-card--compact .diag-probe-item-latency {
  font-size: 13px;
}

.diag-result-card--compact .diag-probe-item-desc {
  font-size: 10px;
}

.diag-result-card--compact .diag-probe-item-meta {
  font-size: 10px;
  padding-left: 56px;
}

.diag-result-card--compact .diag-probe-item-detail {
  padding-left: 56px;
}

.diag-result-card--compact .diag-probe-section-title {
  font-size: 9px;
}

.diag-result-card--compact .diag-probe-pre {
  font-size: 10px;
}

.diag-result-card--compact .diag-cache-summary {
  font-size: 10px;
  padding: 6px 10px;
  margin-top: 8px;
}

.diag-result-card--compact .diag-proxy-warning {
  font-size: 10px;
  padding: 6px 10px;
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
