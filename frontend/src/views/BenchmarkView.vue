<template>
  <section class="tab-content" :class="{ active: $route.path === '/benchmark' }">
    <div class="card">
      <div class="card-header">
        <div class="card-title">测试配置</div>
      </div>
      <!-- Profile 快捷切换 -->
      <div class="profile-section">
        <div class="profile-bar">
          <div class="profile-chips">
            <!-- + 新建按钮 -->
            <button class="profile-chip profile-chip-add" v-show="!multiMode && profileMode !== 'new'" @click="newProfile()" title="新建配置">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              <span>新建</span>
            </button>
            <!-- 新建中的虚线占位 -->
            <div class="profile-chip profile-chip-new" v-show="!multiMode && profileMode === 'new'">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              <input class="profile-chip-name-edit" v-model="profileDraftName" placeholder="配置名称" @keydown.enter.prevent="saveProfile()" @blur="profileDraftName = profileDraftName.trim()" ref="newProfileNameInputRef" @click.stop>
              <button v-if="canSaveProfile()" class="profile-chip-action profile-chip-action-save" @click.stop="saveProfile()" title="保存">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              </button>
            </div>
            <!-- 已有 profile 卡片 -->
            <template v-for="p in profiles" :key="p.name">
              <div class="profile-chip" :class="{ active: multiMode ? multiSelectedProfiles.includes(p.name) : (profileMode === 'selected' && currentProfileName === p.name), 'multi-check': multiMode }" @click.self="multiMode ? toggleMultiProfile(p.name) : switchProfile(p.name)">
                <span class="profile-chip-check" v-show="multiMode && multiSelectedProfiles.includes(p.name)">&#10003;</span>
                <template v-if="!multiMode && profileMode === 'selected' && currentProfileName === p.name && editingProfileName">
                  <input class="profile-chip-name-edit" v-model="profileDraftName" @keydown.enter.prevent="finishRenameProfile()" @keydown.escape.prevent="cancelRenameProfile()" @blur="finishRenameProfile()" ref="renameInputRef" @click.stop>
                </template>
                <template v-if="!( !multiMode && profileMode === 'selected' && currentProfileName === p.name && editingProfileName )">
                  <span class="profile-chip-name" @click.stop="multiMode ? toggleMultiProfile(p.name) : startRenameProfile()" :title="multiMode ? '' : '点击重命名'">{{ p.name }}</span>
                </template>
                <span class="profile-chip-meta" @click.stop="multiMode ? toggleMultiProfile(p.name) : switchProfile(p.name)">{{ profileHost(p.base_url) }}</span>
                <!-- 悬浮操作 -->
                <div v-if="!multiMode && profileMode === 'selected' && currentProfileName === p.name" class="profile-chip-actions" @click.stop>
                  <button v-if="profileDirty" class="profile-chip-action profile-chip-action-save" @click="saveProfile()" title="保存更改">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                  </button>
                  <button class="profile-chip-action profile-chip-action-del" @click="requestDeleteProfile(p.name)" title="删除">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  </button>
                </div>
              </div>
            </template>
          </div>
          <button class="btn btn-ghost btn-sm" @click="toggleMultiMode()" v-show="!running && profiles.length >= 2" style="flex-shrink:0">{{ multiMode ? '切回单配置' : '多配置对比' }}</button>
        </div>
        <div class="profile-multi-hint" v-show="multiMode">
          <span>已选 <strong>{{ multiSelectedProfiles.length }}</strong> 个配置，至少需要 2 个</span>
        </div>

        <!-- 删除确认 -->
        <div class="profile-delete-row" v-show="!multiMode && profileDeleteCandidate">
          <span class="profile-delete-text">确认删除「<strong>{{ profileDeleteCandidate }}</strong>」？不影响已有测试结果。</span>
          <button class="btn btn-danger btn-sm" @click="confirmDeleteProfile(profileDeleteCandidate)">删除</button>
          <button class="btn btn-ghost btn-sm" @click="cancelDeleteProfile()">取消</button>
        </div>
      </div>
      <div class="form-grid">
        <div class="form-group">
          <label class="form-label">目标地址</label>
          <input class="form-input" v-model="form.base_url" placeholder="https://api.anthropic.com" ref="baseUrlInputRef">
        </div>
        <div class="form-group">
          <label class="form-label">模型厂商</label>
          <div class="combobox" ref="providerComboboxRef">
            <input class="form-input" :value="providerDropdownOpen ? providerSearch : providerLabel" :placeholder="'选择模型厂商'" @focus="onProviderFocus" @input="onProviderInput($event)" @keydown.escape="providerDropdownOpen = false" readonly autocomplete="off">
            <button class="combobox-toggle" type="button" @click.stop="providerDropdownOpen = !providerDropdownOpen" @mousedown.prevent>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5l3 3 3-3"/></svg>
            </button>
            <div class="combobox-dropdown" v-show="providerDropdownOpen">
              <div class="combobox-option" :class="{ active: form.provider === '' }" @mousedown.prevent="selectProvider('')">全部</div>
              <div v-for="p in filteredProviders" :key="p.value" class="combobox-option" :class="{ active: form.provider === p.value }" @mousedown.prevent="selectProvider(p.value)">{{ p.label }}</div>
            </div>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">API Key</label>
          <div style="position:relative">
            <input class="form-input" v-model="form.api_key" :type="showApiKey ? 'text' : 'password'" placeholder="sk-..." autocomplete="off" data-1p-ignore style="width:100%;padding-right:40px">
            <button type="button" @click="showApiKey = !showApiKey" style="position:absolute;right:10px;top:50%;transform:translateY(-50%);background:none;border:none;cursor:pointer;color:var(--text-tertiary);padding:4px;line-height:1" title="Show/Hide">
              <svg v-show="!showApiKey" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              <svg v-show="showApiKey" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
            </button>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">模型
            <span v-if="!multiModelMode" style="float:right;font-size:11px;cursor:pointer;color:var(--accent)" @click="toggleMultiModel">多模型测试</span>
            <span v-else style="float:right;font-size:11px;cursor:pointer;color:var(--text-tertiary)" @click="toggleMultiModel">单模型</span>
          </label>
          <!-- 单模型模式 -->
          <div v-show="!multiModelMode" class="combobox" ref="comboboxRef">
            <input class="form-input" :value="modelDropdownOpen ? modelSearch : form.model" :placeholder="form.model || '选择或直接输入模型 ID'" @focus="modelDropdownOpen = true" @input="onModelInput($event)" @keydown.escape="modelDropdownOpen = false" autocomplete="off">
            <button class="combobox-toggle" type="button" @click.stop="modelDropdownOpen = !modelDropdownOpen" @mousedown.prevent>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5l3 3 3-3"/></svg>
            </button>
            <div class="combobox-dropdown" v-show="modelDropdownOpen">
              <template v-for="m in filteredModels" :key="m.id || m">
                <div class="combobox-option" :class="{ active: form.model === (m.id || m) }" @mousedown.prevent="selectModel(m)">{{ m.id || m }}</div>
              </template>
              <div class="combobox-empty" v-show="!filteredModels.length && modelSearch">无匹配模型，将使用输入值</div>
              <div class="combobox-empty" v-show="!filteredModels.length && !modelSearch">
                <span v-if="modelsApiLoading">正在获取模型列表…</span>
                <span v-else-if="form.provider">该厂商下暂无模型数据</span>
                <span v-else>请先选择模型厂商</span>
              </div>
            </div>
          </div>
          <!-- 多模型模式 -->
          <div v-show="multiModelMode">
            <div class="combobox" ref="comboboxRef">
              <input class="form-input" :value="modelSearch" placeholder="输入模型 ID 回车添加，或从下拉选择" @focus="modelDropdownOpen = true" @input="onModelInput($event)" @keydown.enter.prevent="addMultiModel(modelSearch || '')" @keydown.escape="modelDropdownOpen = false" autocomplete="off">
              <button class="combobox-toggle" type="button" @click.stop="modelDropdownOpen = !modelDropdownOpen" @mousedown.prevent>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5l3 3 3-3"/></svg>
              </button>
              <div class="combobox-dropdown" v-show="modelDropdownOpen">
                <template v-for="m in filteredModels" :key="m.id || m">
                  <div class="combobox-option" @mousedown.prevent="addMultiModel(m.id || m)">{{ m.id || m }}</div>
                </template>
                <div class="combobox-empty" v-show="!filteredModels.length && modelSearch">回车添加「{{ modelSearch }}」</div>
                <div class="combobox-empty" v-show="!filteredModels.length && !modelSearch">
                  <span v-if="modelsApiLoading">正在获取模型列表…</span>
                  <span v-else-if="form.provider">该厂商下暂无模型数据</span>
                  <span v-else>请先选择模型厂商</span>
                </div>
              </div>
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px" v-if="multiModels.length">
              <span v-for="(m, i) in multiModels" :key="m" class="profile-chip active" style="font-size:12px;padding:3px 10px;cursor:default">
                {{ m }}
                <button @click="removeMultiModel(i)" style="background:none;border:none;cursor:pointer;color:var(--danger);margin-left:4px;font-size:14px;line-height:1">&times;</button>
              </span>
            </div>
            <div style="font-size:11px;color:var(--text-tertiary);margin-top:4px" v-if="multiModels.length">已添加 {{ multiModels.length }} 个模型</div>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">最大输出 Tokens</label>
          <input class="form-input" type="number" v-model.number="form.max_tokens">
        </div>
        <div class="form-group full">
          <label class="form-label">并发级别 <span class="info-tip" data-tip="选择并发连接数">?</span></label>
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
        <div class="form-group">
          <label class="form-label">每级请求数 <span class="info-tip" data-tip="每个并发级别发送的总请求数，默认等于并发数">?</span></label>
          <input class="form-input" type="number" v-model.number="requestsPerLevel" placeholder="默认等于并发数" min="1">
        </div>
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
        <div class="form-group" v-show="form.mode === 'sustained'">
          <label class="form-label">持续时长 (秒) <span class="info-tip" data-tip="持续模式下每个并发级别的运行时长（秒）">?</span></label>
          <input class="form-input" type="number" v-model.number="form.duration">
        </div>
        <div class="form-group">
          <label class="form-label">超时时间 (秒)</label>
          <input class="form-input" type="number" v-model.number="form.timeout">
        </div>
        <div class="form-group full">
          <label class="form-label">系统提示词</label>
          <input class="form-input" v-model="form.system_prompt">
        </div>
        <div class="form-group full">
          <label class="form-label">用户提示词</label>
          <textarea class="form-textarea" v-model="form.user_prompt" rows="2"></textarea>
        </div>
      </div>
      <div class="btn-group" style="margin-top:20px">
        <button class="btn btn-primary" v-show="!running && !multiModelMode && !multiMode" @click="startBench()">开始测试</button>
        <button class="btn btn-primary" v-show="!running && multiModelMode" @click="startMultiModelBench()" :disabled="multiModels.length < 2">开始多模型测试</button>
        <button class="btn btn-primary" v-show="!running && !multiModelMode && multiMode" @click="startMultiBench()" :disabled="multiSelectedProfiles.length < 2">开始多配置对比测试</button>
        <button class="btn btn-danger" v-show="running" @click="stopBench()">停止</button>
        <button class="btn btn-ghost" v-show="!running && !multiModelMode && !multiMode" @click="dryRun()">连通性验证 <span style="font-weight:400;color:var(--text-tertiary)">(单请求)</span></button>
      </div>

    <!-- Progress Panel -->
    <div class="progress-panel" :class="{ active: running }" v-show="running">
      <div class="card">
        <div class="card-header">
          <div class="card-title">运行中...</div>
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

    <!-- Multi-Server Progress Panel -->
    <div class="progress-panel" :class="{ active: running && multiMode }" v-show="running && multiMode">
      <div class="card">
        <div class="card-header">
          <div class="card-title">多配置并行测试</div>
        </div>
        <template v-for="tid in Object.keys(multiTasks)" :key="tid">
          <div class="multi-task-progress" style="margin-bottom:16px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
              <span style="font-weight:600;font-size:13px">{{ multiTasks[tid]?.model_name || multiTasks[tid]?.profile_name || tid }}</span>
              <span class="status-badge" :class="multiTasks[tid]?.status" style="font-size:11px">{{ multiTasks[tid]?.status === 'running' ? '运行中' : multiTasks[tid]?.status === 'completed' ? '已完成' : multiTasks[tid]?.status }}</span>
            </div>
            <div class="progress-bar-wrap">
              <div class="progress-bar" :style="'width:' + (multiTasks[tid]?.progress.total > 0 ? (multiTasks[tid]?.progress.done / multiTasks[tid]?.progress.total * 100).toFixed(1) : 0) + '%'"></div>
            </div>
            <div class="progress-stats" style="padding:8px 0">
              <div class="progress-stat">
                <div class="progress-stat-value" style="font-size:16px">{{ multiTasks[tid]?.progress.done || 0 }}</div>
                <div class="progress-stat-label">已完成</div>
              </div>
              <div class="progress-stat">
                <div class="progress-stat-value" style="color:var(--success);font-size:16px">{{ multiTasks[tid]?.progress.success || 0 }}</div>
                <div class="progress-stat-label">成功</div>
              </div>
              <div class="progress-stat">
                <div class="progress-stat-value" style="color:var(--danger);font-size:16px">{{ multiTasks[tid]?.progress.failed || 0 }}</div>
                <div class="progress-stat-label">失败</div>
              </div>
              <div class="progress-stat">
                <div class="progress-stat-value" style="font-size:16px">{{ (multiTasks[tid]?.progress.elapsed || 0) + 's' }}</div>
                <div class="progress-stat-label">耗时</div>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- Live Results -->
    <div class="live-results" ref="liveResultsRef">
      <template v-for="(lr, i) in liveResults" :key="i">
        <div class="card" style="margin-bottom:16px">
          <div class="live-result-content"></div>
        </div>
      </template>
    </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { api } from '../api/index.js';
