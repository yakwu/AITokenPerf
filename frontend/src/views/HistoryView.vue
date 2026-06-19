<template>
  <section class="tab-content active">
    <!-- Tab Switcher -->
    <div class="tab-switcher" style="margin-bottom:16px">
      <button class="tab-btn" :class="{ active: activeTab === 'bench' }" @click="activeTab = 'bench'">基准测试</button>
      <button class="tab-btn" :class="{ active: activeTab === 'diag' }" @click="activeTab = 'diag'; loadDiagHistory()">诊断历史</button>
    </div>

    <!-- Bench Tab Content -->
    <template v-if="activeTab === 'bench'">

    <!-- Toolbar -->
    <div class="history-toolbar">
      <div class="search-input-wrap">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input class="form-input" type="text" v-model="search" placeholder="搜索模型 / 目标地址...">
      </div>
      <div class="filter-chips">
        <FilterDropdown v-model="modelFilter" :options="uniqueModels" all-label="全部模型" wide />
        <FilterDropdown v-model="urlFilter" :options="uniqueUrls" all-label="全部地址" wide />
        <FilterDropdown v-model="concurrencyFilter" :options="uniqueConcurrenciesStr" all-label="全部并发" />
        <FilterDropdown v-model="modeFilter" :options="['burst','sustained']" all-label="全部模式" />
        <FilterDropdown v-model="sourceFilter" :options="sourceOptions" all-label="全部来源" />
        <FilterDropdown v-model="siteFilter" :options="uniqueProfiles" all-label="全部站点" wide />
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <div class="compare-bar" :class="{ visible: compareSet.size >= 1 }">
          <span class="compare-bar-label">已选 {{ compareSet.size }} 条</span>
          <span class="compare-bar-tags">
            <span v-for="idx in [...compareSet]" :key="idx" class="compare-tag">
              {{ compareTagLabel(filtered[idx]) }}
              <button class="compare-tag-remove" @click="toggleCompare(idx)">&times;</button>
            </span>
          </span>
          <button class="btn btn-primary btn-sm" :disabled="compareSet.size < 2" @click="enterCompare()">对比</button>
          <button class="btn btn-ghost btn-sm" @click="clearCompare()">取消</button>
        </div>
      </div>
    </div>

    <!-- Comparison view -->
    <div v-if="showCompareView && compareData" class="card" style="padding:0;overflow:hidden">
      <div style="padding:16px;display:flex;align-items:center;gap:12px;border-bottom:1px solid var(--border)">
        <a href="#" class="compare-back-link" @click.prevent="exitCompare">&larr; 返回列表</a>
        <span style="font-weight:600;font-size:15px">对比分析</span>
        <span style="color:var(--text-tertiary);font-size:13px">{{ compareData.records.length }} 条记录</span>
      </div>
      <div class="table-wrap">
        <table class="compare-table">
          <thead>
            <tr>
              <th style="position:sticky;left:0;background:var(--card);z-index:1;min-width:100px">指标</th>
              <th v-for="(rec, ri) in compareData.records" :key="ri">
                {{ rec.config?.profile_name || rec.config?.model || '?' }}
                <br><small style="font-weight:400">{{ rec.config?.concurrency || '?' }}c &middot; {{ fmtTimestamp(rec.timestamp).slice(5) }}</small>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="metric in compareData.metrics" :key="metric.label">
              <td style="position:sticky;left:0;background:var(--card);z-index:1;font-weight:600;white-space:nowrap">{{ metric.label }}</td>
              <td v-for="(rec, ri) in compareData.records" :key="ri"
                :class="getCompareCellClassFor(metric, compareData.records, ri)">
                <span>{{ formatMetricValue(metric, rec) }}</span>
                <span v-if="getPctDiff(metric, compareData.records, ri)"
                  class="compare-pct-diff"
                  :style="{ color: isPositiveDiff(metric, compareData.records, ri) ? 'var(--danger)' : 'var(--success)' }">
                  {{ getPctDiff(metric, compareData.records, ri) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Normal table view -->
    <div v-else class="card" style="padding:0;overflow:hidden">
      <div class="table-wrap">
        <table class="history-table">
          <thead>
            <tr>
              <th style="width:28px"></th>
              <th style="width:130px">时间</th>
              <th style="width:130px">模型</th>
              <th style="max-width:180px">目标地址</th>
              <th style="width:50px">并发</th>
              <th style="width:55px">模式</th>
              <th style="width:72px">成功率</th>
              <th style="width:70px" title="失败请求数（悬停看错误类型）">失败</th>
              <th style="width:78px">TTFT P50</th>
              <th style="width:78px" title="每输出 token 间隔 P50（吐字速度）">TPOT P50</th>
              <th style="width:78px">E2E P50</th>
              <th style="width:72px">吞吐量</th>
              <th style="width:72px" title="每请求输入 Token (P50)">输入 Tok</th>
              <th style="width:72px" title="每请求输出 Token (P50)">输出 Tok</th>
              <th style="width:55px">费用</th>
              <th style="width:80px"></th>
            </tr>
          </thead>
          <tbody>
            <template v-if="!filtered.length">
              <tr>
                <td colspan="16" style="text-align:center;padding:40px;color:var(--text-tertiary)">暂无记录</td>
              </tr>
            </template>
            <template v-for="(r, idx) in filtered" :key="r.filename || idx">
              <tr
                class="history-row"
                :class="{ expanded: expandedRows.has(idx) }"
                @click="onRowClick(r, idx, $event)"
              >
                <td><input type="checkbox" class="compare-check" :checked="compareSet.has(idx)" @change="toggleCompare(idx)" @click.stop></td>
                <td style="font-size:12px;white-space:nowrap">{{ fmtTimestamp(r.timestamp) }}</td>
                <td>
                  <span style="max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;vertical-align:middle" :title="r.config?.model">{{ r.config?.model || '-' }}</span>
                  <span v-if="r.channel_diagnostic_status" class="diag-icon" :class="'diag-' + r.channel_diagnostic_status" :title="diagTooltip(r)" style="display:inline-block;width:8px;height:8px;border-radius:50%;margin-left:4px;vertical-align:middle;flex-shrink:0"></span>
                </td>
                <td style="max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;color:var(--text-secondary)" :title="r.config?.base_url">{{ r.config?.base_url || '-' }}</td>
                <td style="font-size:12px">{{ r.config?.concurrency || '-' }}</td>
                <td style="font-size:12px">{{ r.config?.mode || '-' }}</td>
                <td :class="successRateClass(r.summary?.success_rate)" style="font-weight:600;font-size:12px">{{ fmtPct(r.summary?.success_rate) }}</td>
                <td style="font-size:12px;white-space:nowrap" :title="errorTypesTitle(r)">
                  <span :class="r.summary?.failed_count ? 'danger' : ''" style="font-weight:600">{{ r.summary?.failed_count || 0 }}</span>
                  <span v-if="topErrorType(r)" style="color:var(--text-tertiary);font-size:10px;margin-left:3px">{{ topErrorType(r) }}</span>
                </td>
                <td :class="latencyClass(r.percentiles?.TTFT?.P50, 0.5, 2)" style="font-family:var(--font-mono);font-size:12px;font-weight:500">{{ fmtTime(r.percentiles?.TTFT?.P50) }}</td>
                <td :class="latencyClass(r.percentiles?.TPOT?.P50, 0.05, 0.2)" style="font-family:var(--font-mono);font-size:12px;font-weight:500">{{ fmtTime(r.percentiles?.TPOT?.P50) }}</td>
                <td :class="latencyClass(r.percentiles?.E2E?.P50, 2, 10)" style="font-family:var(--font-mono);font-size:12px;font-weight:500">{{ fmtTime(r.percentiles?.E2E?.P50) }}</td>
                <td :class="qualityClass(r.summary?.throughput_rps, 20, 5)" style="font-family:var(--font-mono);font-size:12px;font-weight:500">{{ fmtNum(r.summary?.throughput_rps) }}/s</td>
                <td style="font-family:var(--font-mono);font-size:12px;font-weight:500">{{ fmtNum(r.summary?.input_tokens?.P50, 0) }}</td>
                <td style="font-family:var(--font-mono);font-size:12px;font-weight:500">{{ fmtNum(r.summary?.output_tokens?.P50, 0) }}</td>
                <td style="font-family:var(--font-mono);font-size:12px;font-weight:500">{{ fmtCostShort(r.summary?.cost_total_usd) }}</td>
                <td style="white-space:nowrap;text-align:right">
                  <span class="history-row-source" v-if="r.schedule_name" :title="r.schedule_name" style="font-size:10px;color:var(--text-tertiary);margin-right:4px">定时</span>
                  <button v-if="r.config?.profile_name" class="btn btn-ghost btn-sm" @click.stop="rerunAtSite(r)" title="重测" style="padding:2px 6px;font-size:11px">重测</button>
                  <button class="btn btn-ghost btn-sm" @click.stop="rerunResult(r)" title="重新运行" style="padding:2px 6px;font-size:11px">↻</button>
                  <button class="btn btn-ghost btn-sm btn-danger-text del-btn" @click.stop="deleteResult(r.filename || '')" title="删除" style="padding:2px 6px;font-size:11px">
                    <span v-if="pendingDelete === (r.filename || '')" class="delete-undo">确认删除</span>
                    <span v-else>✕</span>
                  </button>
                </td>
              </tr>
              <!-- 展开详情 -->
              <tr v-if="expandedRows.has(idx)" class="history-detail-row">
                <td colspan="16" style="padding:0">
                  <div style="padding:12px 16px;background:var(--bg);border-top:1px solid var(--border-subtle)" v-html="detailHtml[idx]"></div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Pagination -->
    <div style="display:flex;align-items:center;justify-content:space-between;padding:16px 0;font-size:13px;color:var(--text-secondary)">
      <div>共 {{ total }} 条记录</div>
      <div style="display:flex;align-items:center;gap:4px" v-show="totalPages > 1">
        <button class="btn btn-ghost btn-sm" :disabled="page <= 1" @click="goToPage(page - 1)">上一页</button>
        <button
          v-for="p in pageNumbers"
          :key="p"
          class="btn btn-sm"
          :class="p === page ? 'btn-primary' : 'btn-ghost'"
          @click="goToPage(p)"
        >{{ p }}</button>
        <button class="btn btn-ghost btn-sm" :disabled="page >= totalPages" @click="goToPage(page + 1)">下一页</button>
      </div>
    </div>

    </template>

    <!-- Diagnostic History Tab -->
    <template v-if="activeTab === 'diag'">
      <div class="diag-history">
        <!-- 筛选栏 -->
        <div class="filter-chips" style="margin-bottom:16px">
          <FilterDropdown v-model="diagFilterProfile" :options="diagFilterOptions.profile_names" all-label="全部站点" wide @update:modelValue="onDiagFilterChange" />
          <FilterDropdown v-model="diagFilterModel" :options="diagFilterOptions.models" all-label="全部模型" wide @update:modelValue="onDiagFilterChange" />
          <FilterDropdown v-model="diagFilterStatus" :options="diagStatusOptions" all-label="全部状态" @update:modelValue="onDiagFilterChange" />
        </div>

        <!-- 列表 -->
        <div class="card" style="padding:0;overflow:hidden">
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style="width:150px">时间</th>
                  <th>站点</th>
                  <th>模型</th>
                  <th style="width:120px">状态</th>
                  <th style="width:80px">置信度</th>
                  <th style="width:40px"></th>
                </tr>
              </thead>
              <tbody>
                <template v-if="!diagItems.length && !diagLoading">
                  <tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text-tertiary)">暂无诊断记录</td></tr>
                </template>
                <template v-for="item in diagItems" :key="item.id">
                  <!-- 摘要行 -->
                  <tr class="history-row" :class="{ expanded: diagExpandedId === item.id }" style="cursor:pointer" @click="toggleDiagExpand(item.id)">
                    <td>{{ fmtDiagTimestamp(item.created_at) }}</td>
                    <td>{{ item.profile_name }}</td>
                    <td style="font-family:var(--font-mono);font-size:12px">{{ item.model }}</td>
                    <td>
                      <span :style="'background:' + diagStatusColor(item.status) + ';color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600'">
                        {{ diagStatusLabel(item.status) }}
                      </span>
                    </td>
                    <td>{{ item.confidence != null ? (item.confidence * 100).toFixed(0) + '%' : '-' }}</td>
                    <td style="text-align:center;font-size:11px;color:var(--text-tertiary)">{{ diagExpandedId === item.id ? '▲' : '▼' }}</td>
                  </tr>
                  <!-- 展开详情 -->
                  <tr v-if="diagExpandedId === item.id">
                    <td colspan="6" style="padding:0">
                      <div style="padding:16px 20px;background:var(--bg-secondary)">
                        <div v-if="diagDetailLoading && !diagDetailCache[item.id]" style="text-align:center;padding:20px;color:var(--text-tertiary)">
                          <span class="result-loading-spinner" style="width:16px;height:16px;border-width:2px;margin-right:8px"></span>
                          加载中...
                        </div>
                        <div v-else-if="diagDetailError && !diagDetailCache[item.id]" style="text-align:center;padding:20px">
                          <span style="color:var(--danger)">加载失败</span>
                          <button class="btn btn-ghost btn-sm" style="margin-left:8px" @click.stop="retryDiagDetail()">重试</button>
                        </div>
                        <DiagnosticCard
                          v-else-if="diagDetailCache[item.id]"
                          :report="diagDetailCache[item.id].report_json"
                          :status="diagDetailCache[item.id].status"
                          :confidence="diagDetailCache[item.id].confidence"
                          :categories="diagDetailCache[item.id].categories"
                          :overall-status="diagDetailCache[item.id].overall_status"
                          compact
                        />
                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </div>

        <!-- 加载更多 -->
        <div v-if="diagHasMore" style="text-align:center;margin-top:12px">
          <button class="btn btn-ghost" @click="loadMoreDiag()" :disabled="diagLoading">
            {{ diagLoading ? '加载中...' : '加载更多' }}
          </button>
        </div>
        <div v-if="diagTotal > 0" style="text-align:center;margin-top:8px;font-size:12px;color:var(--text-tertiary)">
          共 {{ diagTotal }} 条诊断记录
        </div>
      </div>
    </template>
  </section>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api } from '../api/index.js';
