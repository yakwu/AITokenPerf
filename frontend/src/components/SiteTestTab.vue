<template>
  <div class="site-test-tab">
    <div class="card">
      <div class="card-header">
        <div class="card-title">测试配置</div>
      </div>

      <!-- Model Selection (tag-style combobox) -->
      <div class="form-grid">
        <div class="form-group form-group--full">
          <label class="form-label">选择模型 <span class="info-tip" data-tip="从站点已配置的模型中选择一个或多个进行测试">?</span></label>
          <div class="combobox" ref="modelComboboxRef">
            <div class="model-tags-input" @click="modelDropdownOpen = true">
              <span v-for="(m, i) in selectedModels" :key="m" class="model-tag">
                {{ m }}
                <button type="button" class="model-tag-remove" @click.stop="removeModel(i)">&times;</button>
              </span>
              <input
                class="model-tag-search"
                v-model="modelSearch"
                :placeholder="selectedModels.length ? '' : '选择模型（可多选）'"
                @focus="modelDropdownOpen = true"
                @keydown.enter.prevent="addModelFromSearch()"
                @keydown.backspace="onModelBackspace()"
                @keydown.escape="modelDropdownOpen = false"
                autocomplete="off"
                ref="modelSearchInputRef"
                :disabled="running"
              >
            </div>
            <button class="combobox-toggle" type="button" @click.stop="modelDropdownOpen = !modelDropdownOpen" @mousedown.prevent>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5l3 3 3-3"/></svg>
            </button>
            <div class="combobox-dropdown" v-show="modelDropdownOpen">
              <template v-for="m in filteredModels" :key="m">
                <div class="combobox-option" :class="{ active: selectedModels.includes(m) }" @mousedown.prevent="toggleModel(m)">
                  <span v-if="selectedModels.includes(m)" style="color:var(--accent);margin-right:4px">&#10003;</span>
                  {{ m }}
                </div>
              </template>
              <div class="combobox-empty" v-show="!filteredModels.length && modelSearch">
                无匹配模型
              </div>
              <div class="combobox-empty" v-show="!profileModels.length && !modelSearch">
                站点未配置模型，请先在配置 Tab 中添加模型
              </div>
            </div>
          </div>
        </div>

        <!-- Mode Selection -->
        <div class="form-group">
          <label class="form-label">测试模式</label>
          <div class="radio-group-inline">
            <label class="radio-pill" :class="{ active: form.mode === 'burst' }" @click="form.mode = 'burst'">
              <span>Burst <small>瞬时并发</small></span>
            </label>
            <label class="radio-pill" :class="{ active: form.mode === 'sustained' }" @click="form.mode = 'sustained'">
              <span>Sustained <small>持续压力</small></span>
            </label>
          </div>
        </div>

        <!-- Concurrency -->
        <div class="form-group">
          <label class="form-label">并发数 <span class="info-tip" data-tip="选择并发连接数">?</span></label>
          <div class="chip-group">
            <template v-for="val in concurrencyPresets" :key="val">
              <div class="chip" :class="{ selected: selectedConcurrency === val }" @click="selectedConcurrency = val">
                <span>{{ val }}</span>
              </div>
            </template>
            <div class="chip-custom">
              <input class="form-input" type="number" v-model.number="customConcurrency" placeholder="自定义" min="1" style="width:90px;padding:6px 10px;font-size:13px" @keydown.enter.prevent="addCustomConcurrency()">
              <button class="btn btn-ghost btn-sm" @click="addCustomConcurrency()" style="padding:6px 10px">+</button>
            </div>
          </div>
        </div>

        <!-- Advanced Params (collapsible) -->
        <div class="form-group form-group--full">
          <button class="advanced-toggle" @click="showAdvanced = !showAdvanced">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" :style="{ transform: showAdvanced ? 'rotate(90deg)' : '' }"><polyline points="9 18 15 12 9 6"/></svg>
            高级参数
          </button>
        </div>

        <template v-if="showAdvanced">
          <div class="form-group">
            <label class="form-label">每级请求数 <span class="info-tip" data-tip="每个并发级别发送的总请求数，默认等于并发数">?</span></label>
            <input class="form-input" type="number" v-model.number="requestsPerLevel" placeholder="默认等于并发数" min="1">
          </div>
          <div class="form-group">
            <label class="form-label">最大输出 Tokens</label>
            <input class="form-input" type="number" v-model.number="form.max_tokens">
          </div>
          <div class="form-group">
            <label class="form-label">超时时间 (秒)</label>
            <input class="form-input" type="number" v-model.number="form.timeout">
          </div>
          <div class="form-group" v-show="form.mode === 'sustained'">
            <label class="form-label">持续时长 (秒) <span class="info-tip" data-tip="持续模式下每个并发级别的运行时长（秒）">?</span></label>
            <input class="form-input" type="number" v-model.number="form.duration">
          </div>
          <div class="form-group form-group--full">
            <label class="form-label">系统提示词</label>
            <input class="form-input" v-model="form.system_prompt">
          </div>
          <div class="form-group form-group--full">
            <label class="form-label">用户提示词</label>
            <textarea class="form-textarea" v-model="form.user_prompt" rows="2"></textarea>
          </div>
        </template>
      </div>

      <!-- Action Buttons -->
      <div class="btn-group" style="margin-top:20px">
        <button class="btn btn-primary" v-show="!running" @click="startBench()" :disabled="!selectedModels.length">
          开始测试
          <span v-if="selectedModels.length > 1" style="font-weight:400;color:rgba(255,255,255,0.8)">({{ selectedModels.length }} 个模型)</span>
        </button>
        <button class="btn btn-danger" v-show="running" @click="stopBench()">停止</button>
        <button class="btn btn-ghost" v-show="!running" @click="dryRun()" :disabled="!selectedModels.length">
          连通性验证 <span style="font-weight:400;color:var(--text-tertiary)">(单请求)</span>
        </button>
      </div>

      <!-- Progress Panel -->
      <div class="progress-panel" :class="{ active: running }" v-show="running">
        <div class="card">
          <div class="card-header">
            <div class="card-title">
              运行中...
              <span v-if="currentModelIndex >= 0" style="font-size:12px;font-weight:400;color:var(--text-tertiary);margin-left:8px">
                模型 {{ currentModelIndex + 1 }} / {{ totalModels }}
              </span>
            </div>
          </div>
          <div class="progress-bar-wrap">
            <div class="progress-bar" :style="'width:' + (progress.total > 0 ? (progress.done / progress.total * 100).toFixed(1) : 0) + '%'"></div>
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
            <div class="progress-stat">
              <div class="progress-stat-value">{{ progress.rate }}</div>
              <div class="progress-stat-label">请求/秒</div>
            </div>
          </div>
          <div class="progress-log" ref="progressLogRef">
            <template v-for="(log, i) in logs" :key="i">
              <div v-html="log"></div>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- Live Results: Two-column model card layout -->
    <div class="test-results" v-if="modelResults.length > 0" ref="resultsRef">
      <div class="test-results-grid">
        <div v-for="(mr, idx) in modelResults" :key="mr.model" class="result-model-card">
          <!-- Card Header -->
          <div class="result-model-header">
            <div class="result-model-name">{{ mr.model }}</div>
            <div class="result-model-meta">
              <span v-if="mr.running" class="status-badge running" style="font-size:10px;padding:2px 8px">
                <span class="status-dot"></span>测试中
              </span>
              <span v-else-if="mr.result" class="result-model-concurrency">
                并发 {{ mr.result.config?.concurrency || selectedConcurrency }}
              </span>
            </div>
          </div>

          <!-- Loading State -->
          <div v-if="!mr.result && mr.running" class="result-loading">
            <div class="result-loading-spinner"></div>
            <span>等待结果...</span>
          </div>

          <!-- No Result (pending) -->
          <div v-else-if="!mr.result" class="result-pending">
            <span style="color:var(--text-tertiary);font-size:12px">等待测试</span>
          </div>

          <!-- Result Content -->
          <template v-else>
            <!-- 4 Core Metrics -->
            <div class="result-core-metrics">
              <div class="result-metric result-metric--large">
                <div class="result-metric-label">TTFT P50</div>
                <div class="result-metric-value" :class="latencyClass(mr.result.percentiles?.TTFT?.P50, 0.5, 2)">
                  {{ fmtTime(mr.result.percentiles?.TTFT?.P50) }}
                </div>
              </div>
              <div class="result-metric result-metric--large">
                <div class="result-metric-label">TPOT P50</div>
                <div class="result-metric-value" :class="latencyClass(mr.result.percentiles?.TPOT?.P50, 0.05, 0.2)">
                  {{ fmtTime(mr.result.percentiles?.TPOT?.P50) }}
                </div>
              </div>
              <div class="result-metric result-metric--large">
                <div class="result-metric-label">Token/s</div>
                <div class="result-metric-value" :class="qualityClass(mr.result.summary?.token_throughput_tps, 500, 100)">
                  {{ fmtNum(mr.result.summary?.token_throughput_tps, 0) }}
                </div>
              </div>
              <div class="result-metric result-metric--large">
                <div class="result-metric-label">成功率</div>
                <div class="result-metric-value" :class="successRateClass(mr.result.summary?.success_rate)">
                  {{ fmtPct(mr.result.summary?.success_rate) }}
                </div>
              </div>
            </div>

            <!-- Supplementary Metrics Row -->
            <div class="result-supplementary">
              <div class="result-metric result-metric--compact">
                <span class="result-metric-label">TTFT P95</span>
                <span class="result-metric-value-compact">{{ fmtTime(mr.result.percentiles?.TTFT?.P95) }}</span>
              </div>
              <div class="result-metric result-metric--compact">
                <span class="result-metric-label">E2E P50</span>
                <span class="result-metric-value-compact">{{ fmtTime(mr.result.percentiles?.E2E?.P50) }}</span>
              </div>
              <div class="result-metric result-metric--compact">
                <span class="result-metric-label">吞吐量</span>
                <span class="result-metric-value-compact">{{ fmtNum(mr.result.summary?.throughput_rps) }}/s</span>
              </div>
              <div class="result-metric result-metric--compact">
                <span class="result-metric-label">请求数</span>
                <span class="result-metric-value-compact">{{ mr.result.summary?.total_requests || 0 }}</span>
              </div>
            </div>

            <!-- Detail Button -->
            <div class="result-detail-btn-wrap">
              <button class="btn btn-ghost btn-sm result-detail-btn" @click="viewDetail(mr.result)">
                详情 &rarr;
              </button>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { api } from '../api/index.js';
