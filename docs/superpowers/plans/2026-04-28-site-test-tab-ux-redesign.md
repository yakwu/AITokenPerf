# SiteTestTab UX 重设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 SiteTestTab 中的"基准测试"和"渠道诊断"拆分为两个独立 Tab，消除用户困惑

**Architecture:** 单文件 Vue 组件重构，模型选择器提到 Tab 上方共享，基准测试和渠道诊断各占一个 Tab，互不干扰

**Tech Stack:** Vue 3 Composition API, CSS

---

### Task 1: 添加 Tab 状态和 Tab 切换 UI

**Files:**
- Modify: `frontend/src/components/SiteTestTab.vue`

- [ ] **Step 1: 在 `<script setup>` 中添加 `activeTab` 状态**

在 `const showAdvanced = ref(false);` 之后添加：

```js
const activeTab = ref('bench'); // 'bench' | 'diag'
```

- [ ] **Step 2: 在 `<template>` 中将模型选择器提到 form-grid 外面**

把 `<div class="form-grid">` 内部的模型选择器（lines 9-49，从 `<div class="form-group form-group--full">` 到 `</div>` 结束）整体移到 `<div class="form-grid">` 上方，保留原有结构不变。

具体：将 `<div class="card-header">` 和 `<div class="form-grid">` 之间的内容改为：

```html
      <div class="card-header">
        <div class="card-title">测试配置</div>
      </div>

      <!-- Model Selection — shared across tabs -->
      <div class="form-group form-group--full" style="margin-bottom:16px">
        <label class="form-label">选择模型 <span class="info-tip" data-tip="从站点已配置的模型中选择一个或多个进行测试">?</span></label>
        <div class="combobox" ref="modelComboboxRef">
          <!-- ... 原模型选择器内容不变 ... -->
        </div>
      </div>

      <!-- Tab Switcher -->
      <div class="tab-switcher">
        <button class="tab-btn" :class="{ active: activeTab === 'bench' }" @click="activeTab = 'bench'">基准测试</button>
        <button class="tab-btn" :class="{ active: activeTab === 'diag' }" @click="activeTab = 'diag'">渠道诊断</button>
      </div>
```

- [ ] **Step 3: 包裹基准测试内容**

将从"Mode Selection"到"Action Buttons"结束（不含 ConnectivityProgress 和诊断结果）的所有内容包裹在：

```html
      <template v-if="activeTab === 'bench'">
        <!-- Mode Selection -->
        ...
        <!-- Action Buttons (只保留开始测试、停止、连通性验证) -->
      </template>
```

从基准测试的 Action Buttons 中**移除**缓存诊断相关按钮（lines 140-145）：
```html
        <!-- 删除这两段 -->
        <button class="btn btn-ghost" v-show="!running && !diagRunning" @click="runDiagnostics()" ...>
          缓存诊断 ...
        </button>
        <button class="btn btn-ghost" v-show="diagRunning" disabled ...>
          诊断中...
        </button>
```

- [ ] **Step 4: 创建渠道诊断 Tab 内容**

在 `</template>` (基准测试) 之后、`<ConnectivityProgress` 之前，添加：

```html
      <!-- Diagnostics Tab -->
      <template v-if="activeTab === 'diag'">
        <div class="diag-tab-content">
          <div class="diag-info">
            <p style="font-size:13px;color:var(--text-secondary);margin:0 0 8px">
              诊断使用内置固定 prompt 测试渠道的缓存支持情况，不使用上方的提示词配置。
            </p>
            <p style="font-size:12px;color:var(--text-tertiary);margin:0">
              预计消耗 ~10 个请求、~25K tokens
            </p>
          </div>

          <div class="btn-group" style="margin-top:16px">
            <button class="btn btn-ghost" v-show="!diagRunning" @click="runDiagnostics()" :disabled="!selectedModels.length" style="color:var(--accent)">
              开始诊断 <span style="font-weight:400;color:var(--text-tertiary)">({{ selectedModels.length }} 个模型)</span>
            </button>
            <button class="btn btn-ghost" v-show="diagRunning" disabled style="color:var(--text-tertiary)">
              诊断中...
            </button>
          </div>

          <!-- Diagnostic Results -->
          <div v-if="Object.keys(diagResults).length > 0" style="margin-top:16px">
            <div v-for="(result, model) in diagResults" :key="model" style="padding:12px 16px;background:var(--bg);border-radius:8px;margin-bottom:8px;border-left:3px solid var(--accent)">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                <span style="font-family:var(--font-mono);font-size:13px;font-weight:600">{{ model }}</span>
                <span :style="'background:' + diagStatusColor(result.status) + ';color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600'">
                  {{ diagStatusLabel(result.status) }}
                </span>
              </div>
              <div style="display:flex;gap:16px;font-size:12px;color:var(--text-secondary)">
                <span v-if="result.cache_hit_rate != null">缓存命中率: <strong>{{ (result.cache_hit_rate * 100).toFixed(1) }}%</strong></span>
                <span v-if="result.overall_risk">风险: <strong>{{ result.overall_risk }}</strong></span>
                <span v-if="result.confidence != null">置信度: <strong>{{ (result.confidence * 100).toFixed(0) }}%</strong></span>
              </div>
            </div>
          </div>
        </div>
      </template>
```

- [ ] **Step 5: 移除旧的诊断结果区域**

删除原来在 `<ConnectivityProgress>` 之后的诊断结果展示（lines 157-172）：

```html
      <!-- 删除这段 -->
      <!-- Diagnostic Results -->
      <div v-if="Object.keys(diagResults).length > 0" style="margin-top:16px">
        ...
      </div>
```

- [ ] **Step 6: 移除高级参数中的"渠道诊断" checkbox**

删除高级参数中的渠道诊断 checkbox（lines 113-119）：

```html
          <!-- 删除这段 -->
          <div class="form-group form-group--full">
            <label class="form-label">渠道诊断 ...</label>
            <label class="checkbox-label" ...>
              <input type="checkbox" v-model="enableDiagnostics">
              <span>启用缓存诊断（运行测试前先检测缓存命中率）</span>
            </label>
          </div>
```

同时在 `<script setup>` 中删除 `const enableDiagnostics = ref(false);`

- [ ] **Step 7: 添加 Tab 切换 CSS**

在 `<style scoped>` 中添加：

```css
/* ---- Tab Switcher ---- */
.tab-switcher {
  display: flex;
  gap: 4px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0;
}

.tab-btn {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
  margin-bottom: -1px;
}

.tab-btn:hover {
  color: var(--text-secondary);
}

.tab-btn.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

/* ---- Diagnostics Tab ---- */
.diag-tab-content {
  padding: 4px 0;
}

.diag-info {
  padding: 12px 16px;
  background: var(--bg);
  border-radius: var(--radius);
  border-left: 3px solid var(--accent);
}
```

- [ ] **Step 8: 构建前端并验证**

```bash
cd frontend && bun run build
```

Expected: 构建成功，无报错

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/SiteTestTab.vue
git commit -m "refactor: 拆分基准测试和渠道诊断为独立 Tab"
```
