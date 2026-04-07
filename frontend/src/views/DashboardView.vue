<template>
  <section class="tab-content active">
    <div v-if="loading" style="text-align:center;color:var(--text-tertiary);padding:40px">加载中...</div>
    <div v-else v-html="contentHtml"></div>
  </section>
</template>

<script setup>
import { ref, watch } from 'vue';
import { useAppStore } from '../stores/app';
import { getResults } from '../api';
import { fmtTime, fmtPct, fmtNum, escHtml, infoIconHtml } from '../utils/formatters';

const store = useAppStore();
const loading = ref(false);
const contentHtml = ref('');

function host(url) {
  if (!url) return '-';
  try { return new URL(url).hostname; } catch { return url; }
}

function shortModel(m) {
  if (!m) return '-';
  return m.replace('claude-', '').replace('-20251001', '');
}

function relativeTime(ts) {
  if (!ts) return '-';
  const y = +ts.slice(0,4), mo = +ts.slice(4,6)-1, d = +ts.slice(6,8);
  const h = +ts.slice(9,11), mi = +ts.slice(11,13);
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
  return ts.slice(4,6) + '/' + ts.slice(6,8) + ' ' + ts.slice(9,11) + ':' + ts.slice(11,13);
}

function aggregateRuns(runs) {
  const totalReqs = runs.reduce((s, r) => s + (r.summary?.total_requests || 0), 0);
  const totalSuccess = runs.reduce((s, r) => s + (r.summary?.success_count || 0), 0);
  const avgRate = totalReqs > 0 ? (totalSuccess / totalReqs * 100) : 0;
  const ttfts = runs.map(r => r.percentiles?.TTFT?.P50).filter(v => v != null);
  const ttftMin = ttfts.length ? Math.min(...ttfts) : null;
  const ttftMax = ttfts.length ? Math.max(...ttfts) : null;
  const tpsList = runs.map(r => r.summary?.token_throughput_tps).filter(v => v != null && v > 0);
  const avgTps = tpsList.length ? tpsList.reduce((a, b) => a + b, 0) / tpsList.length : null;
  const name = runs[0]?.config?.model || runs[0]?.name || '-';
  return { name, count: runs.length, avgRate, ttftMin, ttftMax, avgTps };
}

function renderAggRow(item, extra = '') {
  const rateClass = item.avgRate >= 95 ? 'success' : item.avgRate >= 80 ? 'accent' : 'danger';
  let ttftStr = '-';
  if (item.ttftMin != null && item.ttftMax != null) {
    ttftStr = item.ttftMin === item.ttftMax
      ? fmtTime(item.ttftMin)
      : fmtTime(item.ttftMin) + ' ~ ' + fmtTime(item.ttftMax);
  }
  const displayName = item.name.includes('.') ? item.name : shortModel(item.name);
  return `<tr>
    <td class="matrix-model">${escHtml(displayName)}${extra}</td>
    <td style="text-align:center">${item.count}</td>
    <td><span class="rate-badge ${rateClass}">${item.avgRate.toFixed(1)}%</span></td>
    <td>${ttftStr}</td>
    <td>${item.avgTps != null ? fmtNum(item.avgTps, 0) + ' t/s' : '-'}</td>
  </tr>`;
}

function renderGroupHeading(name) {
  return `<div class="ep-heading"><div class="ep-name">${escHtml(name)}</div></div>`;
}

function renderGroupMeta(count, rateClass, avgRate) {
  return `<div class="ep-meta">
    <span class="ep-count">${count} 次</span>
    <span class="rate-badge ${rateClass}">${avgRate.toFixed(1)}%</span>
  </div>`;
}

