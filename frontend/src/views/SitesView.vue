<template>
  <section class="tab-content active">
    <!-- Toolbar -->
    <div class="history-toolbar">
      <div class="sites-toolbar-left">
        <span class="sites-count">共 {{ filteredSites.length }} 个站点</span>
        <div class="search-input-wrap">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input class="form-input" type="text" v-model="search" placeholder="搜索站点名称 / 地址...">
        </div>
        <div class="filter-chips">
          <button v-for="f in statusFilters" :key="f.value" class="filter-chip" :class="{ active: statusFilter === f.value }" @click="statusFilter = f.value">{{ f.label }}</button>
        </div>
        <label class="collapse-healthy-toggle" :class="{ active: collapseHealthy }">
          <input type="checkbox" v-model="collapseHealthy">
          <span>折叠健康站点</span>
        </label>
      </div>
      <div class="sites-toolbar-right">
        <button class="btn btn-primary btn-sm" @click="createSite">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          新建站点
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading && !sites.length" style="text-align:center;color:var(--text-tertiary);padding:40px">加载中...</div>

    <!-- Empty State -->
    <div v-else-if="!filteredSites.length && !loading" class="empty-state">
      <div class="empty-state-icon">&#127760;</div>
      <div class="empty-state-text">{{ sites.length ? '没有匹配的站点' : '尚无站点配置' }}</div>
      <p style="color:var(--text-tertiary);font-size:13px">{{ sites.length ? '尝试调整筛选条件' : '请通过配置页创建新站点，然后在目标站点页查看状态。' }}</p>
    </div>

    <!-- Site × Model Health Board -->
    <div v-else class="board-wrap">
      <div class="health-bar">
        <span class="hb-pill err"><span class="dot d-error"></span>异常 {{ healthCounts.error }}</span>
        <span class="hb-pill ok"><span class="dot d-healthy"></span>健康 {{ healthCounts.healthy }}</span>
        <span class="hb-pill un"><span class="dot d-untested"></span>未测 {{ healthCounts.untested }}</span>
        <span class="hb-legend"><i class="ab-up"></i>可用 <i class="ab-degraded"></i>降级 <i class="ab-down"></i>不可用</span>
      </div>
      <table class="board">
        <thead><tr>
          <th></th><th>站点 / 模型</th><th>可用性 · 近{{ BUCKETS }}</th>
          <th>TTFT P50</th><th>趋势</th><th>Token/s</th><th>成功率</th><th>最近测试</th><th></th>
        </tr></thead>
        <tbody>
          <template v-for="site in filteredSites" :key="site.profile.name">
            <tr class="site-row" :class="'h-' + site.health" @click="toggleExpand(site.profile.name)">
              <td><span class="dot" :class="'d-' + site.health"></span></td>
              <td>
                <span class="chev" :class="{ open: isExpanded(site.profile.name) }">▸</span>
                <button class="fav" :class="{ on: isFavorite(site.profile.name) }" @click.stop="toggleFavorite(site.profile.name)" :title="isFavorite(site.profile.name) ? '取消收藏' : '收藏'">★</button>
                <router-link class="sname" :to="`/sites/${encodeURIComponent(site.profile.name)}`" @click.stop>{{ site.profile.name }}</router-link>
                <span class="mcount">{{ getModelMetrics(site).length }} 模型</span>
              </td>
              <td><span class="avail-bars"><i v-for="(rate,i) in siteSeries(site)" :key="i" :class="'ab-'+availabilityClass(rate)" :title="rate==null?'无数据':('成功率 '+rate.toFixed(1)+'%')"></i></span></td>
              <td>{{ siteAvg(site,'ttft') != null ? fmtTime(siteAvg(site,'ttft')) : '-' }} <span class="agg" v-if="siteAvg(site,'ttft')!=null">平均</span></td>
              <td></td>
              <td>{{ siteAvg(site,'tps') != null ? fmtNum(siteAvg(site,'tps'),0) : '-' }}</td>
              <td><span class="rate" :class="rateClass(siteAvg(site,'successRate'))">{{ siteAvg(site,'successRate')!=null ? fmtPct(siteAvg(site,'successRate')) : '-' }}</span></td>
              <td>{{ site.last_test_at ? relativeTime(site.last_test_at) : '未测试' }}</td>
              <td class="row-actions" @click.stop>
                <button class="btn btn-ghost btn-sm" @click="testSite(site)">一键测试</button>
                <button class="btn btn-sm" @click="goDetail(site)">详情 →</button>
              </td>
            </tr>
            <tr v-for="m in (isExpanded(site.profile.name) ? modelRows(site) : [])" :key="site.profile.name + '/' + m.model" class="model-row">
              <td></td>
              <td class="mname">{{ m.model }}</td>
              <td><span class="avail-bars sm"><i v-for="(rate,i) in m.series" :key="i" :class="'ab-'+availabilityClass(rate)" :title="rate==null?'无数据':('成功率 '+rate.toFixed(1)+'%')"></i></span></td>
              <td :style="latencyColorStyle(m.ttft, 0.5, 2)">{{ m.ttft!=null ? fmtTime(m.ttft) : '-' }}</td>
              <td class="spark-cell">
                <svg v-if="m.latencyTrend && m.latencyTrend.length>=2" width="64" height="20" class="sparkline"><polyline :points="sparklinePoints(m.latencyTrend)" fill="none" :stroke="latencyTrendColor(m.latencyTrend)" stroke-width="1.5"/></svg>
                <span v-else class="spark-na">-</span>
              </td>
              <td>{{ m.tps!=null ? fmtNum(m.tps,0) : '-' }}</td>
              <td><span class="rate" :class="rateClass(m.successRate)">{{ m.successRate!=null ? fmtPct(m.successRate) : '-' }}</span></td>
              <td></td>
              <td></td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <!-- Create Site Modal -->
    <ModalOverlay :show="showCreateModal" title="新建站点" max-width="520px" @close="showCreateModal = false">
      <div class="create-site-form">
        <div class="form-group">
          <label class="form-label">站点名称 <span class="required">*</span></label>
          <input ref="createNameRef" class="form-input" v-model="createForm.name" placeholder="例如：生产环境 GPT-4" @keydown.enter="submitCreate">
          <div class="form-error" v-if="createErrors.name">{{ createErrors.name }}</div>
        </div>
        <div class="form-group">
          <label class="form-label">目标地址 <span class="required">*</span></label>
          <input class="form-input" v-model="createForm.base_url" placeholder="https://api.openai.com">
          <div class="form-error" v-if="createErrors.base_url">{{ createErrors.base_url }}</div>
        </div>
        <div class="form-group">
          <label class="form-label">API Key <span class="required">*</span></label>
          <div class="api-key-row">
            <input class="form-input" :type="showApiKey ? 'text' : 'password'" v-model="createForm.api_key" placeholder="sk-...">
            <button class="btn btn-ghost btn-sm" @click="showApiKey = !showApiKey" style="flex-shrink:0">
              {{ showApiKey ? '隐藏' : '显示' }}
            </button>
          </div>
          <div class="form-error" v-if="createErrors.api_key">{{ createErrors.api_key }}</div>
        </div>
        <div class="form-group">
          <label class="form-label">模型 <span class="required">*</span></label>
          <ModelSelector
            v-model="createForm.models"
            :vendor-filter="true"
            :allow-custom="true"
            placeholder="搜索或选择模型"
          />
          <div class="form-hint" v-if="!createForm.models.length && !createErrors.models" style="margin-top:4px">从列表选择或手动输入模型 ID 后回车</div>
          <div class="form-error" v-if="createErrors.models">{{ createErrors.models }}</div>
        </div>
      </div>
      <div class="btn-group" style="margin-top:20px">
        <button class="btn btn-primary" @click="submitCreate" :disabled="createLoading">
          {{ createLoading ? '创建中...' : '创建站点' }}
        </button>
        <button class="btn btn-ghost" @click="showCreateModal = false">取消</button>
      </div>
    </ModalOverlay>

    <!-- Test Confirm Modal -->
    <Teleport to="body">
      <div v-if="confirmTarget" class="modal-overlay" @click.self="confirmTarget = null">
        <div class="modal-box">
          <div class="modal-title">确认启动测试</div>
          <div class="modal-body">
            <div class="modal-row"><span class="modal-label">站点</span><span class="modal-value">{{ confirmTarget.profile.name }}</span></div>
            <div class="modal-row"><span class="modal-label">地址</span><span class="modal-value mono">{{ confirmTarget.profile.base_url }}</span></div>
            <div class="modal-row"><span class="modal-label">模型</span><span class="modal-value mono">{{ confirmTarget.profile.models?.[0] || '-' }}</span></div>
            <div class="modal-row"><span class="modal-label">参数</span><span class="modal-value">并发 10 · burst · max_tokens 512</span></div>
          </div>
          <div class="modal-actions">
            <button class="btn btn-ghost btn-sm" @click="confirmTarget = null">取消</button>
            <button class="btn btn-primary btn-sm" @click="confirmTest">确认测试</button>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue';
