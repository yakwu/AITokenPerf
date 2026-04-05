function fmtTime(s) {
  if (s == null || isNaN(s)) return '-';
  return s < 1 ? (s * 1000).toFixed(0) + 'ms' : s.toFixed(2) + 's';
}

function fmtTimestamp(ts) {
  if (!ts) return '-';
  const mo = ts.slice(4,6), d = ts.slice(6,8);
  const h = ts.slice(9,11), mi = ts.slice(11,13);
  return `${mo}-${d} ${h}:${mi}`;
}

function fmtPct(v) { return v != null ? v.toFixed(1) + '%' : '-'; }

function fmtNum(v, d=1) { return v != null ? v.toFixed(d) : '-'; }

function fmtBigNum(v) {
  if (v == null) return '-';
  if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
  return String(v);
}

function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function toast(msg, type='info') {
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 3000);
}

async function api(path, opts = {}) {
  const res = await fetch((window.__API_BASE__ || '') + path, opts);
  return res.json();
}

const METRIC_INFO = {
  'TTFT': 'Time To First Token \u2014 \u9996\u5b57\u5ef6\u8fdf\uff0c\u4ece\u8bf7\u6c42\u53d1\u51fa\u5230\u6536\u5230\u7b2c\u4e00\u4e2a token \u7684\u65f6\u95f4',
  'TPOT': 'Time Per Output Token \u2014 \u6bcf\u4e2a token \u7684\u8f93\u51fa\u5ef6\u8fdf\uff0c\u8861\u91cf\u751f\u6210\u901f\u5ea6',
  'E2E':  'End to End \u2014 \u5b8c\u6574\u54cd\u5e94\u603b\u8017\u65f6\uff0c\u4ece\u8bf7\u6c42\u53d1\u51fa\u5230\u6700\u540e\u4e00\u4e2a token \u63a5\u6536\u5b8c\u6bd5',
};

function infoIcon(metric) {
  const tip = METRIC_INFO[metric] || metric;
  return `<span class="info-tip" data-tip="${tip}">?</span>`;
}

// Floating tooltip (position: fixed, never clipped by overflow)
document.addEventListener('DOMContentLoaded', () => {
  const el = document.createElement('div');
  el.id = 'tooltip-float';
  document.body.appendChild(el);

  document.addEventListener('mouseover', (e) => {
    const tip = e.target.closest('.info-tip');
    if (!tip || !tip.dataset.tip) return;
    el.textContent = tip.dataset.tip;
    el.style.display = 'block';
    const rect = tip.getBoundingClientRect();
    const left = Math.min(Math.max(8, rect.left), window.innerWidth - el.offsetWidth - 8);
    el.style.left = left + 'px';
    el.style.top = (rect.top - el.offsetHeight - 8) + 'px';
  });

  document.addEventListener('mouseout', (e) => {
    if (e.target.closest('.info-tip')) el.style.display = 'none';
  });
});