function renderSectionCard(title, content, icon = 'globe') {
  const icons = {
    globe: 'M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24Zm88,104a87.62,87.62,0,0,1-6.4,32.94l-44.7-27.49a15.92,15.92,0,0,0-6.24-2.23l-22.82-3.08a16.11,16.11,0,0,0-16,7.86h-8.72l-3.8-7.86a15.91,15.91,0,0,0-11-8.67l-8-1.73L96.14,104h16.71a16.06,16.06,0,0,0,7.73-2l12.25-6.76a16.62,16.62,0,0,0,3-2.14l26.91-24.34A15.93,15.93,0,0,0,166,49.1l-.36-.65A88.11,88.11,0,0,1,216,128ZM143.31,41.34,152,56.9,125.09,81.24,112.85,88H96.14a16,16,0,0,0-13.88,8l-8.73,15.23L63.38,84.19,74.32,58.32a87.87,87.87,0,0,1,69-17ZM40,128a87.53,87.53,0,0,1,8.54-37.8l11.34,30.27a16,16,0,0,0,11.62,10l21.43,4.61L96.74,143a16.09,16.09,0,0,0,14.4,9h1.48l-7.23,16.23a16,16,0,0,0,2.86,17.37l.14.14L128,205.94l-1.94,10A88.11,88.11,0,0,1,40,128Zm102.58,86.78,1.13-5.81a16.09,16.09,0,0,0-4-13.9,1.85,1.85,0,0,1-.14-.14L120,174.74,133.7,144l22.82,3.08,45.72,28.12A88.18,88.18,0,0,1,142.58,214.78Z',
    cube: 'M223.68,66.15,135.68,18h0a15.88,15.88,0,0,0-15.36,0l-88,48.17a16,16,0,0,0-8.32,14v95.64a16,16,0,0,0,8.32,14l88,48.17a15.88,15.88,0,0,0,15.36,0l88-48.17a16,16,0,0,0,8.32-14V80.18A16,16,0,0,0,223.68,66.15ZM128,32h0l80.34,44L128,120,47.66,76ZM40,90l80,43.78v85.79L40,175.82Zm96,129.57V133.82L216,90v85.78Z',
    recent: 'M136,80v43.47l36.12,21.67a8,8,0,0,1-8.24,13.72l-40-24A8,8,0,0,1,120,128V80a8,8,0,0,1,16,0Zm-8-48A95.44,95.44,0,0,0,60.08,60.15C52.81,67.51,46.35,74.59,40,82V64a8,8,0,0,0-16,0v40a8,8,0,0,0,8,8H72a8,8,0,0,0,0-16H49c7.15-8.42,14.27-16.35,22.39-24.57a80,80,0,1,1,1.66,114.75,8,8,0,1,0-11,11.64A96,96,0,1,0,128,32Z',
  };
  const path = icons[icon] || icons.globe;
  return `<section class="card dashboard-section-card">
    <div class="dashboard-section-header">
      <span class="dashboard-section-icon" aria-hidden="true">
        <svg viewBox="0 0 256 256" fill="currentColor"><path d="${path}"></path></svg>
      </span>
      <h2 class="dashboard-section-title">${escHtml(title)}</h2>
    </div>
    ${content}
  </section>`;
}

function renderHeroStats(results) {
  const totalTests = results.length;
  const models = new Set(results.map(r => r.config?.model).filter(Boolean));
  const endpoints = new Set(results.map(r => {
    try { return new URL(r.config?.base_url).hostname; } catch { return r.config?.base_url; }
  }).filter(Boolean));
  const totalRequests = results.reduce((s, r) => s + (r.summary?.total_requests || 0), 0);
  const totalSuccess = results.reduce((s, r) => s + (r.summary?.success_count || 0), 0);
  const overallRate = totalRequests > 0 ? (totalSuccess / totalRequests * 100) : 0;
  const rateClass = overallRate >= 95 ? 'success' : overallRate >= 80 ? 'accent' : 'danger';

  return `<div class="hero-stats">
    <div class="hero-stat"><div class="hero-stat-value">${totalTests}</div><div class="hero-stat-label">测试总数</div></div>
    <div class="hero-stat"><div class="hero-stat-value">${models.size}</div><div class="hero-stat-label">覆盖模型</div></div>
    <div class="hero-stat"><div class="hero-stat-value">${endpoints.size}</div><div class="hero-stat-label">目标服务器</div></div>
    <div class="hero-stat"><div class="hero-stat-value">${totalRequests.toLocaleString()}</div><div class="hero-stat-label">累计请求</div></div>
    <div class="hero-stat"><div class="hero-stat-value ${rateClass}">${overallRate.toFixed(1)}%</div><div class="hero-stat-label">总体成功率</div></div>
  </div>`;
}