import { useAppStore } from '../stores/app';
import { useTimeRangeStore } from '../stores/timeRange';
import { api, getSitesSummary, getCellAvailability } from '../api';
import { fmtTime, fmtPct, fmtNum } from '../utils/formatters';
import { getModelMetrics, sparklinePoints, sparklineEnd, latencyTrendColor, latencyTrendTooltip, getErrorTypes, getTotalErrorCount, getDegradation, availabilityClass, buildAvailabilityLookup, siteAvgSeries } from '../utils/siteMetrics';
import { toast } from '../composables/useToast';
import { useRouter, useRoute } from 'vue-router';
import ModalOverlay from '../components/ModalOverlay.vue';
import ModelSelector from '../components/ModelSelector.vue';

const timeRangeStore = useTimeRangeStore();

const store = useAppStore();
const router = useRouter();
const route = useRoute();

const loading = ref(false);
const sites = ref([]);
const search = ref('');
const statusFilter = ref('all');
const confirmTarget = ref(null);
const availabilityLut = ref({});
const BUCKETS = 24;

// ---- 收藏（localStorage 持久化）----
const FAV_KEY = 'site_favorites';
function loadFavorites() {
  try { return new Set(JSON.parse(localStorage.getItem(FAV_KEY) || '[]')); }
  catch { return new Set(); }
}
const favorites = ref(loadFavorites());
function isFavorite(name) { return favorites.value.has(name); }
function toggleFavorite(name) {
  const next = new Set(favorites.value);
  next.has(name) ? next.delete(name) : next.add(name);
  favorites.value = next;
  localStorage.setItem(FAV_KEY, JSON.stringify([...next]));
}
// ---- 折叠健康站点（localStorage 持久化，默认开）----
const COLLAPSE_KEY = 'sites_collapse_healthy';
const collapseHealthy = ref(localStorage.getItem(COLLAPSE_KEY) !== '0');
watch(collapseHealthy, (val) => {
  localStorage.setItem(COLLAPSE_KEY, val ? '1' : '0');
});
function isCollapsed(site) {
  return collapseHealthy.value && site.health === 'healthy' && !isFavorite(site.profile.name);
}