import { useAppStore } from '../stores/app.js';
import { useTimeRangeStore } from '../stores/timeRange.js';
import { toast } from '../composables/useToast.js';
import {
  fmtTime, fmtTimestamp, fmtPct, fmtNum, fmtCostShort,
} from '../utils/formatters.js';
import { renderResultDetail } from '../utils/resultDetail.js';
import FilterDropdown from '../components/FilterDropdown.vue';
import { listChannelDiagnostics, getChannelDiagnostic, getDiagnosticFilterOptions } from '../api/index.js';
import DiagnosticCard from '../components/DiagnosticCard.vue';
import { diagStatusColor, diagStatusLabel } from '../utils/diagnosticUtils.js';

const store = useAppStore();
const timeRangeStore = useTimeRangeStore();

// ---- State ----
const results = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const search = ref('');
const modeFilter = ref('');
const modelFilter = ref('');
const urlFilter = ref('');
const concurrencyFilter = ref('');
const sourceFilter = ref('');
const siteFilter = ref('');
const sortKey = ref('timestamp');
const sortDir = ref('desc');
const compareSet = reactive(new Set());
const expandedRows = reactive(new Set());
const pendingDelete = ref(null);
let deleteTimer = null;

// Detail HTML caches
const detailHtml = reactive({});