function renderEndpointOverview(results) {
  const epGroups = {};
  for (const r of results) {
    const h = host(r.config?.base_url);
    if (!epGroups[h]) epGroups[h] = [];
    epGroups[h].push(r);
  }

  const endpoints = Object.entries(epGroups).map(([hostName, list]) => {
    const totalReqs = list.reduce((s, r) => s + (r.summary?.total_requests || 0), 0);
    const totalSuccess = list.reduce((s, r) => s + (r.summary?.success_count || 0), 0);
    const avgRate = totalReqs > 0 ? (totalSuccess / totalReqs * 100) : 0;

    const modelMap = {};
    for (const r of list) {
      const model = r.config?.model || '-';
      if (!modelMap[model]) modelMap[model] = [];
      modelMap[model].push(r);
    }
    const models = Object.entries(modelMap).map(([model, runs]) => {
      const agg = aggregateRuns(runs);
      agg.name = model;
      return agg;
    }).sort((a, b) => a.name.localeCompare(b.name));

    return { host: hostName, count: list.length, avgRate, models };
  }).sort((a, b) => b.count - a.count);

  let html = '<div class="ep-grid">';
  for (const ep of endpoints) {
    const epRateClass = ep.avgRate >= 95 ? 'success' : ep.avgRate >= 80 ? 'accent' : 'danger';
    html += `<div class="ep-group">
      <div class="ep-header">
        ${renderGroupHeading(ep.host)}
        ${renderGroupMeta(ep.count, epRateClass, ep.avgRate)}
      </div>
      <div class="table-wrap"><table class="matrix-table"><thead><tr>
        <th>模型</th><th>测试</th><th>成功率</th>
        <th>TTFT P50 ${infoIconHtml('TTFT')}</th><th>Token/s</th>
      </tr></thead><tbody>`;
    for (const m of ep.models) {
      html += renderAggRow(m);
    }
    html += '</tbody></table></div></div>';
  }
  html += '</div>';
  return renderSectionCard('目标服务器概览', html, 'globe');
}

function renderModelOverview(results) {
  const modelGroups = {};
  for (const r of results) {
    const model = r.config?.model || '-';
    if (!modelGroups[model]) modelGroups[model] = [];
    modelGroups[model].push(r);
  }

  const models = Object.entries(modelGroups).map(([model, list]) => {
    const totalReqs = list.reduce((s, r) => s + (r.summary?.total_requests || 0), 0);
    const totalSuccess = list.reduce((s, r) => s + (r.summary?.success_count || 0), 0);
    const avgRate = totalReqs > 0 ? (totalSuccess / totalReqs * 100) : 0;

    const hostMap = {};
    for (const r of list) {
      const h = host(r.config?.base_url);
      if (!hostMap[h]) hostMap[h] = [];
      hostMap[h].push(r);
    }
    const hosts = Object.entries(hostMap).map(([hostName, runs]) => {
      const agg = aggregateRuns(runs);
      agg.name = hostName;
      return agg;
    }).sort((a, b) => {
      if (Math.abs(b.avgRate - a.avgRate) > 5) return b.avgRate - a.avgRate;
      return (b.avgTps || 0) - (a.avgTps || 0);
    });

    return { model, count: list.length, avgRate, hosts };
  }).sort((a, b) => a.model.localeCompare(b.model));

  let html = '<div class="ep-grid">';
  for (const md of models) {
    const mdRateClass = md.avgRate >= 95 ? 'success' : md.avgRate >= 80 ? 'accent' : 'danger';
    html += `<div class="ep-group">
      <div class="ep-header">
        ${renderGroupHeading(shortModel(md.model))}
        ${renderGroupMeta(md.count, mdRateClass, md.avgRate)}
      </div>
      <div class="table-wrap"><table class="matrix-table"><thead><tr>
        <th>目标服务器</th><th>测试</th><th>成功率</th>
        <th>TTFT P50 ${infoIconHtml('TTFT')}</th><th>Token/s</th>
      </tr></thead><tbody>`;
    for (let i = 0; i < md.hosts.length; i++) {
      const h = md.hosts[i];
      const rankBadge = i === 0 && md.hosts.length > 1 ? ' <span class="rank-best">#1</span>' : '';
      html += renderAggRow(h, rankBadge);
    }
    html += '</tbody></table></div></div>';
  }
  html += '</div>';
  return renderSectionCard('模型性能概览', html, 'cube');
}

