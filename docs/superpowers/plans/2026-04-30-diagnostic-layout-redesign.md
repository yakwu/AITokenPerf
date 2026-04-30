# 诊断报表和历史布局重新设计 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将诊断报表和历史记录从表格布局改为卡片式布局，提升视觉层次和移动端体验

**Architecture:** 使用 Vue 3 Composition API 重构三个核心组件：DiagnosticCard（渐变头部+类别网格）、HistoryView（卡片列表替代表格）、SiteTestTab诊断Tab（卡片式类别选择器）

**Tech Stack:** Vue 3, Vite, CSS Grid/Flexbox, CSS Variables

---

## 文件结构

### 修改的文件
- `frontend/src/components/DiagnosticCard.vue` - 诊断结果卡片组件
- `frontend/src/views/HistoryView.vue` - 历史记录页面
- `frontend/src/components/SiteTestTab.vue` - 站点测试页面（诊断Tab部分）

### 保持不变的文件
- `frontend/src/utils/diagnosticUtils.js` - 工具函数（已满足需求）
- `frontend/src/api/index.js` - API 调用
- `frontend/src/composables/` - 组合式函数

---

## Task 1: DiagnosticCard 渐变头部

**Files:**
- Modify: `frontend/src/components/DiagnosticCard.vue:1-86`

- [ ] **Step 1: 添加渐变头部区域**

在 `<template>` 的开头添加渐变头部：

```vue
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

    <!-- 后续内容... -->
  </div>
</template>
```

- [ ] **Step 2: 添加计算属性 totalProbes**

在 `<script setup>` 中添加：

```javascript
const totalProbes = computed(() => {
  if (!props.categories) return 0
  return props.categories.reduce((sum, cat) => sum + (cat.probes?.length || 0), 0)
})
```

- [ ] **Step 3: 添加渐变头部样式**

在 `<style scoped>` 中添加：

```css
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
```

- [ ] **Step 4: 更新卡片样式**

修改 `.diag-result-card` 样式，移除 padding，添加 overflow hidden：

```css
.diag-result-card {
  background: var(--surface-raised, var(--bg));
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  font-size: 12px;
}
```

- [ ] **Step 5: 提交更改**

```bash
git add frontend/src/components/DiagnosticCard.vue
git commit -m "feat(DiagnosticCard): 添加渐变头部区域"
```

---

## Task 2: DiagnosticCard 类别状态网格

**Files:**
- Modify: `frontend/src/components/DiagnosticCard.vue:4-41`

- [ ] **Step 1: 替换类别渲染部分**

移除旧的 category-based rendering，添加新的网格布局：

```vue
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
```

- [ ] **Step 2: 添加类别网格样式**

```css
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
```

- [ ] **Step 3: 更新响应式样式**

```css
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
```

- [ ] **Step 4: 提交更改**

```bash
git add frontend/src/components/DiagnosticCard.vue
git commit -m "feat(DiagnosticCard): 添加类别状态网格"
```

---

## Task 3: DiagnosticCard 清理旧代码

**Files:**
- Modify: `frontend/src/components/DiagnosticCard.vue`

- [ ] **Step 1: 移除旧的渲染逻辑**

移除 `<template>` 中的旧 category-based rendering（第 4-41 行）和 legacy rendering（第 43-84 行）。

保留新的渐变头部和类别网格。

- [ ] **Step 2: 清理未使用的 props**

检查 `props` 定义，移除不再需要的 props：
- `overallRisk` - 未在新设计中使用

```javascript
const props = defineProps({
  report: { type: Object, default: null },
  status: { type: String, default: 'pending' },
  // 移除 overallRisk
  confidence: { type: Number, default: null },
  categories: { type: Array, default: null },
  overallStatus: { type: String, default: '' },
})
```

- [ ] **Step 3: 清理未使用的 imports**

从 `diagnosticUtils.js` 导入中移除未使用的函数：
- `diagStatusTooltip` - 未使用
- `probeTokenColor` - 未使用
- `probeTokenCheck` - 未使用

```javascript
import {
  diagStatusColor,
  diagStatusLabel,
  // 移除 diagStatusTooltip
  diagProbeLabel,
  // 移除 probeTokenColor
  // 移除 probeTokenCheck
  categoryLabel,
  probeDisplayName,
  categoryStatusColor,
} from '../utils/diagnosticUtils.js'
```

