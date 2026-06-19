<template>
  <div class="board-wrap">
    <table class="board">
      <thead><tr>
        <th></th>
        <th class="th-sort" @click="setSort('name')">站点 / 模型<span class="sarr">{{ sortArrow('name') }}</span></th>
        <th class="th-sort" @click="setSort('avail')">可用性 · 近{{ buckets }}<span class="sarr">{{ sortArrow('avail') }}</span></th>
        <th class="th-sort" @click="setSort('ttft')">TTFT P50<span class="sarr">{{ sortArrow('ttft') }}</span></th>
        <th>趋势</th>
        <th class="th-sort" @click="setSort('tps')">Token/s<span class="sarr">{{ sortArrow('tps') }}</span></th>
        <th class="th-sort" @click="setSort('inTok')" title="每请求输入 Token (P50)">输入Tok<span class="sarr">{{ sortArrow('inTok') }}</span></th>
        <th class="th-sort" @click="setSort('outTok')" title="每请求输出 Token (P50)">输出Tok<span class="sarr">{{ sortArrow('outTok') }}</span></th>
        <th class="th-sort" @click="setSort('rate')">成功率<span class="sarr">{{ sortArrow('rate') }}</span></th>
        <th class="th-sort" @click="setSort('last')">最近测试<span class="sarr">{{ sortArrow('last') }}</span></th>
        <th></th>
      </tr></thead>
      <tbody>
        <template v-for="site in sortedSites" :key="site.profile.name">
          <tr class="site-row" :class="'h-' + site.health" @click="toggleExpand(site.profile.name)">
            <td><span class="dot" :class="'d-' + site.health"></span></td>
            <td>
              <button class="fav" :class="{ on: isFavorite(site.profile.name) }" @click.stop="emit('toggle-favorite', site.profile.name)" :title="isFavorite(site.profile.name) ? '取消收藏' : '收藏'">★</button>
              <router-link class="sname" :to="`/sites/${encodeURIComponent(site.profile.name)}`" @click.stop>{{ site.profile.name }}</router-link>
              <span class="mcount">{{ getModelMetrics(site).length }} 模型</span>
              <span v-if="topError(site)" class="err-pill" :title="errPillTitle(site)">{{ topError(site).type }} ×{{ topError(site).count }}</span>
            </td>
            <td><span class="avail-bars" :class="{ dim: isExpanded(site.profile.name) }"><i v-for="(rate,i) in siteSeries(site)" :key="i" :class="'ab-'+availabilityClass(rate)" :title="rate==null?'无数据':('成功率 '+rate.toFixed(1)+'%')"></i></span></td>
            <td>{{ siteAvg(site,'ttft') != null ? fmtTime(siteAvg(site,'ttft')) : '-' }} <span class="agg" v-if="siteAvg(site,'ttft')!=null">平均</span></td>
            <td></td>
            <td>{{ siteAvg(site,'tps') != null ? fmtNum(siteAvg(site,'tps'),0) : '-' }}</td>
            <td>{{ siteAvg(site,'inTok') != null ? fmtNum(siteAvg(site,'inTok'),0) : '-' }}</td>
            <td>{{ siteAvg(site,'outTok') != null ? fmtNum(siteAvg(site,'outTok'),0) : '-' }}</td>
            <td><span class="rate" :class="rateClass(siteRate(site))">{{ siteRate(site)!=null ? fmtPct(siteRate(site)) : '-' }}</span></td>
            <td>{{ site.last_test_at ? relativeTime(site.last_test_at) : '未测试' }}</td>
            <td class="row-actions" @click.stop>
              <button class="btn btn-ghost btn-sm" @click="emit('test-site', site)">一键测试</button>
              <button class="btn btn-sm" @click="emit('navigate-to-detail', site)">详情 →</button>
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
            <td>{{ m.inTok!=null ? fmtNum(m.inTok,0) : '-' }}</td>
            <td>{{ m.outTok!=null ? fmtNum(m.outTok,0) : '-' }}</td>
            <td><span class="rate" :class="rateClass(m.successRate)">{{ m.successRate!=null ? fmtPct(m.successRate) : '-' }}</span></td>
            <td></td>
            <td></td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';
import { fmtTime, fmtPct, fmtNum } from '../utils/formatters';
import { getModelMetrics, sparklinePoints, latencyTrendColor, availabilityClass, siteAvgSeries, seriesAvg, getErrorTypes, getTotalErrorCount } from '../utils/siteMetrics';

const props = defineProps({
  sites: { type: Array, default: () => [] },
  availabilityLut: { type: Object, default: () => ({}) },
  buckets: { type: Number, default: 24 },
  favorites: { type: Set, default: () => new Set() },
});
const emit = defineEmits(['test-site', 'toggle-favorite', 'navigate-to-detail']);

function isFavorite(name) { return props.favorites.has(name); }

// 站点主要错误类型徽章：仅在所选范围内有失败时显示，给已亮红的站点补上「为什么」
function topError(site) {
  const types = getErrorTypes(site);
  if (!types.length) return null;
  const t = types[0].type || '';
  return { type: t.length > 8 ? t.slice(0, 8) + '…' : t, count: types[0].count };
}
function errPillTitle(site) {
  const types = getErrorTypes(site);
  if (!types.length) return '';
  const lines = types.map(e => `${e.type}: ${e.count}`);
  return `主要错误类型\n${lines.join('\n')}\n合计 ${getTotalErrorCount(site)} 次`;
}