function renderRecentTests(results) {
  const recent = results.slice(0, 5);
  let html = `<div class="table-wrap"><table class="recent-table"><thead><tr>
      <th>ID</th><th>时间</th><th>模型</th><th>目标服务器</th>
      <th>并发</th><th>模式</th><th>成功率</th>
      <th>TTFT P50</th><th>Token/s</th>
    </tr></thead><tbody>`;

  for (const r of recent) {
    const c = r.config || {};
    const s = r.summary || {};
    const p = r.percentiles || {};
    const rate = s.success_rate;
    const rateClass = (rate || 0) >= 95 ? 'success' : (rate || 0) >= 80 ? 'accent' : 'danger';
    const tid = r.test_id || '-';
    html += `<tr class="recent-row" style="cursor:pointer" onclick="window.location.href='/history';window._autoExpandTestId='${escHtml(tid)}'">
      <td style="font-family:var(--font-mono);font-size:11px;color:var(--text-tertiary)">${escHtml(tid)}</td>
      <td>${relativeTime(r.timestamp)}</td>
      <td class="matrix-model">${escHtml(shortModel(c.model))}</td>
      <td class="matrix-host">${escHtml(host(c.base_url))}</td>
      <td style="text-align:center">${c.concurrency || '-'}</td>
      <td><span class="mode-tag ${c.mode || ''}">${c.mode || '-'}</span></td>
      <td><span class="rate-badge ${rateClass}">${fmtPct(rate)}</span></td>
      <td>${fmtTime(p.TTFT?.P50)}</td>
      <td>${s.token_throughput_tps != null ? fmtNum(s.token_throughput_tps, 0) : '-'}</td>
    </tr>`;
  }
  html += '</tbody></table></div>';
  return renderSectionCard('最近测试', html, 'recent');
}

async function refreshDashboard() {
  loading.value = true;
  try {
    const data = await getResults({ limit: 500 });
    const results = data.items || [];
    if (!results.length) {
      contentHtml.value = '<div class="empty-state"><div class="empty-state-icon">&#9201;</div><div class="empty-state-text">暂无测试结果</div><p style="color:var(--text-tertiary);font-size:13px">运行一次压测后结果将在此展示。</p></div>';
    } else {
      let html = '';
      html += renderHeroStats(results);
      html += renderEndpointOverview(results);
      html += renderModelOverview(results);
      html += renderRecentTests(results);
      contentHtml.value = html;
    }
  } catch (e) {
    contentHtml.value = '<div style="text-align:center;color:var(--danger);padding:40px">加载失败: ' + escHtml(e.message) + '</div>';
  }
  loading.value = false;
}

import { useRoute } from 'vue-router';
const route = useRoute();
watch(() => route.path, (val) => {
  if (val === '/') refreshDashboard();
}, { immediate: true });
</script>
