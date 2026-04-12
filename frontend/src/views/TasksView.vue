<template>
  <section class="tab-content active">
    <!-- Toolbar -->
    <div class="history-toolbar">
      <div class="sites-toolbar-left">
        <span class="sites-count">共 {{ filteredSchedules.length }} 个任务</span>
        <div class="search-input-wrap">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input class="form-input" type="text" v-model="search" placeholder="搜索任务名称 / 站点...">
        </div>
        <div class="time-range-pills">
          <button
            v-for="f in statusFilters"
            :key="f.value"
            class="time-range-pill"
            :class="{ active: statusFilter === f.value }"
            @click="statusFilter = f.value"
          >{{ f.label }}</button>
        </div>
      </div>
      <div class="sites-toolbar-right">
        <button class="btn btn-primary btn-sm" @click="onCreateTask">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          新建任务
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading && !schedules.length" style="text-align:center;color:var(--text-tertiary);padding:40px">加载中...</div>

    <!-- Empty State -->
    <div v-else-if="!filteredSchedules.length && !loading" class="empty-state">
      <div class="empty-state-icon">&#9200;</div>
      <div class="empty-state-text">{{ schedules.length ? '没有匹配的定时任务' : '尚无定时任务' }}</div>
      <p style="color:var(--text-tertiary);font-size:13px">{{ schedules.length ? '尝试调整筛选条件' : '点击「新建任务」创建你的第一个定时任务' }}</p>
    </div>

    <!-- Schedule Table -->
    <div v-else class="card" style="padding:0;overflow:hidden">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>站点名</th>
              <th>任务名称</th>
              <th>状态</th>
              <th>频率</th>
              <th>模型</th>
              <th>并发</th>
              <th>上次结果</th>
              <th>下次执行</th>
              <th style="width:140px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in filteredSchedules" :key="s.id">
              <!-- Site Name (clickable) -->
              <td>
                <router-link
                  v-if="getSiteName(s)"
                  :to="`/sites/${encodeURIComponent(getSiteName(s))}?tab=trends`"
                  class="site-link"
                  :title="getSiteName(s)"
                >{{ getSiteName(s) }}</router-link>
                <span v-else class="text-tertiary">-</span>
              </td>
              <!-- Task Name -->
              <td style="font-weight:600">
                {{ s.name }}
                <span class="schedule-id">#{{ s.id }}</span>
              </td>
              <!-- Status -->
              <td>
                <span class="status-badge" :class="s.status">
                  <span v-if="s.status === 'active'" class="status-dot"></span>
                  {{ statusLabel(s.status) }}
                </span>
              </td>
              <!-- Frequency -->
              <td>{{ formatInterval(s.schedule_value) }}</td>
              <!-- Model -->
              <td class="model-cell">{{ getModelFromSchedule(s) }}</td>
              <!-- Concurrency -->
              <td>{{ getConcurrencyFromSchedule(s) }}</td>
              <!-- Last Result -->
              <td>
                <div v-if="s.last_run_result" class="last-result">
                  <span
                    class="success-rate"
                    :class="successRateClass(s.last_run_result.success_rate)"
                  >{{ s.last_run_result.success_rate != null ? s.last_run_result.success_rate.toFixed(1) + '%' : '-' }}</span>
                  <span class="last-time" v-if="s.last_run_at">{{ formatTime(s.last_run_at) }}</span>
                </div>
                <span v-else class="no-result">-</span>
              </td>
              <!-- Next Run -->
              <td class="next-run">{{ formatTime(s.next_run_at) }}</td>
              <!-- Actions -->
              <td style="white-space:nowrap">
                <button class="btn btn-ghost btn-sm" v-show="s.status === 'active'" @click="pauseSchedule(s.id)" title="暂停">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
                </button>
                <button class="btn btn-ghost btn-sm" v-show="s.status !== 'active'" @click="resumeSchedule(s.id)" title="恢复">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                </button>
                <button class="btn btn-ghost btn-sm" @click="runNow(s.id)" title="立即执行">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                </button>
                <InlineConfirmDelete
                  :active="deleteCandidate === s.id"
                  title="删除"
                  icon-style="color:var(--danger)"
                  @request.stop="deleteCandidate = s.id"
                  @cancel.stop="deleteCandidate = null"
                  @confirm.stop="confirmDelete(s.id)"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
                </InlineConfirmDelete>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <!-- Create Modal -->
    <ModalOverlay :show="showCreateForm" title="新建定时任务" max-width="640px" @close="showCreateForm = false">
      <!-- 基础信息 -->
      <div class="create-modal-grid">
        <div class="form-group">
          <label class="form-label">目标站点</label>
          <div class="combobox" ref="profileComboboxRef">
            <input class="form-input" :value="createForm.profile_name" placeholder="选择站点"
                   @focus="profileDropdownOpen = true" @keydown.escape="profileDropdownOpen = false"
                   readonly autocomplete="off">
            <button class="combobox-toggle" type="button" @click.stop="profileDropdownOpen = !profileDropdownOpen" @mousedown.prevent>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5l3 3 3-3"/></svg>
            </button>
            <div class="combobox-dropdown" v-show="profileDropdownOpen">
              <div v-for="p in profiles" :key="p.name" class="combobox-option" :class="{ active: createForm.profile_name === p.name }" @mousedown.prevent="selectCreateProfile(p.name)">{{ p.name }}</div>
              <div class="combobox-empty" v-if="!profiles.length">暂无站点配置</div>
            </div>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">任务名称</label>
          <input class="form-input" v-model="createForm.name" placeholder="例如：快速巡检">
        </div>
        <div class="form-group">
          <label class="form-label">执行频率</label>
          <div class="combobox" ref="freqComboboxRef">
            <input class="form-input" :value="frequencyLabel" placeholder="选择频率"
                   @focus="freqDropdownOpen = true" @keydown.escape="freqDropdownOpen = false"
                   readonly autocomplete="off">
            <button class="combobox-toggle" type="button" @click.stop="freqDropdownOpen = !freqDropdownOpen" @mousedown.prevent>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5l3 3 3-3"/></svg>
            </button>
            <div class="combobox-dropdown" v-show="freqDropdownOpen">
              <div v-for="opt in frequencyOptions" :key="opt.value" class="combobox-option" :class="{ active: frequencyPreset === opt.value }" @mousedown.prevent="selectFrequency(opt.value)">{{ opt.label }}</div>
            </div>
          </div>
          <div class="form-hint" v-if="frequencyPreset === 'custom'" style="margin-top:6px">
            <input class="form-input" type="number" v-model.number="createForm.schedule_value" min="60" placeholder="秒" style="width:120px">
          </div>
          <div class="form-hint">每 {{ formatInterval(createForm.schedule_value) }} 执行一次</div>
        </div>
      </div>
      <!-- 模型选择 -->
      <div class="form-group" style="margin-top:16px">
        <label class="form-label">选择模型</label>
        <div class="combobox" ref="modelComboboxRef">
          <div class="model-tags-input" @click="createForm.profile_name && (modelDropdownOpen = true)">
            <span v-for="(m, i) in createForm.models" :key="m" class="model-tag">
              {{ m }}
              <button type="button" class="model-tag-remove" @click.stop="createForm.models.splice(i, 1)">&times;</button>
            </span>
            <input class="model-tag-search" v-model="modelSearch" :placeholder="!createForm.profile_name ? '请先选择站点' : createForm.models.length ? '' : '选择或搜索模型'" :disabled="!createForm.profile_name" @focus="createForm.profile_name && (modelDropdownOpen = true)" @keydown.enter.prevent="addTaskModel()" @keydown.backspace="createForm.models.length && !modelSearch && createForm.models.pop()" @keydown.escape="modelDropdownOpen = false" autocomplete="off">
          </div>
          <button class="combobox-toggle" type="button" @click.stop="createForm.profile_name && (modelDropdownOpen = !modelDropdownOpen)" @mousedown.prevent>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5l3 3 3-3"/></svg>
          </button>
          <div class="combobox-dropdown" v-show="modelDropdownOpen">
            <div v-for="m in filteredTaskModels" :key="m" class="combobox-option" :class="{ active: createForm.models.includes(m) }" @mousedown.prevent="toggleTaskModel(m)">{{ m }}</div>
            <div class="combobox-empty" v-show="!filteredTaskModels.length && modelSearch">无匹配，按回车添加「{{ modelSearch }}」</div>
            <div class="combobox-empty" v-show="!filteredTaskModels.length && !modelSearch">该站点未配置模型</div>
          </div>
        </div>
      </div>
      <!-- 高级参数（折叠） -->
      <div class="advanced-section">
        <button class="advanced-toggle" @click="showAdvanced = !showAdvanced">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 00-2 2v.18a2 2 0 01-1 1.73l-.43.25a2 2 0 01-2 0l-.15-.08a2 2 0 00-2.73.73l-.22.38a2 2 0 00.73 2.73l.15.1a2 2 0 011 1.72v.51a2 2 0 01-1 1.74l-.15.09a2 2 0 00-.73 2.73l.22.38a2 2 0 002.73.73l.15-.08a2 2 0 012 0l.43.25a2 2 0 011 1.73V20a2 2 0 002 2h.44a2 2 0 002-2v-.18a2 2 0 011-1.73l.43-.25a2 2 0 012 0l.15.08a2 2 0 002.73-.73l.22-.39a2 2 0 00-.73-2.73l-.15-.08a2 2 0 01-1-1.74v-.5a2 2 0 011-1.74l.15-.09a2 2 0 00.73-2.73l-.22-.38a2 2 0 00-2.73-.73l-.15.08a2 2 0 01-2 0l-.43-.25a2 2 0 01-1-1.73V4a2 2 0 00-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
          测试参数
          <svg class="advanced-chevron" :class="{ open: showAdvanced }" width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5l3 3 3-3"/></svg>
        </button>
        <div class="advanced-body" v-show="showAdvanced">
          <div class="create-modal-grid" style="grid-template-columns:repeat(3,1fr)">
            <div class="form-group">
              <label class="form-label">并发数</label>
              <input class="form-input" type="number" v-model.number="createForm.concurrency" min="1" max="100" placeholder="1">
            </div>
            <div class="form-group">
              <label class="form-label">超时 (秒)</label>
              <input class="form-input" type="number" v-model.number="createForm.timeout" min="10" placeholder="120">
            </div>
            <div class="form-group">
              <label class="form-label">持续时长 (秒)</label>
              <input class="form-input" type="number" v-model.number="createForm.duration" min="10" placeholder="120">
            </div>
            <div class="form-group">
              <label class="form-label">测试模式</label>
              <div class="time-range-pills">
                <button class="time-range-pill" :class="{ active: createForm.mode === 'burst' }" @click="createForm.mode = 'burst'">突发</button>
                <button class="time-range-pill" :class="{ active: createForm.mode === 'sustained' }" @click="createForm.mode = 'sustained'">持续</button>
              </div>
            </div>
            </div>
            <div class="form-group">
              <label class="form-label">最大 Token</label>
              <input class="form-input" type="number" v-model.number="createForm.max_tokens" min="1" placeholder="512">
            </div>
          </div>
        </div>
      </div>
      <div class="btn-group" style="margin-top:20px">
        <button class="btn btn-primary" @click="createSchedule" :disabled="createLoading">
          {{ createLoading ? '创建中...' : '创建' }}
        </button>
        <button class="btn btn-ghost" @click="showCreateForm = false">取消</button>
      </div>
    </ModalOverlay>
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { useAppStore } from '../stores/app';
import { getSchedules, getProfiles, createScheduleApi, pauseScheduleApi, resumeScheduleApi, runNowApi, deleteScheduleApi } from '../api/index.js';
import { toast } from '../composables/useToast.js';
import { useRoute } from 'vue-router';
import InlineConfirmDelete from '../components/InlineConfirmDelete.vue';
import ModalOverlay from '../components/ModalOverlay.vue';

