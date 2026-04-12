<template>
  <div class="site-config-tab">
    <div class="card">
      <div class="card-header">
        <div class="card-title">站点配置</div>
      </div>

      <!-- Config Form -->
      <div class="form-grid">
        <!-- Site Name (readonly) -->
        <div class="form-group">
          <label class="form-label">站点名称</label>
          <input class="form-input" :value="profile.name" readonly style="opacity:0.7;cursor:default">
        </div>

        <!-- Base URL -->
        <div class="form-group">
          <label class="form-label">目标地址</label>
          <input class="form-input" v-model="form.base_url" placeholder="https://api.anthropic.com">
        </div>

        <!-- API Key -->
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

        <!-- Provider -->
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

        <!-- Models (tag-style combobox) -->
        <div class="form-group form-group--full">
          <label class="form-label">绑定模型</label>
          <div class="combobox" ref="comboboxRef">
            <div class="model-tags-input" @click="modelDropdownOpen = true">
              <span v-for="(m, i) in form.models" :key="m" class="model-tag">
                {{ m }}
                <button type="button" class="model-tag-remove" @click.stop="removeModel(i)">&times;</button>
              </span>
              <input class="model-tag-search" v-model="modelSearch" :placeholder="form.models.length ? '' : '选择或输入模型 ID'" @focus="modelDropdownOpen = true" @keydown.enter.prevent="addModelFromSearch()" @keydown.backspace="onModelBackspace()" @keydown.escape="modelDropdownOpen = false" autocomplete="off" ref="modelSearchInputRef">
            </div>
            <button class="combobox-toggle" type="button" @click.stop="modelDropdownOpen = !modelDropdownOpen" @mousedown.prevent>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5l3 3 3-3"/></svg>
            </button>
            <div class="combobox-dropdown" v-show="modelDropdownOpen">
              <template v-for="m in filteredModels" :key="m.id || m">
                <div class="combobox-option" :class="{ active: form.models.includes(m.id || m) }" @mousedown.prevent="selectModel(m)">{{ m.id || m }}</div>
              </template>
              <div class="combobox-empty" v-show="!filteredModels.length && modelSearch">无匹配模型，按回车添加「{{ modelSearch }}」</div>
              <div class="combobox-empty" v-show="!filteredModels.length && !modelSearch">
                <span v-if="modelsApiLoading">正在获取模型列表...</span>
                <span v-else-if="form.provider">该厂商下暂无模型数据</span>
                <span v-else>请先选择模型厂商</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="site-config-actions">
        <div class="site-config-actions-left">
          <button class="btn btn-primary" @click="saveProfile()" :disabled="!canSave()">
            {{ formDirty ? '更新配置' : '保存配置' }}
          </button>
          <button class="btn btn-ghost" @click="dryRunTest()" :disabled="!canTest()" v-if="form.base_url && form.api_key && form.models.length">
            连通性测试
          </button>
        </div>
        <div class="site-config-actions-right">
          <template v-if="confirmDelete">
            <span class="confirm-delete-text">确认删除「<strong>{{ profile.name }}</strong>」？不影响已有测试结果。</span>
            <button class="btn btn-danger btn-sm" @click="doDelete()">删除</button>
            <button class="btn btn-ghost btn-sm" @click="confirmDelete = false">取消</button>
          </template>
          <button v-else class="btn btn-ghost btn-sm btn-danger-text" @click="confirmDelete = true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
            删除站点
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { api } from '../api/index.js';
import { toast } from '../composables/useToast.js';

const props = defineProps({
  profile: { type: Object, required: true },
});
const emit = defineEmits(['deleted']);

const router = useRouter();

// ---- Template refs ----
const comboboxRef = ref(null);
const providerComboboxRef = ref(null);
const modelSearchInputRef = ref(null);

// ---- Form state ----
const form = ref({
  base_url: '',
  api_key: '',
  models: [],
  provider: '',
});
const showApiKey = ref(false);
const confirmDelete = ref(false);
const formDirty = ref(false);
const savedConfig = ref(null);

// ---- Model combobox ----
const knownModels = ref([]);
const modelsApiLoading = ref(false);
const modelDropdownOpen = ref(false);
const modelSearch = ref('');

// ---- Provider combobox ----
const providerDropdownOpen = ref(false);
const providerSearch = ref('');
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

// ---- Connectivity test ----
const testing = ref(false);

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

// ---- Init form from profile ----
function initForm() {
  if (!props.profile) return;
  form.value.base_url = props.profile.base_url || '';
  form.value.api_key = props.profile.api_key_display || props.profile.api_key || '';
  form.value.models = props.profile.models || (props.profile.model ? [props.profile.model] : []);
  form.value.provider = props.profile.provider || '';
  snapshotConfig();
}

function snapshotConfig() {
  savedConfig.value = {
    base_url: form.value.base_url,
    api_key: form.value.api_key,
    models: [...form.value.models],
    provider: form.value.provider,
  };
  formDirty.value = false;
}

