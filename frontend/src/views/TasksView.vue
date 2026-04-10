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
      <p style="color:var(--text-tertiary);font-size:13px">{{ schedules.length ? '尝试调整筛选条件' : '请进入对应站点详情页创建定时任务' }}</p>
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
                  :to="`/sites/${encodeURIComponent(getSiteName(s))}`"
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
  </section>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue';
import { useAppStore } from '../stores/app';
import { getSchedules, getProfiles, pauseScheduleApi, resumeScheduleApi, runNowApi, deleteScheduleApi } from '../api/index.js';
import { toast } from '../composables/useToast.js';
import { useRoute } from 'vue-router';
import InlineConfirmDelete from '../components/InlineConfirmDelete.vue';

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

// ---- Actions ----
function onCreateTask() {
  toast('请进入对应站点详情页创建定时任务', 'info');
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
onUnmounted(() => { store.refreshFn = null; });
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
</style>
