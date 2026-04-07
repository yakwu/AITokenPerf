export function fmtTime(s) {
  if (s == null || isNaN(s)) return '-';
  return s < 1 ? (s * 1000).toFixed(0) + 'ms' : s.toFixed(2) + 's';
}

export function fmtTimestamp(ts) {
  if (!ts) return '-';
  const mo = ts.slice(4, 6), d = ts.slice(6, 8);
  const h = ts.slice(9, 11), mi = ts.slice(11, 13);
  return `${mo}-${d} ${h}:${mi}`;
}

export function fmtPct(v) { return v != null ? v.toFixed(1) + '%' : '-'; }

export function fmtNum(v, d = 1) { return v != null ? v.toFixed(d) : '-'; }

export function fmtBigNum(v) {
  if (v == null) return '-';
  if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
  return String(v);
}

export function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function qualityColorClass(value, goodThreshold, warnThreshold) {
  if (value == null) return '';
  return value >= goodThreshold ? 'success' : value >= warnThreshold ? 'warning' : 'danger';
}

export function latencyColorClass(value, goodThreshold, warnThreshold) {
  if (value == null) return '';
  return value <= goodThreshold ? 'success' : value <= warnThreshold ? 'warning' : 'danger';
}

export function qualityColorStyle(value, goodThreshold, warnThreshold) {
  if (value == null) return '';
  return value >= goodThreshold ? 'color:var(--success)' : value >= warnThreshold ? 'color:var(--warning)' : 'color:var(--danger)';
}

export function latencyColorStyle(value, goodThreshold, warnThreshold) {
  if (value == null) return '';
  return value <= goodThreshold ? 'color:var(--success)' : value <= warnThreshold ? 'color:var(--warning)' : 'color:var(--danger)';
}

export const METRIC_INFO = {
  'TTFT': 'Time To First Token — 首字延迟，从请求发出到收到第一个 token 的时间',
  'TPOT': 'Time Per Output Token — 每个 token 的输出延迟，衡量生成速度',
  'E2E': 'End to End — 完整响应总耗时，从请求发出到最后一个 token 接收完毕',
};

export function infoIconHtml(metric) {
  const tip = METRIC_INFO[metric] || metric;
  return `<span class="info-tip" data-tip="${escHtml(tip)}">?</span>`;
}
