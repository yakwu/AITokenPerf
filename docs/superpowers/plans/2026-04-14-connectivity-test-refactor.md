# 连通性验证统一重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将三处独立的连通性测试实现（SiteConfigTab、SiteTestTab、ProfileView）统一为一个可复用的 composable + UI 组件。

**Architecture:** 创建 `useConnectivityTest` composable 封装 "调 bench/start → SSE 监听 → 收集结果" 的完整流程，创建 `ConnectivityProgress.vue` 组件渲染内联进度面板。三个消费���引入复用，删除各自的冗余实现。

**Tech Stack:** Vue 3 Composition API, SSE (EventSource), 现有 `useBenchSSE` composable

---

## File Structure

| 操作 | 文件 | 职责 |
|------|------|------|
| Create | `frontend/src/composables/useConnectivityTest.js` | 封装连通性验证逻辑（API 调用 + SSE + 状态） |
| Create | `frontend/src/components/ConnectivityProgress.vue` | 内联进度面板 UI（进度条 + 统计 + 日志 + 结果指标） |
| Modify | `frontend/src/components/SiteConfigTab.vue` | 删除 `dryRunTest()`，引入 composable + 组件 |
| Modify | `frontend/src/components/SiteTestTab.vue` | 删除 `dryRun()` + `runWithSSE()` 中 dry-run 相关逻辑，引入 composable + 组件 |
| Modify | `frontend/src/views/ProfileView.vue` | 删除 `dryRunTest()`，引入 composable + 组件 |

---

### Task 1: 创建 `useConnectivityTest` composable

**Files:**
- Create: `frontend/src/composables/useConnectivityTest.js`
- Read: `frontend/src/composables/useBenchSSE.js`

- [ ] **Step 1: 创建 composable 文件**

```js
// frontend/src/composables/useConnectivityTest.js
import { ref, onUnmounted } from 'vue';
import { api } from '../api/index.js';
import { useBenchSSE } from './useBenchSSE.js';
import { toast } from './useToast.js';
import { escHtml } from '../utils/formatters.js';

export function useConnectivityTest() {
  const running = ref(false);
  const progress = ref({ done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' });
  const logs = ref([]);
  const result = ref(null);   // bench:level_complete 返回的 result 对象
  const error = ref(null);

  const benchSSE = useBenchSSE();
  let elapsedTimer = null;
  let startTime = 0;

  function logLine(html) {
    const time = new Date().toLocaleTimeString();
    logs.value = [...logs.value, `[${time}] ${html}`];
  }

  function cleanup() {
    benchSSE.disconnect();
    if (elapsedTimer) {
      clearInterval(elapsedTimer);
      elapsedTimer = null;
    }
  }

  function reset() {
    running.value = false;
    progress.value = { done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' };
    logs.value = [];
    result.value = null;
    error.value = null;
  }

  /**
   * 启动连通性验证
   * @param {Object} config - { base_url, api_key, model, provider?, custom_endpoint? }
   */
  async function start(config) {
    reset();
    running.value = true;

    const model = config.model;
    logLine(`<span class="info">连通性验证: ${escHtml(model)}</span>`);

    try {
      const res = await api('/api/bench/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: config.base_url,
          api_key: config.api_key,
          model,
          provider: config.provider || '',
          custom_endpoint: config.custom_endpoint || false,
          concurrency_levels: [1],
          requests_per_level: 1,
          mode: 'burst',
          max_tokens: 512,
          timeout: 120,
          duration: 120,
          system_prompt: 'You are a helpful assistant.',
          user_prompt: 'Say hello.',
        }),
      });

      if (res.error) {
        error.value = res.error;
        toast(res.error, 'error');
        logLine(`<span class="fail">${escHtml(res.error)}</span>`);
        running.value = false;
        return;
      }

      await waitForSSE(model);
    } catch (e) {
      error.value = e.message;
      toast('连通性验证失败: ' + e.message, 'error');
      logLine(`<span class="fail">${escHtml(e.message)}</span>`);
    }
    running.value = false;
  }

  function waitForSSE(modelName) {
    return new Promise((resolve) => {
      startTime = Date.now();
      progress.value = { done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' };

      benchSSE.connect((type, d) => {
        switch (type) {
          case 'bench:start':
            logLine(`<span class="info">请求发送中...</span>`);
            break;
          case 'bench:progress':
            progress.value = {
              ...progress.value,
              done: d.done,
              success: d.success,
              failed: d.failed,
              total: d.total,
              elapsed: d.elapsed,
            };
            if (d.elapsed > 0) progress.value.rate = (d.done / d.elapsed).toFixed(1);
            break;
          case 'bench:level_complete':
            result.value = d.result;
            logLine(`<span class="ok">验证完成</span>`);
            break;
          case 'bench:complete':
            cleanup();
            if (!error.value && result.value) {
              toast('连通性验证通过', 'success');
            }
            resolve();
            break;
          case 'bench:stopped':
            cleanup();
            logLine(`<span class="fail">已停止</span>`);
            resolve();
            break;
          case 'bench:error':
            cleanup();
            error.value = d.error;
            logLine(`<span class="fail">错误: ${escHtml(d.error)}</span>`);
            resolve();
            break;
        }
      });

      elapsedTimer = setInterval(() => {
        if (running.value && startTime) {
          progress.value.elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        }
      }, 1000);
    });
  }

  function stop() {
    cleanup();
    running.value = false;
  }

  onUnmounted(() => cleanup());

  return { running, progress, logs, result, error, start, stop, reset };
}
```