- [ ] **Step 4: 验证功能正常**

运行开发服务器，测试诊断功能：
```bash
cd frontend && bun run dev
```

在浏览器中测试：
1. 进入站点详情页
2. 切换到诊断 Tab
3. 运行诊断
4. 验证渐变头部和类别网格显示正常
5. 点击类别展开/折叠正常

- [ ] **Step 5: 提交更改**

```bash
git add frontend/src/components/DiagnosticCard.vue
git commit -m "refactor(DiagnosticCard): 清理旧代码和未使用的导入"
```

---

## Task 4: HistoryView 卡片布局

**Files:**
- Modify: `frontend/src/views/HistoryView.vue:69-142`

- [ ] **Step 1: 替换表格为卡片列表**

移除 `<table>` 布局，添加卡片列表：

```vue
<!-- Normal card view -->
<div v-else class="history-cards-container">
  <div class="history-cards-list">
    <template v-if="!filtered.length">
      <div class="history-empty">暂无记录</div>
    </template>
    <template v-for="(r, idx) in filtered" :key="r.filename || idx">
      <div
        class="history-card"
        :class="{
          'history-card--expanded': expandedRows.has(idx),
          'history-card--warning': r.summary?.success_rate != null && r.summary.success_rate < 95 && r.summary.success_rate >= 80,
          'history-card--danger': r.summary?.success_rate != null && r.summary.success_rate < 80
        }"
        @click="onRowClick(r, idx, $event)"
      >
        <!-- 卡片头部 -->
        <div class="history-card-header">
          <div class="history-card-info">
            <div class="history-card-model">
              <span class="history-card-model-name">{{ r.config?.model || '-' }}</span>
              <span class="history-card-source" :class="r.schedule_name ? 'history-card-source--schedule' : 'history-card-source--manual'">
                {{ r.schedule_name || '手动' }}
              </span>
            </div>
            <div class="history-card-meta">
              {{ r.config?.base_url || '-' }} · {{ fmtTimestamp(r.timestamp) }} · 并发 {{ r.config?.concurrency || '-' }} · {{ r.config?.mode || '-' }}
            </div>
          </div>
          <div class="history-card-metrics">
            <div class="history-card-metric">
              <div class="history-card-metric-value" :class="successRateClass(r.summary?.success_rate)">
                {{ fmtPct(r.summary?.success_rate) }}
              </div>
              <div class="history-card-metric-label">成功率</div>
            </div>
            <div class="history-card-metric">
              <div class="history-card-metric-value" :class="latencyClass(r.percentiles?.TTFT?.P50, 0.5, 2)">
                {{ fmtTime(r.percentiles?.TTFT?.P50) }}
              </div>
              <div class="history-card-metric-label">TTFT P50</div>
            </div>
            <div class="history-card-metric">
              <div class="history-card-metric-value" :class="qualityClass(r.summary?.throughput_rps, 20, 5)">
                {{ fmtNum(r.summary?.throughput_rps) }}/s
              </div>
              <div class="history-card-metric-label">吞吐量</div>
            </div>
          </div>
          <div class="history-card-actions">
            <input type="checkbox" class="compare-check" :checked="compareSet.has(idx)" @change="toggleCompare(idx)" @click.stop>
            <button v-if="r.config?.profile_name" class="btn btn-ghost btn-sm" @click.stop="rerunAtSite(r)" title="重测">
              重测
            </button>
            <button class="btn btn-ghost btn-sm" @click.stop="rerunResult(r)" title="重新运行">
              ↻
            </button>
            <button class="btn btn-ghost btn-sm btn-danger-text" @click.stop="deleteResult(r.filename || '')" title="删除">
              <span v-if="pendingDelete === (r.filename || '')" class="delete-undo">确认删除</span>
              <span v-else>✕</span>
            </button>
          </div>
        </div>

        <!-- 卡片底部补充信息 -->
        <div class="history-card-footer">
          <span>E2E P50: <strong>{{ fmtTime(r.percentiles?.E2E?.P50) }}</strong></span>
          <span>TTFT P95: <strong>{{ fmtTime(r.percentiles?.TTFT?.P95) }}</strong></span>
          <span>费用: <strong>{{ fmtCostShort(r.summary?.cost_total_usd) }}</strong></span>
          <span>请求数: <strong>{{ r.summary?.total_requests || 0 }}</strong></span>
          <span class="history-card-test-id">Test ID: {{ r.test_id || '-' }}</span>
        </div>

        <!-- 展开的详情 -->
        <div v-if="expandedRows.has(idx)" class="history-card-detail">
          <div v-html="detailHtml[idx]"></div>
        </div>
      </div>
    </template>
  </div>
</div>
```