// ---- Diagnostic History State ----
const activeTab = ref('bench');

const diagItems = ref([]);
const diagTotal = ref(0);
const diagOffset = ref(0);
const diagPageSize = 20;
const diagHasMore = computed(() => diagOffset.value + diagPageSize < diagTotal.value);
const diagLoading = ref(false);

// 筛选
const diagFilterProfile = ref('');
const diagFilterModel = ref('');
const diagFilterStatus = ref('');
const diagFilterOptions = ref({ profile_names: [], models: [] });
const diagStatusOptions = ['passed', 'warning', 'no_usage_fields', 'no_cache', 'inconclusive', 'error'];

// 展开详情
const diagExpandedId = ref(null);
const diagDetailCache = ref({});
const diagDetailLoading = ref(false);
const diagDetailError = ref(false);

function fmtDiagTimestamp(ts) {
  if (!ts) return '-';
  // SQLite datetime('now') stores UTC without suffix — append Z so JS converts to local
  let d;
  if (ts.includes('T') && (ts.includes('+') || ts.includes('Z'))) {
    d = new Date(ts);
  } else {
    d = new Date(ts.replace(' ', 'T') + 'Z');
  }
  if (isNaN(d)) return ts;
  const mo = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const h = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  return `${mo}-${day} ${h}:${mi}`;
}

