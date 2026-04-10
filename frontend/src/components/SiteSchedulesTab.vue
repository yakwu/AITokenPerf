<template>
  <div class="site-schedules-tab">
    <!-- Header -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">定时任务</div>
        <button class="btn btn-primary btn-sm" @click="toggleCreateForm">
          {{ showCreateForm ? '取消' : '新建任务' }}
        </button>
      </div>

      <!-- Create Form (inline) -->
      <div v-show="showCreateForm" class="create-form">
        <div class="form-grid">
          <div class="form-group">
            <label class="form-label">任务名称</label>
            <input class="form-input" v-model="createForm.name" placeholder="例如：快速巡检">
          </div>
          <div class="form-group">
            <label class="form-label">执行频率</label>
            <div class="frequency-row">
              <select class="form-input" v-model="frequencyPreset" @change="onFrequencyPresetChange">
                <option v-for="opt in frequencyOptions" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
              <input
                v-if="frequencyPreset === 'custom'"
                class="form-input"
                type="number"
                v-model.number="createForm.schedule_value"
                min="60"
                placeholder="秒"
                style="width:100px"
              >
            </div>
            <div class="form-hint">每 {{ formatInterval(createForm.schedule_value) }} 执行一次</div>
          </div>
          <div class="form-group">
            <label class="form-label">选择模型</label>
            <select class="form-input" v-model="createForm.model">
              <option v-for="m in profileModels" :key="m" :value="m">{{ m }}</option>
            </select>
            <div class="form-hint" v-if="!profileModels.length">站点未配置模型，请先在配置 Tab 中添加</div>
          </div>
        </div>
        <div class="create-form-notice">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
          并发、模式、超时等参数继承自站点测试配置
        </div>
        <div class="btn-group" style="margin-top:12px">
          <button class="btn btn-primary" @click="createSchedule" :disabled="createLoading">
            <span v-if="!createLoading">创建</span>
            <span v-else>创建中...</span>
          </button>
          <button class="btn btn-ghost" @click="showCreateForm = false">取消</button>
        </div>
      </div>
    </div>

    <!-- Schedule List Table -->
    <div class="card schedule-list-card">
      <div v-if="loading && siteSchedules.length === 0" class="table-empty">加载中...</div>
      <div v-else-if="siteSchedules.length === 0" class="table-empty">
        <template v-if="showCreateForm">请填写上方表单创建定时任务</template>
        <template v-else>
          暂无定时任务，点击「新建任务」开始
        </template>
      </div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
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
            <tr v-for="s in siteSchedules" :key="s.id">
              <td style="font-weight:600">
                {{ s.name }}
                <span class="schedule-id">#{{ s.id }}</span>
              </td>
              <td>
                <span class="status-badge" :class="s.status">
                  <span v-if="s.status === 'active'" class="status-dot"></span>
                  {{ s.status === 'active' ? '运行中' : s.status === 'paused' ? '已暂停' : s.status }}
                </span>
              </td>
              <td>{{ formatInterval(s.schedule_value) }}</td>
              <td class="model-cell">{{ getModelFromSchedule(s) }}</td>
              <td>{{ getConcurrencyFromSchedule(s) }}</td>
              <td>
                <div v-if="s.last_run_result" class="last-result">
                  <span
                    class="success-rate"
                    :class="successRateClass(s.last_run_result.success_rate)"
                  >{{ s.last_run_result.success_rate }}%</span>
                  <span class="last-time" v-if="s.last_run_at">{{ formatTime(s.last_run_at) }}</span>
                </div>
                <span v-else class="no-result">-</span>
              </td>
              <td class="next-run">{{ formatTime(s.next_run_at) }}</td>
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
                <button class="btn btn-ghost btn-sm" @click="startEdit(s)" title="编辑" style="color:var(--accent)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 114 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>
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

    <!-- Edit Modal -->
    <ModalOverlay :show="showEditForm" title="编辑定时任务" max-width="560px" @close="showEditForm = false">
      <div class="form-grid">
        <div class="form-group full">
          <label class="form-label">任务名称</label>
          <input class="form-input" v-model="editForm.name">
        </div>
        <div class="form-group">
          <label class="form-label">执行频率</label>
          <div class="frequency-row">
            <select class="form-input" v-model="editFrequencyPreset" @change="onEditFrequencyPresetChange">
              <option v-for="opt in frequencyOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
            <input
              v-if="editFrequencyPreset === 'custom'"
              class="form-input"
              type="number"
              v-model.number="editForm.schedule_value"
              min="60"
              placeholder="秒"
              style="width:100px"
            >
          </div>
          <div class="form-hint">每 {{ formatInterval(editForm.schedule_value) }} 执行一次</div>
        </div>
        <div class="form-group">
          <label class="form-label">选择模型</label>
          <select class="form-input" v-model="editForm.model">
            <option v-for="m in profileModels" :key="m" :value="m">{{ m }}</option>
          </select>
        </div>
      </div>
      <div class="btn-group" style="margin-top:20px">
        <button class="btn btn-primary" @click="saveEdit" :disabled="editLoading">
          <span v-if="!editLoading">保存</span>
          <span v-else>保存中...</span>
        </button>
        <button class="btn btn-ghost" @click="showEditForm = false">取消</button>
      </div>
    </ModalOverlay>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue';