- [ ] **Step 2: 添加卡片样式**

```css
/* 历史记录卡片布局 */
.history-cards-container {
  padding: 0;
}

.history-cards-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.history-empty {
  text-align: center;
  padding: 40px;
  color: var(--text-tertiary);
  font-size: 13px;
}

.history-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: pointer;
  transition: box-shadow 0.2s, transform 0.2s;
}

.history-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.history-card--warning {
  border-color: var(--warning);
}

.history-card--danger {
  border-color: var(--danger);
}

.history-card-header {
  display: flex;
  align-items: center;
  padding: 16px 20px;
  gap: 20px;
}

.history-card-info {
  flex: 1;
  min-width: 0;
}

.history-card-model {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.history-card-model-name {
  font-size: 15px;
  font-weight: 700;
  font-family: var(--font-mono);
  color: var(--text-primary);
}

.history-card-source {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.history-card-source--manual {
  background: var(--accent-bg, #dbeafe);
  color: var(--accent);
}

.history-card-source--schedule {
  background: var(--warning-bg, #fef3c7);
  color: var(--warning-text, #92400e);
}

.history-card-meta {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-card-metrics {
  display: flex;
  gap: 20px;
  align-items: center;
}

.history-card-metric {
  text-align: center;
  min-width: 60px;
}

.history-card-metric-value {
  font-size: 22px;
  font-weight: 700;
  font-family: var(--font-mono);
  line-height: 1.2;
}

.history-card-metric-value.success { color: var(--success); }
.history-card-metric-value.warning { color: var(--warning); }
.history-card-metric-value.danger { color: var(--danger); }

.history-card-metric-label {
  font-size: 10px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.history-card-actions {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-shrink: 0;
}

.btn-danger-text {
  color: var(--danger) !important;
}

.btn-danger-text:hover {
  background: var(--danger-bg, #fef2f2) !important;
}

.history-card-footer {
  background: var(--surface-raised);
  padding: 10px 20px;
  display: flex;
  gap: 24px;
  font-size: 11px;
  color: var(--text-secondary);
  border-top: 1px solid var(--border-subtle);
  flex-wrap: wrap;
}

.history-card-footer strong {
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.history-card-test-id {
  margin-left: auto;
  color: var(--text-tertiary);
}

.history-card-detail {
  border-top: 1px solid var(--border);
  padding: 16px 20px;
}

.delete-undo {
  color: var(--danger);
  font-weight: 600;
}

/* 响应式 */
@media (max-width: 768px) {
  .history-card-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .history-card-metrics {
    width: 100%;
    justify-content: space-between;
  }

  .history-card-actions {
    width: 100%;
    justify-content: flex-end;
  }

  .history-card-footer {
    gap: 12px;
  }

  .history-card-test-id {
    margin-left: 0;
    width: 100%;
  }
}
```

- [ ] **Step 3: 添加辅助函数**

在 `<script setup>` 中添加：

```javascript
function successRateClass(rate) {
  if (rate == null) return '';
  return rate >= 95 ? 'success' : rate >= 80 ? 'warning' : 'danger';
}

function latencyClass(value, good, warn) {
  if (value == null) return '';
  return value <= good ? 'success' : value <= warn ? 'warning' : 'danger';
}

function qualityClass(value, good, warn) {
  if (value == null) return '';
  return value >= good ? 'success' : value >= warn ? 'warning' : 'danger';
}
```

- [ ] **Step 4: 提交更改**

```bash
git add frontend/src/views/HistoryView.vue
git commit -m "feat(HistoryView): 用卡片布局替代表格布局"
```

---

## Task 5: HistoryView 响应式优化

**Files:**
- Modify: `frontend/src/views/HistoryView.vue`

- [ ] **Step 1: 测试移动端显示**