import { toast } from '../composables/useToast.js';
import { useBenchSSE } from '../composables/useBenchSSE.js';
import { renderResultDetail } from '../utils/resultDetail.js';
import { fmtTime, fmtPct, fmtNum, escHtml } from '../utils/formatters.js';

const props = defineProps({
  profile: { type: Object, required: true },
});

// ---- Template refs ----
const modelComboboxRef = ref(null);
const modelSearchInputRef = ref(null);
const progressLogRef = ref(null);
const resultsRef = ref(null);

// ---- Model selection ----
const selectedModels = ref([]);
const modelSearch = ref('');
const modelDropdownOpen = ref(false);

const profileModels = computed(() => {
  if (!props.profile) return [];
  return props.profile.models || (props.profile.model ? [props.profile.model] : []);
});

const filteredModels = computed(() => {
  const q = (modelSearch.value || '').toLowerCase();
  const models = profileModels.value;
  if (!q) return models;
  return models.filter(m => m.toLowerCase().includes(q));
});

function toggleModel(m) {
  const idx = selectedModels.value.indexOf(m);
  if (idx >= 0) {
    selectedModels.value = selectedModels.value.filter(x => x !== m);
  } else {
    selectedModels.value = [...selectedModels.value, m];
  }
}

function removeModel(index) {
  selectedModels.value.splice(index, 1);
}

