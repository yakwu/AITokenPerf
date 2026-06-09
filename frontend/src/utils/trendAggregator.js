/**
 * 时序趋势数据聚合工具
 * 将分钟级数据聚合为固定数量的展示点，空时间段插值连线或断线
 */

const METRIC_FIELDS = [
  'avg_success_rate', 'avg_throughput', 'avg_tps',
  'avg_ttft_p50', 'avg_tpot_p50', 'avg_e2e_p50',
];

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

function lerp(a, b, ratio) {
  if (a == null || b == null) return null;
  return roundTo(a + (b - a) * ratio, 2);
}

/**
 * 根据数据密度计算自适应桶数
 * @param {Array} trend - 后端返回的分钟桶数据（至少 2 个点）
 * @param {number} rangeHours - 时间范围（小时）
 * @returns {{ targetPoints: number, medianInterval: number, bucketWidth: number }}
 */
export function computeAdaptiveBucketCount(trend, rangeHours) {
  // 计算数据点之间的间隔（毫秒）
  const intervals = [];
  for (let i = 1; i < trend.length; i++) {
    intervals.push(parseMinuteToTs(trend[i].minute) - parseMinuteToTs(trend[i - 1].minute));
  }

  // 中位间隔
  let medianInterval;
  if (intervals.length === 0) {
    medianInterval = 60_000; // 单点 fallback: 1 分钟
  } else {
    const sorted = intervals.slice().sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    medianInterval = sorted.length % 2 === 0
      ? (sorted[mid - 1] + sorted[mid]) / 2
      : sorted[mid];
  }

  // 防止中位间隔为 0（所有点在同一分钟）
  if (medianInterval <= 0) medianInterval = 60_000;

  const rangeMs = rangeHours * 3600_000;
  // 钳位后用钳位后的点数反算桶宽，保证 点数×桶宽 == 总跨度。
  // 不钳位时 rangeMs/targetPoints ≈ medianInterval，行为不变；
  // 钳到上限 200 时桶宽自动放大，X 轴才能覆盖完整范围。
  const targetPoints = Math.max(12, Math.min(200, Math.round(rangeMs / medianInterval)));

  return {
    targetPoints,
    medianInterval,
    bucketWidth: rangeMs / targetPoints,
  };
}

/**
 * 将分钟级趋势数据聚合为固定数量的展示点
 * @param {Array} trend - 后端返回的分钟桶数据
 * @param {number} targetPoints - 目标展示点数（默认 144）
 * @param {number|null} rangeHours - 时间范围（小时），指定后 X 轴固定为 [now-hours, now]
 * @returns {{ labels: string[], items: (object|null)[] }}
 */