import {
  getSchedules,
  createScheduleApi,
  updateScheduleApi,
  deleteScheduleApi,
  pauseScheduleApi,
  resumeScheduleApi,
  runNowApi,
} from '../api/index.js';
import { toast } from '../composables/useToast.js';
import InlineConfirmDelete from './InlineConfirmDelete.vue';
import ModalOverlay from './ModalOverlay.vue';

const props = defineProps({
  profile: { type: Object, required: true },
});

// ---- State ----
const loading = ref(false);
const schedules = ref([]);
const showCreateForm = ref(false);
const createLoading = ref(false);
const deleteCandidate = ref(null);
const showEditForm = ref(false);
const editLoading = ref(false);

// ---- Profile data ----
const profileModels = computed(() => {
  if (!props.profile) return [];
  return props.profile.models || (props.profile.model ? [props.profile.model] : []);
});

// ---- Frequency options ----
const frequencyOptions = [
  { label: '每 5 分钟', value: '300' },
  { label: '每 15 分钟', value: '900' },
  { label: '每 30 分钟', value: '1800' },
  { label: '每 1 小时', value: '3600' },
  { label: '每 6 小时', value: '21600' },
  { label: '自定义...', value: 'custom' },
];

// ---- Create form ----
const frequencyPreset = ref('300');

function defaultCreateForm() {
  return {
    name: '',
    schedule_value: 300,
    model: profileModels.value[0] || '',
  };
}

const createForm = ref(defaultCreateForm());

function onFrequencyPresetChange() {
  if (frequencyPreset.value !== 'custom') {
    createForm.value.schedule_value = parseInt(frequencyPreset.value);
  } else {
    createForm.value.schedule_value = 300;
  }
}

function toggleCreateForm() {
  showCreateForm.value = !showCreateForm.value;
  if (showCreateForm.value) {
    createForm.value = defaultCreateForm();
    frequencyPreset.value = '300';
  }
}

// ---- Edit form ----
const editFrequencyPreset = ref('300');

const editForm = ref({
  id: null,
  name: '',
  schedule_value: 300,
  model: '',
});

function onEditFrequencyPresetChange() {
  if (editFrequencyPreset.value !== 'custom') {
    editForm.value.schedule_value = parseInt(editFrequencyPreset.value);
  } else {
    editForm.value.schedule_value = 300;
  }
}

function startEdit(s) {
  const configs = s.configs_json || s.configs || {};
  editForm.value = {
    id: s.id,
    name: s.name || '',
    schedule_value: parseInt(s.schedule_value) || 300,
    model: configs.model || '',
  };
  // Detect preset or custom
  const sv = String(s.schedule_value);
  const match = frequencyOptions.find(o => o.value === sv);
  editFrequencyPreset.value = match ? match.value : 'custom';
  showEditForm.value = true;
}

// ---- Computed: site schedules filtered by profile name ----
const siteSchedules = computed(() => {
  const name = props.profile?.name;
  if (!name) return [];
  return schedules.value.filter(s =>
    (s.profile_ids || []).includes(name)
  );
});