const store = useAppStore();
const route = useRoute();

// ---- State ----
const loading = ref(false);
const schedules = ref([]);
const profiles = ref([]);
const search = ref('');
const statusFilter = ref('all');
const deleteCandidate = ref(null);

const statusFilters = [
  { label: '全部', value: 'all' },
  { label: '运行中', value: 'active' },
  { label: '已暂停', value: 'paused' },
  { label: '异常', value: 'error' },
];

// ---- Create form ----
const showCreateForm = ref(false);
const createLoading = ref(false);
const frequencyPreset = ref('300');
const frequencyOptions = [
  { label: '每 5 分钟', value: '300' },
  { label: '每 15 分钟', value: '900' },
  { label: '每 30 分钟', value: '1800' },
  { label: '每 1 小时', value: '3600' },
  { label: '每 6 小时', value: '21600' },
  { label: '自定义...', value: 'custom' },
];

// Combobox state
const profileDropdownOpen = ref(false);
const freqDropdownOpen = ref(false);
const modelDropdownOpen = ref(false);
const profileComboboxRef = ref(null);
const freqComboboxRef = ref(null);
const modelComboboxRef = ref(null);

function handleDocClick(e) {
  if (profileComboboxRef.value && !profileComboboxRef.value.contains(e.target)) profileDropdownOpen.value = false;
  if (freqComboboxRef.value && !freqComboboxRef.value.contains(e.target)) freqDropdownOpen.value = false;
  if (modelComboboxRef.value && !modelComboboxRef.value.contains(e.target)) modelDropdownOpen.value = false;
}