import { useAppStore } from '../stores/app.js';
import { toast } from '../composables/useToast.js';
import { useBenchSSE } from '../composables/useBenchSSE.js';
// renderResultDetail — 需要后续创建 src/utils/resultDetail.js
import { renderResultDetail } from '../utils/resultDetail.js';
import { escHtml } from '../utils/formatters.js';

const store = useAppStore();

// ---- Template refs ----
const progressLogRef = ref(null);
const liveResultsRef = ref(null);
const renameInputRef = ref(null);
const comboboxRef = ref(null);
const baseUrlInputRef = ref(null);
const newProfileNameInputRef = ref(null);

// ---- Form state ----
const form = ref({
  base_url: '',
  api_key: '',
  model: '',
  provider: '',
  max_tokens: 512,
  mode: 'burst',
  duration: 120,
  timeout: 120,
  system_prompt: 'You are a helpful assistant.',
  user_prompt: 'Write a short essay about the future of artificial intelligence in exactly 200 words.',
});
const showApiKey = ref(false);

// ---- Concurrency ----
const concurrencyPresets = ref([1, 10, 50, 100, 200, 500, 1000]);
const selectedConcurrency = ref(100);
const customConcurrency = ref('');
const requestsPerLevel = ref('');

// ---- Running state ----
const running = ref(false);
const progress = ref({ done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' });
const logs = ref([]);
const liveResults = ref([]);
const pollTimer = ref(null); // 仅用于多服务器轮询
const taskId = ref(null);
const lastCompletedFilename = ref(null);
const benchSSE = useBenchSSE();
const elapsedTimer = ref(null);
let benchStartTime = 0;

// ---- Multi-server ----
const multiMode = ref(false);
const multiSelectedProfiles = ref([]);
const groupId = ref(null);
const multiTasks = ref({});
const multiLogs = ref({});
const multiResults = ref({});
const multiResultFiles = ref([]);

// ---- Profile management ----
const profiles = ref([]);
const currentProfileName = ref('');
const profileDraftName = ref('');
const profileDeleteCandidate = ref('');
const profileMode = ref('selected');
const knownModels = ref([]);
const modelsApiLoading = ref(false);
const modelDropdownOpen = ref(false);
const modelSearch = ref('');
const providerDropdownOpen = ref(false);
const providerSearch = ref('');
const providerComboboxRef = ref(null);
const providerOptions = [
  { value: 'anthropic', label: 'Anthropic (Claude)' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'qwen', label: 'Qwen (通义千问)' },
  { value: 'google', label: 'Google (Gemini)' },
  { value: 'mistral', label: 'Mistral' },
  { value: 'cohere', label: 'Cohere' },
  { value: 'bytedance', label: '字节 (豆包)' },
  { value: 'zhipu', label: '智谱 (GLM)' },
  { value: 'moonshot', label: 'Moonshot (Kimi)' },
  { value: 'other', label: '其他' },
];
const editingProfileName = ref(false);
const profileDirty = ref(false);
const savedProfileConfig = ref(null);

// ---- Multi-model mode ----
const multiModelMode = ref(false);
const multiModels = ref([]);

// ---- Computed ----
const filteredModels = computed(() => {
  const q = (modelSearch.value || '').toLowerCase();
  const models = knownModels.value;
  if (!q) return models;
  return models.filter(m => {
    const id = typeof m === 'string' ? m : (m.id || '');
    return id.toLowerCase().includes(q);
  });
});

const providerLabel = computed(() => {
  const p = providerOptions.find(o => o.value === form.value.provider);
  return p ? p.label : '';
});

const filteredProviders = computed(() => {
  const q = (providerSearch.value || '').toLowerCase();
  if (!q) return providerOptions;
  return providerOptions.filter(p => p.label.toLowerCase().includes(q) || p.value.toLowerCase().includes(q));
});

const currentProfile = computed(() => {
  return profiles.value.find(p => p.name === currentProfileName.value) || null;
});

const orderedProfiles = computed(() => {
  return [...profiles.value].sort((a, b) => {
    if (a.name === currentProfileName.value) return -1;
    if (b.name === currentProfileName.value) return 1;
    // 按创建时间降序，最新的在最左边
    const ta = a.created_at || '';
    const tb = b.created_at || '';
    if (ta && tb) return tb.localeCompare(ta);
    if (ta) return -1;
    if (tb) return 1;
    return 0;
  });
});

const profileDraftExists = computed(() => {
  const trimmed = profileDraftName.value.trim();
  if (!trimmed) return false;
  return profiles.value.some(p => p.name === trimmed);
});

// ---- Watchers ----
watch(() => form.value.base_url, () => checkProfileDirty());
watch(() => form.value.api_key, () => checkProfileDirty());
watch(() => form.value.model, () => checkProfileDirty());
watch(() => form.value.provider, () => checkProfileDirty());

// 自动从 API 获取可用模型列表
watch([() => form.value.base_url, () => form.value.api_key], ([url, key]) => {
  if (url?.trim() && key?.trim()) fetchModelsFromApi();
});

import { useRoute, useRouter } from 'vue-router';
const route = useRoute();
const router = useRouter();

// Apply rerun config when switching to benchmark tab
watch(() => route.path, (val) => {
  if (val === '/benchmark' && store.rerunConfig) {
    loadProfiles().then(() => applyRerunConfig());
  }
});

// Watch rerunConfig changes (set from other views)
watch(() => store.rerunConfig, (val) => {
  if (val && route.path === '/benchmark') {
    loadProfiles().then(() => applyRerunConfig());
  }
});

// Auto-scroll progress log
watch(logs, () => {
  nextTick(() => {
    const el = progressLogRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}, { deep: true });

// Render live results innerHTML (mirrors Alpine x-init approach)
watch(liveResults, () => {
  nextTick(() => {
    const container = liveResultsRef.value;
    if (!container) return;
    const cards = container.querySelectorAll('.live-result-content');
    liveResults.value.forEach((lr, i) => {
      if (cards[i]) {
        cards[i].innerHTML = '<div class=\'card-title\' style=\'margin-bottom:12px\'>结果 — 并发 ' + escHtml(lr.concurrency) + '</div>' + renderResultDetail(lr.result);
      }
    });
  });
}, { deep: true });

// ---- Lifecycle ----
onMounted(() => {
  if (!localStorage.getItem('token')) return;
  const hasRerun = !!store.rerunConfig;
  loadProfiles().then(() => {
    profileMode.value = currentProfileName.value ? 'selected' : 'new';
    snapshotProfileConfig();
    if (hasRerun) applyRerunConfig();
  });
  loadKnownModels(form.value.provider);
  checkRunningStatus();
});

onUnmounted(() => {
  stopSSE();
  stopMultiPolling();
  removeComboboxListener();
});

// ---- Combobox click-outside ----
let comboboxListenerActive = false;
function handleComboboxOutside(e) {
  if (comboboxRef.value && !comboboxRef.value.contains(e.target)) {
    if (modelSearch.value) {
      form.value.model = modelSearch.value;
    }
    modelDropdownOpen.value = false;
  }
}
function addComboboxListener() {
  if (comboboxListenerActive) return;
  comboboxListenerActive = true;
  // 用 setTimeout 跳过当前事件循环，避免打开 dropdown 的同一个 click 立即触发 outside
  setTimeout(() => document.addEventListener('mousedown', handleComboboxOutside), 0);
}
function removeComboboxListener() {
  if (!comboboxListenerActive) return;
  comboboxListenerActive = false;
  document.removeEventListener('mousedown', handleComboboxOutside);
}

watch(modelDropdownOpen, (open) => {
  if (open) addComboboxListener(); else removeComboboxListener();
});

// Provider combobox click-outside
let providerListenerActive = false;
function handleProviderOutside(e) {
  if (providerComboboxRef.value && !providerComboboxRef.value.contains(e.target)) {
    providerDropdownOpen.value = false;
  }
}
watch(providerDropdownOpen, (open) => {
  if (open) {
    if (!providerListenerActive) {
      providerListenerActive = true;
      setTimeout(() => document.addEventListener('mousedown', handleProviderOutside), 0);
    }
  } else {
    if (providerListenerActive) {
      providerListenerActive = false;
      document.removeEventListener('mousedown', handleProviderOutside);
    }
  }
});

function toggleCombobox() {
  if (modelDropdownOpen.value) {
    modelDropdownOpen.value = false;
  } else {
    modelSearch.value = '';
    modelDropdownOpen.value = true;
  }
}

function onModelInput(e) {
  modelSearch.value = e.target.value;
  modelDropdownOpen.value = true;
}

// ---- Rerun config ----
async function applyRerunConfig() {
  const rc = store.rerunConfig;
  if (!rc) return;
  store.rerunConfig = null;

  let matched = null;
  if (rc.profile_name) {
    matched = profiles.value.find(p => p.name === rc.profile_name);
  }
  if (!matched && rc.base_url) {
    matched = profiles.value.find(p => p.base_url === rc.base_url);
  }

  if (matched) {
    await switchProfile(matched.name);
  } else {
    newProfile();
    form.value.base_url = rc.base_url;
  }

  form.value.model = rc.model;
  form.value.provider = rc.provider || form.value.provider;
  form.value.max_tokens = rc.max_tokens;
  form.value.mode = rc.mode;
  form.value.duration = rc.duration;
  form.value.timeout = rc.timeout;
  form.value.system_prompt = rc.system_prompt;
  form.value.user_prompt = rc.user_prompt;
  selectedConcurrency.value = rc.concurrency;
}

// ---- Profile methods ----
async function loadProfiles() {
  try {
    const data = await api('/api/profiles');
    profiles.value = Array.isArray(data.profiles) ? data.profiles : [];
    const active = data.active_profile || '';
    if (active && profiles.value.some(p => p.name === active)) {
      currentProfileName.value = active;
      profileDraftName.value = active;
    }
  } catch {
    profiles.value = [];
  }
}

async function loadKnownModels(provider) {
  modelsApiLoading.value = true;
  try {
    const params = new URLSearchParams();
    if (provider) params.set('provider', provider);
    params.set('enabled_only', 'true');
    const data = await api(`/api/pricing/models?${params}`);
    knownModels.value = data.models || [];
  } catch {
    knownModels.value = [];
  } finally {
    modelsApiLoading.value = false;
  }
}

// Provider combobox handlers
function onProviderFocus() {
  providerSearch.value = '';
  providerDropdownOpen.value = true;
}
function onProviderInput(e) {
  providerSearch.value = e.target.value;
  providerDropdownOpen.value = true;
}
function selectProvider(val) {
  form.value.provider = val;
  providerDropdownOpen.value = false;
  providerSearch.value = '';
  checkProfileDirty();
  loadKnownModels(val);
}

function selectModel(m) {
  const id = typeof m === 'string' ? m : (m.id || '');
  form.value.model = id;
  modelDropdownOpen.value = false;
}

let modelsApiTimer = null;
function fetchModelsFromApi() {
  clearTimeout(modelsApiTimer);
  modelsApiTimer = setTimeout(async () => {
    const url = form.value.base_url?.trim();
    const key = form.value.api_key?.trim();
    if (!url || !key) return;
    const token = localStorage.getItem('token');
    if (!token) return;
    modelsApiLoading.value = true;
    try {
      const apiBase = window.__API_BASE__ || (import.meta.env.DEV ? 'http://localhost:8080' : '');
      const res = await fetch(apiBase + '/api/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
        body: JSON.stringify({ base_url: url, api_key: key }),
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data.models?.length) {
        const apiModels = data.models.map(m => m.id || m.name).filter(Boolean);
        const merged = [...new Set([...knownModels.value, ...apiModels])].sort();
        knownModels.value = merged;
      }
    } catch {
      // API 不可用时静默忽略
    } finally {
      modelsApiLoading.value = false;
    }
  }, 800);
}

function profileReadyFieldCount() {
  return [
    form.value.base_url,
    form.value.api_key,
    form.value.model,
  ].filter(v => String(v || '').trim()).length;
}

function canSaveProfile() {
  return Boolean(
    profileDraftName.value.trim() &&
    form.value.base_url.trim() &&
    form.value.model.trim()
  );
}

function checkProfileDirty() {
  if (!currentProfileName.value || !savedProfileConfig.value) {
    profileDirty.value = false;
    return;
  }
  const s = savedProfileConfig.value;
  profileDirty.value = (
    form.value.base_url !== (s.base_url || '') ||
    form.value.api_key !== (s.api_key || '') ||
    form.value.model !== (s.model || '') ||
    form.value.provider !== (s.provider || '')
  );
}

function snapshotProfileConfig() {
  savedProfileConfig.value = {
    base_url: form.value.base_url,
    api_key: form.value.api_key,
    model: form.value.model,
    provider: form.value.provider,
  };
  profileDirty.value = false;
}

function startRenameProfile() {
  editingProfileName.value = true;
  nextTick(() => {
    const el = renameInputRef.value;
    if (el) { el.focus(); el.select(); }
  });
}

function cancelRenameProfile() {
  profileDraftName.value = currentProfileName.value;
  editingProfileName.value = false;
}

async function finishRenameProfile() {
  if (!editingProfileName.value) return;
  editingProfileName.value = false;
  const newName = profileDraftName.value.trim();
  if (!newName || newName === currentProfileName.value) {
    profileDraftName.value = currentProfileName.value;
    return;
  }
  try {
    await api('/api/profiles/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: newName,
        base_url: form.value.base_url,
        api_key: form.value.api_key,
        model: form.value.model,
        provider: form.value.provider,
        api_version: '2023-06-01',
      }),
    });
    const oldName = currentProfileName.value;
    await api('/api/profiles/' + encodeURIComponent(oldName), { method: 'DELETE' });
    currentProfileName.value = newName;
    toast('已重命名为「' + newName + '」', 'success');
    await loadProfiles();
  } catch (e) {
    toast('重命名失败: ' + e.message, 'error');
    profileDraftName.value = currentProfileName.value;
  }
}

async function saveAsNewProfile() {
  const name = prompt('另存为新配置，输入名称:');
  if (!name || !name.trim()) return;
  const trimmed = name.trim();
  try {
    await api('/api/profiles/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: trimmed,
        base_url: form.value.base_url,
        api_key: form.value.api_key,
        model: form.value.model,
        provider: form.value.provider,
        api_version: '2023-06-01',
      }),
    });
    currentProfileName.value = trimmed;
    profileDraftName.value = trimmed;
    toast('已另存为「' + trimmed + '」', 'success');
    snapshotProfileConfig();
    await loadProfiles();
  } catch (e) {
    toast('另存失败: ' + e.message, 'error');
  }
}