// ---- Helpers ----
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
  return configs.model || '-';
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

// ---- API calls ----
async function refreshSchedules() {
  loading.value = true;
  try {
    const data = await getSchedules();
    schedules.value = data.schedules || [];
  } catch (e) {
    toast('加载定时任务失败: ' + e.message, 'error');
  }
  loading.value = false;
}

async function createSchedule() {
  const f = createForm.value;
  if (!f.name.trim()) {
    toast('请输入任务名称', 'info');
    return;
  }
  if (!f.model) {
    toast('请选择模型', 'info');
    return;
  }

  createLoading.value = true;
  try {
    const payload = {
      name: f.name.trim(),
      profile_ids: [props.profile.name],
      configs_json: {
        concurrency_levels: [10],
        mode: 'burst',
        max_tokens: 512,
        timeout: 120,
        duration: 120,
        model: f.model,
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
    createForm.value = defaultCreateForm();
    frequencyPreset.value = '300';
    await refreshSchedules();
  } catch (e) {
    toast('创建失败: ' + e.message, 'error');
  }
  createLoading.value = false;
}

async function saveEdit() {
  const f = editForm.value;
  if (!f.name.trim()) {
    toast('请输入任务名称', 'info');
    return;
  }

  editLoading.value = true;
  try {
    // Fetch original schedule to preserve configs
    const original = schedules.value.find(s => s.id === f.id);
    const configs = { ...(original?.configs_json || original?.configs || {}) };
    configs.model = f.model;

    const res = await updateScheduleApi(f.id, {
      name: f.name.trim(),
      profile_ids: original?.profile_ids || [props.profile.name],
      configs_json: configs,
      schedule_type: 'interval',
      schedule_value: String(f.schedule_value),
    });
    if (res.error) {
      toast(res.error, 'error');
      return;
    }
    toast('已更新', 'success');
    showEditForm.value = false;
    await refreshSchedules();
  } catch (e) {
    toast('更新失败: ' + e.message, 'error');
  }
  editLoading.value = false;
}

async function pauseSchedule(id) {
  try {
    await pauseScheduleApi(id);
    toast('已暂停', 'info');
    await refreshSchedules();
  } catch (e) {
    toast('操作失败: ' + e.message, 'error');
  }
}

async function resumeSchedule(id) {
  try {
    await resumeScheduleApi(id);
    toast('已恢复', 'success');
    await refreshSchedules();
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
    await refreshSchedules();
  } catch (e) {
    toast('删除失败: ' + e.message, 'error');
  }
}

// ---- Init ----
onMounted(() => {
  refreshSchedules();
});
</script>

<style scoped>
.site-schedules-tab .card {
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 24px;
  box-shadow: var(--shadow-sm);
  margin-bottom: 20px;
}

.site-schedules-tab .card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0;
}

.site-schedules-tab .card-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

/* ---- Create Form ---- */
.create-form {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
}

.create-form .form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px;
}

.create-form .form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.frequency-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.frequency-row .form-input:first-child {
  flex: 1;
}

.create-form-notice {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 8px 12px;
  background: var(--bg);
  border-radius: var(--radius);
  border: 1px solid var(--border-subtle);
}

.form-hint {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

/* ---- Schedule List Table ---- */
.schedule-list-card {
  padding: 0;
  overflow-x: auto;
}

.table-empty {
  text-align: center;
  color: var(--text-tertiary);
  padding: 40px 20px;
  font-size: 14px;
}

.table-wrap table {
  width: 100%;
  border-collapse: collapse;
}

.table-wrap th {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.table-wrap td {
  padding: 12px 16px;
  font-size: 13px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
  vertical-align: middle;
}

.table-wrap tr:last-child td {
  border-bottom: none;
}

.table-wrap tr:hover td {
  background: var(--bg-secondary);
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

/* ---- Edit Form (Modal) ---- */
.site-schedules-tab .form-grid .full {
  grid-column: 1 / -1;
}

/* ---- Responsive ---- */
@media (max-width: 768px) {
  .create-form .form-grid {
    grid-template-columns: 1fr;
  }

  .frequency-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