// ---- 看板展开态（不持久化）+ 可用性辅助 ----
const expanded = ref(new Set());
function toggleExpand(name) { const n = new Set(expanded.value); n.has(name) ? n.delete(name) : n.add(name); expanded.value = n; }
function isExpanded(name) { return expanded.value.has(name); }
function modelRows(site) {
  const lut = props.availabilityLut[site.profile.name] || {};
  // 成功率取可用率柱（series）的均值，与柱同源、覆盖所选时间范围
  return getModelMetrics(site).map(m => {
    const series = lut[m.model] || [];
    return { ...m, series, successRate: seriesAvg(series) };
  });
}
function siteSeries(site) {
  const lut = props.availabilityLut[site.profile.name] || {};
  return siteAvgSeries(Object.values(lut));
}
// 站点成功率 = 站点可用率柱的均值（同源、反映所选时间范围，而非最近一次）
function siteRate(site) {
  return seriesAvg(siteSeries(site));
}
function siteAvg(site, key) {
  const vals = getModelMetrics(site).map(m => m[key]).filter(v => v != null);
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
}

// ---- 列排序：点击列头 升序 → 降序 → 默认 ----
const sortKey = ref('');
const sortDir = ref('asc');
function setSort(key) {
  if (sortKey.value !== key) { sortKey.value = key; sortDir.value = 'asc'; }
  else if (sortDir.value === 'asc') { sortDir.value = 'desc'; }
  else { sortKey.value = ''; }
}
function sortArrow(key) {
  if (sortKey.value !== key) return '';
  return sortDir.value === 'asc' ? '▲' : '▼';
}
function sortValue(site, key) {
  switch (key) {
    case 'name': return site.profile?.name || '';
    case 'avail': { const s = siteSeries(site).filter(v => v != null); return s.length ? s.reduce((a, b) => a + b, 0) / s.length : null; }
    case 'ttft': return siteAvg(site, 'ttft');
    case 'tps': return siteAvg(site, 'tps');
    case 'inTok': return siteAvg(site, 'inTok');
    case 'outTok': return siteAvg(site, 'outTok');
    case 'rate': return siteRate(site);
    case 'last': return site.last_test_at || '';
    default: return null;
  }
}

// 组件内的看板列排序：筛选/搜索/默认智能排序已由父组件完成，这里只处理手动列排序。
const sortedSites = computed(() => {
  if (!sortKey.value) return props.sites;
  const dir = sortDir.value === 'asc' ? 1 : -1, key = sortKey.value;
  return [...props.sites].sort((a, b) => {
    const va = sortValue(a, key), vb = sortValue(b, key);
    const na = va == null || va === '', nb = vb == null || vb === '';
    if (na && nb) return 0;
    if (na) return 1;
    if (nb) return -1;
    return (typeof va === 'string' ? va.localeCompare(vb) : va - vb) * dir;
  });
});

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
</script>

<style scoped>
/* ---- Sparkline (model row) ---- */
.sparkline {
  display: block;
  vertical-align: middle;
}

/* ---- Site × Model Health Board ---- */
.avail-bars { display:inline-flex; align-items:flex-end; gap:1.5px; }
.avail-bars i { display:inline-block; width:4px; height:16px; border-radius:1px; background:var(--border); }
.avail-bars.sm i { height:13px; }
.avail-bars.dim { opacity:.3; }
.avail-bars i.ab-up { background:#21a366; }
.avail-bars i.ab-degraded { background:#f5a623; }
.avail-bars i.ab-down { background:#e5484d; }
.avail-bars i.ab-na { background:var(--border-subtle, #e5e5e5); }
table.board { width:100%; border-collapse:collapse; font-size:12.5px; }
table.board th { text-align:left; font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:var(--text-tertiary); padding:8px 10px; border-bottom:1px solid var(--border); white-space:nowrap; }
.th-sort { cursor:pointer; user-select:none; }
.th-sort:hover { color:var(--text-secondary); }
.sarr { margin-left:3px; font-size:9px; color:var(--accent); }
table.board td { padding:8px 10px; border-bottom:1px solid var(--border-subtle); white-space:nowrap; vertical-align:middle; }
.site-row { cursor:pointer; } .site-row:hover td { background:var(--border-subtle); }
.site-row.h-error td { background:#fef6f6; }
.model-row td { background:var(--bg, #fafafa); }
.mname { padding-left:26px; color:var(--text-secondary); font-weight:600; }
.sname { font-weight:700; color:var(--text-primary); text-decoration:none; }
.sname:hover { color:var(--accent); }
.mcount { font-size:10.5px; font-weight:600; color:#6b7280; background:var(--border-subtle); border-radius:999px; padding:1px 7px; margin-left:6px; }
/* 错误类型徽章：克制的琥珀色，不抢健康点的红，只解释「为什么有失败」 */
.err-pill { font-size:10.5px; font-weight:600; color:#9a5b00; background:#fdf0d5; border:1px solid #f3d9a6; border-radius:999px; padding:1px 7px; margin-left:6px; cursor:default; white-space:nowrap; }
.fav { background:none; border:none; cursor:pointer; color:var(--text-tertiary); font-size:13px; margin-right:7px; }
.fav.on { color:var(--warning); }
.agg { font-size:9px; color:var(--text-tertiary); }
.row-actions { display:flex; gap:6px; justify-content:flex-end; }
.spark-na { color:var(--text-tertiary); }
/* 表格行首健康状态点；SitesView 的 health-bar 另有一份同名 scoped 样式，非冗余 */
.dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
.dot.d-healthy { background:var(--success); } .dot.d-error { background:var(--danger); } .dot.d-untested { background:var(--text-tertiary); }
</style>