async function saveProfile() {
  const trimmed = profileDraftName.value.trim();
  if (!trimmed) {
    toast('请输入配置名称', 'info');
    return;
  }
  if (!form.value.base_url.trim()) {
    toast('请先填写目标地址', 'info');
    return;
  }
  if (!form.value.model.trim()) {
    toast('请先填写模型名称', 'info');
    return;
  }

  try {
    await api('/api/profiles/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: trimmed,
        base_url: form.value.base_url,
        api_key: form.value.api_key,
        model: form.value.model,
        provider: form.value.provider,
        api_version: '2023-06-01',
      }),
    });
    currentProfileName.value = trimmed;
    profileMode.value = 'selected';
    profileDeleteCandidate.value = '';
    toast(profileDraftExists.value ? '配置已更新' : '配置已保存', 'success');
    snapshotProfileConfig();
    await loadProfiles();
  } catch (e) {
    toast('保存失败: ' + e.message, 'error');
  }
}

function newProfile() {
  form.value.base_url = '';
  form.value.api_key = '';
  form.value.model = '';
  currentProfileName.value = '';
  profileDraftName.value = '';
  profileDeleteCandidate.value = '';
  profileMode.value = 'new';
  editingProfileName.value = false;
  savedProfileConfig.value = null;
  profileDirty.value = false;
  nextTick(() => { newProfileNameInputRef.value?.focus(); });
}

