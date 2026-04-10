<template>
  <!-- Header -->
  <header class="header">
    <div class="header-left">
      <div class="logo">AIToken<span>Perf</span></div>
      <div class="status-badge" :class="store.status" v-if="store.user">
        <div class="status-dot"></div>
        <span>{{ store.statusLabels[store.status] || store.status }}</span>
      </div>
    </div>
    <div class="header-right" v-if="store.user">
      <button v-if="store.refreshFn" class="btn btn-ghost btn-sm header-refresh" @click="store.refreshFn()" title="刷新"><i class="ph ph-arrows-clockwise"></i></button>
      <ScheduleIndicator />
      <div class="user-menu" v-click-outside="() => userMenuOpen = false">
        <button class="user-avatar" @click="userMenuOpen = !userMenuOpen">
          {{ (store.user?.email || '?')[0].toUpperCase() }}
        </button>
        <div class="user-dropdown" v-show="userMenuOpen">
          <div class="user-dropdown-email">{{ store.user?.email }}</div>
          <div class="user-dropdown-role" style="font-size:11px;color:var(--text-tertiary);margin-bottom:8px">
            {{ store.user?.role === 'admin' ? '管理员' : '用户' }}
          </div>
          <button class="user-dropdown-item" @click="store.switchTab('settings'); userMenuOpen = false">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.32 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
            个人资料
          </button>
          <button class="user-dropdown-item" v-if="store.user?.role === 'admin'" @click="store.switchTab('admin-users'); userMenuOpen = false">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>
            用户管理
          </button>
          <button class="user-dropdown-item" v-if="store.user?.role === 'admin'" @click="store.switchTab('models'); userMenuOpen = false">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
            模型管理
          </button>
          <div class="user-dropdown-divider"></div>
          <button class="user-dropdown-item user-dropdown-logout" @click="store.logout(); userMenuOpen = false">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
            退出登录
          </button>
        </div>
      </div>
    </div>
  </header>

  <!-- Tabs -->
  <nav class="tab-bar" v-if="store.user">
    <router-link v-for="tab in tabs" :key="tab.path" :to="tab.path" class="tab-btn" :class="{ active: tab.activeMatch ? tab.activeMatch($route.path) : $route.path === tab.path }" @click="userMenuOpen = false">{{ tab.name }}</router-link>
  </nav>

  <!-- Router View -->
  <main class="main">
    <router-view v-if="store.user || $route.path === '/auth'" />
    <router-view v-else-if="!store.user" />
  </main>

  <!-- Detail Overlay -->
  <div id="detailOverlay" class="compare-overlay" @click.self="closeDetailOverlay">
    <div class="compare-modal">
      <div class="compare-modal-header"><h2>结果详情</h2></div>
      <div id="detailOverlayContent" class="compare-modal-body"></div>
    </div>
  </div>

  <!-- Compare Overlay (HistoryView uses this) -->
  <div id="compareOverlay" class="compare-overlay" @click.self="closeCompareOverlay">
    <div class="compare-modal">
      <div class="compare-modal-header"><h2>结果对比</h2></div>
      <div id="compareContent" class="compare-modal-body"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue';
import { useAppStore } from './stores/app';
import { useRouter, useRoute } from 'vue-router';
import ScheduleIndicator from './components/ScheduleIndicator.vue';

const store = useAppStore();

const tabs = [
  { name: '概览', path: '/' },
  { name: '目标站点', path: '/sites', activeMatch: (p) => p.startsWith('/sites') },
  { name: '历史与对比', path: '/history' },
  { name: '定时任务', path: '/tasks' },
];

// Global detail overlay
function closeDetailOverlay() {
  document.getElementById('detailOverlay')?.classList.remove('open');
}
function closeCompareOverlay() {
  document.getElementById('compareOverlay')?.classList.remove('open');
}
// Expose for child components
window.showDetailOverlay = function(detailHtml) {
  const content = document.getElementById('detailOverlayContent');
  if (content) {
    content.innerHTML = detailHtml;
    document.getElementById('detailOverlay')?.classList.add('open');
  }
};
const userMenuOpen = ref(false);
const router = useRouter();
const route = useRoute();

// 未登录时跳转到 /auth
watch(
  () => store.user,
  (u) => {
    if (!u && route.path !== '/auth') {
      router.push('/auth');
    }
  },
  { immediate: true }
);

// 登录后如果在 /auth 跳转到 /
watch(
  () => store.user,
  (u) => {
    if (u && route.path === '/auth') {
      router.push('/');
    }
  }
);

// Simple click-outside directive
const vClickOutside = {
  mounted(el, binding) {
    el.__clickOutside = (e) => {
      if (!el.contains(e.target)) binding.value();
    };
    setTimeout(() => document.addEventListener('click', el.__clickOutside), 0);
  },
  unmounted(el) {
    document.removeEventListener('click', el.__clickOutside);
  },
};
</script>
