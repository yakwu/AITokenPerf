<template>
  <section class="tab-content active">
    <div class="card">
      <div class="card-header">
        <div class="card-title">连接配置</div>
        <button class="btn btn-primary btn-sm" @click="newProfile()" v-if="profileMode !== 'new'">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          新建配置
        </button>
      </div>

      <!-- Profile 卡片列表 -->
      <div class="profile-section">
        <div class="profile-bar">
          <div class="profile-chips">
            <!-- 新建中的虚线占位 -->
            <div class="profile-chip profile-chip-new" v-show="profileMode === 'new'" style="min-width:200px">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              <input class="profile-chip-name-edit" v-model="profileDraftName" placeholder="配置名称" @keydown.enter.prevent="saveProfile()" @blur="profileDraftName = profileDraftName.trim()" ref="newProfileNameInputRef" @click.stop>
              <button v-if="canSaveProfile()" class="profile-chip-action profile-chip-action-save" @click.stop="saveProfile()" title="保存">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              </button>
            </div>
            <!-- 已有 profile 卡片 -->
            <template v-for="p in profiles" :key="p.name">
              <div class="profile-chip" :class="{ active: profileMode === 'selected' && currentProfileName === p.name }" @click.self="selectProfile(p.name)">
                <template v-if="profileMode === 'selected' && currentProfileName === p.name && editingProfileName">
                  <input class="profile-chip-name-edit" v-model="profileDraftName" @keydown.enter.prevent="finishRenameProfile()" @keydown.escape.prevent="cancelRenameProfile()" @blur="finishRenameProfile()" ref="renameInputRef" @click.stop>
                </template>
                <template v-if="!(profileMode === 'selected' && currentProfileName === p.name && editingProfileName)">
                  <span class="profile-chip-name" @click.stop="startRenameProfile()" :title="'点击重命名'">{{ p.name }}</span>
                </template>
                <span class="profile-chip-meta" @click.stop="selectProfile(p.name)">{{ profileHost(p.base_url) }}</span>
                <!-- 悬浮操作 -->
                <div v-if="profileMode === 'selected' && currentProfileName === p.name" class="profile-chip-actions" @click.stop>
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
        </div>

        <!-- 删除确认 -->
        <div class="profile-delete-row" v-show="profileDeleteCandidate">
          <span class="profile-delete-text">确认删除「<strong>{{ profileDeleteCandidate }}</strong>」？不影响已有测试结果。</span>
          <button class="btn btn-danger btn-sm" @click="confirmDeleteProfile(profileDeleteCandidate)">删除</button>
          <button class="btn btn-ghost btn-sm" @click="cancelDeleteProfile()">取消</button>
        </div>
      </div>

      <!-- 连接配置表单 -->
      <div class="form-grid" v-if="profileMode === 'selected' || profileMode === 'new'">
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
          <label class="form-label">模型</label>
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
                <span v-if="modelsApiLoading">正在获取模型列表…</span>
                <span v-else-if="form.provider">该厂商下暂无模型数据</span>
                <span v-else>请先选择模型厂商</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="btn-group" style="margin-top:20px" v-if="profileMode === 'selected' || profileMode === 'new'">
        <button class="btn btn-primary" @click="saveProfile()" :disabled="!canSaveProfile()">
          {{ profileMode === 'new' ? '保存配置' : '更新配置' }}
        </button>
        <button class="btn btn-ghost" @click="dryRunTest()" v-if="profileMode === 'selected' && form.base_url && form.api_key && form.models.length">
          连通性验证
        </button>
      </div>

      <div v-if="profiles.length === 0 && profileMode !== 'new'" style="text-align:center;color:var(--text-tertiary);padding:40px 20px">
        <div style="font-size:14px;margin-bottom:8px">还没有连接配置</div>
        <div style="font-size:12px">点击「新建配置」开始添加你的第一个 API 连接</div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue';
import { api } from '../api/index.js';
import { useAppStore } from '../stores/app.js';
import { toast } from '../composables/useToast.js';

