<template>
  <section class="tab-content active">
    <!-- Tab Navigation -->
    <div class="models-tabs">
      <button
        class="models-tab"
        :class="{ active: activeTab === 'my' }"
        @click="activeTab = 'my'"
      >我的模型</button>
      <button
        class="models-tab"
        :class="{ active: activeTab === 'library' }"
        @click="activeTab = 'library'; loadLibrary()"
      >模型库</button>
    </div>

    <!-- Tab 1: My Models -->
    <div v-if="activeTab === 'my'" class="models-panel">
      <div class="history-toolbar">
        <div class="search-input-wrap">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input class="form-input" v-model="mySearch" placeholder="搜索模型名…" autocomplete="off">
        </div>
        <div class="filter-chips">
          <button class="filter-chip" :class="{ active: myVendor === '' }" @click="myVendor = ''">全部</button>
          <button v-for="v in vendors" :key="v.id" class="filter-chip" :class="{ active: myVendor === v.id }" @click="myVendor = v.id">{{ v.name }}</button>
        </div>
        <div style="margin-left:auto;display:flex;align-items:center;gap:8px">
          <span class="models-count">
            已启用 <strong>{{ enabledCount }}</strong> · 共 {{ myModels.length }}
          </span>
          <button class="btn btn-ghost btn-sm" @click="showAddForm = !showAddForm" :class="{ active: showAddForm }">+ 自定义</button>
        </div>
      </div>

      <!-- Add Custom Model Panel -->
      <div v-show="showAddForm" class="models-add-panel">
        <input class="form-input" v-model="addForm.id" placeholder="模型 ID" @keydown.enter="addCustomModel" autocomplete="off">
        <select class="form-select" v-model="addForm.vendor" style="width:160px">
          <option value="">选择厂商</option>
          <option v-for="v in vendors" :key="v.id" :value="v.id">{{ v.name }}</option>
        </select>
        <button class="btn btn-primary btn-sm" @click="addCustomModel" :disabled="!addForm.id.trim()">添加</button>
        <button class="btn btn-ghost btn-sm" @click="showAddForm = false">取消</button>
      </div>

      <!-- My Models Table -->
      <div class="card" style="width:100%">
        <div v-if="myLoading" class="models-loading">加载中…</div>
        <div v-else class="models-table-wrap">
          <table class="models-table">
            <thead>
              <tr>
                <th class="models-th-check"><input type="checkbox" :checked="allVisibleEnabled" :indeterminate="someVisibleEnabled && !allVisibleEnabled" @change="toggleVisible"></th>
                <th class="models-th-name" @click="toggleSort('id')">模型名 <span class="models-sort-arrow" v-if="sortKey === 'id'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></th>
                <th class="models-th-provider" @click="toggleSort('vendor')">厂商 <span class="models-sort-arrow" v-if="sortKey === 'vendor'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></th>
                <th class="models-th-price">输入价格</th>
                <th class="models-th-price">输出价格</th>
                <th class="models-th-action"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in sortedMyModels" :key="m.id" :class="{ 'models-row-custom': m.custom }">
                <td class="models-td-check"><input type="checkbox" :checked="m.enabled" @change="toggleModel(m.id)"></td>
                <td class="models-td-name" :title="m.id">{{ m.id }}<span v-if="m.custom" class="models-custom-badge">自定义</span></td>
                <td class="models-td-provider">{{ vendorLabel(m.vendor) }}</td>
                <td class="models-td-price">{{ fmtPrice(m.input_cost_per_token) }}</td>
                <td class="models-td-price">{{ fmtPrice(m.output_cost_per_token) }}</td>
                <td class="models-td-action">
                  <button v-if="m.custom" class="models-remove-btn" @click="removeModel(m.id)" title="删除">×</button>
                </td>
              </tr>
              <tr v-if="!sortedMyModels.length">
                <td colspan="6" class="models-empty">无匹配模型</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="btn-group" style="margin-top:16px">
          <button class="btn btn-primary" @click="saveMyModels" :disabled="saving">{{ saving ? '保存中…' : '保存配置' }}</button>
          <span v-if="savedMsg" class="models-save-msg">{{ savedMsg }}</span>
        </div>
      </div>
    </div>

    <!-- Tab 2: Library -->
    <div v-if="activeTab === 'library'" class="models-panel">
      <div class="history-toolbar">
        <div class="search-input-wrap">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input class="form-input" v-model="libSearch" placeholder="搜索模型名…" @input="debouncedLoadLibrary" autocomplete="off">
        </div>
        <div class="combobox" style="max-width:200px" ref="libVendorRef">
          <svg class="combobox-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M3 12h18M3 18h18"/></svg>
          <input class="form-input" v-model="libVendorSearch" placeholder="按厂商过滤…" @focus="libVendorDropOpen = true" @input="libVendorDropOpen = true" autocomplete="off" style="padding-left:32px">
          <button class="combobox-toggle" @click="libVendorDropOpen = !libVendorDropOpen">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5l3 3 3-3"/></svg>
          </button>
          <div class="combobox-dropdown" v-show="libVendorDropOpen">
            <div class="combobox-option" :class="{ active: libVendor === '' }" @mousedown.prevent="selectLibVendor('')">全部厂商</div>
            <div v-for="p in filteredLibVendors" :key="p" class="combobox-option" :class="{ active: libVendor === p }" @mousedown.prevent="selectLibVendor(p)">{{ p }}</div>
            <div class="combobox-empty" v-if="!filteredLibVendors.length && libVendorSearch">无匹配厂商</div>
          </div>
        </div>
        <span class="models-count" style="margin-left:auto">共 {{ libTotal }} 个模型</span>
      </div>

      <div class="card" style="width:100%">
        <div v-if="libLoading" class="models-loading">加载中…</div>
        <div v-else class="models-table-wrap">
          <table class="models-table">
            <thead>
              <tr>
                <th class="models-th-name">模型名</th>
                <th class="models-th-provider">厂商</th>
                <th class="models-th-price">输入价格</th>
                <th class="models-th-price">输出价格</th>
                <th style="width:80px">Max Tokens</th>
                <th class="models-th-action">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in libModels" :key="m.id">
                <td class="models-td-name" :title="m.id">{{ m.id }}</td>
                <td class="models-td-provider">{{ m.provider || '-' }}</td>
                <td class="models-td-price">{{ fmtPrice(m.input_cost_per_token) }}</td>
                <td class="models-td-price">{{ fmtPrice(m.output_cost_per_token) }}</td>
                <td style="font-size:11px;font-family:var(--font-mono)">{{ m.max_input_tokens ? fmtNum(m.max_input_tokens) : '-' }}</td>
                <td class="models-td-action">
                  <button v-if="myModelIds.has(m.id)" class="btn btn-ghost btn-sm" disabled style="opacity:0.5">已添加</button>
                  <button v-else class="btn btn-ghost btn-sm" @click="addFromLibrary(m)">添加</button>
                </td>
              </tr>
              <tr v-if="!libModels.length">
                <td colspan="6" class="models-empty">无匹配模型</td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- Pagination -->
        <div v-if="libTotal > libPageSize" class="models-pagination">
          <button class="btn btn-ghost btn-sm" :disabled="libPage <= 1" @click="libPage--; loadLibrary()">上一页</button>
          <span class="models-page-info">第 {{ libPage }} / {{ Math.ceil(libTotal / libPageSize) }} 页</span>
          <button class="btn btn-ghost btn-sm" :disabled="libPage * libPageSize >= libTotal" @click="libPage++; loadLibrary()">下一页</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { getModelsConfig, putModelsConfig, getLibrary, getVendors, getProviders } from '../api';