// ---- 看板展开态（不持久化）+ 可用性辅助 ----
const expanded = ref(new Set());
function toggleExpand(name) { const n = new Set(expanded.value); n.has(name) ? n.delete(name) : n.add(name); expanded.value = n; }
function isExpanded(name) { return expanded.value.has(name); }
function modelRows(site) {
  const lut = availabilityLut.value[site.profile.name] || {};
  return getModelMetrics(site).map(m => ({ ...m, series: lut[m.model] || [] }));
}
function siteSeries(site) {
  const lut = availabilityLut.value[site.profile.name] || {};
  return siteAvgSeries(Object.values(lut));
}
function siteAvg(site, key) {
  const vals = getModelMetrics(site).map(m => m[key]).filter(v => v != null);
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
}
const healthCounts = computed(() => { const c = { error: 0, healthy: 0, untested: 0 }; for (const s of sites.value) c[s.health] = (c[s.health] || 0) + 1; return c; });

const statusFilters = [
  { label: '全部', value: 'all' },
  { label: '健康', value: 'healthy' },
  { label: '异常', value: 'error' },
  { label: '未测试', value: 'untested' },
];

const filteredSites = computed(() => {
  let list = sites.value;
  if (statusFilter.value !== 'all') {
    list = list.filter(s => s.health === statusFilter.value);
  }
  if (search.value.trim()) {
    const q = search.value.trim().toLowerCase();
    list = list.filter(s =>
      s.profile?.name?.toLowerCase().includes(q) ||
      s.profile?.base_url?.toLowerCase().includes(q)
    );
  }
  // Sort: 收藏置顶，组内 error > healthy > untested，再按 last_test_at desc
  const healthOrder = { error: 0, healthy: 1, untested: 2, unknown: 2 };
  list = [...list].sort((a, b) => {
    const fa = favorites.value.has(a.profile.name) ? 0 : 1;
    const fb = favorites.value.has(b.profile.name) ? 0 : 1;
    if (fa !== fb) return fa - fb;
    const ha = healthOrder[a.health] ?? 2;
    const hb = healthOrder[b.health] ?? 2;
    if (ha !== hb) return ha - hb;
    return (b.last_test_at || '').localeCompare(a.last_test_at || '');
  });
  return list;
});