async function switchProfile(name) {
  try {
    const data = await api('/api/profiles/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (data.error) { toast(data.error, 'error'); return; }
    const c = data.config || {};
    form.value.base_url = c.base_url || '';
    form.value.api_key = c.api_key_display || '';
    form.value.model = c.model || '';
    form.value.provider = c.provider || '';
    currentProfileName.value = name;
    profileDraftName.value = name;
    profileDeleteCandidate.value = '';
    profileMode.value = 'selected';
    editingProfileName.value = false;
    snapshotProfileConfig();
  } catch (e) {
    toast('切换失败: ' + e.message, 'error');
  }
}

function requestDeleteProfile(name) {
  profileDeleteCandidate.value = profileDeleteCandidate.value === name ? '' : name;
}

function cancelDeleteProfile() {
  profileDeleteCandidate.value = '';
}

async function confirmDeleteProfile(name) {
  try {
    await api('/api/profiles/' + encodeURIComponent(name), { method: 'DELETE' });
    if (currentProfileName.value === name) {
      currentProfileName.value = '';
    }
    if (profileDraftName.value === name) {
      profileDraftName.value = '';
    }
    profileDeleteCandidate.value = '';
    toast('配置已删除', 'info');
    await loadProfiles();
  } catch (e) {
    toast('删除失败: ' + e.message, 'error');
  }
}

function profileHost(baseUrl) {
  if (!baseUrl) return '未设置目标地址';
  try {
    return new URL(baseUrl).host;
  } catch {
    return baseUrl;
  }
}

function maskProfileKey(apiKey) {
  if (!apiKey) return '未填写 Key';
  return apiKey.length > 4 ? `Key ••••${apiKey.slice(-4)}` : 'Key 已填写';
}

// ---- Benchmark methods ----
async function checkRunningStatus() {
  const data = await api('/api/bench/status');
  if (data.status === 'running') {
    taskId.value = data.task_id;
    running.value = true;
    store.status = 'running';
    router.push('/benchmark');
    startSSE();
  }
}

function getFormConfig() {
  const conc = selectedConcurrency.value || 100;
  const requests = parseInt(requestsPerLevel.value);
  const config = {
    base_url: form.value.base_url,
    api_key: form.value.api_key,
    model: form.value.model,
    provider: form.value.provider,
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

async function startBench() {
  const config = getFormConfig();
  try {
    const res = await api('/api/bench/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    if (res.error) { toast(res.error, 'error'); return; }
    taskId.value = res.task_id;
    setRunningState(true);
    startSSE();
    toast('测试已启动', 'success');
  } catch (e) { toast('启动失败: ' + e.message, 'error'); }
}

async function stopBench() {
  await api('/api/bench/stop', { method: 'POST' });
  toast('正在停止...', 'info');
}

async function dryRun() {
  const config = getFormConfig();
  config.concurrency_levels = [1];
  config.requests_per_level = 1;
  config.mode = 'burst';
  try {
    const res = await api('/api/bench/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    if (res.error) { toast(res.error, 'error'); return; }
    taskId.value = res.task_id;
    setRunningState(true);
    startSSE();
    toast('连通性验证已启动（1 个请求）', 'info');
  } catch (e) { toast('失败: ' + e.message, 'error'); }
}

function setRunningState(val) {
  running.value = val;
  if (val) {
    logs.value = [];
    liveResults.value = [];
    lastCompletedFilename.value = null;
    progress.value = { done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' };
  }
  store.status = val ? 'running' : 'idle';
}

function startSSE() {
  stopSSE();
  benchStartTime = Date.now();
  benchSSE.connect(handleEvent);
  elapsedTimer.value = setInterval(() => {
    if (running.value) {
      progress.value.elapsed = ((Date.now() - benchStartTime) / 1000).toFixed(1);
      if (progress.value.elapsed > 0 && progress.value.done > 0) {
        progress.value.rate = (progress.value.done / progress.value.elapsed).toFixed(1);
      }
    }
  }, 1000);
}

function stopSSE() {
  benchSSE.disconnect();
  if (elapsedTimer.value) {
    clearInterval(elapsedTimer.value);
    elapsedTimer.value = null;
  }
}

// 多服务器轮询保持不变
function startMultiPolling() {
  stopMultiPolling();
  pollTimer.value = setInterval(() => pollMultiStatus(), 1500);
  pollMultiStatus();
}

function stopMultiPolling() {
  if (pollTimer.value) {
    clearInterval(pollTimer.value);
    pollTimer.value = null;
  }
}

function handleEvent(type, d) {
  switch (type) {
    case 'bench:start':
      logLine(`<span class="info">[第 ${escHtml(d.current_level)}/${escHtml(d.total_levels)} 级] 启动 并发=${escHtml(d.concurrency)} 模式=${escHtml(d.mode)}</span>`);
      break;
    case 'bench:progress':
      progress.value.done = d.done;
      progress.value.success = d.success;
      progress.value.failed = d.failed;
      progress.value.total = d.total;
      progress.value.elapsed = d.elapsed;
      if (d.elapsed > 0) {
        progress.value.rate = (d.done / d.elapsed).toFixed(1);
      }
      break;
    case 'bench:level_complete':
      logLine(`<span class="ok">[完成] 并发=${escHtml(d.concurrency)} ✓</span>`);
      liveResults.value = [...liveResults.value, { concurrency: d.concurrency, result: d.result }];
      if (d.filename) lastCompletedFilename.value = d.filename;
      break;
    case 'bench:complete':
      stopSSE();
      setRunningState(false);
      toast('测试完成！', 'success');
      logLine('<span class="ok">测试完成！</span>');
      if (lastCompletedFilename.value) {
        store.pendingFilename = lastCompletedFilename.value;
      }
      store.switchTab('history');
      break;
    case 'bench:stopped':
      stopSSE();
      setRunningState(false);
      toast('测试已停止', 'info');
      logLine('<span class="fail">测试已被用户停止</span>');
      break;
    case 'bench:error':
      stopSSE();
      setRunningState(false);
      toast('错误: ' + d.error, 'error');
      logLine(`<span class="fail">错误: ${escHtml(d.error)}</span>`);
      break;
  }
}

function logLine(html) {
  const time = new Date().toLocaleTimeString();
  logs.value = [...logs.value, `[${time}] ${html}`];
}

function toggleConcurrency(val) {
  selectedConcurrency.value = val;
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

// ---- Multi-model methods ----
function toggleMultiModel() {
  multiModelMode.value = !multiModelMode.value;
  if (multiModelMode.value && form.value.model) {
    multiModels.value = [form.value.model];
  } else if (!multiModelMode.value) {
    multiModels.value = [];
  }
}

function addMultiModel(model) {
  const id = typeof model === 'string' ? model : (model?.id || '');
  if (!id.trim()) return;
  if (!multiModels.value.includes(id)) {
    multiModels.value = [...multiModels.value, id];
  }
  modelSearch.value = '';
  modelDropdownOpen.value = false;
}

function removeMultiModel(idx) {
  multiModels.value = multiModels.value.filter((_, i) => i !== idx);
}

function getMultiModelConfig() {
  const conc = selectedConcurrency.value || 100;
  const requests = parseInt(requestsPerLevel.value);
  const config = {
    provider: form.value.provider,
    models: multiModels.value,
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

async function startMultiModelBench() {
  if (multiModels.value.length < 2) {
    toast('请至少添加 2 个模型', 'info');
    return;
  }
  const config = getMultiModelConfig();
  try {
    const res = await api('/api/bench/start-multi-model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    if (res.error) { toast(res.error, 'error'); return; }
    groupId.value = res.group_id;
    multiTasks.value = {};
    multiLogs.value = {};
    multiResults.value = {};
    multiResultFiles.value = [];
    for (const tid of res.task_ids) {
      multiTasks.value[tid] = { profile_name: '', model_name: '', status: 'running', progress: { done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' }, event_seq: 0 };
      multiLogs.value[tid] = [];
      multiResults.value[tid] = [];
    }
    setRunningState(true);
    startMultiPolling();
    toast('多模型测试已启动', 'success');
  } catch (e) { toast('启动失败: ' + e.message, 'error'); }
}

// ---- Multi-server methods ----
function toggleMultiMode() {
  multiMode.value = !multiMode.value;
  if (multiMode.value) {
    multiSelectedProfiles.value = currentProfileName.value ? [currentProfileName.value] : [];
  } else {
    multiSelectedProfiles.value = [];
  }
}

function toggleMultiProfile(name) {
  const idx = multiSelectedProfiles.value.indexOf(name);
  if (idx >= 0) {
    multiSelectedProfiles.value = multiSelectedProfiles.value.filter(n => n !== name);
  } else {
    multiSelectedProfiles.value = [...multiSelectedProfiles.value, name];
  }
}

async function startMultiBench() {
  if (multiSelectedProfiles.value.length < 2) {
    toast('请至少选择 2 个配置', 'info');
    return;
  }
  const conc = selectedConcurrency.value || 100;
  const requests = parseInt(requestsPerLevel.value);
  const config = {
    concurrency_levels: [conc],
    mode: form.value.mode,
    max_tokens: parseInt(form.value.max_tokens) || 512,
    timeout: parseInt(form.value.timeout) || 120,
    duration: parseInt(form.value.duration) || 120,
    system_prompt: form.value.system_prompt,
    user_prompt: form.value.user_prompt,
  };
  if (!isNaN(requests) && requests > 0) config.requests_per_level = requests;

  try {
    const res = await api('/api/bench/start-multi', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tasks: multiSelectedProfiles.value.map(name => ({ profile_name: name, config })),
      }),
    });
    if (res.error) { toast(res.error, 'error'); return; }
    groupId.value = res.group_id;
    multiTasks.value = {};
    multiLogs.value = {};
    multiResults.value = {};
    multiResultFiles.value = [];
    for (const tid of res.task_ids) {
      multiTasks.value[tid] = { profile_name: '', status: 'running', progress: { done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' }, event_seq: 0 };
      multiLogs.value[tid] = [];
      multiResults.value[tid] = [];
    }
    setRunningState(true);
    startMultiPolling();
    toast('多服务器测试已启动', 'success');
  } catch (e) { toast('启动失败: ' + e.message, 'error'); }
}

async function pollMultiStatus() {
  if (!groupId.value) return;
  try {
    const data = await api(`/api/bench/status-multi?group_id=${groupId.value}`);
    let allDone = true;
    for (const t of (data.tasks || [])) {
      const mt = multiTasks.value[t.task_id];
      if (!mt) continue;
      mt.profile_name = t.profile_name;
      mt.model_name = t.model_name || '';
      mt.status = t.status;
      mt.progress = {
        done: t.done, total: t.total, success: t.success,
        failed: t.failed, elapsed: t.elapsed,
        rate: t.elapsed > 0 ? (t.done / t.elapsed).toFixed(1) : '-',
      };
      if (t.status === 'running') allDone = false;
      if (t.result_filenames) {
        for (const fn of t.result_filenames) {
          if (!multiResultFiles.value.includes(fn)) multiResultFiles.value.push(fn);
        }
      }
    }
    if (allDone && data.status === 'completed') {
      stopMultiPolling();
      setRunningState(false);
      toast('所有测试完成！', 'success');
      if (multiResultFiles.value.length >= 2) {
        store.pendingCompareFilenames = [...multiResultFiles.value];
        store.switchTab('history');
      }
    }
  } catch (e) {}
}
</script>
