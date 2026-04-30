<template>
  <div class="site-test-tab">
    <!-- Internal Tabs -->
    <div class="site-test-internal-tabs">
      <button class="site-test-internal-tab" :class="{ active: activeTab === 'test' }" @click="activeTab = 'test'">性能测试</button>
      <button class="site-test-internal-tab" :class="{ active: activeTab === 'diag' }" @click="activeTab = 'diag'">诊断</button>
    </div>

    <!-- Test Tab -->
    <template v-if="activeTab === 'test'">
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
        <button class="btn btn-ghost" v-show="!running && !connTest.running.value" @click="runConnTest()" :disabled="!selectedModels.length">
          连通性验证 <span style="font-weight:400;color:var(--text-tertiary)">(单请求)</span>
        </button>
      </div>

      <ConnectivityProgress
        :running="connTest.running.value"
        :progress="connTest.progress.value"
        :logs="connTest.logs.value"
        :result="connTest.result.value"
        :error="connTest.error.value"
        @dismiss="connTest.reset()"
      />

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
    </template>

    <!-- Diag Tab -->
    <template v-if="activeTab === 'diag'">
      <div class="diag-tab-content">
        <div class="create-form-notice">
          <span style="color:var(--info)">i</span>
          <span>仅支持 Anthropic 协议。选择要测试的类别，点击开始诊断</span>
        </div>

        <!-- Category Selector -->
        <div class="diag-category-selector" style="margin-top:12px">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
            <span style="font-size:13px;font-weight:600">测试类别</span>
            <div style="display:flex;gap:8px">
              <button class="btn btn-ghost btn-sm" @click="diagCategories = allDiagCategories.map(c => c.id)">全选</button>
              <button class="btn btn-ghost btn-sm" @click="diagCategories = []">全不选</button>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px">
            <label v-for="cat in allDiagCategories" :key="cat.id" class="diag-category-item" style="display:flex;align-items:center;gap:6px;padding:6px 10px;border:1px solid var(--border-subtle);border-radius:6px;cursor:pointer;font-size:12px;transition:border-color 0.15s">
              <input type="checkbox" :value="cat.id" v-model="diagCategories" style="accent-color:var(--accent)">
              <div>
                <div style="font-weight:600">{{ cat.label }}</div>
                <div style="font-size:11px;color:var(--text-tertiary)">{{ cat.desc }}</div>
              </div>
            </label>
          </div>
        </div>

        <div class="btn-group" style="margin-top:16px">
          <button class="btn btn-ghost" v-show="!diagRunning" @click="runDiagnostics()" :disabled="!selectedModels.length || !diagCategories.length" style="color:var(--accent)">
            开始诊断 <span style="font-weight:400;color:var(--text-tertiary)">({{ selectedModels.length }} 个模型, {{ diagCategories.length }} 个类别)</span>
          </button>
          <button class="btn btn-ghost" v-show="diagRunning" disabled style="color:var(--text-tertiary)">
            <span class="result-loading-spinner" style="width:14px;height:14px;border-width:2px;margin-right:6px"></span>
            诊断中 ({{ diagProgress.done }}/{{ diagProgress.total }})
          </button>
        </div>

        <!-- Diagnostic Results -->
        <div v-if="Object.keys(diagResults).length > 0" style="margin-top:16px">
          <div v-for="model in selectedModels" :key="model" class="diag-result-card" :class="{ 'diag-pending': diagResults[model]?.status === 'pending' }">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
              <span style="font-family:var(--font-mono);font-size:13px;font-weight:600">{{ model }}</span>
              <span v-if="diagResults[model]?.status === 'pending'" style="color:var(--text-tertiary);font-size:11px">等待中</span>
              <span v-else-if="diagResults[model]?.status === 'running'" style="display:flex;align-items:center;gap:6px;color:var(--text-secondary);font-size:11px">
                <span class="result-loading-spinner" style="width:12px;height:12px;border-width:2px"></span>
                诊断中...
              </span>
            </div>
            <DiagnosticCard
              v-if="diagResults[model] && diagResults[model].status !== 'pending' && diagResults[model].status !== 'running'"
              :report="diagResults[model]"
              :status="diagResults[model].status"
              :overall-risk="diagResults[model].overall_risk"
              :confidence="diagResults[model].confidence"
              :categories="diagResults[model].categories"
              :overall-status="diagResults[model].overall_status"
            />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { api } from '../api/index.js';
