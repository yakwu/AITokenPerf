<template>
  <section class="tab-content active">
    <div class="health-bar">
      <span class="hb-pill err"><span class="dot d-error"></span>告警中 {{ alerts.length }}</span>
      <span class="hb-pill ok"><span class="dot d-healthy"></span>健康 {{ healthCounts.healthy }}</span>
      <span class="hb-pill un"><span class="dot d-untested"></span>未测 {{ healthCounts.untested }}</span>
    </div>

    <div v-if="loading" class="alert-ok">加载中…</div>
    <div v-else-if="alerts.length" class="alert-area">
      <div v-for="a in alerts" :key="a.profile + '/' + a.model" class="alert-card">
        <span class="dot d-error"></span>
        <strong>{{ a.profile }} × {{ a.model }}</strong>
        <span class="alert-meta">连续 {{ a.streak }} 轮 · {{ a.task_count > 1 ? ('所属 ' + a.task_count + ' 个任务') : ((a.tasks[0] && a.tasks[0].name) || '未命名任务') }}</span>
        <router-link class="btn btn-sm" :to="`/sites/${encodeURIComponent(a.profile)}`">进站点 →</router-link>
      </div>
    </div>
    <div v-else class="alert-ok">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
      <span>一切正常</span>
    </div>

    <SiteHealthBoard
      :sites="sites"
      :availability-lut="availabilityLut"
      :buckets="BUCKETS"
      :favorites="favorites"
      @test-site="onTestSite"
      @toggle-favorite="onToggleFavorite"
      @navigate-to-detail="onNavigateToDetail"
    />

    <details class="tasks-fold">
      <summary>监控任务跑批状态（{{ schedules.length }}）</summary>
      <table class="board"><tbody>
        <tr v-for="s in schedules" :key="s.id">
          <td>{{ s.name }}</td><td>{{ siteOf(s) }}</td><td>{{ s.status }}</td>
        </tr>
      </tbody></table>
    </details>
  </section>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useAppStore } from '../stores/app';
import { useTimeRangeStore } from '../stores/timeRange';
import { getSitesSummary, getCellAvailability, getActiveAlerts, getSchedules } from '../api';
import { buildAvailabilityLookup } from '../utils/siteMetrics';
import { toast } from '../composables/useToast';
import SiteHealthBoard from '../components/SiteHealthBoard.vue';

const store = useAppStore();
const route = useRoute();
const router = useRouter();
const timeRangeStore = useTimeRangeStore();
const BUCKETS = 24;
const loading = ref(false);
const sites = ref([]);
const availabilityLut = ref({});
const alerts = ref([]);
const schedules = ref([]);

const FAV_KEY = 'site_favorites';
function loadFavorites() {
  try { return new Set(JSON.parse(localStorage.getItem(FAV_KEY) || '[]')); }
  catch { return new Set(); }
}
const favorites = ref(loadFavorites());
function onToggleFavorite(name) {
  const next = new Set(favorites.value);
  next.has(name) ? next.delete(name) : next.add(name);
  favorites.value = next;
  localStorage.setItem(FAV_KEY, JSON.stringify([...next]));
}

const healthCounts = computed(() => {
  const c = { healthy: 0, untested: 0 };
  for (const s of sites.value) { if (s.health === 'healthy') c.healthy++; else if (s.health === 'untested') c.untested++; }
  return c;
});
function siteOf(s) { return (s.profile_ids && s.profile_ids[0]) || '-'; }
function onTestSite() { toast('请进入站点详情发起测试', 'info'); }
function onNavigateToDetail(site) {
  const name = site.profile?.name;
  if (name) router.push(`/sites/${encodeURIComponent(name)}`);
}

async function loadData() {
  loading.value = true;
  try {
    const [summary, avail, al, sch] = await Promise.all([
      getSitesSummary({ hours: timeRangeStore.hours }),
      getCellAvailability({ hours: timeRangeStore.hours, buckets: BUCKETS }).catch(() => ({ cells: [] })),
      getActiveAlerts().catch(() => ({ alerts: [] })),
      getSchedules().catch(() => ({ schedules: [] })),
    ]);
    sites.value = summary.summary || [];
    availabilityLut.value = buildAvailabilityLookup(avail.cells || []);
    alerts.value = al.alerts || [];
    schedules.value = sch.schedules || [];
  } catch (e) {
    toast('加载监控总览失败: ' + e.message, 'error');
  } finally {
    loading.value = false;
  }
}

watch(() => route.name, (val) => { if (val === 'monitor') loadData(); }, { immediate: true });
watch(() => timeRangeStore.hours, () => { if (route.name === 'monitor') loadData(); });
store.refreshFn = loadData;
onUnmounted(() => { if (store.refreshFn === loadData) store.refreshFn = null; });
</script>

<style scoped>
.alert-area { display:flex; flex-direction:column; gap:8px; margin:14px 0; }
.alert-card { display:flex; align-items:center; gap:10px; padding:10px 14px; border:1px solid #f3c2c2; background:#fef6f6; border-radius:8px; }
.alert-meta { color:var(--text-tertiary); font-size:12px; }
.alert-card .btn { margin-left:auto; }
.alert-ok { display:flex; align-items:center; gap:6px; color:var(--success); padding:12px 0; font-weight:600; }
.tasks-fold { margin-top:18px; }
.tasks-fold summary { cursor:pointer; font-size:13px; color:var(--text-secondary); }
.health-bar { display:flex; align-items:center; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
.hb-pill { font-size:12px; font-weight:700; padding:5px 11px; border-radius:999px; display:flex; align-items:center; gap:6px; }
.hb-pill.err { background:#fdecec; color:#c0282d; } .hb-pill.ok { background:#e7f6ec; color:#1a7f43; } .hb-pill.un { background:#eee; color:#777; }
.dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
.dot.d-healthy { background:var(--success); } .dot.d-error { background:var(--danger); } .dot.d-untested { background:var(--text-tertiary); }
</style>
