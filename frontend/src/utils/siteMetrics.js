/**
 * 站点指标聚合工具函数
 * 从 SitesView.vue 抽取，纯函数，不依赖组件响应式状态。
 */

export function getModelMetrics(site) {
  const results = site.latest_results || [];
  const sparklineData = site.sparkline_data || {};
  const modelMap = {};
  for (const r of results) {
    const model = r.config?.model || '-';
    if (!modelMap[model]) {
      modelMap[model] = { results: [] };
    }
    modelMap[model].results.push(r);
  }
  // 确保 sparkline_data 中有但 latest_results 中没有的 model 也出现
  for (const model of Object.keys(sparklineData)) {
    if (!modelMap[model]) {
      modelMap[model] = { results: [] };
    }
  }

  return Object.entries(modelMap).map(([model, { results }]) => {
    const totalReqs = results.reduce((s, r) => s + (r.summary?.total_requests || 0), 0);
    const totalSuccess = results.reduce((s, r) => s + (r.summary?.success_count || r.summary?.successful_requests || 0), 0);
    const successRate = totalReqs > 0 ? (totalSuccess / totalReqs * 100) : null;

    const ttfts = results.map(r => r.percentiles?.TTFT?.P50).filter(v => v != null);
    const ttft = ttfts.length ? ttfts.reduce((a, b) => a + b, 0) / ttfts.length : null;

    const tpots = results.map(r => r.percentiles?.TPOT?.P50).filter(v => v != null);
    const tpot = tpots.length ? tpots.reduce((a, b) => a + b, 0) / tpots.length : null;

    const tpsList = results.map(r => r.summary?.token_throughput_tps).filter(v => v != null && v > 0);
    const tps = tpsList.length ? tpsList.reduce((a, b) => a + b, 0) / tpsList.length : null;

    // Sparkline trend: 失败率（从 latest_results 计算每次测试的失败率）
    const failRateTrend = results.slice().reverse().map(r => {
      const total = r.summary?.total_requests || 0;
      const success = r.summary?.success_count || r.summary?.successful_requests || 0;
      return total > 0 ? (100 - success / total * 100) : null;
    }).filter(v => v != null);

    return { model, ttft, failRateTrend, tpot, tps, successRate };
  }).sort((a, b) => a.model.localeCompare(b.model));
}

export function sparklinePoints(values) {
  if (!values || values.length < 2) return '';
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  return values.map((v, i) => {
    const x = (i / (values.length - 1)) * 60;
    const y = 20 - ((v - min) / range) * 18;
    return `${x},${y}`;
  }).join(' ');
}

export function sparklineTooltip(values) {
  if (!values || values.length < 2) return '';
  const first = values[0];
  const last = values[values.length - 1];
  const diff = last - first;
  const arrow = diff > 0 ? '↑' : diff < 0 ? '↓' : '→';
  return `失败率趋势: ${first.toFixed(1)}% → ${last.toFixed(1)}% (${arrow}${Math.abs(diff).toFixed(1)}%)`;
}

export function getErrorTypes(site) {
  const results = site.latest_results || [];
  const errorCounts = {};
  for (const r of results) {
    const errDetails = r.error_details;
    if (Array.isArray(errDetails)) {
      for (const e of errDetails) {
        const type = e?.error_type;
        if (type) {
          errorCounts[type] = (errorCounts[type] || 0) + 1;
        }
      }
    }
  }
  return Object.entries(errorCounts)
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
}

export function getTotalErrorCount(site) {
  return getErrorTypes(site).reduce((s, e) => s + e.count, 0);
}

export function getDegradation(site) {
  const results = site.latest_results || [];
  if (results.length < 3) return null;

  // Split results: earlier half vs recent half
  const half = Math.ceil(results.length / 2);
  const recent = results.slice(0, half);
  const earlier = results.slice(half);

  const calcAvgRate = (list) => {
    const rates = list
      .map(r => {
        const s = r.summary || {};
        const total = s.total_requests || 0;
        return total > 0 ? (s.success_count || s.successful_requests || 0) / total * 100 : null;
      })
      .filter(v => v != null);
    return rates.length ? rates.reduce((a, b) => a + b, 0) / rates.length : null;
  };

  const recentRate = calcAvgRate(recent);
  const earlierRate = calcAvgRate(earlier);

  if (recentRate == null || earlierRate == null) return null;
  const drop = earlierRate - recentRate;
  if (drop >= 5) {
    return `成功率较近期下降 ${drop.toFixed(0)}%`;
  }
  return null;
}
