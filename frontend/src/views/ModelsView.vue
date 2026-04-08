<template>
  <section class="tab-content active">
    <!-- Toolbar（和历史记录页同结构） -->
    <div class="history-toolbar">
      <div class="search-input-wrap">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input class="form-input" v-model="search" placeholder="搜索模型名…" autocomplete="off">
      </div>
      <div class="filter-chips">
        <div class="combobox" ref="filterComboboxRef" style="min-width:160px;width:auto">
          <input class="form-input" :value="filterDropdownOpen ? filterSearch : filterLabel" :placeholder="'全部厂商'" @focus="onFilterFocus" @input="onFilterInput($event)" @keydown.escape="filterDropdownOpen = false" readonly autocomplete="off">
          <button class="combobox-toggle" type="button" @click.stop="filterDropdownOpen = !filterDropdownOpen" @mousedown.prevent>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5l3 3 3-3"/></svg>
          </button>
          <div class="combobox-dropdown" v-show="filterDropdownOpen">
            <div class="combobox-option" :class="{ active: filterProvider === '' }" @mousedown.prevent="selectFilterProvider('')">全部提供商</div>
            <div v-for="p in filteredFilterOptions" :key="p.value" class="combobox-option" :class="{ active: filterProvider === p.value }" @mousedown.prevent="selectFilterProvider(p.value)">{{ p.label }}</div>
          </div>
        </div>
      </div>
      <div style="margin-left:auto;display:flex;align-items:center;gap:8px">
        <span class="models-count">
          已启用 <strong>{{ enabledSet.size }}</strong>
          <span v-if="!enabledSet.size" style="color:var(--accent)">(全部)</span>
          · 共 {{ allModels.length }}
        </span>
        <button class="btn btn-ghost btn-sm" @click="showAddForm = !showAddForm" :class="{ active: showAddForm }">+ 自定义</button>
      </div>
    </div>

    <!-- 添加自定义模型面板 -->
    <div v-show="showAddForm" class="models-add-panel">
      <input class="form-input" v-model="addForm.id" placeholder="模型 ID" @keydown.enter="addCustomModel" autocomplete="off">
      <input class="form-input" v-model="addForm.provider" placeholder="厂商" autocomplete="off">
      <input class="form-input" v-model="addForm.input_price" placeholder="输入价格 ($/token)" autocomplete="off">
      <input class="form-input" v-model="addForm.output_price" placeholder="输出价格 ($/token)" autocomplete="off">
      <button class="btn btn-primary btn-sm" @click="addCustomModel" :disabled="!addForm.id.trim()">添加</button>
      <button class="btn btn-ghost btn-sm" @click="showAddForm = false">取消</button>
    </div>

    <!-- 卡片：表格 -->
    <div class="card" style="width:100%">
      <div v-if="loading" class="models-loading">加载中…</div>

      <div v-else class="models-table-wrap">
        <table class="models-table">
          <thead>
            <tr>
              <th class="models-th-check"><input type="checkbox" :checked="allVisibleEnabled" :indeterminate="someVisibleEnabled && !allVisibleEnabled" @change="toggleVisible"></th>
              <th class="models-th-name" @click="toggleSort('id')">
                模型名
                <span class="models-sort-arrow" v-if="sortKey === 'id'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="models-th-provider" @click="toggleSort('provider')">
                提供商
                <span class="models-sort-arrow" v-if="sortKey === 'provider'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="models-th-price" @click="toggleSort('input')">
                输入价格
                <span class="models-sort-arrow" v-if="sortKey === 'input'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="models-th-price" @click="toggleSort('output')">
                输出价格
                <span class="models-sort-arrow" v-if="sortKey === 'output'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="models-th-action"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in sortedModels" :key="m.id" :class="{ 'models-row-custom': m._custom }">
              <td class="models-td-check"><input type="checkbox" :checked="enabledSet.has(m.id)" @change="toggleModel(m.id)"></td>
              <td class="models-td-name" :title="m.id">{{ m.id }}<span v-if="m._custom" class="models-custom-badge">自定义</span></td>
              <td class="models-td-provider">{{ m.provider || '-' }}</td>
              <td class="models-td-price">{{ fmtPrice(m.input_cost_per_token) }}</td>
              <td class="models-td-price">{{ fmtPrice(m.output_cost_per_token) }}</td>
              <td class="models-td-action">
                <button v-if="m._custom" class="models-remove-btn" @click="removeCustom(m.id)" title="删除">×</button>
              </td>
            </tr>
            <tr v-if="!sortedModels.length">
              <td colspan="6" class="models-empty">无匹配模型</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 底部保存 -->
      <div class="btn-group" style="margin-top:16px">
        <button class="btn btn-primary" @click="save" :disabled="saving">
          <span v-if="!saving">保存配置</span>
          <span v-else>保存中…</span>
        </button>
        <span v-if="savedMsg" class="models-save-msg">{{ savedMsg }}</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue';
