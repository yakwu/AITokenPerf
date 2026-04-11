import {
  fmtTime, fmtPct, fmtNum, fmtBigNum, fmtTimestamp, escHtml,
  qualityColorClass, latencyColorClass, infoIconHtml, fmtCost
} from './formatters';

// Alias to match original global function name used in app.js
const infoIcon = infoIconHtml;

export function renderResultDetail(r) {
  const s = r.summary || {};
  const p = r.percentiles || {};
  const c = r.config || {};
  const successClass = s.success_rate >= 95 ? 'success' : s.success_rate >= 80 ? 'warning' : 'danger';
  const throughputClass = qualityColorClass(s.throughput_rps, 20, 5);
  const tokenRateClass = qualityColorClass(s.token_throughput_tps, 500, 100);
  const ttftClass = latencyColorClass(p.TTFT?.P50, 0.5, 2);
  const tpotClass = latencyColorClass(p.TPOT?.P50, 0.05, 0.2);
  const e2eClass = latencyColorClass(p.E2E?.P50, 2, 10);

  let html = `
    <div style="margin-bottom:12px;font-size:13px;color:var(--text-secondary);font-family:var(--font-mono)">
      ${r.test_id ? `<span style="background:var(--bg);padding:2px 8px;border-radius:4px;font-size:11px;color:var(--text-tertiary)">#${escHtml(r.test_id)}</span> ` : ''}${escHtml(c.base_url || '-')} &middot; ${escHtml(c.model || '-')} &middot; ${fmtTimestamp(r.timestamp)}
    </div>
    <div class="metrics-grid">
      <div class="metrics-group-header-row">
        <div class="metrics-group-header">质量指标（越高越好）</div>
        <div class="metrics-group-header">延迟指标（越低越好）</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">成功率</div>
        <div class="metric-value ${successClass}">${fmtPct(s.success_rate)}</div>
        <div class="metric-sub">${s.success_count || 0} / ${s.total_requests || 0} 请求</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">吞吐量</div>
        <div class="metric-value ${throughputClass}">${fmtNum(s.throughput_rps)}</div>
        <div class="metric-sub">req/s</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Token 速率</div>
        <div class="metric-value ${tokenRateClass}">${fmtNum(s.token_throughput_tps, 0)}</div>
        <div class="metric-sub">tokens/s</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">TTFT P50 ${infoIcon('TTFT')}</div>
        <div class="metric-value ${ttftClass}">${fmtTime(p.TTFT?.P50)}</div>
        <div class="metric-sub">P95: ${fmtTime(p.TTFT?.P95)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">TPOT P50 ${infoIcon('TPOT')}</div>
        <div class="metric-value ${tpotClass}">${fmtTime(p.TPOT?.P50)}</div>
        <div class="metric-sub">P95: ${fmtTime(p.TPOT?.P95)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">E2E P50 ${infoIcon('E2E')}</div>
        <div class="metric-value ${e2eClass}">${fmtTime(p.E2E?.P50)}</div>
        <div class="metric-sub">P95: ${fmtTime(p.E2E?.P95)}</div>
      </div>
      <div class="metrics-group-header">基础信息</div>
      <div class="metric-card">
        <div class="metric-label">输出 Tokens</div>
        <div class="metric-value">${fmtNum(s.output_tokens?.Avg, 0)}</div>
        <div class="metric-sub">总计 ${fmtBigNum(s.total_output_tokens)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">输入 Tokens</div>
        <div class="metric-value">${fmtNum(s.input_tokens?.Avg, 0)}</div>
        <div class="metric-sub">总计 ${fmtBigNum(s.total_input_tokens)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">耗时</div>
        <div class="metric-value">${fmtTime(s.duration_seconds)}</div>
        <div class="metric-sub">并发: ${escHtml(c.concurrency || '-')}</div>
      </div>`;

  // 费用卡片
  if (s.cost_total_usd != null && s.cost_total_usd > 0) {
    html += `
      <div class="metric-card">
        <div class="metric-label">预估费用</div>
        <div class="metric-value">${fmtCost(s.cost_total_usd)}</div>
        <div class="metric-sub">输入: ${fmtCost(s.cost_input_usd)}<br>输出: ${fmtCost(s.cost_output_usd)}</div>
      </div>`;
  }

  html += `</div>`;

  // Percentile table
  if (p.TTFT || p.TPOT || p.E2E) {
    html += `<div class="card" style="margin-bottom:20px"><div class="card-title" style="margin-bottom:12px">百分位分布</div>
      <div class="table-wrap"><table class="pct-table"><thead><tr>
        <th>指标</th><th>Min</th><th>P50</th><th>P95</th><th>P99</th><th>P99.5</th><th>Max</th><th>Avg</th>
      </tr></thead><tbody>`;
    for (const [name, vals] of Object.entries(p)) {
      html += `<tr><td>${escHtml(name)} ${infoIcon(name)}</td><td>${fmtTime(vals.Min)}</td><td>${fmtTime(vals.P50)}</td><td>${fmtTime(vals.P95)}</td><td>${fmtTime(vals.P99)}</td><td>${fmtTime(vals['P99.5'])}</td><td>${fmtTime(vals.Max)}</td><td>${fmtTime(vals.Avg)}</td></tr>`;
    }
    html += '</tbody></table></div></div>';

    // Token distribution table
    const tokIn = s.input_tokens;
    const tokOut = s.output_tokens;
    if (tokIn || tokOut) {
      html += `<div class="card" style="margin-bottom:20px"><div class="card-title" style="margin-bottom:12px">Token 分布</div>
        <div class="table-wrap"><table class="pct-table"><thead><tr>
          <th>类型</th><th>Min</th><th>P50</th><th>P95</th><th>P99</th><th>Max</th><th>Avg</th><th>总计</th>
        </tr></thead><tbody>`;
      if (tokIn) {
        html += `<tr><td>输入 Tokens</td><td>${fmtNum(tokIn.Min, 0)}</td><td>${fmtNum(tokIn.P50, 0)}</td><td>${fmtNum(tokIn.P95, 0)}</td><td>${fmtNum(tokIn.P99, 0)}</td><td>${fmtNum(tokIn.Max, 0)}</td><td>${fmtNum(tokIn.Avg, 0)}</td><td>${fmtBigNum(s.total_input_tokens)}</td></tr>`;
      }
      if (tokOut) {
        html += `<tr><td>输出 Tokens</td><td>${fmtNum(tokOut.Min, 0)}</td><td>${fmtNum(tokOut.P50, 0)}</td><td>${fmtNum(tokOut.P95, 0)}</td><td>${fmtNum(tokOut.P99, 0)}</td><td>${fmtNum(tokOut.Max, 0)}</td><td>${fmtNum(tokOut.Avg, 0)}</td><td>${fmtBigNum(s.total_output_tokens)}</td></tr>`;
      }
      html += '</tbody></table></div></div>';
    }
  }

  // Request distribution bar
  {
    const total = s.total_requests || 0;
    const successCount = s.success_count || 0;
    const errors = r.errors || {};
    const errorDetails = r.error_details || [];

    const segments = [];
    if (successCount > 0) {
      segments.push({ label: '成功', count: successCount, color: '#2D8B55', bg: '#2D8B55' });
    }
    const errColors = ['#D63B3B', '#E07B3B', '#C73BC7', '#8B5CF6', '#3B7DD6'];
    let colorIdx = 0;
    const sortedErrors = Object.entries(errors).sort((a, b) => b[1] - a[1]);
    for (const [type, count] of sortedErrors) {
      segments.push({ label: type, count, color: errColors[colorIdx % errColors.length], bg: errColors[colorIdx % errColors.length] });
      colorIdx++;
    }

    if (total > 0) {
      html += `<div class="card" style="margin-bottom:20px">
        <div class="card-title" style="margin-bottom:14px">请求分布</div>`;

      html += `<div class="dist-bar">`;
      segments.forEach(seg => {
        const pct = (seg.count / total * 100);
        if (pct < 0.3) return;
        const tip = `${seg.label}: ${seg.count} (${pct.toFixed(1)}%)`;
        html += `<div class="dist-seg" style="width:${pct}%;background:${seg.bg}" data-tip="${escHtml(tip)}">
          ${pct >= 8 ? `<span>${pct.toFixed(1)}%</span>` : ''}
        </div>`;
      });
      html += `</div>`;

      html += `<div class="dist-legend">`;
      segments.forEach(seg => {
        const pct = (seg.count / total * 100).toFixed(1);
        html += `<div class="dist-legend-item">
          <span class="dist-dot" style="background:${seg.color}"></span>
          <span class="dist-legend-label">${escHtml(seg.label)}</span>
          <span class="dist-legend-value">${seg.count} <span style="color:var(--text-tertiary)">(${pct}%)</span></span>
        </div>`;
      });
      html += `</div>`;

      if (errorDetails.length) {
        html += `<details style="margin-top:12px"><summary style="cursor:pointer;font-size:12px;color:var(--text-secondary);font-weight:600;user-select:none">查看 ${errorDetails.length} 条错误详情</summary>`;
        html += `<div class="progress-log" style="max-height:240px;margin-top:8px">`;
        const showCount = Math.min(errorDetails.length, 30);
        errorDetails.slice(0, showCount).forEach(e => {
          let meta = '';
          if (e.phase) meta += ` <span style="color:var(--text-tertiary)">[${escHtml(e.phase)}]</span>`;
          if (e.duration != null) meta += ` <span style="color:var(--text-tertiary)">${e.duration}s</span>`;
          if (e.tokens_received > 0) meta += ` <span style="color:var(--text-tertiary)">${e.tokens_received}toks</span>`;
          html += `<div><span class="fail">[#${escHtml(e.request_id)}]</span> <span style="color:#F59E3B">HTTP ${escHtml(e.status_code)}</span> ${escHtml(e.error || '')}${meta}</div>`;
        });
        if (errorDetails.length > showCount) {
          html += `<div style="color:var(--text-tertiary)">... 还有 ${errorDetails.length - showCount} 条</div>`;
        }
        html += '</div></details>';
      }

      html += '</div>';
    }
  }

  // Charts
  const chartsId = `charts_${escHtml(r.timestamp)}_${Math.random().toString(36).slice(2, 6)}`;
  html += `<div class="charts-row" id="${chartsId}"></div>`;

  const _chartsId = chartsId;
  const _p = p;
  requestAnimationFrame(() => {
    const tryRender = () => {
      const container = document.getElementById(_chartsId);
      if (container) {
        // renderPercentilesChart is a global function from the original app.js
        if (typeof window.renderPercentilesChart === 'function') {
          window.renderPercentilesChart(container, _p);
        }
      } else {
        requestAnimationFrame(tryRender);
      }
    };
    tryRender();
  });

  return html;
}