function siteCardClass(site) {
  if (site.health === 'untested') return 'site-card--untested';
  if (site.health === 'error') return 'site-card--error';
  return 'site-card--healthy';
}

function healthLabel(h) {
  if (h === 'healthy') return '健康';
  if (h === 'error') return '异常';
  if (h === 'untested') return '未测试';
  return '未知';
}

function relativeTime(ts) {
  if (!ts) return '-';
  const y = +ts.slice(0, 4), mo = +ts.slice(4, 6) - 1, d = +ts.slice(6, 8);
  const h = +ts.slice(9, 11), mi = +ts.slice(11, 13);
  const date = new Date(y, mo, d, h, mi);
  const now = new Date();
  const diffMs = now - date;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return diffMin + '分钟前';
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return diffH + '小时前';
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7) return diffD + '天前';
  return ts.slice(4, 6) + '/' + ts.slice(6, 8) + ' ' + ts.slice(9, 11) + ':' + ts.slice(11, 13);
}

function latencyColorStyle(value, goodThreshold, warnThreshold) {
  if (value == null) return '';
  return value <= goodThreshold ? 'color:var(--success)' : value <= warnThreshold ? 'color:var(--warning)' : 'color:var(--danger)';
}

function rateClass(rate) {
  if (rate == null) return '';
  return rate >= 95 ? 'success' : rate >= 80 ? 'accent' : 'danger';
}

function goHistoryWithError(site, errorType) {
  const name = site.profile?.name;
  if (name && errorType) {
    router.push({ path: '/history', query: { site: name, error: errorType } });
  }
}

function goSiteHistory(site) {
  const name = site.profile?.name;
  if (name) {
    router.push(`/sites/${encodeURIComponent(name)}`);
  }
}

async function testSite(site) {
  const profile = site.profile;
  if (!profile?.models?.length) {
    toast('该站点未配置模型', 'info');
    return;
  }
  confirmTarget.value = site;
}

async function confirmTest() {
  const site = confirmTarget.value;
  confirmTarget.value = null;
  if (!site) return;

  const profile = site.profile;
  try {
    const res = await api('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profile_name: profile.name,
        models: [profile.models[0]],
        source: 'quick_test',
        concurrency_levels: [10],
        requests_per_level: 10,
        mode: 'burst',
        max_tokens: 512,
        timeout: 120,
        duration: 120,
        system_prompt: 'You are a helpful assistant.',
        user_prompt: 'Say hello.',
      }),
    });

    if (res.error) {
      toast(res.error, 'error');
      return;
    }

    toast('测试已启动', 'success');
    pollTestCompletion(res.run_id, site);
  } catch (e) {
    toast('启动测试失败: ' + e.message, 'error');
  }
}

async function pollTestCompletion(runId, site) {
  const siteName = site?.profile?.name || '';
  const poll = async () => {
    try {
      const status = await api(`/api/runs/${encodeURIComponent(runId)}`);
      if (status.status === 'running') {
        setTimeout(poll, 2000);
      } else {
        await loadData();
        if (siteName) {
          toast(`${siteName} 测试完成 — 点击查看详情`, 'success', {
            onClick: () => router.push(`/sites/${encodeURIComponent(siteName)}?tab=trends`),
          });
        } else {
          toast('测试完成，数据已刷新', 'success');
        }
      }
    } catch {
      await loadData();
    }
  };
  setTimeout(poll, 2000);
}

function goDetail(site) {
  const name = site.profile?.name;
  if (name) {
    router.push(`/sites/${encodeURIComponent(name)}?tab=trends`);
  }
}

// ---- Create Site Modal ----
const showCreateModal = ref(false);
const createLoading = ref(false);
const createErrors = ref({});
const createForm = ref({
  name: '',
  base_url: '',
  api_key: '',
  models: [],
});
const showApiKey = ref(false);

function createSite() {
  createForm.value = { name: '', base_url: '', api_key: '', models: [] };
  createErrors.value = {};
  showApiKey.value = false;
  showCreateModal.value = true;
}

function validateCreate() {
  const f = createForm.value;
  const errs = {};
  if (!f.name.trim()) errs.name = '请输入站点名称';
  if (!f.base_url.trim()) errs.base_url = '请输入目标地址';
  if (!f.api_key.trim()) errs.api_key = '请输入 API Key';
  if (!f.models.length) errs.models = '请至少选择一个模型';
  createErrors.value = errs;
  return Object.keys(errs).length === 0;
}