import { toast } from '../composables/useToast.js';
import { useBenchSSE } from '../composables/useBenchSSE.js';
import ConnectivityProgress from './ConnectivityProgress.vue';
import DiagnosticCard from './DiagnosticCard.vue';
import { useConnectivityTest } from '../composables/useConnectivityTest.js';
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
const selectedConcurrency = ref(1);
const customConcurrency = ref('');
const requestsPerLevel = ref('');
const showAdvanced = ref(false);

// ---- Diagnostics state ----
const activeTab = ref('test');
const diagCategories = ref(['connectivity', 'streaming', 'context', 'tool_use', 'structured', 'cache'])
const allDiagCategories = [
  { id: 'connectivity', label: '连通性', desc: '基础连通验证' },
  { id: 'streaming', label: '流式传输', desc: '流式长输出' },
  { id: 'context', label: '多轮上下文', desc: '6轮对话' },
  { id: 'tool_use', label: '工具调用', desc: 'function calling' },
  { id: 'structured', label: '结构化输出', desc: 'JSON 输出' },
  { id: 'cache', label: 'Prompt Cache', desc: '缓存诊断' },
]
const diagRunning = ref(false)
const diagProgress = ref({ done: 0, total: 0 })
const diagResults = ref({})

// ---- Running state ----
const running = ref(false);
const progress = ref({ done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' });
const logs = ref([]);
const benchSSE = useBenchSSE();
const connTest = useConnectivityTest();
const elapsedTimer = ref(null);
const currentRunId = ref('');
let benchStartTime = 0;

// ---- Multi-model parallel testing ----
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
function buildConfig(models) {
  const conc = selectedConcurrency.value || 1;
  const requests = parseInt(requestsPerLevel.value);
  const config = {
    profile_name: props.profile.name,
    models,
    source: 'manual',
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
  currentRunId.value = '';
  progress.value = { done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' };

  for (const mr of modelResults.value) mr.running = true;
  logLine(`<span class="info">并行启动 ${selectedModels.value.length} 个模型</span>`);

  try {
    const config = buildConfig([...selectedModels.value]);
    const res = await api('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    if (res.error) {
      toast(res.error, 'error');
      logLine(`<span class="fail">启动失败: ${escHtml(res.error)}</span>`);
      if (res.requested_slots != null) {
        logLine(`<span class="fail">请求槽位 ${escHtml(res.requested_slots)}，可用 ${escHtml(res.available_slots ?? 0)}</span>`);
      }
      running.value = false;
      for (const mr of modelResults.value) mr.running = false;
      return;
    }
    currentRunId.value = res.run_id;
    await runWithSSE(res.run_id);
  } catch (e) {
    toast(`测试失败: ${e.message}`, 'error');
    logLine(`<span class="fail">测试失败: ${escHtml(e.message)}</span>`);
  }

  running.value = false;
  currentModelIndex.value = -1;
  currentRunId.value = '';
  for (const mr of modelResults.value) mr.running = false;
  if (modelResults.value.some(mr => mr.result)) {
    toast('测试完成！', 'success');
  }
}

function runConnTest() {
  if (!selectedModels.value.length) {
    toast('请至少选择一个模型', 'info');
    return;
  }
  connTest.start({
    profile_name: props.profile.name,
    model: selectedModels.value[0],
  });
}

function runWithSSE(runId) {
  return new Promise((resolve) => {
    benchStartTime = Date.now();
    progress.value = { done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' };
    const completedModels = new Set();

    benchSSE.connect(runId, (type, d) => {
      switch (type) {
        case 'bench:start':
          logLine(`<span class="info">[第 ${escHtml(d.current_level)}/${escHtml(d.total_levels)} 级] 启动 并发=${escHtml(d.concurrency)} 模式=${escHtml(d.mode)}</span>`);
          break;
        case 'bench:progress':
          progress.value = { ...progress.value, done: d.done, success: d.success, failed: d.failed, total: d.total, elapsed: d.elapsed };
          if (d.elapsed > 0) progress.value.rate = (d.done / d.elapsed).toFixed(1);
          break;
        case 'bench:level_complete': {
          const modelName = d.model || d.result?.config?.model || '';
          logLine(`<span class="ok">[完成] 并发=${escHtml(d.concurrency)} -- ${escHtml(modelName || '-')}</span>`);
          const idx = modelResults.value.findIndex(mr => mr.model === modelName);
          if (idx >= 0) {
            modelResults.value[idx].result = d.result;
            modelResults.value[idx].running = false;
          }
          if (d.filename) {
            logLine(`<span class="info">结果已保存: ${escHtml(d.filename)}</span>`);
          }
          break;
        }
        case 'bench:complete': {
          // 多模型并行时，每个模型都会发 bench:complete，需等全部完成才关闭
          if (d.model) completedModels.add(d.model);
          const doneCount = completedModels.size;
          const totalCount = modelResults.value.length;
          logLine(`<span class="ok">模型 ${d.model || ''} 测试完成 (${doneCount}/${totalCount})</span>`);
          if (doneCount >= totalCount) {
            stopSSE();
            logLine('<span class="ok">所有模型测试完成！</span>');
            resolve();
          }
          break;
        }
        case 'bench:stopped':
          stopSSE();
          logLine('<span class="fail">测试已被用户停止</span>');
          resolve();
          break;
        case 'bench:error': {
          // 多模型并行时，某个模型出错不应中断其他模型
          if (d.model) {
            completedModels.add(d.model);
            const idx = modelResults.value.findIndex(mr => mr.model === d.model);
            if (idx >= 0) modelResults.value[idx].running = false;
          }
          logLine(`<span class="fail">模型 ${d.model || ''} 错误: ${escHtml(d.error)}</span>`);
          const doneCount = completedModels.size;
          const totalCount = modelResults.value.length;
          if (doneCount >= totalCount) {
            stopSSE();
            resolve();
          }
          break;
        }
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
  if (currentRunId.value) {
    await api(`/api/runs/${encodeURIComponent(currentRunId.value)}/stop`, { method: 'POST' });
  }
  running.value = false;
  toast('正在停止...', 'info');
}

// ---- Diagnostics ----
async function runDiagnostics() {
  if (!selectedModels.value.length) {
    toast('请至少选择一个模型', 'info')
    return
  }
  if (!diagCategories.value.length) {
    toast('请至少选择一个测试类别', 'info')
    return
  }
  if (!props.profile.base_url) {
    toast('站点缺少目标地址', 'error')
    return
  }

  diagRunning.value = true
  diagProgress.value = { done: 0, total: selectedModels.value.length }
  diagResults.value = {}
  // Initialize pending state for all models
  for (const m of selectedModels.value) {
    diagResults.value[m] = { status: 'pending' }
  }

  try {
    // Run diagnostics for each model sequentially
    for (const model of selectedModels.value) {
      diagResults.value[model] = { ...diagResults.value[model], status: 'running' }
      try {
        const res = await api('/api/diagnostics', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            profile_name: props.profile.name,
            model,
            categories: diagCategories.value,
          }),
        })
        if (res.error) {
          diagResults.value[model] = { status: 'error', error: res.error }
        } else {
          diagResults.value[model] = res
        }
      } catch (e) {
        diagResults.value[model] = { status: 'error', error: e.message }
      }
      diagProgress.value.done++
    }
    toast('诊断完成！', 'success')
  } catch (e) {
    toast(`诊断失败: ${e.message}`, 'error')
  }

  diagRunning.value = false
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

/* ---- Internal Tabs ---- */
.site-test-internal-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 16px;
}

.site-test-internal-tab {
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.site-test-internal-tab:hover {
  color: var(--text-primary);
}

.site-test-internal-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

/* ---- Diagnostics Tab ---- */
.diag-tab-content {
  animation: fadeIn 0.15s ease;
}

.create-form-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  padding: 8px 12px;
  background: var(--bg);
  border-radius: var(--radius);
  border: 1px solid var(--border-subtle);
}

.diag-category-item:hover {
  border-color: var(--accent) !important;
}

.diag-result-card {
  background: var(--surface-raised, var(--bg));
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px;
  margin-bottom: 8px;
}

.diag-result-card.diag-pending {
  opacity: 0.5;
}
</style>
