<template>
  <section class="tab-content active">
    <!-- Loading -->
    <div v-if="loading && !sites.length" style="text-align:center;color:var(--text-tertiary);padding:40px">
      加载中...
    </div>

    <template v-else>
      <!-- Top: 5 Summary Cards -->
      <div class="dash-summary-row">
        <div class="dash-summary-card">
          <div class="dash-summary-value">{{ sites.length }}</div>
          <div class="dash-summary-label">
            目标站点数
            <span v-if="healthyCount > 0" class="dash-summary-sub success">{{ healthyCount }} 健康</span>
          </div>
        </div>
        <div class="dash-summary-card">
          <div class="dash-summary-value">{{ activeSchedules }}</div>
          <div class="dash-summary-label">
            活跃定时任务
            <span v-if="pausedSchedules > 0" class="dash-summary-sub muted">{{ pausedSchedules }} 已暂停</span>
          </div>
        </div>
        <div class="dash-summary-card">
          <div class="dash-summary-value">{{ todayTestCount }}</div>
          <div class="dash-summary-label">今日测试数</div>
        </div>
        <div class="dash-summary-card">
          <div class="dash-summary-value" :class="rateColorClass(overallSuccessRate)">
            {{ fmtPct(overallSuccessRate) }}
          </div>
          <div class="dash-summary-label">
            整体成功率
            <span v-if="yesterdayRate != null" class="dash-summary-sub" :class="rateDiffClass">
              vs 昨日 {{ rateDiff >= 0 ? '+' : '' }}{{ rateDiff.toFixed(1) }}%
            </span>
          </div>
        </div>
        <div class="dash-summary-card">
          <div class="dash-summary-value">{{ modelCount }}</div>
          <div class="dash-summary-label">
            覆盖模型数
            <span v-if="vendorCount > 0" class="dash-summary-sub muted">{{ vendorCount }} 家厂商</span>
          </div>
        </div>
      </div>

      <!-- Main: two-column layout -->
      <div class="dash-main">
        <!-- Left column: Site Status List -->
        <div class="dash-sites-panel">
          <h3 class="dash-panel-title">站点状态</h3>
          <div v-if="!sites.length" class="dash-empty">暂无站点</div>
          <div v-else class="dash-site-list">
            <div
              v-for="site in sites"
              :key="site.profile.name"
              class="dash-site-row"
              :class="siteRowClass(site)"
              @click="goSiteDetail(site)"
            >
              <span class="site-health-dot" :class="site.health"></span>
              <div class="dash-site-info">
                <span class="dash-site-name">{{ site.profile.name }}</span>
                <span class="dash-site-url">{{ hostName(site.profile.base_url) }}</span>
              </div>
              <div class="dash-site-metrics">
                <template v-if="site.health !== 'untested' && getSiteLatestMetrics(site)">
                  <span class="dash-metric" title="TTFT P50">{{ fmtTime(getSiteLatestMetrics(site).ttft) }}</span>
                  <span class="dash-metric" title="Token/s">{{ getSiteLatestMetrics(site).tps != null ? fmtNum(getSiteLatestMetrics(site).tps, 0) + ' t/s' : '-' }}</span>
                  <span class="rate-badge" :class="rateColorClass(getSiteLatestMetrics(site).successRate)" style="font-size:11px">
                    {{ fmtPct(getSiteLatestMetrics(site).successRate) }}
                  </span>
                </template>
                <template v-else>
                  <span class="dash-metric dash-metric--muted">未测试</span>
                </template>
              </div>
            </div>
          </div>
        </div>

        <!-- Right column -->
        <div class="dash-right-col">
          <!-- Right top: Anomaly Alerts -->
          <div class="dash-alerts-panel">
            <h3 class="dash-panel-title">异常告警</h3>
            <div v-if="!alerts.length" class="dash-empty">暂无异常</div>
            <div v-else class="dash-alert-list">
              <div
                v-for="alert in alerts"
                :key="alert.siteName"
                class="dash-alert-item"
              >
                <div class="dash-alert-header">
                  <span
                    class="dash-alert-site"
                    @click.stop="goSiteHistory(alert.siteName)"
                  >{{ alert.siteName }}</span>
                  <span class="dash-alert-desc">{{ alert.description }}</span>
                </div>
                <div v-if="alert.errorTags.length" class="dash-alert-tags">
                  <span
                    v-for="tag in alert.errorTags"
                    :key="tag"
                    class="dash-alert-tag"
                    @click.stop="showTagToast(tag)"
                  >{{ tag }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Right bottom: Recent Activity -->
          <div class="dash-activity-panel">
            <h3 class="dash-panel-title">最近活动</h3>
            <div v-if="!recentActivity.length" class="dash-empty">暂无活动</div>
            <div v-else class="dash-activity-list">
              <div
                v-for="act in recentActivity"
                :key="act.filename"
                class="dash-activity-item"
                @click="showDetail(act.raw)"
              >
                <span class="dash-activity-time">{{ relativeTime(act.timestamp) }}</span>
                <span class="dash-activity-icon" :class="act.success ? 'ok' : 'fail'">
                  {{ act.success ? '\u2713' : '\u2717' }}
                </span>
                <span class="dash-activity-site">{{ act.siteName }}</span>
                <span class="dash-activity-model">{{ act.model }}</span>
                <span class="rate-badge" :class="rateColorClass(act.successRate)" style="font-size:11px">
                  {{ fmtPct(act.successRate) }}
                </span>
                <span class="dash-activity-source">{{ act.source }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue';
import { useAppStore } from '../stores/app';
import { useTimeRangeStore } from '../stores/timeRange';
import { getSitesSummary, getSchedules, getResults } from '../api';
import { fmtTime, fmtPct, fmtNum } from '../utils/formatters';
import { renderResultDetail } from '../utils/resultDetail';
import { toast } from '../composables/useToast';
import { useRouter, useRoute } from 'vue-router';

const store = useAppStore();
const timeRangeStore = useTimeRangeStore();
const router = useRouter();
const route = useRoute();

const loading = ref(false);
const sites = ref([]);
const schedules = ref([]);
const results = ref([]);

// --- Computed ---

const healthyCount = computed(() => sites.value.filter(s => s.health === 'healthy').length);

const activeSchedules = computed(() => schedules.value.filter(s => s.status === 'active').length);
const pausedSchedules = computed(() => schedules.value.filter(s => s.status === 'paused').length);

// Today's test count
const todayTestCount = computed(() => {
  const today = new Date();
  const prefix = String(today.getFullYear()) +
    String(today.getMonth() + 1).padStart(2, '0') +
    String(today.getDate()).padStart(2, '0');
  return results.value.filter(r => r.timestamp && r.timestamp.startsWith(prefix)).length;
});

// Overall success rate
const overallSuccessRate = computed(() => {
  const items = results.value;
  const totalReqs = items.reduce((s, r) => s + (r.summary?.total_requests || 0), 0);
  const totalSuccess = items.reduce((s, r) => s + (r.summary?.successful_requests || 0), 0);
  return totalReqs > 0 ? (totalSuccess / totalReqs * 100) : null;
});

// Yesterday's success rate for comparison
const yesterdayRate = computed(() => {
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const prefix = String(yesterday.getFullYear()) +
    String(yesterday.getMonth() + 1).padStart(2, '0') +
    String(yesterday.getDate()).padStart(2, '0');
  const ydResults = results.value.filter(r => r.timestamp && r.timestamp.startsWith(prefix));
  const totalReqs = ydResults.reduce((s, r) => s + (r.summary?.total_requests || 0), 0);
  const totalSuccess = ydResults.reduce((s, r) => s + (r.summary?.successful_requests || 0), 0);
  return totalReqs > 0 ? (totalSuccess / totalReqs * 100) : null;
});

const rateDiff = computed(() => {
  if (overallSuccessRate.value == null || yesterdayRate.value == null) return 0;
  return overallSuccessRate.value - yesterdayRate.value;
});

const rateDiffClass = computed(() => {
  const diff = rateDiff.value;
  if (diff > 0) return 'success';
  if (diff < -3) return 'danger';
  if (diff < 0) return 'warning';
  return '';
});

// Model / vendor counts
const modelCount = computed(() => {
  const models = new Set(results.value.map(r => r.config?.model).filter(Boolean));
  return models.size;
});

const vendorCount = computed(() => {
  const vendors = new Set();
  for (const s of sites.value) {
    const provider = s.profile?.provider;
    if (provider) vendors.add(provider);
  }
  return vendors.size;
});

// Alerts: sites with error health
const alerts = computed(() => {
  return sites.value
    .filter(s => s.health === 'error')
    .map(site => {
      const latestResults = site.latest_results || [];
      // Calculate avg success rate from latest results
      const totalReqs = latestResults.reduce((s, r) => s + (r.summary?.total_requests || 0), 0);
      const totalSuccess = latestResults.reduce((s, r) => s + (r.summary?.successful_requests || 0), 0);
      const avgRate = totalReqs > 0 ? (totalSuccess / totalReqs * 100) : 0;

      // Collect error types with counts
      const errorMap = {};
      for (const r of latestResults) {
        const errs = r.errors || {};
        for (const [type, count] of Object.entries(errs)) {
          errorMap[type] = (errorMap[type] || 0) + count;
        }
      }

      const errorTags = Object.entries(errorMap)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([type, count]) => `${type} \u00d7 ${count}`);

      const desc = avgRate > 0
        ? `成功率 ${avgRate.toFixed(1)}%`
        : '持续异常';

      return {
        siteName: site.profile?.name || '-',
        description: desc,
        errorTags,
      };
    });
});

// Recent activity: from results, X records sorted with failures first
const recentActivity = computed(() => {
  const items = results.value.slice(0, 30);
  const activities = items.map(r => {
    const s = r.summary || {};
    const c = r.config || {};
    const rate = s.success_rate;
    const success = rate != null && rate >= 95;
    return {
      timestamp: r.timestamp,
      success,
      siteName: c.profile_name || hostName(c.base_url),
      model: shortModel(c.model),
      successRate: rate,
      source: r.scheduled_task_id ? '定时' : '手动',
      filename: r.filename,
      raw: r,
    };
  });

  // Sort: failures first, then by timestamp descending
  activities.sort((a, b) => {
    if (a.success !== b.success) return a.success ? 1 : -1;
    return (b.timestamp || '').localeCompare(a.timestamp || '');
  });

  return activities.slice(0, 15);
});

// --- Methods ---

function hostName(url) {
  if (!url) return '-';
  try { return new URL(url).hostname; } catch { return url; }
}

function shortModel(m) {
  if (!m) return '-';
  return m.replace('claude-', '').replace(/-202\d{5}/, '');
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

function rateColorClass(rate) {
  if (rate == null) return '';
  return rate >= 95 ? 'success' : rate >= 80 ? 'accent' : 'danger';
}

function siteRowClass(site) {
  if (site.health === 'error') return 'dash-site-row--error';
  if (site.health === 'untested') return 'dash-site-row--untested';
  return '';
}

// Get aggregated metrics for a site from its latest_results
function getSiteLatestMetrics(site) {
  const results = site.latest_results || [];
  if (!results.length) return null;

  const totalReqs = results.reduce((s, r) => s + (r.summary?.total_requests || 0), 0);
  const totalSuccess = results.reduce((s, r) => s + (r.summary?.successful_requests || 0), 0);
  const successRate = totalReqs > 0 ? (totalSuccess / totalReqs * 100) : null;

  const ttfts = results.map(r => r.percentiles?.TTFT?.P50).filter(v => v != null);
  const ttft = ttfts.length ? ttfts.reduce((a, b) => a + b, 0) / ttfts.length : null;

  const tpsList = results.map(r => r.summary?.token_throughput_tps).filter(v => v != null && v > 0);
  const tps = tpsList.length ? tpsList.reduce((a, b) => a + b, 0) / tpsList.length : null;

  return { ttft, tps, successRate };
}

function goSiteDetail(site) {
  const name = site.profile?.name;
  if (name) {
    router.push(`/sites/${encodeURIComponent(name)}`);
  }
}

function goSiteHistory(siteName) {
  if (siteName) {
    router.push(`/sites/${encodeURIComponent(siteName)}?tab=trends`);
  }
}

function showTagToast(tag) {
  toast('查看历史记录中的该错误类型: ' + tag, 'info');
}

function showDetail(result) {
  window.showDetailOverlay(renderResultDetail(result));
}

// --- Data Loading ---

async function loadDashboard() {
  loading.value = true;
  try {
    const [sitesData, schedulesData, resultsData] = await Promise.all([
      getSitesSummary({ hours: timeRangeStore.hours }).catch(() => ({ summary: [] })),
      getSchedules().catch(() => []),
      getResults({ limit: 100 }).catch(() => ({ items: [] })),
    ]);

    sites.value = sitesData.summary || [];
    schedules.value = Array.isArray(schedulesData) ? schedulesData : [];
    results.value = resultsData.items || [];
  } catch (e) {
    toast('加载概览数据失败: ' + e.message, 'error');
  }
  loading.value = false;
}

watch(() => route.path, (val) => {
  if (val === '/') loadDashboard();
}, { immediate: true });

watch(() => timeRangeStore.hours, () => {
  if (route.path === '/') loadDashboard();
});

store.refreshFn = loadDashboard;
onUnmounted(() => { store.refreshFn = null; });
</script>

<style scoped>
/* ---- Summary Cards Row ---- */
.dash-summary-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.dash-summary-card {
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  text-align: center;
  box-shadow: var(--shadow-sm);
}

.dash-summary-value {
  font-size: 28px;
  font-weight: 800;
  color: var(--text-primary);
  font-family: var(--font-mono);
  line-height: 1.2;
}

.dash-summary-value.success { color: var(--success); }
.dash-summary-value.danger { color: var(--danger); }
.dash-summary-value.accent { color: var(--warning); }

.dash-summary-label {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 6px;
}

.dash-summary-sub {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  margin-left: 4px;
  padding: 1px 6px;
  border-radius: 4px;
}

.dash-summary-sub.success {
  color: var(--success);
  background: var(--success-light);
}

.dash-summary-sub.muted {
  color: var(--text-tertiary);
  background: var(--border-subtle);
}

.dash-summary-sub.danger {
  color: var(--danger);
  background: var(--danger-light);
}

.dash-summary-sub.warning {
  color: var(--warning);
  background: var(--warning-light);
}

/* ---- Main Two-Column Layout ---- */
.dash-main {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  align-items: start;
}

.dash-panel-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

/* ---- Left: Site Status List ---- */
.dash-sites-panel {
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  box-shadow: var(--shadow-sm);
}

.dash-site-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dash-site-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.dash-site-row:hover {
  background: var(--border-subtle);
}

.dash-site-row--error {
  background: var(--danger-light);
}

.dash-site-row--error:hover {
  background: #fde5e5;
}

.dash-site-row--untested {
  opacity: 0.65;
}

.dash-site-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dash-site-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dash-site-url {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dash-site-metrics {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.dash-metric {
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--text-secondary);
  white-space: nowrap;
}

.dash-metric--muted {
  color: var(--text-tertiary);
  font-family: var(--font-body);
  font-style: italic;
}

/* Health dot — reuse global styles from SitesView */
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

/* ---- Right Column ---- */
.dash-right-col {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ---- Right Top: Anomaly Alerts ---- */
.dash-alerts-panel {
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  box-shadow: var(--shadow-sm);
}

.dash-alert-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dash-alert-item {
  padding: 10px 12px;
  border-radius: 8px;
  transition: background 0.15s;
}

.dash-alert-item:hover {
  background: var(--border-subtle);
}

.dash-alert-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
}

.dash-alert-site {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  cursor: pointer;
}

.dash-alert-site:hover {
  color: var(--accent);
}

.dash-alert-desc {
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--danger);
  font-weight: 500;
}

.dash-alert-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.dash-alert-tag {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 4px;
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
  font-family: var(--font-mono);
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}

.dash-alert-tag:hover {
  background: var(--danger-light);
  color: var(--danger);
}

/* ---- Right Bottom: Recent Activity ---- */
.dash-activity-panel {
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  box-shadow: var(--shadow-sm);
}

.dash-activity-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dash-activity-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
  font-size: 13px;
}

.dash-activity-item:hover {
  background: var(--border-subtle);
}

.dash-activity-time {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-tertiary);
  white-space: nowrap;
  min-width: 60px;
}

.dash-activity-icon {
  font-size: 14px;
  font-weight: 700;
  width: 18px;
  text-align: center;
  flex-shrink: 0;
}

.dash-activity-icon.ok { color: var(--success); }
.dash-activity-icon.fail { color: var(--danger); }

.dash-activity-site {
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100px;
}

.dash-activity-model {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.dash-activity-source {
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
  padding: 1px 6px;
  background: var(--border-subtle);
  border-radius: 4px;
}

/* ---- Empty State ---- */
.dash-empty {
  text-align: center;
  padding: 24px 0;
  color: var(--text-tertiary);
  font-size: 13px;
}

/* ---- Responsive ---- */
@media (max-width: 1024px) {
  .dash-summary-row {
    grid-template-columns: repeat(3, 1fr);
  }
  .dash-main {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .dash-summary-row {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