// ---- Computed ----
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));

const uniqueModels = computed(() =>
  [...new Set(results.value.map(r => r.config?.model).filter(Boolean))].sort()
);

const uniqueUrls = computed(() => {
  const norm = u => (u || '').replace(/\/+$/, '');
  return [...new Set(results.value.map(r => r.config?.base_url).filter(Boolean).map(norm))].sort();
});

const uniqueConcurrencies = computed(() =>
  [...new Set(results.value.map(r => r.config?.concurrency).filter(Boolean))].sort((a, b) => a - b)
);

const uniqueScheduleNames = computed(() =>
  [...new Set(results.value.map(r => r.schedule_name).filter(Boolean))].sort()
);

const uniqueConcurrenciesStr = computed(() =>
  uniqueConcurrencies.value.map(c => String(c))
);

const sourceOptions = computed(() =>
  ['手动', ...uniqueScheduleNames.value]
);

const uniqueProfiles = computed(() =>
  [...new Set(results.value.map(r => r.config?.profile_name).filter(Boolean))].sort()
);

// Comparison view state
const showCompareView = ref(false);

const filtered = computed(() => {
  let list = results.value.filter(r => {
    const c = r.config || {};
    if (modeFilter.value && c.mode !== modeFilter.value) return false;
    if (modelFilter.value && c.model !== modelFilter.value) return false;
    if (urlFilter.value && (c.base_url || '').replace(/\/+$/, '') !== urlFilter.value) return false;
    if (concurrencyFilter.value && String(c.concurrency) !== concurrencyFilter.value) return false;
    if (sourceFilter.value) {
      const src = r.schedule_name || '手动';
      if (src !== sourceFilter.value) return false;
    }
    if (siteFilter.value && (r.config?.profile_name || '') !== siteFilter.value) return false;
    if (search.value) {
      const hay = `${c.model} ${c.base_url} ${r.timestamp} ${r.test_id || ''} ${r.schedule_name || ''}`.toLowerCase();
      if (!hay.includes(search.value.toLowerCase())) return false;
    }
    return true;
  });

  list.sort((a, b) => {
    let va, vb;
    switch (sortKey.value) {
      case 'timestamp': va = a.timestamp || ''; vb = b.timestamp || ''; break;
      case 'test_id': va = a.test_id || ''; vb = b.test_id || ''; break;
      case 'concurrency': va = a.config?.concurrency || 0; vb = b.config?.concurrency || 0; break;
      case 'success_rate': va = a.summary?.success_rate || 0; vb = b.summary?.success_rate || 0; break;
      case 'ttft': va = a.percentiles?.TTFT?.P50 || 999; vb = b.percentiles?.TTFT?.P50 || 999; break;
      case 'e2e': va = a.percentiles?.E2E?.P50 || 999; vb = b.percentiles?.E2E?.P50 || 999; break;
      case 'throughput': va = a.summary?.throughput_rps || 0; vb = b.summary?.throughput_rps || 0; break;
      case 'cost': va = a.summary?.cost_total_usd || 0; vb = b.summary?.cost_total_usd || 0; break;
      default: va = a.timestamp || ''; vb = b.timestamp || '';
    }
    const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
    return sortDir.value === 'asc' ? cmp : -cmp;
  });

  return list;
});

const pageNumbers = computed(() => {
  const t = totalPages.value;
  if (t <= 7) return Array.from({ length: t }, (_, i) => i + 1);
  const pages = new Set([1, t]);
  for (let i = page.value - 2; i <= page.value + 2; i++) {
    if (i >= 1 && i <= t) pages.add(i);
  }
  return [...pages].sort((a, b) => a - b);
});

