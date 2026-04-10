<template>
  <div class="schedule-indicator" v-if="activeSchedules.length > 0" ref="indicatorRef">
    <button class="indicator-pill" @click.stop="togglePanel" :class="{ open: panelOpen }">
      <span class="indicator-dot"></span>
      <span class="indicator-text">{{ activeSchedules.length }} 运行中</span>
    </button>
    <div class="indicator-panel" v-show="panelOpen" @click.stop>
      <div class="panel-header">活跃定时任务</div>
      <div class="panel-list">
        <div
          v-for="s in activeSchedules"
          :key="s.id"
          class="panel-item"
          :class="{ 'has-error': hasError(s) }"
        >
          <div class="item-main">
            <span class="item-name">{{ s.name }}</span>
            <span class="item-site">{{ getSiteName(s) }}</span>
          </div>
          <div class="item-meta">
            <span class="item-freq">{{ formatInterval(s.schedule_value) }}</span>
            <span
              v-if="s.last_run_result"
              class="item-rate"
              :class="successRateClass(s.last_run_result.success_rate)"
            >{{ s.last_run_result.success_rate }}%</span>
            <span v-else class="item-rate no-data">-</span>
          </div>
        </div>
      </div>
      <router-link to="/tasks" class="panel-footer" @click="panelOpen = false">
        查看全部定时任务
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
      </router-link>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { getSchedules, getProfiles } from '../api/index.js';

const panelOpen = ref(false);
const schedules = ref([]);
const profiles = ref([]);
const indicatorRef = ref(null);

const activeSchedules = computed(() =>
  schedules.value.filter(s => s.status === 'active')
);

function togglePanel() {
  panelOpen.value = !panelOpen.value;
}

function getSiteName(s) {
  const pids = s.profile_ids || [];
  if (!pids.length) return '-';
  const p = profiles.value.find(pr => pr.name === pids[0]);
  return p ? (p.display_name || p.name) : pids[0];
}

function hasError(s) {
  if (!s.last_run_result) return false;
  return s.last_run_result.success_rate != null && s.last_run_result.success_rate < 80;
}

function formatInterval(seconds) {
  const s = parseInt(seconds) || 0;
  if (s < 60) return s + 's';
  if (s < 3600) return (s / 60) + 'min';
  return (s / 3600) + 'h';
}

function successRateClass(rate) {
  if (rate == null) return '';
  if (rate >= 95) return 'good';
  if (rate >= 80) return 'warn';
  return 'bad';
}

let timer = null;
let clickOutsideHandler = null;

async function fetchData() {
  try {
    const [schedData, profData] = await Promise.all([
      getSchedules(),
      getProfiles(),
    ]);
    schedules.value = schedData.schedules || [];
    profiles.value = profData.profiles || profData || [];
  } catch {
    // silently ignore
  }
}

onMounted(async () => {
  await fetchData();
  timer = setInterval(fetchData, 30000);

  clickOutsideHandler = (e) => {
    if (indicatorRef.value && !indicatorRef.value.contains(e.target)) {
      panelOpen.value = false;
    }
  };
  document.addEventListener('click', clickOutsideHandler);
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
  if (clickOutsideHandler) document.removeEventListener('click', clickOutsideHandler);
});
</script>

<style scoped>
.schedule-indicator {
  position: relative;
}

.indicator-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 20px;
  border: 1px solid var(--border);
  background: var(--surface-raised);
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  transition: var(--transition);
  line-height: 1;
}

.indicator-pill:hover {
  border-color: var(--success);
  background: var(--success-light);
  color: var(--success);
}

.indicator-pill.open {
  border-color: var(--success);
  background: var(--success-light);
  color: var(--success);
}

.indicator-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--success);
  animation: pulse-glow 2s ease-in-out infinite;
  flex-shrink: 0;
}

@keyframes pulse-glow {
  0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(45,139,85,0.4); }
  50% { opacity: 0.6; box-shadow: 0 0 0 4px rgba(45,139,85,0); }
}

.indicator-text {
  white-space: nowrap;
}

.indicator-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 340px;
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  z-index: 100;
  overflow: hidden;
}

.panel-header {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 12px 16px 8px;
}

.panel-list {
  max-height: 280px;
  overflow-y: auto;
}

.panel-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-top: 1px solid var(--border-subtle);
  transition: background 0.15s;
}

.panel-item:hover {
  background: var(--bg);
}

.panel-item.has-error {
  background: var(--danger-light);
}

.panel-item.has-error:hover {
  background: color-mix(in srgb, var(--danger-light) 80%, transparent);
}

.item-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.item-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-site {
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  flex-shrink: 0;
  margin-left: 12px;
}

.item-freq {
  font-size: 11px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

.item-rate {
  font-size: 13px;
  font-weight: 700;
}

.item-rate.good { color: var(--success); }
.item-rate.warn { color: var(--warning); }
.item-rate.bad { color: var(--danger); }
.item-rate.no-data { color: var(--text-tertiary); font-weight: 400; }

.panel-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
  text-decoration: none;
  transition: var(--transition);
}

.panel-footer:hover {
  background: var(--accent-light);
}
</style>