在浏览器中打开开发者工具，切换到移动设备视图，检查：
1. 卡片是否正确堆叠
2. 指标是否正确排列
3. 操作按钮是否可用

- [ ] **Step 2: 调整移动端样式**

根据测试结果调整断点和样式。确保：
- 768px 以下：指标垂直排列
- 480px 以下：操作按钮堆叠

- [ ] **Step 3: 测试对比功能**

确保对比功能在卡片布局下正常工作：
1. 选择多条记录
2. 点击对比按钮
3. 验证对比视图正常显示

- [ ] **Step 4: 提交更改**

```bash
git add frontend/src/views/HistoryView.vue
git commit -m "fix(HistoryView): 优化移动端响应式布局"
```

---

## Task 6: SiteTestTab 诊断 Tab 类别选择器

**Files:**
- Modify: `frontend/src/components/SiteTestTab.vue:281-341`

- [ ] **Step 1: 替换类别选择器**

移除旧的平铺 checkbox，添加卡片式选择器：

```vue
<!-- Category Selector -->
<div class="diag-category-selector" style="margin-top:12px">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
    <span style="font-size:14px;font-weight:600">测试类别</span>
    <div style="display:flex;gap:8px">
      <button class="btn btn-ghost btn-sm" @click="diagCategories = allDiagCategories.map(c => c.id)">全选</button>
      <button class="btn btn-ghost btn-sm" @click="diagCategories = []">全不选</button>
    </div>
  </div>
  <div class="diag-category-grid">
    <label
      v-for="cat in allDiagCategories"
      :key="cat.id"
      class="diag-category-option"
      :class="{ 'diag-category-option--selected': diagCategories.includes(cat.id) }"
    >
      <input type="checkbox" :value="cat.id" v-model="diagCategories" class="diag-category-checkbox">
      <div class="diag-category-option-content">
        <div class="diag-category-option-label">{{ cat.label }}</div>
        <div class="diag-category-option-desc">{{ cat.desc }}</div>
      </div>
    </label>
  </div>
</div>
```

- [ ] **Step 2: 添加类别选择器样式**

```css
/* 诊断类别选择器 */
.diag-category-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.diag-category-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 16px;
  border: 2px solid var(--border);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s;
  background: var(--bg);
}

.diag-category-option:hover {
  border-color: var(--accent);
  background: var(--accent-bg, #eff6ff);
}

.diag-category-option--selected {
  border-color: var(--accent);
  background: var(--accent-bg, #eff6ff);
}

.diag-category-checkbox {
  accent-color: var(--accent);
  width: 16px;
  height: 16px;
  margin-top: 2px;
  flex-shrink: 0;
}

.diag-category-option-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.diag-category-option-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.diag-category-option-desc {
  font-size: 12px;
  color: var(--text-secondary);
}

@media (max-width: 768px) {
  .diag-category-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .diag-category-grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 3: 优化诊断按钮**

更新诊断按钮样式和文本：

```vue
<div class="btn-group" style="margin-top:16px">
  <button class="btn btn-primary" v-show="!diagRunning" @click="runDiagnostics()" :disabled="!selectedModels.length || !diagCategories.length">
    开始诊断
    <span style="font-weight:400;opacity:0.9">({{ selectedModels.length }} 个模型, {{ diagCategories.length }} 个类别)</span>
  </button>
  <button class="btn btn-ghost" v-show="diagRunning" disabled style="color:var(--text-tertiary)">
    <span class="result-loading-spinner" style="width:14px;height:14px;border-width:2px;margin-right:6px"></span>
    诊断中 ({{ diagProgress.done }}/{{ diagProgress.total }})
  </button>