function addModelFromSearch() {
  if (modelSearch.value && profileModels.value.includes(modelSearch.value)) {
    if (!selectedModels.value.includes(modelSearch.value)) {
      selectedModels.value = [...selectedModels.value, modelSearch.value];
    }
    modelSearch.value = '';
  }
}

function onModelBackspace() {
  if (!modelSearch.value && selectedModels.value.length) {
    selectedModels.value.pop();
  }
}

// Click outside for model combobox
let modelListenerActive = false;
function handleModelOutside(e) {
  if (modelComboboxRef.value && !modelComboboxRef.value.contains(e.target)) {
    modelDropdownOpen.value = false;
  }
}
function addModelListener() {
  if (modelListenerActive) return;
  modelListenerActive = true;
  setTimeout(() => document.addEventListener('mousedown', handleModelOutside), 0);
}
function removeModelListener() {
  if (!modelListenerActive) return;
  modelListenerActive = false;
  document.removeEventListener('mousedown', handleModelOutside);
}
watch(modelDropdownOpen, (open) => {
  if (open) addModelListener(); else removeModelListener();
});

// ---- Form state ----
const form = ref({
  mode: 'burst',
  max_tokens: 512,
  timeout: 120,
  duration: 120,
  system_prompt: 'You are a helpful assistant.',
  user_prompt: 'Write a short essay about the future of artificial intelligence in exactly 200 words.',
});
const concurrencyPresets = ref([1, 5, 10, 20, 50, 100]);
const selectedConcurrency = ref(10);
const customConcurrency = ref('');
const requestsPerLevel = ref('');
const showAdvanced = ref(false);

