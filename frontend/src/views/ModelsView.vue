<template>
  <section class="tab-content active">
    <div class="settings-page">
      <div class="card">
        <div class="card-header">
          <div class="card-title">模型管理</div>
          <div style="font-size:12px;color:var(--text-tertiary)">
            已启用 <strong>{{ enabledSet.size }}</strong> 个模型
            <span v-if="!enabledSet.size" style="color:var(--accent)">(全部显示)</span>
          </div>
        </div>

        <!-- 工具栏 -->
        <div style="display:flex;gap:10px;align-items:center;margin-bottom:16px;flex-wrap:wrap">
          <input class="form-input" v-model="search" placeholder="搜索模型名…" style="flex:1;min-width:200px">
          <select class="form-select" v-model="filterProvider" style="min-width:140px">
            <option value="">全部厂商</option>
            <option value="anthropic">Anthropic</option>
            <option value="openai">OpenAI</option>
            <option value="deepseek">DeepSeek</option>
            <option value="qwen">Qwen</option>
            <option value="google">Google</option>
            <option value="mistral">Mistral</option>
            <option value="cohere">Cohere</option>
            <option value="bytedance">字节</option>
            <option value="zhipu">智谱</option>
            <option value="moonshot">Moonshot</option>
          </select>
          <button class="btn btn-ghost btn-sm" @click="selectAll">全选</button>
          <button class="btn btn-ghost btn-sm" @click="selectNone">全不选</button>
        </div>

        <!-- 加载状态 -->
        <div v-if="loading" style="text-align:center;padding:40px;color:var(--text-tertiary)">加载中…</div>

        <!-- 模型列表 -->
        <div v-else class="table-wrap" style="max-height:60vh">
          <table class="pct-table">
            <thead>
              <tr>
                <th style="width:40px;text-align:center">
                  <input type="checkbox" :checked="allVisibleEnabled" :indeterminate="someVisibleEnabled && !allVisibleEnabled" @change="toggleVisible">
                </th>
                <th>模型名</th>
                <th>厂商</th>
                <th style="text-align:right">输入价格</th>
                <th style="text-align:right">输出价格</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in filteredModels" :key="m.id">
                <td style="text-align:center">
                  <input type="checkbox" :checked="enabledSet.has(m.id)" @change="toggleModel(m.id)">
                </td>
                <td style="font-family:var(--font-mono);font-size:12px">{{ m.id }}</td>
                <td style="font-size:12px;color:var(--text-secondary)">{{ m.provider || '-' }}</td>
                <td style="text-align:right;font-size:12px;font-family:var(--font-mono)">{{ fmtPrice(m.input_cost_per_token) }}</td>
                <td style="text-align:right;font-size:12px;font-family:var(--font-mono)">{{ fmtPrice(m.output_cost_per_token) }}</td>
              </tr>
              <tr v-if="!filteredModels.length">
                <td colspan="5" style="text-align:center;color:var(--text-tertiary);padding:20px">无匹配模型</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 底部操作 -->
        <div class="btn-group" style="margin-top:16px">
          <button class="btn btn-primary" @click="save" :disabled="saving">
            <span v-if="!saving">保存配置</span>
            <span v-else>保存中…</span>
          </button>
          <span v-if="savedMsg" class="settings-msg success" style="display:inline-block;margin:0;padding:6px 14px">{{ savedMsg }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { getPricingModels, getModelsConfig, putModelsConfig } from '../api';
import { toast } from '../composables/useToast';

const loading = ref(true);
const saving = ref(false);
const savedMsg = ref('');
const search = ref('');
const filterProvider = ref('');

const allModels = ref([]);
const enabledSet = ref(new Set());

onMounted(async () => {
  try {
    const [modelsRes, configRes] = await Promise.all([
      getPricingModels(''),
      getModelsConfig(),
    ]);
    allModels.value = modelsRes.models || [];
    const enabled = configRes.enabled_models || [];
    enabledSet.value = new Set(enabled);
  } catch (e) {
    toast('加载模型列表失败: ' + e.message, 'error');
  }
  loading.value = false;
});

const filteredModels = computed(() => {
  let list = allModels.value;
  const q = search.value.toLowerCase().trim();
  if (q) {
    list = list.filter(m => m.id.toLowerCase().includes(q));
  }
  if (filterProvider.value) {
    list = list.filter(m => m.provider === filterProvider.value);
  }
  return list;
});

const visibleIds = computed(() => filteredModels.value.map(m => m.id));

const allVisibleEnabled = computed(() =>
  visibleIds.value.length > 0 && visibleIds.value.every(id => enabledSet.value.has(id))
);
const someVisibleEnabled = computed(() =>
  visibleIds.value.some(id => enabledSet.value.has(id))
);

function toggleModel(id) {
  const s = new Set(enabledSet.value);
  if (s.has(id)) s.delete(id); else s.add(id);
  enabledSet.value = s;
}

function selectAll() {
  const s = new Set(enabledSet.value);
  for (const id of visibleIds.value) s.add(id);
  enabledSet.value = s;
}

function selectNone() {
  const s = new Set(enabledSet.value);
  for (const id of visibleIds.value) s.delete(id);
  enabledSet.value = s;
}

function toggleVisible() {
  if (allVisibleEnabled.value) selectNone(); else selectAll();
}

function fmtPrice(v) {
  if (!v) return '-';
  if (v < 0.00001) return '$' + (v * 1000000).toFixed(2) + '/M';
  return '$' + (v * 1000).toFixed(2) + '/K';
}

async function save() {
  saving.value = true;
  savedMsg.value = '';
  try {
    const models = [...enabledSet.value];
    await putModelsConfig(models);
    savedMsg.value = `已保存 ${models.length} 个模型`;
    toast('模型配置已保存', 'success');
    setTimeout(() => savedMsg.value = '', 3000);
  } catch (e) {
    toast('保存失败: ' + e.message, 'error');
  }
  saving.value = false;
}
</script>