const store = useAppStore();

// ---- Template refs ----
const renameInputRef = ref(null);
const comboboxRef = ref(null);
const baseUrlInputRef = ref(null);
const newProfileNameInputRef = ref(null);
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

// ---- Watchers ----
watch(() => form.value.base_url, () => checkProfileDirty());
watch(() => form.value.api_key, () => checkProfileDirty());
watch(() => form.value.models, () => checkProfileDirty(), { deep: true });
watch(() => form.value.provider, () => checkProfileDirty());

// ---- Combobox click-outside ----
let comboboxListenerActive = false;
function handleComboboxOutside(e) {
  if (comboboxRef.value && !comboboxRef.value.contains(e.target)) {
    if (modelSearch.value) {
      addModel(modelSearch.value);
      modelSearch.value = '';
    }
    modelDropdownOpen.value = false;
  }
}
function addComboboxListener() {
  if (comboboxListenerActive) return;
  comboboxListenerActive = true;
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

// ---- Profile methods ----
async function loadProfiles() {
  try {
    const data = await api('/api/profiles');
    profiles.value = Array.isArray(data.profiles) ? data.profiles : [];
    const active = data.active_profile || '';
    if (active && profiles.value.some(p => p.name === active)) {
      currentProfileName.value = active;
      profileDraftName.value = active;
      const p = profiles.value.find(p => p.name === active);
      if (p) {
        form.value.base_url = p.base_url || '';
        form.value.api_key = p.api_key_display || '';
        form.value.models = p.models || (p.model ? [p.model] : []);
        form.value.provider = p.provider || '';
        snapshotProfileConfig();
      }
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

function canSaveProfile() {
  return Boolean(
    profileDraftName.value.trim() &&
    form.value.base_url.trim() &&
    form.value.models.length > 0
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
    JSON.stringify(form.value.models) !== JSON.stringify(s.models || []) ||
    form.value.provider !== (s.provider || '')
  );
}

function snapshotProfileConfig() {
  savedProfileConfig.value = {
    base_url: form.value.base_url,
    api_key: form.value.api_key,
    models: [...form.value.models],
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
        models: form.value.models,
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
  if (!form.value.models.length) {
    toast('请至少选择一个模型', 'info');
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
        models: form.value.models,
        provider: form.value.provider,
        api_version: '2023-06-01',
      }),
    });
    currentProfileName.value = trimmed;
    profileMode.value = 'selected';
    profileDeleteCandidate.value = '';
    toast(profileDirty.value ? '配置已更新' : '配置已保存', 'success');
    snapshotProfileConfig();
    await loadProfiles();
  } catch (e) {
    toast('保存失败: ' + e.message, 'error');
  }
}

function newProfile() {
  form.value.base_url = '';
  form.value.api_key = '';
  form.value.models = [];
  form.value.provider = '';
  currentProfileName.value = '';
  profileDraftName.value = '';
  profileDeleteCandidate.value = '';
  profileMode.value = 'new';
  editingProfileName.value = false;
  savedProfileConfig.value = null;
  profileDirty.value = false;
  nextTick(() => { newProfileNameInputRef.value?.focus(); });
}

async function selectProfile(name) {
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
    form.value.models = c.models || (c.model ? [c.model] : []);
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
      form.value.base_url = '';
      form.value.api_key = '';
      form.value.models = [];
      form.value.provider = '';
      profileMode.value = 'new';
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

async function dryRunTest() {
  const token = localStorage.getItem('token');
  if (!token) return;
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
    toast('连通性验证已启动', 'info');
    store.switchTab('bench');
  } catch (e) { toast('失败: ' + e.message, 'error'); }
}

// ---- Lifecycle ----
onMounted(() => {
  if (!localStorage.getItem('token')) return;
  loadProfiles().then(() => {
    profileMode.value = currentProfileName.value ? 'selected' : 'new';
    snapshotProfileConfig();
  });
  loadKnownModels(form.value.provider);
});
</script>
