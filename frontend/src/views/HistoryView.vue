<template>
  <section class="tab-content active">
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
      </div>
      <div class="compare-btn-wrap" :class="{ visible: compareSet.size >= 2 }">
        <button class="btn btn-primary btn-sm" @click="openCompare()">对比</button>
        <button class="btn btn-ghost btn-sm" @click="clearCompare()">清除</button>
      </div>
    </div>

    <div class="card" style="padding:0;overflow:hidden">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width:30px"></th>
              <th style="width:90px">测试 ID</th>
              <th style="width:130px" class="sortable" :class="sortKey === 'timestamp' ? ('active-sort ' + sortDir) : ''" @click="toggleSort('timestamp')">时间 <span class="sort-arrow" v-if="sortKey === 'timestamp'">{{ sortDir === 'desc' ? '▼' : '▲' }}</span></th>
              <th style="width:130px">模型</th>
              <th style="max-width:200px">目标地址</th>
              <th style="width:60px" class="sortable" :class="sortKey === 'concurrency' ? ('active-sort ' + sortDir) : ''" @click="toggleSort('concurrency')">并发 <span class="sort-arrow" v-if="sortKey === 'concurrency'">{{ sortDir === 'desc' ? '▼' : '▲' }}</span></th>
              <th style="width:80px">模式</th>
              <th style="width:100px">来源</th>
              <th style="width:72px" class="sortable" :class="sortKey === 'success_rate' ? ('active-sort ' + sortDir) : ''" @click="toggleSort('success_rate')">成功率 <span class="sort-arrow" v-if="sortKey === 'success_rate'">{{ sortDir === 'desc' ? '▼' : '▲' }}</span></th>
              <th style="width:82px" class="sortable" :class="sortKey === 'ttft' ? ('active-sort ' + sortDir) : ''" @click="toggleSort('ttft')">TTFT P50 <span class="sort-arrow" v-if="sortKey === 'ttft'">{{ sortDir === 'desc' ? '▼' : '▲' }}</span></th>
              <th style="width:82px" class="sortable" :class="sortKey === 'e2e' ? ('active-sort ' + sortDir) : ''" @click="toggleSort('e2e')">E2E P50 <span class="sort-arrow" v-if="sortKey === 'e2e'">{{ sortDir === 'desc' ? '▼' : '▲' }}</span></th>
              <th style="width:100px" class="sortable" :class="sortKey === 'throughput' ? ('active-sort ' + sortDir) : ''" @click="toggleSort('throughput')">吞吐量 <span class="sort-arrow" v-if="sortKey === 'throughput'">{{ sortDir === 'desc' ? '▼' : '▲' }}</span></th>
              <th style="width:64px"></th>
            </tr>
          </thead>
          <tbody>
            <template v-if="!filtered.length">
              <tr>
                <td colspan="13" style="text-align:center;padding:40px;color:var(--text-tertiary)">暂无记录</td>
              </tr>
            </template>
            <template v-for="(r, idx) in filtered" :key="r.filename || idx">
              <!-- Main row -->
              <tr
                class="history-row"
                :class="{ expanded: !isGroup(r) && expandedRows.has(idx) }"
                style="cursor:pointer"
                @click="onRowClick(r, idx, $event)"
              >
                <td><input type="checkbox" class="compare-check" :checked="compareSet.has(idx)" @change="toggleCompare(idx)" @click.stop></td>
                <td style="font-family:var(--font-mono);font-size:11px;color:var(--text-tertiary)">{{ r.test_id || '-' }}</td>
                <td>{{ fmtTimestamp(r.timestamp) }}</td>
                <td style="max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="r.config?.model || ''">{{ r.config?.model || '-' }}</td>
                <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="r.config?.base_url || ''">{{ r.config?.base_url || '-' }}</td>
                <td>{{ r.config?.concurrency || '-' }}</td>
                <td>{{ r.config?.mode || '-' }}</td>
                <td style="font-size:12px;color:var(--text-tertiary);max-width:120px;overflow:hidden;white-space:nowrap">
                  <template v-if="r.schedule_name">
                    <template v-if="isGroup(r)">
                      <span style="font-weight:600;display:inline-block;max-width:70px;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom" :title="r.schedule_name">{{ r.schedule_name }}</span>
                      <span style="background:var(--accent);color:#fff;font-size:10px;padding:1px 6px;border-radius:8px;margin-left:4px;white-space:nowrap">{{ r.children_count }}次</span>
                    </template>
                    <template v-else><span style="display:inline-block;max-width:110px;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom" :title="r.schedule_name">{{ r.schedule_name }}</span></template>
                  </template>
                  <template v-else><span style="color:var(--accent)">手动</span></template>
                </td>
                <td :style="successRateStyle(r.summary?.success_rate) + ';font-weight:600'">{{ fmtPct(r.summary?.success_rate) }}</td>
                <td :style="latencyColorStyle(r.percentiles?.TTFT?.P50, 0.5, 2) + ';font-weight:600'">{{ fmtTime(r.percentiles?.TTFT?.P50) }}</td>
                <td :style="latencyColorStyle(r.percentiles?.E2E?.P50, 2, 10) + ';font-weight:600'">{{ fmtTime(r.percentiles?.E2E?.P50) }}</td>
                <td :style="qualityColorStyle(r.summary?.throughput_rps, 20, 5) + ';font-weight:600'">{{ fmtNum(r.summary?.throughput_rps) }} /s</td>
                <td style="white-space:nowrap">
                  <button class="del-btn expand-btn" @click.stop="rerunResult(r)" title="重新运行" style="color:var(--accent)">&#8635;</button>
                  <button class="del-btn expand-btn" @click.stop="deleteResult(r.filename || '')" title="删除" style="color:var(--danger)">
                    <span v-if="pendingDelete === (r.filename || '')" class="delete-undo">确认删除</span>
                    <span v-else>&#10005;</span>
                  </button>
                </td>
              </tr>

              <!-- Group children -->
              <template v-if="isGroup(r) && expandedGroups.has(idx)">
                <template v-for="(child, ci) in (r.children || [])" :key="child.filename || ci">
                  <tr
                    class="history-row group-child"
                    style="cursor:pointer"
                    @click="toggleGroupChildDetail(idx, ci)"
                  >
                    <td></td>
                    <td style="font-family:var(--font-mono);font-size:11px;color:var(--text-tertiary)">{{ child.test_id || '-' }}</td>
                    <td style="font-size:12px">{{ fmtTimestamp(child.timestamp) }}</td>
                    <td style="font-size:12px;max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="child.config?.model || ''">{{ child.config?.model || '-' }}</td>
                    <td style="font-size:12px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="child.config?.base_url || ''">{{ child.config?.base_url || '-' }}</td>
                    <td style="font-size:12px">{{ child.config?.concurrency || '-' }}</td>
                    <td style="font-size:12px">{{ child.config?.mode || '-' }}</td>
                    <td style="font-size:11px;color:var(--text-tertiary)">{{ child.schedule_name || '' }}</td>
                    <td :style="successRateStyle(child.summary?.success_rate) + ';font-weight:600;font-size:12px'">{{ fmtPct(child.summary?.success_rate) }}</td>
                    <td :style="latencyColorStyle(child.percentiles?.TTFT?.P50, 0.5, 2) + ';font-weight:600;font-size:12px'">{{ fmtTime(child.percentiles?.TTFT?.P50) }}</td>
                    <td :style="latencyColorStyle(child.percentiles?.E2E?.P50, 2, 10) + ';font-weight:600;font-size:12px'">{{ fmtTime(child.percentiles?.E2E?.P50) }}</td>
                    <td :style="qualityColorStyle(child.summary?.throughput_rps, 20, 5) + ';font-weight:600;font-size:12px'">{{ fmtNum(child.summary?.throughput_rps) }} /s</td>
                    <td>
                      <button class="del-btn expand-btn" @click.stop="rerunResult(child)" title="重新运行" style="color:var(--accent);font-size:11px">&#8635;</button>
                    </td>
                  </tr>
                  <tr class="detail-row" :class="{ open: groupChildDetailOpen(idx, ci) }">
                    <td colspan="13">
                      <div v-html="groupChildDetailHtml(idx, ci)"></div>
                    </td>
                  </tr>
                </template>
              </template>

              <!-- Detail row (non-group) -->
              <tr v-if="!isGroup(r)" class="detail-row" :class="{ open: expandedRows.has(idx) }">
                <td colspan="13">
                  <div v-html="detailHtml[idx]"></div>
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
  </section>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue';