import { toast } from '../composables/useToast';

const activeTab = ref('my');

// ---- Shared ----
const vendors = ref([]);

function vendorLabel(vendorId) {
  const v = vendors.value.find(x => x.id === vendorId);
  return v ? v.name : vendorId || '-';
}

function fmtPrice(v) {
  if (!v) return '-';
  return '$' + (v * 1000000).toFixed(2) + '/M';
}

function fmtNum(v) {
  if (v >= 1000000) return (v / 1000000).toFixed(1) + 'M';
  if (v >= 1000) return (v / 1000).toFixed(0) + 'K';
  return String(v);
}

// ---- Tab 1: My Models ----
const myLoading = ref(true);
const saving = ref(false);
const savedMsg = ref('');
const mySearch = ref('');
const myVendor = ref('');
const sortKey = ref('id');
const sortDir = ref('asc');
const showAddForm = ref(false);
const addForm = ref({ id: '', vendor: '' });

const myModels = ref([]);
const myModelIds = computed(() => new Set(myModels.value.map(m => m.id)));
const enabledCount = computed(() => myModels.value.filter(m => m.enabled).length);

const filteredMyModels = computed(() => {
  let list = myModels.value;
  const q = mySearch.value.toLowerCase().trim();
  if (q) list = list.filter(m => m.id.toLowerCase().includes(q));
  if (myVendor.value) list = list.filter(m => m.vendor === myVendor.value);
  return list;
});

const sortedMyModels = computed(() => {
  const list = [...filteredMyModels.value];
  return list.sort((a, b) => {
    let va, vb;
    switch (sortKey.value) {
      case 'id': va = a.id; vb = b.id; break;
      case 'vendor': va = a.vendor || ''; vb = b.vendor || ''; break;
      default: return 0;
    }
    const cmp = va.localeCompare(vb);
    return sortDir.value === 'asc' ? cmp : -cmp;
  });
});