async function submitCreate() {
  if (!validateCreate()) return;
  createLoading.value = true;
  try {
    const f = createForm.value;
    const res = await api('/api/profiles/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: f.name.trim(),
        base_url: f.base_url.trim(),
        api_key: f.api_key.trim(),
        api_key_action: 'replace',
        api_version: '2023-06-01',
        models: f.models,
      }),
    });
    if (res.error) {
      toast(res.error, 'error');
      createLoading.value = false;
      return;
    }
    toast('站点已创建', 'success');
    showCreateModal.value = false;
    router.push(`/sites/${encodeURIComponent(f.name.trim())}?tab=test`);
  } catch (e) {
    toast('创建失败: ' + e.message, 'error');
  }
  createLoading.value = false;
}

async function loadData() {
  loading.value = true;
  try {
    const [summaryData, availData] = await Promise.all([
      getSitesSummary({ hours: timeRangeStore.hours }),
      getCellAvailability({ hours: timeRangeStore.hours, buckets: BUCKETS }).catch(() => ({ cells: [] })),
    ]);
    sites.value = summaryData.summary || [];
    availabilityLut.value = buildAvailabilityLookup(availData.cells || []);
  } catch (e) {
    toast('加载站点数据失败: ' + e.message, 'error');
  }
  loading.value = false;
}

watch(() => route.path, (val) => {
  if (val === '/sites') loadData();
}, { immediate: true });

watch(() => timeRangeStore.hours, () => {
  if (route.path === '/sites' || route.path.startsWith('/sites/')) loadData();
});

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

/* ---- Sites Grid ---- */
.sites-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

/* ---- Site Card ---- */
.site-card {
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  gap: 14px;
  transition: box-shadow 0.2s, transform 0.2s;
  overflow: hidden;
}

.site-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.site-card--healthy {}

.site-card--error {}

.site-card--untested {
  opacity: 0.7;
}

/* ---- Card Header ---- */
.site-card-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.site-card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
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

.site-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.site-name-link {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  text-decoration: none;
  transition: color 0.15s;
}

.site-name-link:hover {
  color: var(--accent);
}

.site-status-label {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 6px;
  white-space: nowrap;
  flex-shrink: 0;
}

.site-status-label.healthy { background: var(--success-light); color: var(--success); }
.site-status-label.error { background: var(--danger-light); color: var(--danger); }
.site-status-label.untested,
.site-status-label.unknown { background: var(--border-subtle); color: var(--text-tertiary); }

.site-card-url {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.site-card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.site-card-time {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* ---- Untested State ---- */
.site-card-untested {
  text-align: center;
  padding: 24px 0;
  color: var(--text-tertiary);
  font-size: 13px;
}

/* ---- Metrics ---- */
.site-card-metrics {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.site-card-metrics .table-wrap {
  border-radius: 8px;
}

.site-card-metrics table {
  font-size: 12px;
}

.site-card-metrics thead th {
  font-size: 10px;
  padding: 8px 10px;
}

.site-card-metrics tbody td {
  padding: 7px 10px;
  font-size: 11.5px;
}

/* ---- Error Tags ---- */
.site-error-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.site-error-label {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-right: 2px;
}

.site-error-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--danger-light);
  color: var(--danger);
  font-size: 11px;
  font-weight: 600;
  font-family: var(--font-mono);
  cursor: pointer;
  transition: opacity 0.15s, background 0.15s;
}

.site-error-tag:hover {
  opacity: 0.8;
  background: var(--danger);
  color: #fff;
}

/* ---- Degradation Warning ---- */
.site-degradation-warning {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 6px;
  background: var(--warning-light, #fef3cd);
  color: var(--warning, #d97706);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s;
}

.site-degradation-warning:hover {
  opacity: 0.85;
}

/* ---- Sparkline ---- */
.sparkline-cell {
  padding: 4px 6px !important;
  vertical-align: middle;
}

.sparkline {
  display: block;
  vertical-align: middle;
}

.sparkline-na {
  color: var(--text-tertiary);
  font-size: 11px;
}

/* ---- Card Actions ---- */
.site-card-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--border-subtle);
}

.site-detail-btn {
  color: var(--accent);
  font-weight: 600;
}

.site-detail-btn:hover {
  color: var(--accent-hover);
}

/* ---- Responsive ---- */
@media (max-width: 768px) {
  .sites-grid {
    grid-template-columns: 1fr;
  }
}

/* ---- Create Site Form ---- */
.create-site-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.api-key-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.api-key-row .form-input {
  flex: 1;
  min-width: 0;
}

.required {
  color: var(--danger);
  font-size: 12px;
}

.form-error {
  font-size: 12px;
  color: var(--danger);
  margin-top: 4px;
}

.form-hint {
  font-size: 11px;
  color: var(--text-tertiary);
}

.site-fav-btn {
  background: none; border: none; cursor: pointer;
  font-size: 15px; line-height: 1; padding: 0 2px;
  color: var(--text-tertiary); flex-shrink: 0;
}
.site-fav-btn.active { color: var(--warning); }
.collapse-healthy-toggle {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--text-secondary); cursor: pointer; user-select: none;
}
.collapse-healthy-toggle.active { color: var(--accent); }
.site-card-collapsed-hint {
  font-size: 12px; color: var(--text-tertiary); padding: 8px 0;
}