import { api } from '../api/index.js';
import { useAppStore } from '../stores/app.js';
import { toast } from '../composables/useToast.js';
import {
  fmtTime, fmtTimestamp, fmtPct, fmtNum, fmtBigNum,
  escHtml, qualityColorStyle, latencyColorStyle
} from '../utils/formatters.js';
import { renderResultDetail } from '../utils/resultDetail.js';
import { Chart, registerables } from 'chart.js';
Chart.register(...registerables);
import FilterDropdown from '../components/FilterDropdown.vue';

const store = useAppStore();

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
const sortKey = ref('timestamp');
const sortDir = ref('desc');
const compareSet = reactive(new Set());
const expandedRows = reactive(new Set());
const expandedGroups = reactive(new Set());
const pendingDelete = ref(null);
let deleteTimer = null;

// Detail HTML caches
const detailHtml = reactive({});
const groupChildDetailHtmlMap = reactive({});

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

// ---- Helpers ----
function isGroup(r) {
  return r.children_count && r.children_count > 1;
}

function successRateStyle(rate) {
  if (rate == null) return '';
  return rate >= 95 ? 'color:var(--success)' : rate >= 80 ? 'color:var(--warning)' : 'color:var(--danger)';
}

function groupChildDetailKey(idx, ci) {
  return `${idx}-${ci}`;
}