function checkDirty() {
  if (!savedConfig.value) { formDirty.value = false; return; }
  const s = savedConfig.value;
  formDirty.value = (
    form.value.base_url !== (s.base_url || '') ||
    form.value.api_key !== (s.api_key || '') ||
    JSON.stringify(form.value.models) !== JSON.stringify(s.models || []) ||
    form.value.provider !== (s.provider || '')
  );
}

// ---- Watchers ----
watch(() => form.value.base_url, () => checkDirty());
watch(() => form.value.api_key, () => checkDirty());
watch(() => form.value.models, () => checkDirty(), { deep: true });
watch(() => form.value.provider, () => checkDirty());

watch(() => props.profile, () => {
  initForm();
  if (props.profile?.provider) loadKnownModels(props.profile.provider);
}, { immediate: true });

// ---- Model combobox ----
function addModel(name) {
  const n = name.trim();
  if (!n || form.value.models.includes(n)) return;
  form.value.models.push(n);
}

function removeModel(index) {
  form.value.models.splice(index, 1);
}

function selectModel(m) {
  const id = typeof m === 'string' ? m : (m.id || '');
  addModel(id);
  modelSearch.value = '';
  modelDropdownOpen.value = false;
}

function addModelFromSearch() {
  if (modelSearch.value) {
    addModel(modelSearch.value);
    modelSearch.value = '';
  }
}

function onModelBackspace() {
  if (!modelSearch.value && form.value.models.length) {
    form.value.models.pop();
  }
}

// Click outside for model combobox
let modelListenerActive = false;
function handleModelOutside(e) {
  if (comboboxRef.value && !comboboxRef.value.contains(e.target)) {
    if (modelSearch.value) {
      addModel(modelSearch.value);
      modelSearch.value = '';
    }
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

// ---- Provider combobox ----
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
  checkDirty();
  loadKnownModels(val);
}

// Click outside for provider combobox
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

// ---- Load known models ----
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

// ---- Validation ----
function canSave() {
  return Boolean(
    form.value.base_url.trim() &&
    form.value.models.length > 0
  );
}

function canTest() {
  return Boolean(
    form.value.base_url.trim() &&
    form.value.api_key.trim() &&
    form.value.models.length > 0 &&
    !testing.value
  );
}

// ---- Actions ----
async function saveProfile() {
  if (!form.value.base_url.trim()) {
    toast('请先填写目标地址', 'info');
    return;
  }
  if (!form.value.models.length) {
    toast('请至少选择一个模型', 'info');
    return;
  }

  try {
    await api('/api/profiles/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: props.profile.name,
        base_url: form.value.base_url,
        api_key: form.value.api_key,
        models: form.value.models,
        provider: form.value.provider,
        api_version: '2023-06-01',
      }),
    });
    toast(formDirty.value ? '配置已更新' : '配置已保存', 'success');
    snapshotConfig();
  } catch (e) {
    toast('保存失败: ' + e.message, 'error');
  }
}

async function dryRunTest() {
  if (!canTest()) return;
  testing.value = true;
  try {
    const res = await api('/api/bench/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        base_url: form.value.base_url,
        api_key: form.value.api_key,
        model: form.value.models[0] || '',
        provider: form.value.provider,
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
    if (res.error) { toast(res.error, 'error'); return; }
    toast('连通性测试已启动', 'info');
  } catch (e) {
    toast('测试失败: ' + e.message, 'error');
  } finally {
    testing.value = false;
  }
}

async function doDelete() {
  try {
    await api('/api/profiles/' + encodeURIComponent(props.profile.name), { method: 'DELETE' });
    toast('站点已删除', 'info');
    emit('deleted');
  } catch (e) {
    toast('删除失败: ' + e.message, 'error');
  }
}

// ---- Cleanup ----
onUnmounted(() => {
  removeModelListener();
  if (providerListenerActive) {
    document.removeEventListener('mousedown', handleProviderOutside);
  }
});

// ---- Init ----
onMounted(() => {
  if (props.profile?.provider) {
    loadKnownModels(props.profile.provider);
  }
});
</script>

<style scoped>
.site-config-tab .card {
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 24px;
}

.site-config-tab .card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.site-config-tab .card-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.site-config-tab .form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.site-config-tab .form-group--full {
  grid-column: 1 / -1;
}

/* ---- Actions ---- */
.site-config-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid var(--border-subtle);
  gap: 16px;
  flex-wrap: wrap;
}

.site-config-actions-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.site-config-actions-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.confirm-delete-text {
  font-size: 13px;
  color: var(--danger);
}

.btn-danger-text {
  color: var(--danger);
}

.btn-danger-text:hover {
  background: var(--danger-light);
  color: var(--danger);
}

@media (max-width: 768px) {
  .site-config-tab .form-grid {
    grid-template-columns: 1fr;
  }

  .site-config-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .site-config-actions-left,
  .site-config-actions-right {
    justify-content: flex-end;
  }
}
</style>