</div>
```

- [ ] **Step 4: 提交更改**

```bash
git add frontend/src/components/SiteTestTab.vue
git commit -m "feat(SiteTestTab): 重新设计诊断类别选择器"
```

---

## Task 7: SiteTestTab 诊断结果展示

**Files:**
- Modify: `frontend/src/components/SiteTestTab.vue:319-339`

- [ ] **Step 1: 优化诊断结果卡片样式**

更新诊断结果区域的样式：

```vue
<!-- Diagnostic Results -->
<div v-if="Object.keys(diagResults).length > 0" class="diag-results-container">
  <div v-for="model in selectedModels" :key="model" class="diag-result-model-card">
    <div class="diag-result-model-header">
      <span class="diag-result-model-name">{{ model }}</span>
      <span v-if="diagResults[model]?.status === 'pending'" class="diag-result-status diag-result-status--pending">
        等待中
      </span>
      <span v-else-if="diagResults[model]?.status === 'running'" class="diag-result-status diag-result-status--running">
        <span class="result-loading-spinner" style="width:12px;height:12px;border-width:2px"></span>
        诊断中...
      </span>
    </div>
    <DiagnosticCard
      v-if="diagResults[model] && diagResults[model].status !== 'pending' && diagResults[model].status !== 'running'"
      :report="diagResults[model]"
      :status="diagResults[model].status"
      :confidence="diagResults[model].confidence"
      :categories="diagResults[model].categories"
      :overall-status="diagResults[model].overall_status"
    />
  </div>
</div>
```

- [ ] **Step 2: 添加诊断结果样式**

```css
/* 诊断结果展示 */
.diag-results-container {
  margin-top: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.diag-result-model-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.diag-result-model-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--surface-raised);
  border-bottom: 1px solid var(--border-subtle);
}

.diag-result-model-name {
  font-family: var(--font-mono);
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.diag-result-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.diag-result-status--pending {
  color: var(--text-tertiary);
}

.diag-result-status--running {
  color: var(--accent);
}
```

- [ ] **Step 3: 测试诊断流程**

1. 选择模型和类别
2. 点击开始诊断
3. 验证进度显示正常
4. 验证结果卡片显示正确
5. 测试展开/折叠功能

- [ ] **Step 4: 提交更改**

```bash
git add frontend/src/components/SiteTestTab.vue
git commit -m "feat(SiteTestTab): 优化诊断结果展示"
```

---

## Task 8: 集成测试和最终优化

**Files:**
- Modify: `frontend/src/components/DiagnosticCard.vue`
- Modify: `frontend/src/views/HistoryView.vue`
- Modify: `frontend/src/components/SiteTestTab.vue`

- [ ] **Step 1: 运行完整测试流程**

```bash
cd frontend && bun run dev
```

测试场景：
1. **DiagnosticCard:**
   - 运行诊断，验证渐变头部显示正确
   - 验证类别网格显示所有类别
   - 点击类别展开/折叠正常
   - 验证缓存类别特殊显示

2. **HistoryView:**
   - 查看历史记录列表
   - 验证卡片显示关键指标
   - 测试搜索和筛选功能
   - 测试分页功能
   - 测试对比功能
   - 测试删除功能

3. **SiteTestTab:**
   - 验证类别选择器显示正确
   - 测试全选/全不选功能
   - 运行诊断，验证结果展示

- [ ] **Step 2: 修复发现的问题**

记录并修复测试中发现的问题。

- [ ] **Step 3: 性能优化**

检查是否有性能问题：
- 大量记录时的渲染性能
- 动画流畅度
- 内存占用

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat: 完成诊断报表和历史布局重新设计"
```

- [ ] **Step 5: 清理 Visual Companion**

停止 Visual Companion 服务器：
```bash
/Users/yakun/.claude/plugins/cache/claude-plugins-official/superpowers/5.0.7/skills/brainstorming/scripts/stop-server.sh /Users/yakun/linkingrid/AITokenPerf/.claude/worktrees/unified-diagnostics/.superpowers/brainstorm/51301-1777553463
```

---

## 实施顺序

建议按以下顺序实施：

1. **Task 1-3: DiagnosticCard 改进** - 核心组件，影响其他组件
2. **Task 4-5: HistoryView 改进** - 独立页面，可并行开发
3. **Task 6-7: SiteTestTab 改进** - 依赖 DiagnosticCard
4. **Task 8: 集成测试** - 最后验证所有功能

每个 Task 完成后都应该提交，确保代码可追溯。

---

## 注意事项

1. **保持向后兼容** - 新设计应该支持现有的数据格式
2. **响应式优先** - 移动端体验是重要目标
3. **渐进增强** - 先实现核心功能，再优化细节
4. **频繁提交** - 每个 Task 完成后提交，便于回滚
5. **测试驱动** - 边开发边测试，发现问题及时修复
