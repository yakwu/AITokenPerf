// ============ renderResultDetail (shared by dashboard, benchmark, history) ============
function renderResultDetail(r) {
  const s = r.summary || {};
  const p = r.percentiles || {};
  const c = r.config || {};
  const successClass = s.success_rate >= 95 ? 'success' : s.success_rate >= 80 ? 'accent' : 'danger';

  let html = `
    <div style="margin-bottom:12px;font-size:13px;color:var(--text-secondary);font-family:var(--font-mono)">
      ${r.test_id ? `<span style="background:var(--bg);padding:2px 8px;border-radius:4px;font-size:11px;color:var(--text-tertiary)">#${r.test_id}</span> ` : ''}${c.base_url || '-'} &middot; ${c.model || '-'} &middot; ${fmtTimestamp(r.timestamp)}
    </div>
    <div class="metrics-grid">
      <div class="metric-card">
        <div class="metric-label">成功率</div>
        <div class="metric-value ${successClass}">${fmtPct(s.success_rate)}</div>
        <div class="metric-sub">${s.success_count || 0} / ${s.total_requests || 0} 请求</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">吞吐量</div>
        <div class="metric-value">${fmtNum(s.throughput_rps)}</div>
        <div class="metric-sub">req/s</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Token 速率</div>
        <div class="metric-value">${fmtNum(s.token_throughput_tps, 0)}</div>
        <div class="metric-sub">tokens/s</div>
      </div>
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
        <div class="metric-label">TTFT P50 ${infoIcon('TTFT')}</div>
        <div class="metric-value accent">${fmtTime(p.TTFT?.P50)}</div>
        <div class="metric-sub">P95: ${fmtTime(p.TTFT?.P95)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">TPOT P50 ${infoIcon('TPOT')}</div>
        <div class="metric-value">${fmtTime(p.TPOT?.P50)}</div>
        <div class="metric-sub">P95: ${fmtTime(p.TPOT?.P95)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">E2E P50 ${infoIcon('E2E')}</div>
        <div class="metric-value accent">${fmtTime(p.E2E?.P50)}</div>
        <div class="metric-sub">P95: ${fmtTime(p.E2E?.P95)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">耗时</div>
        <div class="metric-value">${fmtTime(s.duration_seconds)}</div>
        <div class="metric-sub">并发: ${c.concurrency || '-'}</div>
      </div>
    </div>`;

  // Percentile table
  if (p.TTFT || p.TPOT || p.E2E) {
    html += `<div class="card" style="margin-bottom:20px"><div class="card-title" style="margin-bottom:12px">\u767e\u5206\u4f4d\u5206\u5e03</div>
      <div class="table-wrap"><table class="pct-table"><thead><tr>
        <th>\u6307\u6807</th><th>Min</th><th>P50</th><th>P95</th><th>P99</th><th>P99.5</th><th>Max</th><th>Avg</th>
      </tr></thead><tbody>`;
    for (const [name, vals] of Object.entries(p)) {
      html += `<tr><td>${name} ${infoIcon(name)}</td><td>${fmtTime(vals.Min)}</td><td>${fmtTime(vals.P50)}</td><td>${fmtTime(vals.P95)}</td><td>${fmtTime(vals.P99)}</td><td>${fmtTime(vals['P99.5'])}</td><td>${fmtTime(vals.Max)}</td><td>${fmtTime(vals.Avg)}</td></tr>`;
    }
    html += '</tbody></table></div></div>';

  // Token distribution table
  const tokIn = s.input_tokens;
  const tokOut = s.output_tokens;
  if (tokIn || tokOut) {
    html += `<div class="card" style="margin-bottom:20px"><div class="card-title" style="margin-bottom:12px">Token \u5206\u5e03</div>
      <div class="table-wrap"><table class="pct-table"><thead><tr>
        <th>\u7c7b\u578b</th><th>Min</th><th>P50</th><th>P95</th><th>P99</th><th>Max</th><th>Avg</th><th>\u603b\u8ba1</th>
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
        <div class="card-title" style="margin-bottom:14px">\u8bf7\u6c42\u5206\u5e03</div>`;

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
        html += `<details style="margin-top:12px"><summary style="cursor:pointer;font-size:12px;color:var(--text-secondary);font-weight:600;user-select:none">\u67e5\u770b ${errorDetails.length} \u6761\u9519\u8bef\u8be6\u60c5</summary>`;
        html += `<div class="progress-log" style="max-height:240px;margin-top:8px">`;
        const showCount = Math.min(errorDetails.length, 30);
        errorDetails.slice(0, showCount).forEach(e => {
          const msg = (e.error || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
          html += `<div><span class="fail">[#${e.request_id}]</span> <span style="color:#F59E3B">HTTP ${e.status_code}</span> ${msg}</div>`;
        });
        if (errorDetails.length > showCount) {
          html += `<div style="color:var(--text-tertiary)">... \u8fd8\u6709 ${errorDetails.length - showCount} \u6761</div>`;
        }
        html += '</div></details>';
      }

      html += '</div>';
    }
  }

  // Charts
  const chartsId = `charts_${r.timestamp}_${Math.random().toString(36).slice(2, 6)}`;
  html += `<div class="charts-row" id="${chartsId}"></div>`;

  const _chartsId = chartsId;
  const _p = p;
  requestAnimationFrame(() => {
    const tryRender = () => {
      const container = document.getElementById(_chartsId);
      if (container) {
        renderPercentilesChart(container, _p);
      } else {
        requestAnimationFrame(tryRender);
      }
    };
    tryRender();
  });

  return html;
}

// ============ Alpine Store ============
const VALID_TABS = ['dashboard', 'benchmark', 'history', 'schedules', 'config', 'auth', 'settings', 'admin-users'];

function isLoggedIn() {
  return !!localStorage.getItem('token');
}

function getTabFromHash() {
  if (!isLoggedIn()) return 'auth';
  const hash = location.hash.replace('#', '');
  if (hash === 'auth') return 'dashboard';
  return VALID_TABS.includes(hash) ? hash : 'dashboard';
}

// 防止 switchTab 设置 location.hash 后 hashchange handler 覆盖 tab
let _switchingTab = false;

document.addEventListener('alpine:init', () => {
  const userStr = localStorage.getItem('user');
  Alpine.store('app', {
    tab: getTabFromHash(),
    status: 'idle',
    statusLabels: { idle: '\u7a7a\u95f2', running: '\u8fd0\u884c\u4e2d', stopping: '\u505c\u6b62\u4e2d' },
    user: userStr ? JSON.parse(userStr) : null,
    switchTab(t) {
      if (!isLoggedIn() && t !== 'auth') return;
      _switchingTab = true;
      this.tab = t;
      location.hash = t === 'dashboard' ? '' : t;
      // 短暂延迟后重置标志，确保 hashchange handler 不会覆盖
      setTimeout(() => { _switchingTab = false; }, 50);
    },
    setUser(user, token) {
      this.user = user;
      localStorage.setItem('token', token);
      localStorage.setItem('user', JSON.stringify(user));
    },
    logout() {
      this.user = null;
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      this.tab = 'auth';
      location.hash = 'auth';
    },
  });
});

// 浏览器前进/后退时同步 tab
window.addEventListener('hashchange', () => {
  if (_switchingTab) return;
  const store = Alpine.store('app');
  if (store) store.tab = getTabFromHash();
});
