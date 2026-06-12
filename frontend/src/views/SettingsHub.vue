<template>
  <section class="tab-content active">
    <h1 class="settings-hub-title">设置</h1>
    <nav class="settings-subtabs">
      <router-link to="/settings/notifiers" class="settings-subtab">告警渠道</router-link>
      <router-link v-if="isAdmin" to="/settings/models" class="settings-subtab">模型库</router-link>
      <router-link v-if="isAdmin" to="/settings/users" class="settings-subtab">用户管理</router-link>
      <router-link to="/settings/profile" class="settings-subtab">个人资料</router-link>
    </nav>
    <div class="settings-hub-body">
      <router-view />
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue';
import { useAppStore } from '../stores/app';
const store = useAppStore();
const isAdmin = computed(() => store.user?.role === 'admin');
</script>

<style scoped>
.settings-hub-title { font-size: 20px; font-weight: 700; margin: 0 0 16px; }
.settings-subtabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
.settings-subtab {
  padding: 10px 16px; font-size: 13px; font-weight: 600;
  color: var(--text-secondary); text-decoration: none;
  border-bottom: 2px solid transparent; margin-bottom: -1px;
}
.settings-subtab:hover { color: var(--text-primary); }
.settings-subtab.router-link-active { color: var(--accent); border-bottom-color: var(--accent); }
.settings-hub-body :deep(.tab-content) { padding: 0; }
</style>