// Comparison data for inline compare view
const compareData = computed(() => {
  const list = filtered.value;
  const selected = [...compareSet].map(i => list[i]).filter(Boolean);
  if (selected.length < 2) return null;

  const metrics = [
    { label: '模型', getValue: r => r.config?.model || '-', higherIsBetter: null },
    { label: '并发', getValue: r => String(r.config?.concurrency || '-'), higherIsBetter: null },
    { label: 'TTFT P50', getValue: r => r.percentiles?.TTFT?.P50, higherIsBetter: false, format: fmtTime },
    { label: 'TPOT P50', getValue: r => r.percentiles?.TPOT?.P50, higherIsBetter: false, format: fmtTime },
    { label: 'Token/s', getValue: r => r.summary?.throughput_rps, higherIsBetter: true, format: v => fmtNum(v) + ' /s' },
    { label: '成功率', getValue: r => r.summary?.success_rate, higherIsBetter: true, format: fmtPct },
    { label: '错误', getValue: r => {
      const total = r.summary?.total_requests || 0;
      const success = r.summary?.successful_requests || 0;
      return total - success;
    }, higherIsBetter: false, format: v => String(v ?? '-') },
  ];

  return { records: selected, metrics };
});

// ---- Helpers ----
function successRateClass(rate) {
  if (rate == null) return '';
  return rate >= 95 ? 'success' : rate >= 80 ? 'warning' : 'danger';
}

// 记录顶层 errors 是 {错误类型: 次数}（后端 report["errors"]），按次数降序
function sortedErrorEntries(r) {
  const errs = r.errors || {};
  return Object.entries(errs).filter(([t]) => t).sort((a, b) => b[1] - a[1]);
}

// 失败列内联展示的主要错误类型（截断，避免过长撑宽）
function topErrorType(r) {
  const entries = sortedErrorEntries(r);
  if (!entries.length) return '';
  const t = entries[0][0];
  return t.length > 10 ? t.slice(0, 10) + '…' : t;
}

// 失败列悬停提示：完整错误类型 + 次数
function errorTypesTitle(r) {
  const entries = sortedErrorEntries(r);
  if (!entries.length) return r.summary?.failed_count ? '有失败但无错误类型明细' : '无失败';
  return entries.map(([t, c]) => `${t}: ${c}`).join('\n');
}

function latencyClass(value, good, warn) {
  if (value == null) return '';
  return value <= good ? 'success' : value <= warn ? 'warning' : 'danger';
}

function qualityClass(value, good, warn) {
  if (value == null) return '';
  return value >= good ? 'success' : value >= warn ? 'warning' : 'danger';
}

function diagTooltip(r) {
  const statusMap = {
    passed: 'Claude 缓存命中',
    warning: '缓存证据异常',
    inconclusive: '无法判断',
    no_usage_fields: '未返回缓存 usage',
    no_cache: '未达到缓存阈值',
    error: '诊断失败',
  };
  const s = statusMap[r.channel_diagnostic_status] || '未知';
  const rate = r.channel_diagnostic_cache_hit_rate;
  const parts = [`诊断: ${s}`];
  if (rate != null) parts.push(`缓存命中率: ${(rate * 100).toFixed(1)}%`);
  return parts.join(' | ');
}

// ---- Actions ----
async function refresh() {
  const params = new URLSearchParams({ limit: pageSize, offset: (page.value - 1) * pageSize, raw: true });
  if (timeRangeStore.hours) params.set('hours', timeRangeStore.hours);
  const data = await api(`/api/results?${params}`);
  results.value = data.items || [];
  total.value = data.total || 0;
  await nextTick();
  tryAutoCompare();
  tryAutoExpand();
}

function goToPage(p) {
  if (p < 1 || p > totalPages.value || p === page.value) return;
  page.value = p;
  // Clear expanded state
  for (const k of Object.keys(detailHtml)) delete detailHtml[k];
  expandedRows.clear();
  refresh();
}

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc';
  } else {
    sortKey.value = key;
    sortDir.value = 'desc';
  }
}

function toggleDetail(idx) {
  if (expandedRows.has(idx)) {
    expandedRows.delete(idx);
    delete detailHtml[idx];
  } else {
    expandedRows.add(idx);
    const r = filtered.value[idx];
    if (r) detailHtml[idx] = renderResultDetail(r);
  }
}

function onRowClick(r, idx, event) {
  if (event.target.tagName === 'INPUT' || event.target.closest('.del-btn')) return;
  toggleDetail(idx);
}

function toggleCompare(idx) {
  if (compareSet.has(idx)) {
    compareSet.delete(idx);
  } else {
    compareSet.add(idx);
  }
}

function clearCompare() {
  compareSet.clear();
  showCompareView.value = false;
}

function enterCompare() {
  if (compareSet.size < 2) { toast('请至少选择 2 条记录', 'info'); return; }
  showCompareView.value = true;
}

function exitCompare() {
  showCompareView.value = false;
}

function rerunAtSite(r) {
  const profileName = r.config?.profile_name;
  if (!profileName) { toast('该记录无站点信息', 'info'); return; }
  router.push('/sites/' + encodeURIComponent(profileName));
}

