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
      </div>
      <div class="sites-toolbar-right">
        <button class="btn btn-primary btn-sm" @click="createSite">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          新建站点
        </button>
      </div>
    </div>

    <!-- 告警卡区（连续 2 轮才翻红；无告警不显示） -->
    <div v-if="alerts.length" class="alert-area">
      <div v-for="(a, i) in alerts" :key="a.profile + '/' + a.model + '/' + i" class="alert-card">
        <span class="dot d-error"></span>
        <strong>{{ a.profile }} × {{ a.model }}</strong>
        <span class="alert-meta">连续 {{ a.streak }} 轮 · {{ a.task_count > 1 ? ('所属 ' + a.task_count + ' 个任务') : (a.tasks?.[0]?.name || '未命名任务') }}</span>
        <router-link class="btn btn-sm" :to="`/sites/${encodeURIComponent(a.profile)}`">进站点 →</router-link>
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
        <span class="hb-pill err" title="连续多轮失败才计入「告警中」；只看最近一次失败的站点请用下方「异常」筛选"><span class="dot d-error"></span>告警中 {{ alerts.length }}</span>
        <span class="hb-pill ok"><span class="dot d-healthy"></span>健康 {{ healthCounts.healthy }}</span>
        <span class="hb-pill un"><span class="dot d-untested"></span>未测 {{ healthCounts.untested }}</span>
        <span class="hb-legend"><i class="ab-up"></i>可用 <i class="ab-degraded"></i>降级 <i class="ab-down"></i>不可用</span>
      </div>
      <SiteHealthBoard
        :sites="filteredSites"
        :availability-lut="availabilityLut"
        :buckets="BUCKETS"
        :favorites="favorites"
        @test-site="testSite"
        @toggle-favorite="toggleFavorite"
        @navigate-to-detail="goDetail"
      />
    </div>

    <details v-if="schedules.length" class="tasks-fold">
      <summary>监控任务跑批状态（{{ schedules.length }}）</summary>
      <table class="board"><tbody>
        <tr v-for="s in schedules" :key="s.id">
          <td>{{ s.name }}</td><td>{{ siteOf(s) }}</td><td>{{ s.status }}</td>
        </tr>
      </tbody></table>
    </details>

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
import { api, getSitesSummary, getCellAvailability, getActiveAlerts, getSchedules } from '../api';
import { buildAvailabilityLookup } from '../utils/siteMetrics';
import { toast } from '../composables/useToast';
import { useRouter, useRoute } from 'vue-router';
import ModalOverlay from '../components/ModalOverlay.vue';
import ModelSelector from '../components/ModelSelector.vue';
import SiteHealthBoard from '../components/SiteHealthBoard.vue';

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
const alerts = ref([]);
const schedules = ref([]);
function siteOf(s) { return (s.profile_ids && s.profile_ids.length) ? s.profile_ids.join('、') : '-'; }
const BUCKETS = 24;

// ---- 收藏（localStorage 持久化）----
const FAV_KEY = 'site_favorites';
function loadFavorites() {
  try { return new Set(JSON.parse(localStorage.getItem(FAV_KEY) || '[]')); }
  catch { return new Set(); }
}
const favorites = ref(loadFavorites());
function toggleFavorite(name) {
  const next = new Set(favorites.value);
  next.has(name) ? next.delete(name) : next.add(name);
  favorites.value = next;
  localStorage.setItem(FAV_KEY, JSON.stringify([...next]));
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
  // 默认智能排序：收藏置顶 → error > healthy > untested → last_test_at desc
  // （看板列头点击的手动列排序由 SiteHealthBoard 组件内部叠加处理）
  const healthOrder = { error: 0, healthy: 1, untested: 2, unknown: 2 };
  return [...list].sort((a, b) => {
    const fa = favorites.value.has(a.profile.name) ? 0 : 1;
    const fb = favorites.value.has(b.profile.name) ? 0 : 1;
    if (fa !== fb) return fa - fb;
    const ha = healthOrder[a.health] ?? 2;
    const hb = healthOrder[b.health] ?? 2;
    if (ha !== hb) return ha - hb;
    return (b.last_test_at || '').localeCompare(a.last_test_at || '');
  });
});

function goDetail(site) {
  const name = site.profile?.name;
  if (name) {
    router.push(`/sites/${encodeURIComponent(name)}?tab=trends`);
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

async function loadBoard() {
  // 时间范围相关：站点摘要 + 可用性
  try {
    const [summaryData, availData] = await Promise.all([
      getSitesSummary({ hours: timeRangeStore.hours }),
      getCellAvailability({ hours: timeRangeStore.hours, buckets: BUCKETS }).catch(() => ({ cells: [] })),
    ]);
    sites.value = summaryData.summary || [];
    availabilityLut.value = buildAvailabilityLookup(availData.cells || []);
  } catch (e) {
    toast('加载站点数据失败: ' + e.message, 'error');
    sites.value = [];
    availabilityLut.value = {};
  }
}

async function loadStatic() {
  // 与时间范围无关：告警 + 跑批调度
  const [alertData, schedData] = await Promise.all([
    getActiveAlerts().catch(() => ({ alerts: [] })),
    getSchedules().catch(() => ({ schedules: [] })),
  ]);
  alerts.value = alertData.alerts || [];
  schedules.value = schedData.schedules || [];
}

// 进入页面 / 手动刷新：全量
async function loadData() {
  loading.value = true;
  await Promise.all([loadBoard(), loadStatic()]);
  loading.value = false;
}

// 仅时间范围变化：只刷新看板，不重拉告警/跑批
async function reloadBoard() {
  loading.value = true;
  await loadBoard();
  loading.value = false;
}

watch(() => route.path, (val) => {
  if (val === '/sites') loadData();
}, { immediate: true });

watch(() => timeRangeStore.hours, () => {
  if (route.path === '/sites' || route.path.startsWith('/sites/')) reloadBoard();
});

store.refreshFn = loadData;
onUnmounted(() => { if (store.refreshFn === loadData) store.refreshFn = null; });
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

/* ---- 站点健康统计条（全量统计，与看板表格搭配） ---- */
.health-bar { display:flex; align-items:center; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
.hb-pill { font-size:12px; font-weight:700; padding:5px 11px; border-radius:999px; display:flex; align-items:center; gap:6px; }
.hb-pill.err { background:#fdecec; color:#c0282d; } .hb-pill.ok { background:#e7f6ec; color:#1a7f43; } .hb-pill.un { background:#eee; color:#777; }
.hb-legend { margin-left:auto; font-size:11px; color:var(--text-tertiary); display:flex; align-items:center; gap:6px; }
.hb-legend i { display:inline-block; width:9px; height:11px; border-radius:1px; }
.hb-legend i.ab-up{background:#21a366;} .hb-legend i.ab-degraded{background:#f5a623;} .hb-legend i.ab-down{background:#e5484d;}
.dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
.dot.d-healthy { background:var(--success); } .dot.d-error { background:var(--danger); } .dot.d-untested { background:var(--text-tertiary); }
.alert-area { display:flex; flex-direction:column; gap:8px; margin:14px 0; }
.alert-card { display:flex; align-items:center; gap:10px; padding:10px 14px; border:1px solid #f3c2c2; background:#fef6f6; border-radius:8px; }
.alert-meta { color:var(--text-tertiary); font-size:12px; }
.alert-card .btn { margin-left:auto; }
.tasks-fold { margin-top:18px; }
.tasks-fold summary { cursor:pointer; font-size:13px; color:var(--text-secondary); }
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