function groupChildDetailOpen(idx, ci) {
  return !!groupChildDetailHtmlMap[groupChildDetailKey(idx, ci)];
}

function groupChildDetailHtml(idx, ci) {
  return groupChildDetailHtmlMap[groupChildDetailKey(idx, ci)] || '';
}

// ---- Actions ----
async function refresh() {
  const data = await api(`/api/results?limit=${pageSize}&offset=${(page.value - 1) * pageSize}`);
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
  for (const k of Object.keys(groupChildDetailHtmlMap)) delete groupChildDetailHtmlMap[k];
  expandedRows.clear();
  expandedGroups.clear();
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

function toggleGroupExpand(idx) {
  if (expandedGroups.has(idx)) {
    expandedGroups.delete(idx);
    // Clear child detail caches for this group
    for (const k of Object.keys(groupChildDetailHtmlMap)) {
      if (k.startsWith(idx + '-')) delete groupChildDetailHtmlMap[k];
    }
  } else {
    expandedGroups.add(idx);
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

function toggleGroupChildDetail(idx, ci) {
  const key = groupChildDetailKey(idx, ci);
  if (groupChildDetailHtmlMap[key]) {
    delete groupChildDetailHtmlMap[key];
  } else {
    const r = filtered.value[idx];
    const child = r?.children?.[ci];
    if (child) groupChildDetailHtmlMap[key] = renderResultDetail(child);
  }
}

function onRowClick(r, idx, event) {
  if (event.target.tagName === 'INPUT' || event.target.closest('.del-btn')) return;
  if (isGroup(r)) {
    toggleGroupExpand(idx);
  } else {
    toggleDetail(idx);
  }
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
}

function rerunResult(r) {
  const c = r.config || {};
  store.rerunConfig = {
    profile_name: c.profile_name || '',
    base_url: c.base_url || '',
    model: c.model || '',
    max_tokens: c.max_tokens || 512,
    concurrency: c.concurrency || 100,
    mode: c.mode || 'burst',
    duration: c.duration || 120,
    timeout: c.timeout || 120,
    system_prompt: c.system_prompt || '',
    user_prompt: c.user_prompt || '',
  };
  store.switchTab('benchmark');
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

function closeDetailOverlay() {
  document.getElementById('detailOverlay')?.classList.remove('open');
}

function closeCompare() {
  document.getElementById('compareOverlay')?.classList.remove('open');
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
      setTimeout(() => openCompare(), 200);
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
      // Child in a group: expand group then show child detail
      toggleGroupExpand(foundIdx);
      nextTick(() => {
        toggleGroupChildDetail(foundIdx, foundChildIdx);
      });
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
});

onUnmounted(() => {
  if (deleteTimer) clearTimeout(deleteTimer);
});

import { useRoute } from 'vue-router';
const route = useRoute();
// Watch for route change to refresh
watch(() => route.path, (val) => {
  if (val === '/history') refresh();
});

</script>