// ---- Running state ----
const running = ref(false);
const progress = ref({ done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' });
const logs = ref([]);
const benchSSE = useBenchSSE();
const elapsedTimer = ref(null);
let benchStartTime = 0;

// ---- Multi-model sequential testing ----
const modelQueue = ref([]);
const currentModelIndex = ref(-1);
const totalModels = computed(() => modelQueue.value.length);

// ---- Results per model ----
const modelResults = ref([]);

// ---- Color helpers ----
function latencyClass(value, good, warn) {
  if (value == null) return '';
  return value <= good ? 'success' : value <= warn ? 'warning' : 'danger';
}

function qualityClass(value, good, warn) {
  if (value == null) return '';
  return value >= good ? 'success' : value >= warn ? 'warning' : 'danger';
}

function successRateClass(value) {
  if (value == null) return '';
  return value >= 95 ? 'success' : value >= 80 ? 'warning' : 'danger';
}

// ---- Build config for API call ----
function buildConfig(model) {
  const conc = selectedConcurrency.value || 10;
  const requests = parseInt(requestsPerLevel.value);
  const config = {
    base_url: props.profile.base_url,
    api_key: props.profile.api_key_display || props.profile.api_key,
    model,
    provider: props.profile.provider || '',
    concurrency_levels: [conc],
    mode: form.value.mode,
    max_tokens: parseInt(form.value.max_tokens) || 512,
    timeout: parseInt(form.value.timeout) || 120,
    duration: parseInt(form.value.duration) || 120,
    system_prompt: form.value.system_prompt,
    user_prompt: form.value.user_prompt,
  };
  if (!isNaN(requests) && requests > 0) config.requests_per_level = requests;
  return config;
}

// ---- Test execution ----
async function startBench() {
  if (!selectedModels.value.length) {
    toast('请至少选择一个模型', 'info');
    return;
  }
  if (!props.profile.base_url) {
    toast('站点缺少目标地址', 'error');
    return;
  }

  // Initialize results for all selected models
  modelQueue.value = [...selectedModels.value];
  modelResults.value = selectedModels.value.map(m => ({
    model: m,
    result: null,
    running: false,
  }));
  logs.value = [];
  running.value = true;
  currentModelIndex.value = -1;

  // Run models sequentially
  for (let i = 0; i < modelQueue.value.length; i++) {
    if (!running.value) break;
    currentModelIndex.value = i;
    modelResults.value[i].running = true;
    progress.value = { done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' };

    logLine(`<span class="info">[模型 ${i + 1}/${modelQueue.value.length}] 开始测试 ${escHtml(modelQueue.value[i])}</span>`);

    try {
      const config = buildConfig(modelQueue.value[i]);
      const res = await api('/api/bench/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      if (res.error) {
        toast(`模型 ${modelQueue.value[i]} 启动失败: ${res.error}`, 'error');
        logLine(`<span class="fail">模型 ${escHtml(modelQueue.value[i])} 启动失败: ${escHtml(res.error)}</span>`);
        modelResults.value[i].running = false;
        continue;
      }
      // Wait for SSE to complete
      await runWithSSE(modelQueue.value[i]);
      modelResults.value[i].running = false;
    } catch (e) {
      toast(`模型 ${modelQueue.value[i]} 失败: ${e.message}`, 'error');
      logLine(`<span class="fail">模型 ${escHtml(modelQueue.value[i])} 失败: ${escHtml(e.message)}</span>`);
      modelResults.value[i].running = false;
    }
  }

  running.value = false;
  currentModelIndex.value = -1;
  if (modelResults.value.some(mr => mr.result)) {
    toast('测试完成！', 'success');
  }
}

async function dryRun() {
  if (!selectedModels.value.length) {
    toast('请至少选择一个模型', 'info');
    return;
  }
  // Use first selected model
  const model = selectedModels.value[0];
  const config = buildConfig(model);
  config.concurrency_levels = [1];
  config.requests_per_level = 1;
  config.mode = 'burst';

  running.value = true;
  logs.value = [];
  modelResults.value = [{ model, result: null, running: true }];
  currentModelIndex.value = 0;

  logLine(`<span class="info">连通性验证: ${escHtml(model)}</span>`);

  try {
    const res = await api('/api/bench/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    if (res.error) {
      toast(res.error, 'error');
      logLine(`<span class="fail">${escHtml(res.error)}</span>`);
      running.value = false;
      modelResults.value[0].running = false;
      return;
    }
    await runWithSSE(model);
  } catch (e) {
    toast('失败: ' + e.message, 'error');
    logLine(`<span class="fail">${escHtml(e.message)}</span>`);
  }
  running.value = false;
  modelResults.value[0].running = false;
  currentModelIndex.value = -1;
}

function runWithSSE(modelName) {
  return new Promise((resolve) => {
    benchStartTime = Date.now();
    progress.value = { done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' };

    benchSSE.connect((type, d) => {
      switch (type) {
        case 'bench:start':
          logLine(`<span class="info">[第 ${escHtml(d.current_level)}/${escHtml(d.total_levels)} 级] 启动 并发=${escHtml(d.concurrency)} 模式=${escHtml(d.mode)}</span>`);
          break;
        case 'bench:progress':
          progress.value = { ...progress.value, done: d.done, success: d.success, failed: d.failed, total: d.total, elapsed: d.elapsed };
          if (d.elapsed > 0) progress.value.rate = (d.done / d.elapsed).toFixed(1);
          break;
        case 'bench:level_complete': {
          logLine(`<span class="ok">[完成] 并发=${escHtml(d.concurrency)} -- ${escHtml(modelName)}</span>`);
          // Store result for current model
          const idx = modelResults.value.findIndex(mr => mr.model === modelName);
          if (idx >= 0) {
            modelResults.value[idx].result = d.result;
          }
          if (d.filename) {
            logLine(`<span class="info">结果已保存: ${escHtml(d.filename)}</span>`);
          }
          break;
        }
        case 'bench:complete':
          stopSSE();
          logLine('<span class="ok">测试完成！</span>');
          resolve();
          break;
        case 'bench:stopped':
          stopSSE();
          logLine('<span class="fail">测试已被用户停止</span>');
          resolve();
          break;
        case 'bench:error':
          stopSSE();
          logLine(`<span class="fail">错误: ${escHtml(d.error)}</span>`);
          resolve();
          break;
      }
    });

    elapsedTimer.value = setInterval(() => {
      if (running.value) {
        progress.value.elapsed = ((Date.now() - benchStartTime) / 1000).toFixed(1);
        if (progress.value.elapsed > 0 && progress.value.done > 0) {
          progress.value.rate = (progress.value.done / progress.value.elapsed).toFixed(1);
        }
      }
    }, 1000);
  });
}

async function stopBench() {
  await api('/api/bench/stop', { method: 'POST' });
  running.value = false;
  toast('正在停止...', 'info');
}

function stopSSE() {
  benchSSE.disconnect();
  if (elapsedTimer.value) {
    clearInterval(elapsedTimer.value);
    elapsedTimer.value = null;
  }
}

function logLine(html) {
  const time = new Date().toLocaleTimeString();
  logs.value = [...logs.value, `[${time}] ${html}`];
}

function addCustomConcurrency() {
  const val = parseInt(customConcurrency.value);
  if (!val || val <= 0) return;
  selectedConcurrency.value = val;
  if (!concurrencyPresets.value.includes(val)) {
    concurrencyPresets.value = [...concurrencyPresets.value, val].sort((a, b) => a - b);
  }
  customConcurrency.value = '';
}

// ---- View detail ----
function viewDetail(result) {
  window.showDetailOverlay(renderResultDetail(result));
}

// ---- Auto-select all models when profile changes ----
watch(() => props.profile, (p) => {
  if (p) {
    const models = p.models || (p.model ? [p.model] : []);
    selectedModels.value = [...models];
  }
}, { immediate: true });

// ---- Auto-scroll logs ----
watch(logs, () => {
  nextTick(() => {
    const el = progressLogRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}, { deep: true });

// ---- Cleanup ----
onUnmounted(() => {
  stopSSE();
  removeModelListener();
});
</script>

<style scoped>
.site-test-tab .form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.site-test-tab .form-group--full {
  grid-column: 1 / -1;
}

/* ---- Advanced Toggle ---- */
.advanced-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
  padding: 0;
  transition: color 0.15s;
}

.advanced-toggle:hover {
  color: var(--accent-hover);
}

.advanced-toggle svg {
  transition: transform 0.2s;
}

/* ---- Progress Panel Override ---- */
.site-test-tab .progress-panel {
  margin-top: 24px;
}

/* ---- Results Grid ---- */
.test-results {
  margin-top: 24px;
}

.test-results-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

@media (max-width: 768px) {
  .test-results-grid {
    grid-template-columns: 1fr;
  }
}

/* ---- Result Model Card ---- */
.result-model-card {
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px;
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.15s, transform 0.15s;
}

.result-model-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.result-model-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 8px;
}

.result-model-name {
  font-family: var(--font-mono);
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-model-concurrency {
  font-size: 11px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

.result-model-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* ---- Core Metrics ---- */
.result-core-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 12px;
}

.result-metric--large {
  text-align: center;
  padding: 12px 8px;
  background: var(--bg);
  border-radius: var(--radius);
}

.result-metric--large .result-metric-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

.result-metric--large .result-metric-value {
  font-family: var(--font-mono);
  font-size: 20px;
  font-weight: 700;
  line-height: 1.2;
}

.result-metric-value.success { color: var(--success); }
.result-metric-value.warning { color: var(--warning); }
.result-metric-value.danger { color: var(--danger); }

/* ---- Supplementary Metrics Row ---- */
.result-supplementary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  padding: 10px 0;
  border-top: 1px solid var(--border-subtle);
}

.result-metric--compact {
  display: flex;
  align-items: center;
  gap: 4px;
}

.result-metric--compact .result-metric-label {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.result-metric--compact .result-metric-value-compact {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

/* ---- Detail Button ---- */
.result-detail-btn-wrap {
  margin-top: 8px;
  display: flex;
  justify-content: flex-end;
}

.result-detail-btn {
  font-size: 12px;
}

/* ---- Loading State ---- */
.result-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 32px;
  color: var(--text-tertiary);
  font-size: 13px;
}

.result-loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.result-pending {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
}

/* ---- Responsive ---- */
@media (max-width: 768px) {
  .site-test-tab .form-grid {
    grid-template-columns: 1fr;
  }

  .result-core-metrics {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
