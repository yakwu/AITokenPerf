<template>
  <div class="schedule-indicator" v-if="runningTasks.length > 0" ref="indicatorRef">
    <button class="indicator-pill" @click.stop="togglePanel" :class="{ open: panelOpen }">
      <span class="indicator-dot"></span>
      <span class="indicator-text">{{ runningTasks.length }} 执行中</span>
    </button>
    <div class="indicator-panel" v-show="panelOpen" @click.stop>
      <div class="panel-header">正在执行的任务</div>
      <div class="panel-list">
        <div
          v-for="t in runningTasks"
          :key="t.task_id"
          class="panel-item"
        >
          <div class="item-main">
            <span class="item-name">{{ t.model || '-' }}</span>
            <span class="item-site">{{ t.profile_name || '-' }}</span>
          </div>
          <div class="item-meta">
            <div class="item-progress-bar">
              <div class="item-progress-fill" :style="{ width: progressPct(t) + '%' }"></div>
            </div>
            <span class="item-progress-text">{{ t.done }}/{{ t.total }} · {{ t.elapsed }}s</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import { getRunningTasks } from '../api/index.js';

const panelOpen = ref(false);
const runningTasks = ref([]);
const indicatorRef = ref(null);

function togglePanel() {
  panelOpen.value = !panelOpen.value;
}

function progressPct(t) {
  if (!t.total || t.total === 0) return 0;
  return Math.min(100, Math.round(t.done / t.total * 100));
}

let timer = null;
let clickOutsideHandler = null;

async function fetchData() {
  try {
    const data = await getRunningTasks();
    runningTasks.value = data.tasks || [];
  } catch {
    // silently ignore
  }
}

onMounted(async () => {
  await fetchData();
  timer = setInterval(fetchData, 5000);

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
  border-color: var(--accent);
  background: var(--accent-light);
  color: var(--accent);
}

.indicator-pill.open {
  border-color: var(--accent);
  background: var(--accent-light);
  color: var(--accent);
}

.indicator-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent);
  animation: pulse-glow 2s ease-in-out infinite;
  flex-shrink: 0;
}

@keyframes pulse-glow {
  0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(232,93,38,0.4); }
  50% { opacity: 0.6; box-shadow: 0 0 0 4px rgba(232,93,38,0); }
}

.indicator-text {
  white-space: nowrap;
}

.indicator-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 320px;
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  z-index: 1000;
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
  font-family: var(--font-mono);
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
  gap: 4px;
  flex-shrink: 0;
  margin-left: 12px;
  min-width: 80px;
}

.item-progress-bar {
  width: 80px;
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
}

.item-progress-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
  transition: width 0.3s;
}

.item-progress-text {
  font-size: 10px;
  font-family: var(--font-mono);
  color: var(--text-tertiary);
  white-space: nowrap;
}
</style>
