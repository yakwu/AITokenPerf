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
import { ref, watch } from 'vue';
import { api } from '../api/index.js';
import { toast } from '../composables/useToast.js';
import ModelSelector from './ModelSelector.vue';

const props = defineProps({
  profile: { type: Object, required: true },
});
const emit = defineEmits(['deleted']);

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

// ---- Connectivity test ----
const testing = ref(false);

// ---- Init form from profile ----
function initForm() {
  if (!props.profile) return;
  form.value.base_url = props.profile.base_url || '';
  form.value.api_key = props.profile.api_key_display || props.profile.api_key || '';
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
        custom_endpoint: form.value.custom_endpoint,
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
