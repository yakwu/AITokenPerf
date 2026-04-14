<template>
  <div class="notification-center" ref="containerRef">
    <button class="notification-bell" @click.stop="togglePanel" :class="{ 'has-unread': unreadCount() > 0 }">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>
      <span v-if="unreadCount() > 0" class="notification-badge">{{ unreadCount() > 9 ? '9+' : unreadCount() }}</span>
    </button>
    <div class="notification-panel" v-show="panelOpen" @click.stop>
      <div class="notification-panel-header">
        <span class="notification-panel-title">消息中心</span>
        <button v-if="notifications.length" class="btn btn-ghost btn-sm" @click="clearAll" style="font-size:11px;padding:2px 8px">清空</button>
      </div>
      <div class="notification-panel-list">
        <div v-if="!notifications.length" class="notification-empty">暂无消息</div>
        <div
          v-for="n in reversedNotifications"
          :key="n.id"
          class="notification-item"
          :class="{ unread: !n.read }"
          @click="onItemClick(n)"
        >
          <div class="notification-item-icon" :class="{ 'has-fail': n.hasFail }">
            <svg v-if="!n.hasFail" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          </div>
          <div class="notification-item-content">
            <div class="notification-item-title">{{ n.title }}</div>
            <div class="notification-item-models">{{ n.modelsText }}</div>
            <div class="notification-item-meta">{{ n.subtitle }} · {{ timeAgo(n.time) }}</div>
          </div>
          <button class="notification-item-dismiss" @click.stop="dismiss(n.id)">&times;</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { useNotifications } from '../composables/useNotifications.js';

const router = useRouter();
const { notifications, dismiss, markAllRead, clearAll, unreadCount } = useNotifications();

const panelOpen = ref(false);
const containerRef = ref(null);

const reversedNotifications = computed(() => [...notifications.value].reverse());

function togglePanel() {
  panelOpen.value = !panelOpen.value;
  if (panelOpen.value) {
    markAllRead();
  }
}

function onItemClick(n) {
  if (n.profileName) {
    router.push(`/sites/${encodeURIComponent(n.profileName)}?tab=trends`);
  }
  panelOpen.value = false;
}

function timeAgo(ts) {
  const diff = Math.floor((Date.now() - ts) / 1000);
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return `${Math.floor(diff / 86400)} 天前`;
}

let clickOutsideHandler = null;
onMounted(() => {
  clickOutsideHandler = (e) => {
    if (containerRef.value && !containerRef.value.contains(e.target)) {
      panelOpen.value = false;
    }
  };
  document.addEventListener('click', clickOutsideHandler);
});
onUnmounted(() => {
  if (clickOutsideHandler) document.removeEventListener('click', clickOutsideHandler);
});
</script>

<style scoped>
.notification-center {
  position: relative;
}

.notification-bell {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: none;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: var(--transition);
}

.notification-bell:hover {
  color: var(--text-primary);
  background: var(--bg);
}

.notification-bell.has-unread {
  color: var(--text-secondary);
}

.notification-badge {
  position: absolute;
  top: 2px;
  right: 2px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: var(--danger);
  color: white;
  font-size: 10px;
  font-weight: 700;
  line-height: 16px;
  text-align: center;
}

.notification-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 340px;
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  z-index: 1000;
  overflow: hidden;
}

.notification-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.notification-panel-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.notification-panel-list {
  max-height: 360px;
  overflow-y: auto;
}

.notification-empty {
  padding: 32px 16px;
  text-align: center;
  font-size: 13px;
  color: var(--text-tertiary);
}

.notification-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 16px;
  cursor: pointer;
  transition: background 0.1s;
  border-bottom: 1px solid var(--border-subtle);
}

.notification-item:last-child {
  border-bottom: none;
}

.notification-item:hover {
  background: var(--bg);
}

.notification-item.unread {
  background: var(--accent-light);
}

.notification-item.unread:hover {
  background: color-mix(in srgb, var(--accent-light) 80%, var(--bg));
}

.notification-item-icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
  background: var(--success-light, #e6f4ec);
  color: var(--success, #2D8B55);
}

.notification-item-icon.has-fail {
  background: var(--danger-light, #fef0f0);
  color: var(--danger, #D63B3B);
}

.notification-item-content {
  flex: 1;
  min-width: 0;
}

.notification-item-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.notification-item-models {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 1px;
}

.notification-item-meta {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 1px;
}

.notification-item-dismiss {
  background: none;
  border: none;
  font-size: 14px;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: 2px 4px;
  line-height: 1;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.1s, color 0.1s;
}

.notification-item:hover .notification-item-dismiss {
  opacity: 1;
}

.notification-item-dismiss:hover {
  color: var(--text-primary);
}
</style>
