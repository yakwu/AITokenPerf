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

  <!-- 右下角完成通知 -->
  <Teleport to="body">
    <div class="done-notifications" v-if="doneNotifications.length > 0">
      <div
        v-for="n in doneNotifications"
        :key="n.id"
        class="done-notify"
        @click="onNotifyClick(n)"
      >
        <div class="done-notify-icon">✓</div>
        <div class="done-notify-body">
          <div class="done-notify-title">{{ n.title }}</div>
          <div class="done-notify-sub">{{ n.subtitle }}</div>
        </div>
        <button class="done-notify-close" @click.stop="dismissNotify(n.id)">×</button>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { getRunningTasks } from '../api/index.js';

const router = useRouter();

const panelOpen = ref(false);
const runningTasks = ref([]);
const indicatorRef = ref(null);

// 完成通知
const doneNotifications = ref([]);
let prevTaskIds = new Set();
let prevTaskMeta = new Map(); // task_id -> { model, profile_name, elapsed }
let notifyIdCounter = 0;
const MAX_NOTIFICATIONS = 5;

function togglePanel() {
  panelOpen.value = !panelOpen.value;
}

function progressPct(t) {
  if (!t.total || t.total === 0) return 0;
  return Math.min(100, Math.round(t.done / t.total * 100));
}

function addNotification(title, subtitle, profileName) {
  notifyIdCounter++;
  doneNotifications.value.push({
    id: notifyIdCounter,
    title,
    subtitle,
    profileName,
    time: Date.now(),
  });
  // 超过 5 条，移除最旧的
  while (doneNotifications.value.length > MAX_NOTIFICATIONS) {
    doneNotifications.value.shift();
  }
}

function dismissNotify(id) {
  doneNotifications.value = doneNotifications.value.filter(n => n.id !== id);
}

function onNotifyClick(n) {
  if (n.profileName) {
    router.push(`/sites/${encodeURIComponent(n.profileName)}?tab=trends`);
  }
  dismissNotify(n.id);
}

function detectCompleted(currentTasks) {
  const currentIds = new Set(currentTasks.map(t => t.task_id));

  // 找出消失的任务（上次在运行，本次不在了 → 已完成）
  const completedIds = [];
  for (const id of prevTaskIds) {
    if (!currentIds.has(id)) {
      completedIds.push(id);
    }
  }

  if (completedIds.length === 0) {
    // 更新 meta
    updateMeta(currentTasks);
    prevTaskIds = currentIds;
    return;
  }

  // 按 profile_name 聚合（定时任务的多个模型会聚合成一条通知）
  const grouped = {};
  for (const id of completedIds) {
    const meta = prevTaskMeta.get(id);
    if (!meta) continue;
    const key = meta.profile_name || id;
    if (!grouped[key]) {
      grouped[key] = { profile_name: meta.profile_name, models: [], elapsed: 0 };
    }
    grouped[key].models.push(meta.model || '?');
    grouped[key].elapsed = Math.max(grouped[key].elapsed, meta.elapsed || 0);
  }

  for (const [, g] of Object.entries(grouped)) {
    const modelCount = g.models.length;
    const title = modelCount > 1
      ? `${g.profile_name || '测试'} 完成 · ${modelCount} 个模型`
      : `${g.profile_name || '测试'} · ${g.models[0]} 完成`;
    const subtitle = `用时 ${g.elapsed}s · 点击查看`;
    addNotification(title, subtitle, g.profile_name);
  }

  // 清理已完成的 meta
  for (const id of completedIds) {
    prevTaskMeta.delete(id);
  }

  updateMeta(currentTasks);
  prevTaskIds = currentIds;
}

function updateMeta(tasks) {
  for (const t of tasks) {
    prevTaskMeta.set(t.task_id, {
      model: t.model || '-',
      profile_name: t.profile_name || '',
      elapsed: t.elapsed || 0,
    });
  }
}

let timer = null;
let clickOutsideHandler = null;

async function fetchData() {
  try {
    const data = await getRunningTasks();
    const tasks = data.tasks || [];
    detectCompleted(tasks);
    runningTasks.value = tasks;
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

<style>
/* 右下角完成通知（非 scoped，Teleport 到 body） */
.done-notifications {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 2000;
  display: flex;
  flex-direction: column-reverse;
  gap: 8px;
  max-width: 340px;
}

.done-notify {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  background: var(--surface-raised, #fff);
  border: 1px solid var(--border, #e0e0e0);
  border-left: 3px solid var(--success, #2D8B55);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  cursor: pointer;
  transition: transform 0.15s, opacity 0.15s;
  animation: notifySlideIn 0.25s ease;
}

.done-notify:hover {
  transform: translateX(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.16);
}

@keyframes notifySlideIn {
  from { opacity: 0; transform: translateX(40px); }
  to { opacity: 1; transform: translateX(0); }
}

.done-notify-icon {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--success, #2D8B55);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.done-notify-body {
  flex: 1;
  min-width: 0;
}

.done-notify-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #111);
  line-height: 1.3;
}

.done-notify-sub {
  font-size: 11px;
  color: var(--text-tertiary, #999);
  margin-top: 2px;
}

.done-notify-close {
  background: none;
  border: none;
  font-size: 16px;
  color: var(--text-tertiary, #999);
  cursor: pointer;
  padding: 0 2px;
  line-height: 1;
  flex-shrink: 0;
  transition: color 0.15s;
}

.done-notify-close:hover {
  color: var(--text-primary, #111);
}
</style>
