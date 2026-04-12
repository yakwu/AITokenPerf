<template>
  <section class="tab-content active">
    <!-- Breadcrumb -->
    <div class="site-detail-breadcrumb">
      <router-link to="/sites" class="breadcrumb-back">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        目标站点
      </router-link>
      <span class="breadcrumb-sep">/</span>
      <div class="breadcrumb-switcher" ref="switcherRef">
        <button class="breadcrumb-current" @click.stop="switcherOpen = !switcherOpen">
          <span class="site-health-dot" :class="siteHealth" v-if="siteHealth"></span>
          {{ siteName }}
          <svg class="breadcrumb-chevron" :class="{ open: switcherOpen }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <div class="switcher-dropdown" v-show="switcherOpen">
          <div
            v-for="s in allSites"
            :key="s.name"
            class="switcher-item"
            :class="{ active: s.name === siteName }"
            @click="switchSite(s.name)"
          >
            <span class="site-health-dot" :class="s.health" v-if="s.health"></span>
            <span class="switcher-item-name">{{ s.name }}</span>
          </div>
          <div v-if="!allSites.length" class="switcher-empty">无站点</div>
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" style="text-align:center;color:var(--text-tertiary);padding:40px">加载中...</div>

    <!-- Not Found -->
    <div v-else-if="!profile" class="empty-state">
      <div class="empty-state-text">站点「{{ siteName }}」不存在</div>
      <p style="color:var(--text-tertiary);font-size:13px">请返回目标站点列表检查</p>
    </div>

    <!-- Tab Content -->
    <template v-else>
      <!-- Internal Tabs -->
      <div class="site-detail-tabs">
        <button
          v-for="tab in internalTabs"
          :key="tab.key"
          class="site-detail-tab"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >{{ tab.label }}</button>
      </div>

      <!-- Config Tab -->
      <div v-if="activeTab === 'config'" class="site-detail-panel">
        <SiteConfigTab :profile="profile" @deleted="onSiteDeleted" />
      </div>

      <!-- Test Tab -->
      <div v-if="activeTab === 'test'" class="site-detail-panel">
        <SiteTestTab :profile="profile" />
      </div>

      <div v-if="activeTab === 'schedule'" class="site-detail-panel">
        <SiteSchedulesTab :profile="profile" />
      </div>

      <div v-if="activeTab === 'history'" class="site-detail-panel">
        <SiteTrendsTab :profile="profile" />
      </div>
    </template>
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getProfiles, getSitesSummary } from '../api';
import { toast } from '../composables/useToast';
import SiteConfigTab from '../components/SiteConfigTab.vue';
import SiteTestTab from '../components/SiteTestTab.vue';
import SiteSchedulesTab from '../components/SiteSchedulesTab.vue';
import SiteTrendsTab from '../components/SiteTrendsTab.vue';

const route = useRoute();
const router = useRouter();

const props = defineProps({ id: { type: String, required: true } });

const siteName = computed(() => decodeURIComponent(props.id));
const loading = ref(false);
const profile = ref(null);
const siteHealth = ref('');
const activeTab = ref('test');
const allSites = ref([]);
const switcherOpen = ref(false);
const switcherRef = ref(null);

const internalTabs = [
  { key: 'test', label: '单次任务' },
  { key: 'schedule', label: '定时任务' },
  { key: 'history', label: '历史趋势' },
  { key: 'config', label: '配置' },
];

// Map URL query ?tab= to internal tab keys
const tabQueryMap = { test: 'test', schedule: 'schedule', trends: 'history', history: 'history', config: 'config' };

async function loadSiteData() {
  loading.value = true;
  try {
    // Load profiles to get site config
    const profileData = await getProfiles();
    const profiles = Array.isArray(profileData.profiles) ? profileData.profiles : [];
    const found = profiles.find(p => p.name === siteName.value);
    profile.value = found || null;

    // Load health status from sites summary
    const summaryData = await getSitesSummary();
    const summaries = summaryData.summary || [];
    const siteSummary = summaries.find(s => s.profile?.name === siteName.value);
    siteHealth.value = siteSummary?.health || '';

    // 构建站点切换列表
    allSites.value = profiles.map(p => {
      const s = summaries.find(ss => ss.profile?.name === p.name);
      return { name: p.name, health: s?.health || '' };
    });
  } catch (e) {
    toast('加载站点数据失败: ' + e.message, 'error');
    profile.value = null;
  }
  loading.value = false;
}

function switchSite(name) {
  switcherOpen.value = false;
  if (name !== siteName.value) {
    const tabQuery = route.query.tab || 'trends';
    router.push(`/sites/${encodeURIComponent(name)}?tab=${tabQuery}`);
  }
}

function onClickOutside(e) {
  if (switcherRef.value && !switcherRef.value.contains(e.target)) {
    switcherOpen.value = false;
  }
}

function onSiteDeleted() {
  router.push('/sites');
}

watch(() => route.params.id, () => {
  if (route.name === 'site-detail') {
    const tabQuery = route.query.tab;
    activeTab.value = tabQueryMap[tabQuery] || 'test';
    loadSiteData();
  }
}, { immediate: true });

onMounted(() => {
  document.addEventListener('click', onClickOutside);
});

onUnmounted(() => {
  document.removeEventListener('click', onClickOutside);
});
</script>

<style scoped>
/* ---- Breadcrumb ---- */
.site-detail-breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 20px;
  font-size: 14px;
}

.breadcrumb-back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--accent);
  text-decoration: none;
  font-weight: 500;
  transition: color 0.15s;
}

.breadcrumb-back:hover {
  color: var(--accent-hover);
}

.breadcrumb-sep {
  color: var(--text-tertiary);
  font-size: 12px;
}

.breadcrumb-current {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-primary);
  font-weight: 600;
  background: none;
  border: none;
  font-size: 14px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.15s;
}

.breadcrumb-current:hover {
  background: var(--border-subtle);
}

.breadcrumb-chevron {
  transition: transform 0.15s;
  color: var(--text-tertiary);
}

.breadcrumb-chevron.open {
  transform: rotate(180deg);
}

.breadcrumb-switcher {
  position: relative;
}

.switcher-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  min-width: 200px;
  max-height: 300px;
  overflow-y: auto;
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  z-index: 100;
  padding: 4px 0;
}

.switcher-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  cursor: pointer;
  transition: background 0.1s;
}

.switcher-item:hover {
  background: var(--border-subtle);
}

.switcher-item.active {
  color: var(--accent);
  font-weight: 600;
}

.switcher-item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.switcher-empty {
  padding: 12px 14px;
  font-size: 12px;
  color: var(--text-tertiary);
  text-align: center;
}

.site-health-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.site-health-dot.healthy { background: var(--success); }
.site-health-dot.error { background: var(--danger); }
.site-health-dot.untested,
.site-health-dot.unknown { background: var(--text-tertiary); }

/* ---- Internal Tabs ---- */
.site-detail-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 20px;
}

.site-detail-tab {
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

.site-detail-tab:hover {
  color: var(--text-primary);
}

.site-detail-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

/* ---- Panel ---- */
.site-detail-panel {
  animation: fadeIn 0.15s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ---- Placeholder ---- */
.site-detail-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: var(--text-tertiary);
  gap: 12px;
}

.placeholder-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-secondary);
}

.placeholder-hint {
  font-size: 13px;
  color: var(--text-tertiary);
}
</style>