function getPctDiff(metric, records, idx) {
  if (metric.higherIsBetter === null) return null;
  const vals = records.map(r => metric.getValue(r));
  const current = vals[idx];
  if (current == null) return null;
  const nonNull = vals.filter(v => v != null);
  if (nonNull.length < 2) return null;

  let best;
  if (metric.higherIsBetter) {
    best = Math.max(...nonNull);
  } else {
    best = Math.min(...nonNull);
  }
  if (best === 0 || current === best) return null;
  const diff = ((current - best) / Math.abs(best)) * 100;
  if (Math.abs(diff) < 0.1) return null;
  return diff > 0 ? `+${diff.toFixed(0)}%` : `${diff.toFixed(0)}%`;
}

function compareTagLabel(r) {
  if (!r) return '?';
  const c = r.config || {};
  return c.profile_name || c.model || r.test_id || '?';
}

function getCompareCellClassFor(metric, records, idx) {
  if (metric.higherIsBetter === null) return '';
  const vals = records.map(r => metric.getValue(r));
  const current = vals[idx];
  if (current == null || typeof current !== 'number') return '';
  const nonNull = vals.filter(v => v != null && typeof v === 'number');
  if (nonNull.length < 2) return '';
  const best = metric.higherIsBetter ? Math.max(...nonNull) : Math.min(...nonNull);
  if (current === best) return 'compare-best';
  return '';
}

function formatMetricValue(metric, rec) {
  const val = metric.getValue(rec);
  if (val == null) return '-';
  if (metric.format) return metric.format(val);
  return String(val);
}

function isPositiveDiff(metric, records, idx) {
  const vals = records.map(r => metric.getValue(r));
  const current = vals[idx];
  if (current == null) return false;
  const nonNull = vals.filter(v => v != null && typeof v === 'number');
  if (nonNull.length < 2) return false;
  const best = metric.higherIsBetter ? Math.max(...nonNull) : Math.min(...nonNull);
  if (best === 0) return false;
  const diff = ((current - best) / Math.abs(best)) * 100;
  return diff > 0;
}

function rerunResult(r) {
  const c = r.config || {};
  const profileName = c.profile_name || '';
  if (profileName) {
    router.push(`/sites/${encodeURIComponent(profileName)}`);
  } else {
    toast('无法定位站点', 'info');
  }
}

function deleteResult(filename) {
  if (pendingDelete.value === filename) {
    clearTimeout(deleteTimer);
    pendingDelete.value = null;
    confirmDelete(filename);
    return;
  }
  pendingDelete.value = filename;
  deleteTimer = setTimeout(() => {
    if (pendingDelete.value === filename) {
      pendingDelete.value = null;
    }
  }, 3000);
}

async function confirmDelete(filename) {
  await api('/api/results/' + filename, { method: 'DELETE' });
  toast('已删除', 'info');
  refresh();
}

// ---- Diagnostic History Functions ----
async function loadDiagHistory(reset = true) {
  if (diagLoading.value) return;
  diagLoading.value = true;
  if (reset) {
    diagOffset.value = 0;
    diagExpandedId.value = null;
    diagDetailCache.value = {};
  }
  try {
    const params = { limit: diagPageSize, offset: diagOffset.value };
    if (diagFilterProfile.value) params.profile_name = diagFilterProfile.value;
    if (diagFilterModel.value) params.model = diagFilterModel.value;
    if (diagFilterStatus.value) params.status = diagFilterStatus.value;
    const data = await listChannelDiagnostics(params);
    if (reset) {
      diagItems.value = data.items;
    } else {
      diagItems.value.push(...data.items);
    }
    diagTotal.value = data.total;
  } finally {
    diagLoading.value = false;
  }
}

async function loadDiagFilterOptions() {
  const params = {};
  if (diagFilterProfile.value) params.profile_name = diagFilterProfile.value;
  if (diagFilterModel.value) params.model = diagFilterModel.value;
  if (diagFilterStatus.value) params.status = diagFilterStatus.value;
  diagFilterOptions.value = await getDiagnosticFilterOptions(params);
}

function onDiagFilterChange() {
  loadDiagFilterOptions();
  loadDiagHistory(true);
}

function loadMoreDiag() {
  diagOffset.value += diagPageSize;
  loadDiagHistory(false);
}

async function toggleDiagExpand(id) {
  if (diagExpandedId.value === id) {
    diagExpandedId.value = null;
    return;
  }
  diagExpandedId.value = id;
  if (diagDetailCache.value[id]) return;

  diagDetailLoading.value = true;
  diagDetailError.value = false;
  try {
    const detail = await getChannelDiagnostic(id);
    diagDetailCache.value[id] = detail;
  } catch {
    diagDetailError.value = true;
  } finally {
    diagDetailLoading.value = false;
  }
}

function retryDiagDetail() {
  if (diagExpandedId.value) {
    delete diagDetailCache.value[diagExpandedId.value];
    toggleDiagExpand(diagExpandedId.value);
  }
}