export function aggregateToFixedPoints(trend, targetPoints = 144, rangeHours = null) {
  if (!trend || trend.length === 0) {
    if (rangeHours) return emptyRange(rangeHours, targetPoints);
    return { labels: [], items: [] };
  }
  if (trend.length === 1 && !rangeHours) {
    return { labels: [formatLabel(parseMinuteToTs(trend[0].minute))], items: [trend[0]] };
  }

  // 确定时间范围：优先使用 rangeHours 固定范围
  let firstTs, lastTs;
  if (rangeHours) {
    lastTs = Date.now();
    firstTs = lastTs - rangeHours * 3600_000;
  } else {
    firstTs = parseMinuteToTs(trend[0].minute);
    lastTs = parseMinuteToTs(trend[trend.length - 1].minute);
  }

  // 数据点不多且无固定范围，走 fillGaps
  if (!rangeHours && trend.length <= targetPoints) {
    return fillGaps(trend);
  }

  const totalRange = lastTs - firstTs;
  if (totalRange <= 0) return fillGaps(trend);

  // 自适应桶数：当 targetPts 为 null 时根据数据密度计算
  let actualTargetPoints = targetPoints;
  let actualBucketWidth;
  let gapThreshold;

  if (targetPoints == null && trend.length >= 2) {
    const adaptive = computeAdaptiveBucketCount(trend, rangeHours || (totalRange / 3600_000));
    actualTargetPoints = adaptive.targetPoints;
    actualBucketWidth = adaptive.bucketWidth;
    gapThreshold = adaptive.medianInterval * 2; // 2 倍中位间隔
  } else {
    actualTargetPoints = targetPoints || 144;
    actualBucketWidth = totalRange / actualTargetPoints;
    // 非自适应模式也计算 gapThreshold 用于插值
    const intervals = [];
    for (let i = 1; i < trend.length; i++) {
      intervals.push(parseMinuteToTs(trend[i].minute) - parseMinuteToTs(trend[i - 1].minute));
    }
    if (intervals.length > 0) {
      const sorted = intervals.slice().sort((a, b) => a - b);
      const mid = Math.floor(sorted.length / 2);
      const median = sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
      gapThreshold = median * 2;
    } else {
      gapThreshold = actualBucketWidth * 2;
    }
  }

  const bucketWidth = actualBucketWidth;
  const buckets = Array.from({ length: actualTargetPoints }, () => []);

  for (const point of trend) {
    const ts = parseMinuteToTs(point.minute);
    const idx = Math.min(Math.floor((ts - firstTs) / bucketWidth), actualTargetPoints - 1);
    if (idx >= 0) buckets[idx].push(point);
  }

  // 预计算：前后最近的非空桶索引
  const nonEmptyIndices = [];
  for (let i = 0; i < actualTargetPoints; i++) {
    if (buckets[i].length > 0) nonEmptyIndices.push(i);
  }

  function computeWeightedAvg(bucket, field) {
    let sum = 0, wSum = 0;
    for (const p of bucket) {
      const val = p[field];
      if (val != null) {
        const w = p.run_count || 1;
        sum += val * w;
        wSum += w;
      }
    }
    return wSum > 0 ? roundTo(sum / wSum, 2) : null;
  }

  const labels = [];
  const items = [];

  for (let i = 0; i < actualTargetPoints; i++) {
    const midTs = firstTs + (i + 0.5) * bucketWidth;

    if (buckets[i].length > 0) {
      // 有数据的桶：加权平均
      const totalWeight = buckets[i].reduce((s, p) => s + (p.run_count || 1), 0);

      labels.push(formatLabel(midTs));
      const metrics = {};
      for (const f of METRIC_FIELDS) metrics[f] = computeWeightedAvg(buckets[i], f);
      items.push({
        ...metrics,
        run_count: totalWeight,
        interpolated: false,
      });
    } else {
      // 空桶：检查是否可以插值
      let prevIdx = -1, nextIdx = -1;
      for (let j = nonEmptyIndices.length - 1; j >= 0; j--) {
        if (nonEmptyIndices[j] < i) { prevIdx = nonEmptyIndices[j]; break; }
      }
      for (let j = 0; j < nonEmptyIndices.length; j++) {
        if (nonEmptyIndices[j] > i) { nextIdx = nonEmptyIndices[j]; break; }
      }

      const gapFromPrev = prevIdx >= 0 ? (i - prevIdx) * bucketWidth : Infinity;
      const gapFromNext = nextIdx >= 0 ? (nextIdx - i) * bucketWidth : Infinity;

      if (prevIdx >= 0 && nextIdx >= 0 && Math.max(gapFromPrev, gapFromNext) < gapThreshold) {
        // 线性插值
        const ratio = (i - prevIdx) / (nextIdx - prevIdx);
        const prevItem = items[prevIdx];
        const nextBucket = buckets[nextIdx];

        function interpolateField(field) {
          const pv = prevItem[field];
          const nv = computeWeightedAvg(nextBucket, field);
          if (pv == null || nv == null) return null;
          return roundTo(pv + (nv - pv) * ratio, 2);
        }

        labels.push(formatLabel(midTs));
        const metrics = {};
        for (const f of METRIC_FIELDS) metrics[f] = interpolateField(f);
        items.push({
          ...metrics,
          run_count: 0,
          interpolated: true,
        });
      } else {
        // 大间隔：断线
        labels.push(formatLabel(midTs));
        items.push(null);
      }
    }
  }

  return { labels, items };
}

/**
 * 指定范围内无数据时，仍生成空的时间轴标签
 */
function emptyRange(rangeHours, targetPoints) {
  const now = Date.now();
  const start = now - rangeHours * 3600_000;
  const step = (now - start) / targetPoints;
  const labels = [];
  const items = [];
  for (let i = 0; i < targetPoints; i++) {
    labels.push(formatLabel(start + (i + 0.5) * step));
    items.push(null);
  }
  return { labels, items };
}

/**
 * 少量数据时检测间隔，小间隔插值填充，大间隔插入 null 断开连线
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
  const mid = Math.floor(sorted.length / 2);
  const medianInterval = sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
  const gapThreshold = medianInterval * 2;

  const labels = [];
  const items = [];

  for (let i = 0; i < trend.length; i++) {
    if (i > 0) {
      const gap = parseMinuteToTs(trend[i].minute) - parseMinuteToTs(trend[i - 1].minute);
      if (gap >= gapThreshold) {
        labels.push(null);
        items.push(null);
      } else if (gap > medianInterval * 1.01) {
        const gapBuckets = Math.round(gap / medianInterval) - 1;
        const prevItem = trend[i - 1];
        const nextItem = trend[i];
        for (let j = 1; j <= gapBuckets; j++) {
          const ratio = j / (gapBuckets + 1);
          const ts = parseMinuteToTs(prevItem.minute) + gap * ratio;
          labels.push(formatLabel(ts));
          const metrics = {};
          for (const f of METRIC_FIELDS) metrics[f] = lerp(prevItem[f], nextItem[f], ratio);
          items.push({
            ...metrics,
            run_count: 0,
            interpolated: true,
          });
        }
      }
    }
    labels.push(formatLabel(parseMinuteToTs(trend[i].minute)));
    items.push({ ...trend[i], interpolated: false });
  }

  return { labels, items };
}