function resetCreateForm() {
  createForm.value = { name: '', profile_name: '', schedule_value: 300, models: [], concurrency: 1, mode: 'burst', max_tokens: 512, timeout: 120, duration: 120 };
  frequencyPreset.value = '300';
  profileDropdownOpen.value = false;
  freqDropdownOpen.value = false;
  modelDropdownOpen.value = false;
  showAdvanced.value = false;
}

const createForm = ref({ name: '', profile_name: '', schedule_value: 300, models: [], concurrency: 1, mode: 'burst', max_tokens: 512, timeout: 120, duration: 120 });

const selectedProfileModels = computed(() => {
  const p = profiles.value.find(p => p.name === createForm.value.profile_name);
  if (!p) return [];
  return p.models || (p.model ? [p.model] : []);
});

const frequencyLabel = computed(() => {
  if (frequencyPreset.value === 'custom') return '自定义';
  const opt = frequencyOptions.find(o => o.value === frequencyPreset.value);
  return opt ? opt.label : '';
});

function selectCreateProfile(name) {
  createForm.value.profile_name = name;
  createForm.value.models = [];
  profileDropdownOpen.value = false;
}

function selectFrequency(value) {
  frequencyPreset.value = value;
  if (value !== 'custom') {
    createForm.value.schedule_value = parseInt(value);
  } else {
    createForm.value.schedule_value = 300;
  }
  freqDropdownOpen.value = false;
}