/* ---- Site × Model Health Board ---- */
.avail-bars { display:inline-flex; align-items:flex-end; gap:1.5px; }
.avail-bars i { display:inline-block; width:4px; height:16px; border-radius:1px; background:var(--border); }
.avail-bars.sm i { height:13px; }
.avail-bars i.ab-up { background:#21a366; }
.avail-bars i.ab-degraded { background:#f5a623; }
.avail-bars i.ab-down { background:#e5484d; }
.avail-bars i.ab-na { background:var(--border-subtle, #e5e5e5); }
table.board { width:100%; border-collapse:collapse; font-size:12.5px; }
table.board th { text-align:left; font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:var(--text-tertiary); padding:8px 10px; border-bottom:1px solid var(--border); white-space:nowrap; }
table.board td { padding:8px 10px; border-bottom:1px solid var(--border-subtle); white-space:nowrap; vertical-align:middle; }
.site-row { cursor:pointer; } .site-row:hover td { background:var(--border-subtle); }
.site-row.h-error td { background:#fef6f6; }
.model-row td { background:var(--bg, #fafafa); }
.mname { padding-left:26px; color:var(--text-secondary); font-weight:600; }
.chev { display:inline-block; width:14px; color:var(--text-tertiary); font-size:10px; transition:transform .15s; }
.chev.open { transform:rotate(90deg); }
.sname { font-weight:700; color:var(--text-primary); text-decoration:none; }
.sname:hover { color:var(--accent); }
.mcount { font-size:10.5px; font-weight:600; color:#6b7280; background:var(--border-subtle); border-radius:999px; padding:1px 7px; margin-left:6px; }
.fav { background:none; border:none; cursor:pointer; color:var(--text-tertiary); font-size:13px; }
.fav.on { color:var(--warning); }
.agg { font-size:9px; color:var(--text-tertiary); }
.row-actions { display:flex; gap:6px; justify-content:flex-end; }
.spark-na { color:var(--text-tertiary); }
.health-bar { display:flex; align-items:center; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
.hb-pill { font-size:12px; font-weight:700; padding:5px 11px; border-radius:999px; display:flex; align-items:center; gap:6px; }
.hb-pill.err { background:#fdecec; color:#c0282d; } .hb-pill.ok { background:#e7f6ec; color:#1a7f43; } .hb-pill.un { background:#eee; color:#777; }
.hb-legend { margin-left:auto; font-size:11px; color:var(--text-tertiary); display:flex; align-items:center; gap:6px; }
.hb-legend i { display:inline-block; width:9px; height:11px; border-radius:1px; }
.hb-legend i.ab-up{background:#21a366;} .hb-legend i.ab-degraded{background:#f5a623;} .hb-legend i.ab-down{background:#e5484d;}
.dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
.dot.d-healthy { background:var(--success); } .dot.d-error { background:var(--danger); } .dot.d-untested { background:var(--text-tertiary); }
</style>

<style>
/* Modal styles (non-scoped for Teleport to body) */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.15s ease;
}

.modal-box {
  background: var(--surface-raised, #fff);
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 12px;
  padding: 24px;
  width: 400px;
  max-width: 90vw;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  animation: slideUp 0.2s ease;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.modal-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary, #111);
  margin-bottom: 16px;
}

.modal-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 20px;
}

.modal-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 13px;
}

.modal-label {
  color: var(--text-tertiary, #999);
  flex-shrink: 0;
  width: 40px;
  text-align: right;
}

.modal-value {
  color: var(--text-primary, #111);
  font-weight: 500;
  word-break: break-all;
}

.modal-value.mono {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