- [ ] **Step 2: 确认文件创建成功**

Run: `head -5 frontend/src/composables/useConnectivityTest.js`
Expected: 看到 import 语句

- [ ] **Step 3: Commit**

```bash
git add frontend/src/composables/useConnectivityTest.js
git commit -m "feat: 新增 useConnectivityTest composable 统一连通性验证逻辑"
```

---

### Task 2: 创建 `ConnectivityProgress.vue` 组件

**Files:**
- Create: `frontend/src/components/ConnectivityProgress.vue`
- Read: `frontend/src/styles/components.css` (全局 progress 样式已存在)
- Read: `frontend/src/utils/formatters.js` (fmtTime, fmtPct, fmtNum)

- [ ] **Step 1: 创建组件文件**

```vue
<!-- frontend/src/components/ConnectivityProgress.vue -->
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
```

- [ ] **Step 2: 确认文件创建成功**

Run: `head -5 frontend/src/components/ConnectivityProgress.vue`
Expected: 看到 `<template>` 标签

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ConnectivityProgress.vue
git commit -m "feat: 新增 ConnectivityProgress 内联进度面板组件"
```

---

### Task 3: 改造 SiteConfigTab.vue

**Files:**
- Modify: `frontend/src/components/SiteConfigTab.vue`

**改动要点：**
- 删除 `testing` ref 和 `canTest()` 和 `dryRunTest()` 函数
- 引入 `useConnectivityTest` 和 `ConnectivityProgress`
- 按钮改为调用 `connTest.start()`
- 按钮下方放置 `<ConnectivityProgress />` 组件
- 按钮文字从"连通性测试"改为"连通性验证"

- [ ] **Step 1: 修改 script 部分 — 替换 imports 和状态**

在 `<script setup>` 中：

删除：
```js
// ---- Connectivity test ----
const testing = ref(false);
```

删除整个 `canTest()` 函数（第 152-159 行）。

删除整个 `dryRunTest()` 函数（第 192-221 行）。

添加 import 和 composable 调用：
```js
import ConnectivityProgress from './ConnectivityProgress.vue';
import { useConnectivityTest } from '../composables/useConnectivityTest.js';

const connTest = useConnectivityTest();

function canTest() {
  return Boolean(
    form.value.base_url.trim() &&
    form.value.api_key.trim() &&
    form.value.models.length > 0 &&
    !connTest.running.value
  );
}

function runConnTest() {
  if (!canTest()) return;
  connTest.start({
    base_url: form.value.base_url,
    api_key: form.value.api_key,
    model: form.value.models[0] || '',
    custom_endpoint: form.value.custom_endpoint,
  });
}
```

- [ ] **Step 2: 修改 template 部分 — 按钮和进度组件**

将按钮行（第 57-59 行）：
```html
<button class="btn btn-ghost" @click="dryRunTest()" :disabled="!canTest()" v-if="form.base_url && form.api_key && form.models.length">
  连通性测试
</button>
```

替换为：
```html
<button class="btn btn-ghost" @click="runConnTest()" :disabled="!canTest()" v-if="form.base_url && form.api_key && form.models.length">
  连通性验证
</button>
```

在 `</div><!-- site-config-actions -->` 之后（第 72 行后），`</div><!-- card -->` 之前，插入：
```html
<ConnectivityProgress
  :running="connTest.running.value"
  :progress="connTest.progress.value"
  :logs="connTest.logs.value"
  :result="connTest.result.value"
  :error="connTest.error.value"
  @dismiss="connTest.reset()"
/>
```

- [ ] **Step 3: 确认编译无报错**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -20` (如果项目有 TypeScript) 或直接 `bun run build 2>&1 | tail -20`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/SiteConfigTab.vue
git commit -m "refactor: SiteConfigTab 连通性测试改用统一 composable + 进度组件"
```

---

### Task 4: 改造 SiteTestTab.vue

**Files:**
- Modify: `frontend/src/components/SiteTestTab.vue`

**改动要点：**
- 删除 `dryRun()` 函数（第 478-518 行）
- 引入 `useConnectivityTest` 和 `ConnectivityProgress`
- "连通性验证" 按钮改为调用 composable
- 在按钮区域下方（现有 progress-panel 之前）插入 `<ConnectivityProgress />`（仅 dry-run 时显示）
- 保留 `startBench()` / `runWithSSE()` / `stopBench()` 等完整压测流程不变

- [ ] **Step 1: 添加 import 和 composable**

在 `<script setup>` 的 import 区域添加：
```js
import ConnectivityProgress from './ConnectivityProgress.vue';
import { useConnectivityTest } from '../composables/useConnectivityTest.js';
```

在 running state 区域（`const running = ref(false)` 附近）添加：
```js
const connTest = useConnectivityTest();
```

- [ ] **Step 2: 删除 dryRun 函数，新增 runConnTest**

删除整个 `dryRun()` 函数（第 478-518 行）。

添加：
```js
function runConnTest() {
  if (!selectedModels.value.length) {
    toast('请至少选择一个模型', 'info');
    return;
  }
  connTest.start({
    base_url: props.profile.base_url,
    api_key: props.profile.api_key_display || props.profile.api_key,
    model: selectedModels.value[0],
    provider: props.profile.provider || '',
    custom_endpoint: props.profile.custom_endpoint || false,
  });
}
```

- [ ] **Step 3: 修改 template — 按钮和组件**

将第 123 行的按钮：
```html
<button class="btn btn-ghost" v-show="!running" @click="dryRun()" :disabled="!selectedModels.length">
  连通性验证 <span style="font-weight:400;color:var(--text-tertiary)">(单请求)</span>