const modelSearch = ref('');
const showAdvanced = ref(false);

const filteredTaskModels = computed(() => {
  const q = (modelSearch.value || '').toLowerCase();
  const list = selectedProfileModels.value.filter(m => !createForm.value.models.includes(m));
  if (!q) return list;
  return list.filter(m => m.toLowerCase().includes(q));
});

function toggleTaskModel(m) {
  const idx = createForm.value.models.indexOf(m);
  if (idx >= 0) createForm.value.models.splice(idx, 1);
  else createForm.value.models.push(m);
  modelSearch.value = '';
}

function addTaskModel() {
  if (!modelSearch.value.trim()) return;
  const n = modelSearch.value.trim();
  if (!createForm.value.models.includes(n)) createForm.value.models.push(n);
  modelSearch.value = '';
}

// ---- Profile lookup map ----
const profileMap = computed(() => {
  const map = {};
  for (const p of profiles.value) {
    map[p.name] = p;
  }
  return map;
});

// ---- Filtered schedules ----
const filteredSchedules = computed(() => {
  let list = schedules.value;

  // Status filter
  if (statusFilter.value !== 'all') {
    if (statusFilter.value === 'error') {
      list = list.filter(s => {
        const sr = s.last_run_result?.success_rate;
        return sr != null && sr < 80;
      });
    } else {
      list = list.filter(s => s.status === statusFilter.value);
    }
  }

  // Search filter
  if (search.value.trim()) {
    const q = search.value.trim().toLowerCase();
    list = list.filter(s => {
      const siteName = getSiteName(s) || '';
      return (
        (s.name || '').toLowerCase().includes(q) ||
        siteName.toLowerCase().includes(q) ||
        String(s.id).includes(q)
      );
    });
  }

  return list;
});

