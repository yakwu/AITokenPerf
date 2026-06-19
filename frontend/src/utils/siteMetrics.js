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

    const e2es = results.map(r => r.percentiles?.E2E?.P50).filter(v => v != null);
    const e2e = e2es.length ? e2es.reduce((a, b) => a + b, 0) / e2es.length : null;

    const tpsList = results.map(r => r.summary?.token_throughput_tps).filter(v => v != null && v > 0);
    const tps = tpsList.length ? tpsList.reduce((a, b) => a + b, 0) / tpsList.length : null;

    // 输入/输出 token：取每条结果每请求 P50 的均值
    const inToks = results.map(r => r.summary?.input_tokens?.P50).filter(v => v != null);
    const inTok = inToks.length ? inToks.reduce((a, b) => a + b, 0) / inToks.length : null;
    const outToks = results.map(r => r.summary?.output_tokens?.P50).filter(v => v != null);
    const outTok = outToks.length ? outToks.reduce((a, b) => a + b, 0) / outToks.length : null;

    // Sparkline: TTFT 延迟趋势（优先后端 7 天 sparkline_data，回退 latest_results）
    const latencyTrend = getSparklineTrend(site, model);

    return { model, ttft, tpot, e2e, tps, inTok, outTok, successRate, latencyTrend };
  }).sort((a, b) => a.model.localeCompare(b.model));
}

// 取某模型的 TTFT 延迟趋势序列：优先后端 sparkline_data，回退 latest_results 的 TTFT P50
export function getSparklineTrend(site, model) {
  if (site.sparkline_data && site.sparkline_data[model]) {
    return site.sparkline_data[model];
  }
  const results = site.latest_results || [];
  const ttfts = results
    .filter(r => r.config?.model === model)
    .map(r => r.percentiles?.TTFT?.P50)
    .filter(v => v != null);
  return ttfts.slice(0, 10).reverse();
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

// 延迟趋势 sparkline 末端点坐标（用于画当前点小圆点）
export function sparklineEnd(values) {
  if (!values || values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const last = values[values.length - 1];
  return { x: 60, y: 20 - ((last - min) / range) * 18 };
}

// 延迟趋势配色：统一中性色，只看走势形状。涨跌的具体数值交给 latencyTrendTooltip，
// 不再用红/绿染色（红/绿会把"延迟变化方向"误导成"健康好坏"，且末点一抖就翻色）。
export function latencyTrendColor() {
  return 'var(--text-secondary)';
}

export function latencyTrendTooltip(values) {
  if (!values || values.length < 2) return '暂无足够趋势数据';
  const first = values[0];
  const last = values[values.length - 1];
  const diff = last - first;
  const arrow = diff > 0 ? '↑' : diff < 0 ? '↓' : '→';
  const pct = first > 0 ? Math.abs(diff / first * 100) : 0;
  return `TTFT 延迟趋势(7天): ${first.toFixed(2)}s → ${last.toFixed(2)}s (${arrow}${pct.toFixed(0)}%)`;
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

// 可用性着色：成功率(%) → 档位。阈值 绿≥95 / 橙80–95 / 红<80；空桶=na
export function availabilityClass(rate) {
  if (rate == null) return 'na';
  if (rate >= 95) return 'up';
  if (rate >= 80) return 'degraded';
  return 'down';
}

// /api/sites/availability 的 cells 数组 → 查找表 {profile: {model: series}}
export function buildAvailabilityLookup(cells) {
  const lut = {};
  for (const c of cells || []) {
    if (!lut[c.profile]) lut[c.profile] = {};
    lut[c.profile][c.model] = c.series || [];
  }
  return lut;
}

// 站点级可用性序列 = 各模型同一桶成功率平均（忽略 null 空桶）；无数据→[]
export function siteAvgSeries(modelSeriesList) {
  const lists = (modelSeriesList || []).filter(s => Array.isArray(s) && s.length);
  if (!lists.length) return [];
  const n = Math.max(...lists.map(s => s.length));
  const out = [];
  for (let i = 0; i < n; i++) {
    const vals = lists.map(s => s[i]).filter(v => v != null);
    out.push(vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null);
  }
  return out;
}

// 可用性序列 → 区间成功率：非空桶（!= null）的平均，全空/空/缺省 → null。
// 用于把"成功率"数字与可用率柱同源，反映所选时间范围而非最近一次。
export function seriesAvg(series) {
  const vals = (series || []).filter(v => v != null);
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
}