function openCompare() {
  const list = filtered.value;
  const selected = [...compareSet].map(i => list[i]).filter(Boolean);
  if (selected.length < 2) { toast('请至少选择 2 条记录', 'info'); return; }

  const el = document.getElementById('compareContent');
  let html = '<div class="table-wrap"><table class="pct-table"><thead><tr><th style="text-transform:none">指标</th>';
  selected.forEach(r => {
    const c = r.config || {};
    const taskLabel = r.schedule_name || '';
    const nameLabel = c.profile_name || c.model || '?';
    html += `<th style="text-transform:none">${taskLabel ? '<div style="font-size:11px;color:var(--accent);margin-bottom:2px;font-weight:600">' + escHtml(taskLabel) + '</div>' : ''}${escHtml(nameLabel)}<br><small style="font-weight:400;text-transform:none">${escHtml(String(c.concurrency || '?'))}c · ${escHtml(fmtTimestamp(r.timestamp).slice(5))}</small></th>`;
  });
  html += '</tr></thead><tbody>';

  const rows = [
    ['成功率', r => fmtPct(r.summary?.success_rate), r => r.summary?.success_rate, true],
    ['吞吐量', r => fmtNum(r.summary?.throughput_rps) + ' /s', r => r.summary?.throughput_rps, true],
    ['Token 速率', r => fmtNum(r.summary?.token_throughput_tps, 0) + ' t/s', r => r.summary?.token_throughput_tps, true],
    ['TTFT P50', r => fmtTime(r.percentiles?.TTFT?.P50), r => r.percentiles?.TTFT?.P50, false],
    ['TTFT P95', r => fmtTime(r.percentiles?.TTFT?.P95), r => r.percentiles?.TTFT?.P95, false],
    ['TTFT P99', r => fmtTime(r.percentiles?.TTFT?.P99), r => r.percentiles?.TTFT?.P99, false],
    ['TPOT P50', r => fmtTime(r.percentiles?.TPOT?.P50), r => r.percentiles?.TPOT?.P50, false],
    ['TPOT P95', r => fmtTime(r.percentiles?.TPOT?.P95), r => r.percentiles?.TPOT?.P95, false],
    ['E2E P50', r => fmtTime(r.percentiles?.E2E?.P50), r => r.percentiles?.E2E?.P50, false],
    ['E2E P95', r => fmtTime(r.percentiles?.E2E?.P95), r => r.percentiles?.E2E?.P95, false],
    ['E2E P99', r => fmtTime(r.percentiles?.E2E?.P99), r => r.percentiles?.E2E?.P99, false],
    ['平均输出 Tokens', r => fmtNum(r.summary?.avg_output_tokens, 0), r => r.summary?.avg_output_tokens, null],
    ['输入 Tokens (P50)', r => fmtNum(r.summary?.input_tokens?.P50, 0), r => r.summary?.input_tokens?.P50, null],
    ['输出 Tokens (P50)', r => fmtNum(r.summary?.output_tokens?.P50, 0), r => r.summary?.output_tokens?.P50, null],
    ['总输入 Tokens', r => fmtBigNum(r.summary?.total_input_tokens), r => r.summary?.total_input_tokens, null],
    ['总输出 Tokens', r => fmtBigNum(r.summary?.total_output_tokens), r => r.summary?.total_output_tokens, null],
  ];

  rows.forEach(([label, fmtFn, valFn, higherIsBetter]) => {
    html += `<tr><td>${label}</td>`;
    let bestIdx = -1, worstIdx = -1;
    if (higherIsBetter !== null && selected.length >= 2) {
      const vals = selected.map(r => valFn(r) ?? null);
      const hasAny = vals.some(v => v != null);
      if (hasAny) {
        const nonNull = vals.map((v, i) => [v, i]).filter(([v]) => v != null);
        if (nonNull.length >= 2) {
          nonNull.sort((a, b) => higherIsBetter ? b[0] - a[0] : a[0] - b[0]);
          bestIdx = nonNull[0][1];
          worstIdx = nonNull[nonNull.length - 1][1];
          if (bestIdx === worstIdx) { bestIdx = -1; worstIdx = -1; }
        }
      }
    }
    selected.forEach((r, i) => {
      let cls = '';
      if (i === bestIdx) cls = ' class="compare-best"';
      else if (i === worstIdx) cls = ' class="compare-worst"';
      html += `<td${cls}>${fmtFn(r)}</td>`;
    });
    html += '</tr>';
  });

  html += '</tbody></table></div>';
  html += `<div style="margin-top:20px"><div class="card-title" style="margin-bottom:4px">TTFT & E2E 对比</div><div class="chart-container"><canvas id="compareChart"></canvas></div></div>`;

  el.innerHTML = html;
  document.getElementById('compareOverlay').classList.add('open');

  setTimeout(() => {
    const canvas = document.getElementById('compareChart');
    if (!canvas) return;
    const labels = selected.map(r => {
      const name = r.schedule_name || r.config?.profile_name || r.config?.model || '?';
      return `${name.slice(-16)} ${r.config?.concurrency || '?'}c`;
    });
    new Chart(canvas, {
        type: 'bar',
        data: {
          labels,
          datasets: [
            { label: 'TTFT P50', data: selected.map(r => r.percentiles?.TTFT?.P50 || 0), backgroundColor: '#3B7DD644', borderColor: '#3B7DD6', borderWidth: 2, borderRadius: 4 },
            { label: 'TTFT P95', data: selected.map(r => r.percentiles?.TTFT?.P95 || 0), backgroundColor: '#F59E3B44', borderColor: '#F59E3B', borderWidth: 2, borderRadius: 4 },
            { label: 'E2E P50', data: selected.map(r => r.percentiles?.E2E?.P50 || 0), backgroundColor: '#E85D2644', borderColor: '#E85D26', borderWidth: 2, borderRadius: 4 },
            { label: 'E2E P95', data: selected.map(r => r.percentiles?.E2E?.P95 || 0), backgroundColor: '#D63B3B44', borderColor: '#D63B3B', borderWidth: 2, borderRadius: 4 },
          ]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { position: 'top', labels: { font: { family: "'DM Sans'" }, usePointStyle: true, pointStyle: 'rectRounded' } },
            tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${fmtTime(ctx.parsed.y)}` } }
          },
          scales: {
            y: { title: { display: true, text: 'Seconds' }, grid: { color: '#F0EEE9' }, ticks: { callback: v => fmtTime(v) } },
            x: { grid: { display: false } }
          }
        }
      });
  }, 50);
}

function _showDetailOverlay(detail) {
  window.showDetailOverlay(renderResultDetail(detail));
}


// ---- Auto-compare from multi-bench results ----
function tryAutoCompare() {
  if (!store.pendingCompareFilenames) return;
  const filenames = store.pendingCompareFilenames;
  store.pendingCompareFilenames = null;
  nextTick(() => {
    const indices = [];
    for (const fn of filenames) {
      const idx = filtered.value.findIndex(r => r.filename === fn);
      if (idx >= 0) indices.push(idx);
    }
    if (indices.length >= 2) {
      indices.forEach(i => compareSet.add(i));
      setTimeout(() => { showCompareView.value = true; }, 200);
    }
  });
}

// ---- Auto-expand from dashboard/schedules navigation ----
function tryAutoExpand() {
  if (!store.pendingFilename) return;
  const fn = store.pendingFilename;
  store.pendingFilename = null;

  // Try to find in current page
  let foundIdx = -1;
  let foundChildIdx = -1;
  for (let i = 0; i < filtered.value.length; i++) {
    const r = filtered.value[i];
    if (r.filename === fn) { foundIdx = i; break; }
    if (r.children) {
      const ci = r.children.findIndex(c => c.filename === fn);
      if (ci >= 0) { foundIdx = i; foundChildIdx = ci; break; }
    }
  }

  if (foundIdx >= 0) {
    if (foundChildIdx >= 0) {
      // TODO: group expansion not yet implemented (toggleGroupExpand/toggleGroupChildDetail don't exist)
      // Fallback: expand the parent record
      toggleDetail(foundIdx);
    } else {
      toggleDetail(foundIdx);
    }
  } else {
    // Not on current page: fetch single detail and show overlay
    api('/api/results/' + encodeURIComponent(fn)).then(detail => {
      if (detail && !detail.error) {
        _showDetailOverlay(detail);
      }
    }).catch(() => {});
  }
}

// ---- Lifecycle ----
onMounted(() => {
  if (localStorage.getItem('token')) {
    refresh();
  }
  store.refreshFn = refresh;
  loadDiagFilterOptions();
});

onUnmounted(() => {
  if (deleteTimer) clearTimeout(deleteTimer);
  store.refreshFn = null;
});

const route = useRoute();
const router = useRouter();
// Watch for route change to refresh
watch(() => route.path, (val) => {
  if (val === '/history') refresh();
});

watch(() => timeRangeStore.hours, () => {
  page.value = 1;
  refresh();
});

</script>

<style scoped>
.diag-icon.diag-passed { background: var(--success); }
.diag-icon.diag-warning { background: var(--warning); }
.diag-icon.diag-critical { background: var(--danger); }
.diag-icon.diag-inconclusive { background: var(--text-tertiary); }
.diag-icon.diag-no_usage_fields { background: var(--info); }
.diag-icon.diag-error { background: var(--danger); }

.tab-switcher {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0;
}
.tab-btn {
  padding: 8px 16px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: all 0.15s;
}
.tab-btn:hover {
  color: var(--text);
}
.tab-btn.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}
/* 历史记录表格 */
.history-table {
  width: 100%;
  border-collapse: collapse;
}

.history-table th {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
  background: var(--surface-raised, var(--bg-secondary));
}

.history-table td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-subtle);
  vertical-align: middle;
}

.history-row {
  cursor: pointer;
  transition: background 0.1s;
}

.history-row:hover {
  background: var(--surface-raised, var(--bg-secondary));
}

.history-row.expanded {
  background: var(--surface-raised, var(--bg-secondary));
}

.history-detail-row td {
  background: var(--bg);
  border-bottom: 2px solid var(--border);
}

.success { color: var(--success); }
.warning { color: var(--warning); }
.danger { color: var(--danger); }

.delete-undo {
  color: var(--danger);
  font-weight: 600;
}

.btn-danger-text {
  color: var(--danger) !important;
}

.btn-danger-text:hover {
  background: var(--danger-bg, #fef2f2) !important;
}

/* 响应式 */
@media (max-width: 768px) {
  .history-table th:nth-child(4),
  .history-table td:nth-child(4) {
    display: none;
  }
}
</style>