// ---- Helpers ----
function getSiteName(schedule) {
  const ids = schedule.profile_ids || [];
  return ids.length > 0 ? ids[0] : null;
}

function statusLabel(status) {
  if (status === 'active') return '运行中';
  if (status === 'paused') return '已暂停';
  return status || '-';
}

function formatInterval(seconds) {
  const s = parseInt(seconds) || 0;
  if (s < 60) return s + ' 秒';
  if (s < 3600) return (s / 60) + ' 分钟';
  return (s / 3600) + ' 小时';
}

function formatTime(iso) {
  if (!iso) return '-';
  try {
    const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function getModelFromSchedule(s) {
  const configs = s.configs_json || s.configs || {};
  const models = configs.models || (configs.model ? [configs.model] : []);
  if (!models.length) return '-';
  if (models.length <= 2) return models.join(', ');
  return models.slice(0, 2).join(', ') + ' +' + (models.length - 2);
}

function getConcurrencyFromSchedule(s) {
  const configs = s.configs_json || s.configs || {};
  const levels = configs.concurrency_levels || [];
  return levels.length ? levels.join(', ') : '-';
}

function successRateClass(rate) {
  if (rate == null) return '';
  if (rate >= 95) return 'good';
  if (rate >= 80) return 'warn';
  return 'bad';
}

// ---- Actions ----
function onCreateTask() {
  resetCreateForm();
  showCreateForm.value = true;
}

async function createSchedule() {
  const f = createForm.value;
  if (!f.profile_name) {
    toast('请选择目标站点', 'info');
    return;
  }
  if (!f.name.trim()) {
    toast('请输入任务名称', 'info');
    return;
  }
  if (!f.models.length) {
    toast('请至少选择一个模型', 'info');
    return;
  }

  createLoading.value = true;
  try {
    const payload = {
      name: f.name.trim(),
      profile_ids: [f.profile_name],
      configs_json: {
        concurrency_levels: [parseInt(f.concurrency) || 1],
        mode: f.mode || 'burst',
        max_tokens: parseInt(f.max_tokens) || 512,
        timeout: parseInt(f.timeout) || 120,
        duration: parseInt(f.duration) || 120,
        models: f.models,
      },
      schedule_type: 'interval',
      schedule_value: String(f.schedule_value),
    };
    const res = await createScheduleApi(payload);
    if (res.error) {
      toast(res.error, 'error');
      return;
    }
    toast('定时任务已创建', 'success');
    showCreateForm.value = false;
    resetCreateForm();
    await loadData();
  } catch (e) {
    toast('创建失败: ' + e.message, 'error');
  }
  createLoading.value = false;
}

async function pauseSchedule(id) {
  try {
    await pauseScheduleApi(id);
    toast('已暂停', 'info');
    await loadData();
  } catch (e) {
    toast('操作失败: ' + e.message, 'error');
  }
}

async function resumeSchedule(id) {
  try {
    await resumeScheduleApi(id);
    toast('已恢复', 'success');
    await loadData();
  } catch (e) {
    toast('操作失败: ' + e.message, 'error');
  }
}

async function runNow(id) {
  try {
    await runNowApi(id);
    toast('已触发执行', 'info');
  } catch (e) {
    toast('触发失败: ' + e.message, 'error');
  }
}

async function confirmDelete(id) {
  try {
    await deleteScheduleApi(id);
    toast('已删除', 'info');
    deleteCandidate.value = null;
    await loadData();
  } catch (e) {
    toast('删除失败: ' + e.message, 'error');
  }
}

// ---- Data loading ----
async function loadData() {
  loading.value = true;
  try {
    const [schedData, profData] = await Promise.all([
      getSchedules(),
      getProfiles(),
    ]);
    schedules.value = schedData.schedules || [];
    profiles.value = Array.isArray(profData) ? profData : (profData.profiles || []);
  } catch (e) {
    toast('加载定时任务失败: ' + e.message, 'error');
  }
  loading.value = false;
}

// ---- Lifecycle ----
watch(() => route.path, (val) => {
  if (val === '/tasks') loadData();
}, { immediate: true });

store.refreshFn = loadData;
onMounted(() => { document.addEventListener('mousedown', handleDocClick); });
onUnmounted(() => { store.refreshFn = null; document.removeEventListener('mousedown', handleDocClick); });
</script>

<style scoped>
.sites-toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
  flex-wrap: wrap;
}

.sites-toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.sites-count {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

/* ---- Site Link ---- */
.site-link {
  color: var(--accent);
  font-weight: 600;
  text-decoration: none;
  transition: var(--transition);
  max-width: 140px;
  display: inline-block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.site-link:hover {
  color: var(--accent-hover);
  text-decoration: underline;
}

.text-tertiary {
  color: var(--text-tertiary);
}

/* ---- Schedule ID ---- */
.schedule-id {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 400;
  margin-left: 4px;
}

/* ---- Status Badge ---- */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 12px;
}

.status-badge.active {
  color: var(--success);
  background: color-mix(in srgb, var(--success) 10%, transparent);
}

.status-badge.paused {
  color: var(--text-tertiary);
  background: var(--bg-secondary);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--success);
  animation: pulse-dot 2s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ---- Model Cell ---- */
.model-cell {
  font-family: var(--font-mono);
  font-size: 12px;
}

/* ---- Last Result ---- */
.last-result {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.success-rate {
  font-weight: 700;
  font-size: 13px;
}

.success-rate.good { color: var(--success); }
.success-rate.warn { color: var(--warning); }
.success-rate.bad { color: var(--danger); }

.last-time {
  font-size: 11px;
  color: var(--text-tertiary);
}

.no-result {
  color: var(--text-tertiary);
}

/* ---- Next Run ---- */
.next-run {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

/* ---- Create Modal ---- */
.create-modal-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.frequency-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.frequency-row .form-input:first-child {
  flex: 1;
}

.form-hint {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

/* ---- Advanced Section ---- */
.advanced-section {
  margin-top: 16px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius);
  overflow: hidden;
}

.advanced-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 14px;
  background: var(--bg);
  border: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  transition: background 0.15s;
}

.advanced-toggle:hover {
  background: var(--bg-secondary);
}

.advanced-chevron {
  margin-left: auto;
  transition: transform 0.2s;
}

.advanced-chevron.open {
  transform: rotate(180deg);
}

.advanced-body {
  padding: 14px;
  border-top: 1px solid var(--border-subtle);
}

@media (max-width: 768px) {
  .create-modal-grid {
    grid-template-columns: 1fr;
  }
}
</style>
