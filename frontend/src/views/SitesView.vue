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

    <!-- Loading -->
    <div v-if="loading && !sites.length" style="text-align:center;color:var(--text-tertiary);padding:40px">加载中...</div>

    <!-- Empty State -->
    <div v-else-if="!filteredSites.length && !loading" class="empty-state">
      <div class="empty-state-icon">&#127760;</div>
      <div class="empty-state-text">{{ sites.length ? '没有匹配的站点' : '尚无站点配置' }}</div>
      <p style="color:var(--text-tertiary);font-size:13px">{{ sites.length ? '尝试调整筛选条件' : '请通过配置页创建新站点，然后在目标站点页查看状态。' }}</p>
    </div>

    <!-- Site Card Grid -->
    <div v-else class="sites-grid">
      <div
        v-for="site in filteredSites"
        :key="site.profile.name"
        class="site-card"
        :class="siteCardClass(site)"
      >
        <!-- Card Header -->
        <div class="site-card-header">
          <div class="site-card-title-row">
            <span class="site-health-dot" :class="site.health"></span>
            <span class="site-name">{{ site.profile.name }}</span>
            <span class="site-status-label" :class="site.health">{{ healthLabel(site.health) }}</span>
          </div>
          <div class="site-card-url">{{ site.profile.base_url }}</div>
          <div class="site-card-meta">
            <span v-if="site.last_test_at" class="site-card-time">{{ relativeTime(site.last_test_at) }}</span>
            <span v-else class="site-card-time">未测试</span>
          </div>
        </div>

        <!-- Untested State -->
        <div v-if="site.health === 'untested' || !site.latest_results?.length" class="site-card-untested">
          <span>尚无测试数据</span>
        </div>

        <!-- Model Metrics Table -->
        <div v-else class="site-card-metrics">
          <div class="table-wrap">
            <table class="matrix-table">
              <thead>
                <tr>
                  <th>模型</th>
                  <th>TTFT P50</th>
                  <th>TPOT P50</th>
                  <th>Token·s⁻¹</th>
                  <th>成功率</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in getModelMetrics(site)" :key="m.model">
                  <td class="matrix-model">{{ m.model }}</td>
                  <td :style="latencyColorStyle(m.ttft, 0.5, 2)">{{ fmtTime(m.ttft) }}</td>
                  <td :style="latencyColorStyle(m.tpot, 0.01, 0.05)">{{ fmtTime(m.tpot) }}</td>
                  <td>{{ m.tps != null ? fmtNum(m.tps, 0) + ' t/s' : '-' }}</td>
                  <td><span class="rate-badge" :class="rateClass(m.successRate)">{{ fmtPct(m.successRate) }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Error Distribution Tags -->
          <div v-if="getErrorTypes(site).length" class="site-error-tags">
            <span class="site-error-tag" v-for="err in getErrorTypes(site)" :key="err">{{ err }}</span>
          </div>
        </div>

        <!-- Card Actions -->
        <div class="site-card-actions">
          <button class="btn btn-ghost btn-sm" @click="testSite(site)">一键测试</button>
          <button class="btn btn-sm site-detail-btn" @click="goDetail(site)">详情 &rarr;</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue';
import { useAppStore } from '../stores/app';
import { api, getSitesSummary } from '../api';
import { fmtTime, fmtPct, fmtNum } from '../utils/formatters';
import { toast } from '../composables/useToast';
import { useRouter, useRoute } from 'vue-router';

const store = useAppStore();
const router = useRouter();
const route = useRoute();

const loading = ref(false);
const sites = ref([]);
const search = ref('');
const statusFilter = ref('all');

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

function getModelMetrics(site) {
  const results = site.latest_results || [];
  const modelMap = {};
  for (const r of results) {
    const model = r.config?.model || '-';
    if (!modelMap[model]) {
      modelMap[model] = { results: [] };
    }
    modelMap[model].results.push(r);
  }

  return Object.entries(modelMap).map(([model, { results }]) => {
    const totalReqs = results.reduce((s, r) => s + (r.summary?.total_requests || 0), 0);
    const totalSuccess = results.reduce((s, r) => s + (r.summary?.successful_requests || 0), 0);
    const successRate = totalReqs > 0 ? (totalSuccess / totalReqs * 100) : null;

    const ttfts = results.map(r => r.percentiles?.TTFT?.P50).filter(v => v != null);
    const ttft = ttfts.length ? ttfts.reduce((a, b) => a + b, 0) / ttfts.length : null;

    const tpots = results.map(r => r.percentiles?.TPOT?.P50).filter(v => v != null);
    const tpot = tpots.length ? tpots.reduce((a, b) => a + b, 0) / tpots.length : null;

    const tpsList = results.map(r => r.summary?.token_throughput_tps).filter(v => v != null && v > 0);
    const tps = tpsList.length ? tpsList.reduce((a, b) => a + b, 0) / tpsList.length : null;

    return { model, ttft, tpot, tps, successRate };
  }).sort((a, b) => a.model.localeCompare(b.model));
}

function getErrorTypes(site) {
  const results = site.latest_results || [];
  const errors = new Set();
  for (const r of results) {
    const errDetails = r.error_details;
    if (Array.isArray(errDetails)) {
      for (const e of errDetails) {
        if (e?.error_type) errors.add(e.error_type);
      }
    }
  }
  return [...errors].slice(0, 5);
}

async function testSite(site) {
  const profile = site.profile;
  if (!profile?.models?.length) {
    toast('该站点未配置模型', 'info');
    return;
  }

  try {
    const res = await api('/api/bench/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        base_url: profile.base_url,
        api_key: profile.api_key_display || '',
        model: profile.models[0],
        provider: profile.provider || '',
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

    // Poll until test completes, then refresh data
    pollTestCompletion(res.task_id);
  } catch (e) {
    toast('启动测试失败: ' + e.message, 'error');
  }
}

async function pollTestCompletion(taskId) {
  const poll = async () => {
    try {
      const status = await api('/api/bench/status');
      if (status.running) {
        setTimeout(poll, 2000);
      } else {
        // Test complete, refresh site data
        await loadData();
        toast('测试完成，数据已刷新', 'success');
      }
    } catch {
      // On error, just refresh
      await loadData();
    }
  };
  setTimeout(poll, 2000);
}

function goDetail(site) {
  const name = site.profile?.name;
  if (name) {
    router.push(`/sites/${encodeURIComponent(name)}`);
  }
}

function createSite() {
  toast('请通过配置页创建新站点', 'info');
  store.switchTab('config');
}

async function loadData() {
  loading.value = true;
  try {
    const data = await getSitesSummary();
    sites.value = data.summary || [];
  } catch (e) {
    toast('加载站点数据失败: ' + e.message, 'error');
  }
  loading.value = false;
}

watch(() => route.path, (val) => {
  if (val === '/sites') loadData();
}, { immediate: true });

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

.site-card--healthy {
  border-left: 3px solid var(--success);
}

.site-card--error {
  border-left: 3px solid var(--danger);
}

.site-card--untested {
  border-left: 3px solid var(--text-tertiary);
  border-style: solid;
  border-left-style: solid;
  opacity: 0.85;
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
}

.site-error-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--danger-light);
  color: var(--danger);
  font-size: 11px;
  font-weight: 600;
  font-family: var(--font-mono);
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
</style>