const visibleIds = computed(() => sortedMyModels.value.map(m => m.id));
const allVisibleEnabled = computed(() =>
  visibleIds.value.length > 0 && visibleIds.value.every(id => {
    const m = myModels.value.find(x => x.id === id);
    return m?.enabled;
  })
);
const someVisibleEnabled = computed(() =>
  visibleIds.value.some(id => {
    const m = myModels.value.find(x => x.id === id);
    return m?.enabled;
  })
);

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc';
  } else {
    sortKey.value = key;
    sortDir.value = 'asc';
  }
}

function toggleModel(id) {
  const m = myModels.value.find(x => x.id === id);
  if (m) m.enabled = !m.enabled;
}

function toggleVisible() {
  const target = !allVisibleEnabled.value;
  for (const id of visibleIds.value) {
    const m = myModels.value.find(x => x.id === id);
    if (m) m.enabled = target;
  }
}

function addCustomModel() {
  const id = addForm.value.id.trim();
  if (!id) return;
  if (myModels.value.some(m => m.id === id)) {
    toast('模型已存在', 'error');
    return;
  }
  myModels.value.push({
    id,
    vendor: addForm.value.vendor,
    enabled: true,
    custom: true,
  });
  addForm.value = { id: '', vendor: '' };
}

function removeModel(id) {
  myModels.value = myModels.value.filter(m => m.id !== id);
}

async function saveMyModels() {
  saving.value = true;
  savedMsg.value = '';
  try {
    await putModelsConfig({
      vendors: vendors.value,
      models: myModels.value,
    });
    savedMsg.value = `已保存 ${myModels.value.length} 个模型`;
    toast('模型配置已保存', 'success');
    setTimeout(() => savedMsg.value = '', 3000);
  } catch (e) {
    toast('保存失败: ' + e.message, 'error');
  }
  saving.value = false;
}

// ---- Tab 2: Library ----
const libLoading = ref(false);
const libSearch = ref('');
const libVendor = ref('');
const libVendorSearch = ref('');
const libVendorDropOpen = ref(false);
const libVendorRef = ref(null);
const libModels = ref([]);
const libTotal = ref(0);
const libPage = ref(1);
const libPageSize = 50;

// LiteLLM providers（从后端动态获取）
const libProviders = ref([]);

const filteredLibVendors = computed(() => {
  const q = libVendorSearch.value.toLowerCase().trim();
  if (!q) return libProviders.value;
  return libProviders.value.filter(p => p.toLowerCase().includes(q));
});

function selectLibVendor(vendorId) {
  libVendor.value = vendorId;
  libVendorSearch.value = vendorId || '';
  libVendorDropOpen.value = false;
  libPage.value = 1;
  loadLibrary();
}

let libTimer = null;
function debouncedLoadLibrary() {
  clearTimeout(libTimer);
  libTimer = setTimeout(() => { libPage.value = 1; loadLibrary(); }, 300);
}

async function loadLibrary() {
  libLoading.value = true;
  try {
    const data = await getLibrary({
      search: libSearch.value,
      vendor: libVendor.value,
      page: libPage.value,
      pageSize: libPageSize,
    });
    libModels.value = data.models || [];
    libTotal.value = data.total || 0;
  } catch (e) {
    toast('加载模型库失败: ' + e.message, 'error');
  }
  libLoading.value = false;
}

function addFromLibrary(model) {
  if (myModels.value.some(m => m.id === model.id)) return;

  let vendor = '';
  const provider = (model.provider || '').toLowerCase();
  for (const v of vendors.value) {
    if (provider.includes(v.id)) {
      vendor = v.id;
      break;
    }
  }

  myModels.value.push({
    id: model.id,
    vendor,
    enabled: true,
  });
  toast(`已添加 ${model.id}`, 'success');
}

// ---- Init ----
let clickOutsideHandler = null;

onMounted(async () => {
  try {
    const [configRes, vendorsRes] = await Promise.all([
      getModelsConfig(),
      getVendors(),
    ]);
    vendors.value = vendorsRes.vendors || [];
    myModels.value = configRes.models || [];
  } catch (e) {
    toast('加载失败: ' + e.message, 'error');
  }
  myLoading.value = false;

  // 异步加载 LiteLLM providers（不阻塞页面）
  getProviders().then(res => {
    libProviders.value = res.providers || [];
  }).catch(() => {});

  clickOutsideHandler = (e) => {
    if (libVendorRef.value && !libVendorRef.value.contains(e.target)) {
      libVendorDropOpen.value = false;
    }
  };
  document.addEventListener('click', clickOutsideHandler);
});

onUnmounted(() => {
  if (clickOutsideHandler) document.removeEventListener('click', clickOutsideHandler);
});
</script>

<style scoped>
/* ---- Tab Navigation ---- */
.models-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 20px;
}

.models-tab {
  padding: 10px 20px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.models-tab:hover {
  color: var(--text-primary);
}

.models-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.models-panel {
  animation: fadeIn 0.15s ease;
}

.combobox-search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-tertiary);
  pointer-events: none;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ---- Pagination ---- */
.models-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--border-subtle);
}

.models-page-info {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}
</style>