</button>
```

替换为：
```html
<button class="btn btn-ghost" v-show="!running && !connTest.running.value" @click="runConnTest()" :disabled="!selectedModels.length">
  连通性验证 <span style="font-weight:400;color:var(--text-tertiary)">(单请求)</span>
</button>
```

在 `</div><!-- btn-group -->` 和 `<!-- Progress Panel -->` 之间插入：
```html
<ConnectivityProgress
  :running="connTest.running.value"
  :progress="connTest.progress.value"
  :logs="connTest.logs.value"
  :result="connTest.result.value"
  :error="connTest.error.value"
  @dismiss="connTest.reset()"
/>
```

- [ ] **Step 4: 确认编译无报错**

Run: `cd frontend && bun run build 2>&1 | tail -20`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SiteTestTab.vue
git commit -m "refactor: SiteTestTab dryRun 改用统一 composable + 进度组件"
```

---

### Task 5: 改造 ProfileView.vue

**Files:**
- Modify: `frontend/src/views/ProfileView.vue`

**改动要点：**
- 删除 `dryRunTest()` 函数（第 540-567 行）
- 引入 `useConnectivityTest` 和 `ConnectivityProgress`
- 按钮文字已经是"连通性验证"，无需改
- 删除跳转 `store.switchTab('bench')` 逻辑
- 在按钮下方插入 `<ConnectivityProgress />`

- [ ] **Step 1: 添加 import 和 composable**

在 `<script setup>` 的 import 区域添加：
```js
import ConnectivityProgress from '../components/ConnectivityProgress.vue';
import { useConnectivityTest } from '../composables/useConnectivityTest.js';
```

在适当位置添加：
```js
const connTest = useConnectivityTest();

function runConnTest() {
  connTest.start({
    base_url: form.value.base_url,
    api_key: form.value.api_key,
    model: form.value.models[0] || '',
    provider: form.value.provider,
    custom_endpoint: form.value.custom_endpoint || false,
  });
}
```

- [ ] **Step 2: 删除旧的 dryRunTest 函数**

删除第 540-567 行的 `dryRunTest()` 函数。

- [ ] **Step 3: 修改 template — 按钮和组件**

将第 118 行的按钮：
```html
<button class="btn btn-ghost" @click="dryRunTest()" v-if="profileMode === 'selected' && form.base_url && form.api_key && form.models.length">
  连通性验证
</button>
```

替换为：
```html
<button class="btn btn-ghost" @click="runConnTest()" :disabled="connTest.running.value" v-if="profileMode === 'selected' && form.base_url && form.api_key && form.models.length">
  连通性验证
</button>
```

在 `</div><!-- profile-actions -->` 之后插入：
```html
<ConnectivityProgress
  :running="connTest.running.value"
  :progress="connTest.progress.value"
  :logs="connTest.logs.value"
  :result="connTest.result.value"
  :error="connTest.error.value"
  @dismiss="connTest.reset()"
/>
```

- [ ] **Step 4: 确认编译无报错**

Run: `cd frontend && bun run build 2>&1 | tail -20`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/ProfileView.vue
git commit -m "refactor: ProfileView 连通性验证改用统一 composable + 进度组件"
```

---

### Task 6: 全局验证

- [ ] **Step 1: 完整构建验证**

Run: `cd frontend && bun run build`
Expected: 构建成功，无 warning 无 error

- [ ] **Step 2: 启动开发服务器手动验证**

Run: `cd frontend && bun run dev`

手动测试清单：
1. 打开配置页 → 点"连通性验证" → 应显示内联进度面板 → 完成后显示 TTFT/TPOT/E2E 指标 → 点关闭可收起
2. 打开测试页 → 点"连通性验证(单请求)" → 同上效果
3. 打开测试页 → 点"开始测试" → 完整压测流程应不受影响，进度面板正常
4. 打开 Profile 管理页 → 点"连通性验证" → 同上效果，不再跳转到 bench 页

- [ ] **Step 3: 最终 Commit**

```bash
git add -A
git commit -m "refactor: 统一三处连通性验证为 useConnectivityTest + ConnectivityProgress"
```
