<template>
  <div class="site-config-tab">
    <div class="card">
      <div class="card-header">
        <div class="card-title">站点配置</div>
      </div>

      <!-- Config Form -->
      <div class="form-grid">
        <!-- Site Name (with rename) -->
        <div class="form-group">
          <label class="form-label">站点名称</label>
          <div v-if="!renaming" class="rename-row">
            <input class="form-input" :value="profile.name" readonly style="opacity:0.7;cursor:default;flex:1">
            <button class="btn btn-ghost btn-sm rename-btn" @click="startRename" title="改名">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              改名
            </button>
          </div>
          <div v-else class="rename-row">
            <input class="form-input" v-model="renameValue" ref="renameInputRef"
                   @keyup.enter="confirmRename" @keyup.esc="cancelRename"
                   placeholder="输入新站点名称" style="flex:1">
            <button class="btn btn-primary btn-sm" @click="confirmRename" :disabled="renaming && !renameValue.trim()">确认</button>
            <button class="btn btn-ghost btn-sm" @click="cancelRename">取消</button>
          </div>
        </div>

        <!-- Base URL -->
        <div class="form-group">
          <label class="form-label">目标地址</label>
          <input class="form-input" v-model="form.base_url" :placeholder="form.custom_endpoint ? 'https://open.bigmodel.cn/api/paas/v4/chat/completions' : 'https://api.anthropic.com'">
          <label class="checkbox-label">
            <input type="checkbox" v-model="form.custom_endpoint">
            <span>完整 URL 模式</span>
            <span class="form-hint">勾选后不再自动追加 /v1/chat/completions 等路径后缀</span>
          </label>
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

        <!-- Models -->
        <div class="form-group form-group--full">
          <label class="form-label">绑定模型</label>
          <ModelSelector
            v-model="form.models"
            :vendor-filter="true"
            :allow-custom="true"
            placeholder="选择或输入模型 ID"
          />
        </div>
      </div>

      <!-- Actions -->
      <div class="site-config-actions">
        <div class="site-config-actions-left">
          <button class="btn btn-primary" @click="saveProfile()" :disabled="!canSave()">
            {{ formDirty ? '更新配置' : '保存配置' }}
          </button>
          <button class="btn btn-ghost" @click="runConnTest()" :disabled="!canTest()" v-if="form.base_url && form.api_key && form.models.length">
            连通性验证
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

      <ConnectivityProgress
        :running="connTest.running.value"
        :progress="connTest.progress.value"
        :logs="connTest.logs.value"
        :result="connTest.result.value"
        :error="connTest.error.value"
        @dismiss="connTest.reset()"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue';
import { api } from '../api/index.js';
import { renameProfile } from '../api/index.js';
import { toast } from '../composables/useToast.js';
import ModelSelector from './ModelSelector.vue';
import ConnectivityProgress from './ConnectivityProgress.vue';
import { useConnectivityTest } from '../composables/useConnectivityTest.js';

const props = defineProps({
  profile: { type: Object, required: true },
});
const emit = defineEmits(['deleted', 'renamed']);

// ---- Form state ----
const form = ref({
  base_url: '',
  api_key: '',
  models: [],
  custom_endpoint: false,
});
const showApiKey = ref(false);
const confirmDelete = ref(false);
const formDirty = ref(false);
const savedConfig = ref(null);

// ---- Rename state ----
const renaming = ref(false);
const renameValue = ref('');
const renameInputRef = ref(null);

function startRename() {
  renameValue.value = props.profile.name;
  renaming.value = true;
  nextTick(() => {
    if (renameInputRef.value) {
      renameInputRef.value.focus();
      renameInputRef.value.select();
    }
  });
}

function cancelRename() {
  renaming.value = false;
  renameValue.value = '';
}

async function confirmRename() {
  const newName = renameValue.value.trim();
  if (!newName) {
    toast('新名称不能为空', 'info');
    return;
  }
  if (newName === props.profile.name) {
    cancelRename();
    return;
  }
  try {
    const res = await renameProfile(props.profile.name, newName);
    if (res.error) {
      toast('改名失败: ' + res.error, 'error');
      return;
    }
    toast(`站点已改名为「${newName}」`, 'success');
    renaming.value = false;
    renameValue.value = '';
    emit('renamed', newName);
  } catch (e) {
    toast('改名失败: ' + e.message, 'error');
  }
}

// ---- Init form from profile ----
function initForm() {
  if (!props.profile) return;
  form.value.base_url = props.profile.base_url || '';
  form.value.api_key = props.profile.api_key_display || '';
  form.value.models = props.profile.models || (props.profile.model ? [props.profile.model] : []);
  form.value.custom_endpoint = !!props.profile.custom_endpoint;
  snapshotConfig();
}

function snapshotConfig() {
  savedConfig.value = {
    base_url: form.value.base_url,
    api_key: form.value.api_key,
    models: [...form.value.models],
    custom_endpoint: form.value.custom_endpoint,
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
    form.value.custom_endpoint !== (s.custom_endpoint || false)
  );
}

// ---- Watchers ----
watch(() => form.value.base_url, () => checkDirty());
watch(() => form.value.api_key, () => checkDirty());
watch(() => form.value.models, () => checkDirty(), { deep: true });
watch(() => form.value.custom_endpoint, () => checkDirty());

watch(() => props.profile, () => {
  initForm();
}, { immediate: true });

// ---- Validation ----
function canSave() {
  return Boolean(
    form.value.base_url.trim() &&
    form.value.models.length > 0
  );
}

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
  if (formDirty.value) {
    toast('请先保存配置后再验证连通性', 'info');
    return;
  }
  connTest.start({
    profile_name: props.profile.name,
    model: form.value.models[0] || '',
  });
}

// ---- Actions ----
function apiKeyAction() {
  const value = (form.value.api_key || '').trim();
  if (!value) return 'clear';
  if (value.startsWith('...')) return 'keep';
  return 'replace';
}

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
        api_key_action: apiKeyAction(),
        models: form.value.models,
        custom_endpoint: form.value.custom_endpoint,
        api_version: '2023-06-01',
      }),
    });
    toast(formDirty.value ? '配置已更新' : '配置已保存', 'success');
    snapshotConfig();
  } catch (e) {
    toast('保存失败: ' + e.message, 'error');
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

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  width: 15px;
  height: 15px;
  cursor: pointer;
  flex-shrink: 0;
}

.form-hint {
  color: var(--text-tertiary);
  font-size: 12px;
}

.rename-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rename-btn {
  white-space: nowrap;
  flex-shrink: 0;
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