import { getPricingModels, getModelsConfig, putModelsConfig } from '../api';
import { toast } from '../composables/useToast';

const loading = ref(true);
const saving = ref(false);
const savedMsg = ref('');
const search = ref('');
const filterProvider = ref('');
const sortKey = ref('id');
const sortDir = ref('asc');
const showAddForm = ref(false);

const addForm = ref({ id: '', provider: '', input_price: '', output_price: '' });

// 提供商筛选 combobox
const filterDropdownOpen = ref(false);
const filterSearch = ref('');
const filterComboboxRef = ref(null);

const allModels = ref([]);
const customModels = ref([]);
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
    const knownIds = new Set(allModels.value.map(m => m.id));
    customModels.value = enabled
      .filter(id => !knownIds.has(id))
      .map(id => ({ id, provider: '', input_cost_per_token: 0, output_cost_per_token: 0, _custom: true }));
  } catch (e) {
    toast('加载模型列表失败: ' + e.message, 'error');
  }
  loading.value = false;
});

// 筛选 combobox handlers
// 从实际数据提取所有提供商，按模型数量降序排列
const filterOptions = computed(() => {
  const counts = {};
  for (const m of allModels.value) {
    const p = m.provider || 'unknown';
    counts[p] = (counts[p] || 0) + 1;
  }
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([value, count]) => ({ value, label: `${value} (${count})` }));
});

const filterLabel = computed(() => {
  const p = filterOptions.value.find(o => o.value === filterProvider.value);
  return p ? p.value : '';
});
const filteredFilterOptions = computed(() => {
  const q = (filterSearch.value || '').toLowerCase();
  if (!q) return filterOptions.value;
  return filterOptions.value.filter(p => p.value.toLowerCase().includes(q));
});
function onFilterFocus() { filterSearch.value = ''; filterDropdownOpen.value = true; }
function onFilterInput(e) { filterSearch.value = e.target.value; filterDropdownOpen.value = true; }
function selectFilterProvider(val) { filterProvider.value = val; filterDropdownOpen.value = false; filterSearch.value = ''; }

// 筛选 combobox click-outside
let filterListenerActive = false;
function handleFilterOutside(e) {
  if (filterComboboxRef.value && !filterComboboxRef.value.contains(e.target)) {
    filterDropdownOpen.value = false;
  }
}
watch(filterDropdownOpen, (open) => {
  if (open) {
    if (!filterListenerActive) {
      filterListenerActive = true;
      setTimeout(() => document.addEventListener('mousedown', handleFilterOutside), 0);
    }
  } else if (filterListenerActive) {
    filterListenerActive = false;
    document.removeEventListener('mousedown', handleFilterOutside);
  }
});

const filteredModels = computed(() => {
  let list = [...allModels.value, ...customModels.value];
  const q = search.value.toLowerCase().trim();
  if (q) list = list.filter(m => m.id.toLowerCase().includes(q));
  if (filterProvider.value) list = list.filter(m => m.provider === filterProvider.value);
  return list;
});

const sortedModels = computed(() => {
  const list = filteredModels.value;
  if (!sortKey.value) return list;
  return [...list].sort((a, b) => {
    let va, vb;
    switch (sortKey.value) {
      case 'id': va = a.id; vb = b.id; break;
      case 'provider': va = a.provider || ''; vb = b.provider || ''; break;
      case 'input': va = a.input_cost_per_token || 0; vb = b.input_cost_per_token || 0; break;
      case 'output': va = a.output_cost_per_token || 0; vb = b.output_cost_per_token || 0; break;
      default: return 0;
    }
    const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
    return sortDir.value === 'asc' ? cmp : -cmp;
  });
});

const visibleIds = computed(() => sortedModels.value.map(m => m.id));
const allVisibleEnabled = computed(() =>
  visibleIds.value.length > 0 && visibleIds.value.every(id => enabledSet.value.has(id))
);
const someVisibleEnabled = computed(() =>
  visibleIds.value.some(id => enabledSet.value.has(id))
);

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc';
  } else {
    sortKey.value = key;
    sortDir.value = key === 'id' ? 'asc' : 'desc';
  }
}

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

function addCustomModel() {
  const name = addForm.value.id.trim();
  if (!name) return;
  const all = [...allModels.value, ...customModels.value];
  if (all.some(m => m.id === name)) {
    toast('模型已存在', 'error');
    return;
  }
  customModels.value.push({
    id: name,
    provider: addForm.value.provider.trim(),
    input_cost_per_token: parseFloat(addForm.value.input_price) || 0,
    output_cost_per_token: parseFloat(addForm.value.output_price) || 0,
    _custom: true,
  });
  const s = new Set(enabledSet.value);
  s.add(name);
  enabledSet.value = s;
  addForm.value = { id: '', provider: '', input_price: '', output_price: '' };
}

function removeCustom(id) {
  customModels.value = customModels.value.filter(m => m.id !== id);
  const s = new Set(enabledSet.value);
  s.delete(id);
  enabledSet.value = s;
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
