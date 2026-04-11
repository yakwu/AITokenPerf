/**
 * 时序趋势数据聚合工具
 * 将分钟级数据聚合为固定数量的展示点，空时间段插入 null 实现断线
 */

export function parseMinuteToTs(m) {
  return new Date(
    `${m.slice(0, 4)}-${m.slice(4, 6)}-${m.slice(6, 8)}T${m.slice(9, 11)}:${m.slice(11, 13) || '00'}:00`
  ).getTime();
}

function formatLabel(tsMs) {
  const d = new Date(tsMs);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  return `${mm}-${dd} ${hh}:${mi}`;
}

function roundTo(val, decimals) {
  const f = 10 ** decimals;
  return Math.round(val * f) / f;
}

/**
 * 将分钟级趋势数据聚合为固定数量的展示点
 * @param {Array} trend - 后端返回的分钟桶数据
 * @param {number} targetPoints - 目标展示点数（默认 144）
 * @returns {{ labels: string[], items: (object|null)[] }}
 */
export function aggregateToFixedPoints(trend, targetPoints = 144) {
  if (!trend || trend.length === 0) return { labels: [], items: [] };
  if (trend.length === 1) {
    return { labels: [formatLabel(parseMinuteToTs(trend[0].minute))], items: [trend[0]] };
  }

  // 数据点不多，不需要聚合，但仍需检测间隔断开
  if (trend.length <= targetPoints) {
    return fillGaps(trend);
  }

  // 数据量超过 targetPoints，执行桶聚合
  const firstTs = parseMinuteToTs(trend[0].minute);
  const lastTs = parseMinuteToTs(trend[trend.length - 1].minute);
  const totalRange = lastTs - firstTs;
  if (totalRange <= 0) return fillGaps(trend);

  const bucketWidth = totalRange / targetPoints;
  const buckets = Array.from({ length: targetPoints }, () => []);

  for (const point of trend) {
    const ts = parseMinuteToTs(point.minute);
    const idx = Math.min(Math.floor((ts - firstTs) / bucketWidth), targetPoints - 1);
    if (idx >= 0) buckets[idx].push(point);
  }

  const labels = [];
  const items = [];

  for (let i = 0; i < targetPoints; i++) {
    const midTs = firstTs + (i + 0.5) * bucketWidth;
    if (buckets[i].length === 0) {
      labels.push(formatLabel(midTs));
      items.push(null);
      continue;
    }

    const totalWeight = buckets[i].reduce((s, p) => s + (p.run_count || 1), 0);

    function weightedAvg(field) {
      let sum = 0, wSum = 0;
      for (const p of buckets[i]) {
        const val = p[field];
        if (val != null) {
          const w = p.run_count || 1;
          sum += val * w;
          wSum += w;
        }
      }
      return wSum > 0 ? roundTo(sum / wSum, 2) : null;
    }

    labels.push(formatLabel(midTs));
    items.push({
      avg_success_rate: weightedAvg('avg_success_rate'),
      avg_throughput: weightedAvg('avg_throughput'),
      avg_tps: weightedAvg('avg_tps'),
      avg_ttft_p50: weightedAvg('avg_ttft_p50'),
      avg_tpot_p50: weightedAvg('avg_tpot_p50'),
      avg_e2e_p50: weightedAvg('avg_e2e_p50'),
      run_count: totalWeight,
    });
  }

  return { labels, items };
}

/**
 * 少量数据时检测间隔，插入 null 断开连线
 */
function fillGaps(trend) {
  if (trend.length < 2) {
    return {
      labels: trend.map(r => formatLabel(parseMinuteToTs(r.minute))),
      items: [...trend],
    };
  }

  const intervals = [];
  for (let i = 1; i < trend.length; i++) {
    intervals.push(parseMinuteToTs(trend[i].minute) - parseMinuteToTs(trend[i - 1].minute));
  }
  const sorted = intervals.slice().sort((a, b) => a - b);
  const medianInterval = sorted[Math.floor(sorted.length / 2)];
  const gapThreshold = medianInterval * 2;

  const labels = [];
  const items = [];

  for (let i = 0; i < trend.length; i++) {
    if (i > 0) {
      const gap = parseMinuteToTs(trend[i].minute) - parseMinuteToTs(trend[i - 1].minute);
      if (gap > gapThreshold) {
        labels.push(null);
        items.push(null);
      }
    }
    labels.push(formatLabel(parseMinuteToTs(trend[i].minute)));
    items.push(trend[i]);
  }

  return { labels, items };
}
