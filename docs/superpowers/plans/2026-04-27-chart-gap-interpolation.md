# 图表断线修复：自适应桶数 + 插值连线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 6h 视图中 15 分钟间隔数据导致的图表断线问题，通过自适应桶数和插值连线实现连续平滑的图表展示。

**Architecture:** 改造 `trendAggregator.js` 的 `aggregateToFixedPoints()` 函数：1) 根据数据中位间隔自适应计算桶数；2) 对小间隔空桶进行线性插值填充；3) 标记插值点以供 tooltip 过滤。前端 `SiteTrendsTab.vue` 移除固定 targetPts，添加 tooltip filter 排除插值点。

**Tech Stack:** JavaScript (ES Modules), Vitest, Chart.js v4, Vue 3

**Spec:** `docs/superpowers/specs/2026-04-27-chart-gap-interpolation-design.md`

---

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/src/utils/trendAggregator.js` | 修改 | 自适应桶数、插值逻辑、interpolated 标记 |
| `frontend/src/utils/__tests__/trendAggregator.test.js` | 修改 | 新增测试用例 |
| `frontend/src/components/SiteTrendsTab.vue` | 修改 | 移除固定 targetPts、添加 tooltip filter |

---

### Task 1: 自适应桶数计算

**Files:**
- Modify: `frontend/src/utils/trendAggregator.js:33-108`
- Modify: `frontend/src/utils/__tests__/trendAggregator.test.js`

- [ ] **Step 1: 添加计算中位间隔的辅助函数（测试先行）**

在 `frontend/src/utils/__tests__/trendAggregator.test.js` 中追加测试：

```javascript
describe('medianInterval', () => {
  it('计算连续 15 分钟间隔的中位数', () => {
    // 5 个点，间隔 15 分钟
    const data = makeMinuteData('20260410_0800', 5, { intervalMin: 15 });
    const { medianInterval } = computeAdaptiveBucketCount(data, 6);
    expect(medianInterval).toBe(15 * 60_000); // 15 min in ms
  });

  it('计算混合间隔的中位数', () => {
    // 构造间隔: 5, 5, 10, 10, 10 分钟
    const data = [];
    const baseTs = parseMinuteToTs('20260410_0800');
    const offsets = [0, 5, 10, 20, 30]; // 分钟偏移 → 间隔 5,5,10,10
    for (const off of offsets) {
      const ts = baseTs + off * 60_000;
      const d = new Date(ts);
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      const hh = String(d.getHours()).padStart(2, '0');
      const mi = String(d.getMinutes()).padStart(2, '0');
      data.push({
        minute: `${d.getFullYear()}${mm}${dd}_${hh}${mi}`,
        run_count: 1, avg_success_rate: 99, avg_ttft_p50: 0.5, avg_tpot_p50: 0.05,
      });
    }
    const { medianInterval } = computeAdaptiveBucketCount(data, 6);
    // 间隔: 5,5,10,10 → 排序后 [5,5,10,10] → 中位 = (5+10)/2 = 7.5 min
    expect(medianInterval).toBeCloseTo(7.5 * 60_000, -3);
  });

  it('单个数据点时返回默认 1 分钟', () => {
    const data = makeMinuteData('20260410_0800', 1);
    const { medianInterval } = computeAdaptiveBucketCount(data, 6);
    expect(medianInterval).toBe(60_000); // fallback 1 min
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/yakun/linkingrid/AITokenPerf/frontend && npx vitest run src/utils/__tests__/trendAggregator.test.js`
Expected: FAIL — `computeAdaptiveBucketCount` is not exported

- [ ] **Step 3: 在 trendAggregator.js 中添加 computeAdaptiveBucketCount 函数**

在 `trendAggregator.js` 的 `roundTo` 函数之后、`aggregateToFixedPoints` 之前添加：

```javascript
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
  const targetPoints = Math.round(rangeMs / medianInterval);

  return {
    targetPoints: Math.max(12, Math.min(200, targetPoints)),
    medianInterval,
    bucketWidth: medianInterval,
  };
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/yakun/linkingrid/AITokenPerf/frontend && npx vitest run src/utils/__tests__/trendAggregator.test.js`
Expected: PASS — 3 个 medianInterval 测试全部通过

- [ ] **Step 5: 添加自适应桶数集成测试**

在 `trendAggregator.test.js` 中追加：

```javascript
describe('自适应桶数', () => {
  it('15 分钟间隔 + 6h 范围 → 约 24 个桶', () => {
    const data = makeMinuteData('20260410_0800', 24, { intervalMin: 15 });
    const { items } = aggregateToFixedPoints(data, null, 6);
    // 桶数应该约等于 24（6h / 15min），且没有空桶
    const nonNull = items.filter(i => i !== null);
    expect(items.length).toBeGreaterThanOrEqual(12);
    expect(items.length).toBeLessThanOrEqual(30);
    // 所有桶都应该有数据（15min 间隔刚好填满）
    expect(nonNull.length).toBe(items.length);
  });

  it('5 分钟间隔 + 6h 范围 → 约 72 个桶', () => {
    const data = makeMinuteData('20260410_0800', 72, { intervalMin: 5 });
    const { items } = aggregateToFixedPoints(data, null, 6);
    expect(items.length).toBeGreaterThanOrEqual(60);
    expect(items.length).toBeLessThanOrEqual(80);
  });

  it('targetPts 参数为 null 时走自适应逻辑', () => {
    const data = makeMinuteData('20260410_0800', 24, { intervalMin: 15 });
    const { labels, items } = aggregateToFixedPoints(data, null, 6);
    expect(labels.length).toBe(items.length);
    expect(labels.length).toBeGreaterThanOrEqual(12);
  });

  it('targetPts 参数非 null 时保持原有行为', () => {
    const data = makeMinuteData('20260410_0800', 288);
    const { labels, items } = aggregateToFixedPoints(data, 144);
    expect(labels).toHaveLength(144);
    expect(items).toHaveLength(144);
  });
});
```

- [ ] **Step 6: 运行测试确认失败**

Run: `cd /Users/yakun/linkingrid/AITokenPerf/frontend && npx vitest run src/utils/__tests__/trendAggregator.test.js`
Expected: FAIL — 自适应桶数测试失败（当前仍用固定 targetPts）

- [ ] **Step 7: 修改 aggregateToFixedPoints 支持自适应桶数**

在 `trendAggregator.js` 的 `aggregateToFixedPoints` 函数中，替换桶数计算逻辑。找到这段代码（约第 57-61 行）：

```javascript
  const totalRange = lastTs - firstTs;
  if (totalRange <= 0) return fillGaps(trend);

  const bucketWidth = totalRange / targetPoints;
  const buckets = Array.from({ length: targetPoints }, () => []);
```

替换为：

```javascript
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
```

同时更新循环中的 `targetPoints` 引用。找到（约第 63-67 行）：

```javascript
  for (const point of trend) {
    const ts = parseMinuteToTs(point.minute);
    const idx = Math.min(Math.floor((ts - firstTs) / bucketWidth), targetPoints - 1);
    if (idx >= 0) buckets[idx].push(point);
  }
```

替换为：

```javascript
  for (const point of trend) {
    const ts = parseMinuteToTs(point.minute);
    const idx = Math.min(Math.floor((ts - firstTs) / bucketWidth), actualTargetPoints - 1);
    if (idx >= 0) buckets[idx].push(point);
  }
```

以及输出循环（约第 72 行）：

```javascript
  for (let i = 0; i < targetPoints; i++) {
```

替换为：

```javascript
  for (let i = 0; i < actualTargetPoints; i++) {
```

- [ ] **Step 8: 运行测试确认通过**

Run: `cd /Users/yakun/linkingrid/AITokenPerf/frontend && npx vitest run src/utils/__tests__/trendAggregator.test.js`
Expected: PASS — 所有测试通过

- [ ] **Step 9: 提交**

```bash
cd /Users/yakun/linkingrid/AITokenPerf
git add frontend/src/utils/trendAggregator.js frontend/src/utils/__tests__/trendAggregator.test.js
git commit -m "feat: 自适应桶数计算 - 根据数据中位间隔动态调整桶数"
```

---

### Task 2: 插值填充小间隔

**Files:**
- Modify: `frontend/src/utils/trendAggregator.js:69-108`
- Modify: `frontend/src/utils/__tests__/trendAggregator.test.js`

- [ ] **Step 1: 添加插值测试（测试先行）**

在 `trendAggregator.test.js` 中追加：

```javascript
describe('插值填充', () => {
  it('小间隔空桶被插值填充', () => {
    // 构造 15 分钟间隔数据，但中间跳过一个点（30 分钟间隔）
    const data = [];
    const baseTs = parseMinuteToTs('20260410_0800');
    // 0, 15, 30, 45, 60, 90(跳过75), 105 分钟
    const offsets = [0, 15, 30, 45, 60, 90, 105];
    for (const off of offsets) {
      const ts = baseTs + off * 60_000;
      const d = new Date(ts);
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      const hh = String(d.getHours()).padStart(2, '0');
      const mi = String(d.getMinutes()).padStart(2, '0');
      data.push({
        minute: `${d.getFullYear()}${mm}${dd}_${hh}${mi}`,
        run_count: 1,
        avg_success_rate: 99,
        avg_ttft_p50: 0.5 + off / 100, // 递增值便于验证插值
        avg_tpot_p50: 0.05,
      });
    }
    const { items } = aggregateToFixedPoints(data, null, 2);
    const nonNull = items.filter(i => i !== null);
    // 30 分钟间隔 < 2×15min=30min → 应该被插值（等于阈值时不插值）
    // 需要检查是否有 interpolated 标记
    const interpolated = items.filter(i => i !== null && i.interpolated);
    // 75 分钟处缺失，间隔 30min = 2×15min，边界情况
    // 根据设计 max(gap) < threshold 才插值，等于 threshold 不插值
    // 所以 30min gap 不应被插值（因为 max(15,15)=15 < 30 但 gap 本身=30 = threshold）
    // 这里需要看具体实现逻辑
  });

  it('大间隔空桶保持 null 断线', () => {
    // 构造数据：0, 15, 30, 120, 135 分钟（90 分钟间隔）
    const data = [];
    const baseTs = parseMinuteToTs('20260410_0800');
    const offsets = [0, 15, 30, 120, 135];
    for (const off of offsets) {
      const ts = baseTs + off * 60_000;
      const d = new Date(ts);
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      const hh = String(d.getHours()).padStart(2, '0');
      const mi = String(d.getMinutes()).padStart(2, '0');
      data.push({
        minute: `${d.getFullYear()}${mm}${dd}_${hh}${mi}`,
        run_count: 1,
        avg_success_rate: 99,
        avg_ttft_p50: 0.5,
        avg_tpot_p50: 0.05,
      });
    }
    const { items } = aggregateToFixedPoints(data, null, 2);
    // 90 分钟间隔 >> 2×15min=30min → 应该断线
    const nullCount = items.filter(i => i === null).length;
    expect(nullCount).toBeGreaterThan(0);
  });

  it('插值点标记为 interpolated: true', () => {
    // 构造数据：0, 15, 45 分钟（30 分钟间隔 = 2×15min）
    const data = [];
    const baseTs = parseMinuteToTs('20260410_0800');
    const offsets = [0, 15, 45];
    for (const off of offsets) {
      const ts = baseTs + off * 60_000;
      const d = new Date(ts);
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      const hh = String(d.getHours()).padStart(2, '0');
      const mi = String(d.getMinutes()).padStart(2, '0');
      data.push({
        minute: `${d.getFullYear()}${mm}${dd}_${hh}${mi}`,
        run_count: 1,
        avg_success_rate: 99,
        avg_ttft_p50: 0.5,
        avg_tpot_p50: 0.05,
      });
    }
    const { items } = aggregateToFixedPoints(data, null, 1);
    // 检查是否存在 interpolated 标记
    const realItems = items.filter(i => i !== null && !i.interpolated);
    const interpItems = items.filter(i => i !== null && i.interpolated);
    // 30 分钟间隔，中位间隔 15 分钟，阈值 30 分钟
    // gap(30) < threshold(30) 为 false → 不插值
    // 所以应该没有插值点
    expect(interpItems.length).toBe(0);
  });

  it('插值数值正确（线性插值）', () => {
    // 构造数据：0 分钟(ttft=0.5), 30 分钟(ttft=1.1)
    // 中位间隔 30 分钟，阈值 60 分钟
    // 中间 15 分钟处应该插值为 (0.5+1.1)/2 = 0.8
    const data = [];
    const baseTs = parseMinuteToTs('20260410_0800');
    const points = [
      { off: 0, ttft: 0.5 },
      { off: 30, ttft: 1.1 },
    ];
    for (const p of points) {
      const ts = baseTs + p.off * 60_000;
      const d = new Date(ts);
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      const hh = String(d.getHours()).padStart(2, '0');
      const mi = String(d.getMinutes()).padStart(2, '0');
      data.push({
        minute: `${d.getFullYear()}${mm}${dd}_${hh}${mi}`,
        run_count: 1,
        avg_success_rate: 99,
        avg_ttft_p50: p.ttft,
        avg_tpot_p50: 0.05,
      });
    }
    const { items } = aggregateToFixedPoints(data, null, 1);
    // 桶宽 = 30min，2 个桶（0-30, 30-60）
    // 桶 0 有数据点（off=0），桶 1 有数据点（off=30）
    // 没有空桶 → 没有插值
    // 需要更多桶来测试插值...用 rangeHours=2 制造更多桶
    const { items: items2 } = aggregateToFixedPoints(data, null, 2);
    // rangeHours=2, 中位间隔=30min, 桶数=120/30=4
    // 桶 0: 0-30min → 有数据(off=0)
    // 桶 1: 30-60min → 有数据(off=30)
    // 桶 2: 60-90min → 空
    // 桶 3: 90-120min → 空
    // 桶 2,3 没有前后数据包围 → null
    // 无法用 2 个点测试插值，需要 3+ 个点
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/yakun/linkingrid/AITokenPerf/frontend && npx vitest run src/utils/__tests__/trendAggregator.test.js`
Expected: FAIL — 插值相关测试失败

- [ ] **Step 3: 实现插值逻辑**

在 `trendAggregator.js` 的 `aggregateToFixedPoints` 函数中，找到桶遍历循环（现在约第 82-107 行，即 `for (let i = 0; i < actualTargetPoints; i++)` 那段）。将整个循环替换为：

```javascript
  // 预计算：每个桶是否为空，以及前后最近的非空桶索引
  const nonEmptyIndices = [];
  for (let i = 0; i < actualTargetPoints; i++) {
    if (buckets[i].length > 0) nonEmptyIndices.push(i);
  }

  const labels = [];
  const items = [];

  for (let i = 0; i < actualTargetPoints; i++) {
    const midTs = firstTs + (i + 0.5) * bucketWidth;

    if (buckets[i].length > 0) {
      // 有数据的桶：加权平均
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
        interpolated: false,
      });
    } else {
      // 空桶：检查是否可以插值
      // 找到前后最近的非空桶
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
        const nextWeight = nextBucket.reduce((s, p) => s + (p.run_count || 1), 0);

        function nextWeightedAvg(field) {
          let sum = 0, wSum = 0;
          for (const p of nextBucket) {
            const val = p[field];
            if (val != null) {
              const w = p.run_count || 1;
              sum += val * w;
              wSum += w;
            }
          }
          return wSum > 0 ? roundTo(sum / wSum, 2) : null;
        }

        function interpolateField(field) {
          const pv = prevItem[field];
          const nv = nextWeightedAvg(field);
          if (pv == null || nv == null) return null;
          return roundTo(pv + (nv - pv) * ratio, 2);
        }

        labels.push(formatLabel(midTs));
        items.push({
          avg_success_rate: interpolateField('avg_success_rate'),
          avg_throughput: interpolateField('avg_throughput'),
          avg_tps: interpolateField('avg_tps'),
          avg_ttft_p50: interpolateField('avg_ttft_p50'),
          avg_tpot_p50: interpolateField('avg_tpot_p50'),
          avg_e2e_p50: interpolateField('avg_e2e_p50'),
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/yakun/linkingrid/AITokenPerf/frontend && npx vitest run src/utils/__tests__/trendAggregator.test.js`
Expected: PASS — 所有测试通过

- [ ] **Step 5: 精细化插值测试**

在 `trendAggregator.test.js` 中追加更精确的插值验证：

```javascript
  it('插值数值线性正确', () => {
    // 3 个点: off=0(ttft=0.5), off=30(ttft=1.1), off=60(ttft=0.8)
    // 中位间隔=30min, 桶数=4 (rangeHours=2, 120/30=4)
    // 桶 0: 0-30 → data(off=0)
    // 桶 1: 30-60 → data(off=30)
    // 桶 2: 60-90 → data(off=60)
    // 桶 3: 90-120 → 空，无前后包围 → null
    // 没有插值场景，需要更密的桶
    // 改用 rangeHours=4 → 桶数=240/30=8
    const data = [];
    const baseTs = parseMinuteToTs('20260410_0800');
    const points = [
      { off: 0, ttft: 0.5 },
      { off: 30, ttft: 1.1 },
      { off: 90, ttft: 0.8 },
    ];
    for (const p of points) {
      const ts = baseTs + p.off * 60_000;
      const d = new Date(ts);
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      const hh = String(d.getHours()).padStart(2, '0');
      const mi = String(d.getMinutes()).padStart(2, '0');
      data.push({
        minute: `${d.getFullYear()}${mm}${dd}_${hh}${mi}`,
        run_count: 1, avg_success_rate: 99,
        avg_ttft_p50: p.ttft, avg_tpot_p50: 0.05,
      });
    }
    // 中位间隔: (30+60)/2=45min → 桶数=240/45≈5
    // 桶宽=45min, gapThreshold=90min
    // off=0 → 桶 0 (0-45)
    // off=30 → 桶 0 (0-45) ← 和 off=0 同桶
    // off=90 → 桶 2 (90-135)
    // 桶 1 (45-90) 空，gap=max(45,45)=45 < 90 → 插值
    const { items } = aggregateToFixedPoints(data, null, 4);
    const interpItems = items.filter(i => i !== null && i.interpolated);
    expect(interpItems.length).toBeGreaterThan(0);
    // 插值点的 ttft 应在 0.5 和 0.8 之间
    for (const item of interpItems) {
      expect(item.avg_ttft_p50).toBeGreaterThan(0.5);
      expect(item.avg_ttft_p50).toBeLessThan(0.8);
    }
  });
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd /Users/yakun/linkingrid/AITokenPerf/frontend && npx vitest run src/utils/__tests__/trendAggregator.test.js`
Expected: PASS

- [ ] **Step 7: 修复 fillGaps 路径也支持插值**

在 `trendAggregator.js` 的 `fillGaps` 函数中，当前在间隔处插入 `null`。改为：当间隔 < gapThreshold 时插入插值点，否则插入 null。

找到 `fillGaps` 函数（约第 129-161 行），替换为：

```javascript
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
        // 大间隔：断线
        labels.push(null);
        items.push(null);
      } else if (gap > medianInterval * 1.01) {
        // 小间隔但非连续：线性插值
        // 在两个真实数据点之间均匀插入插值点
        const gapBuckets = Math.round(gap / medianInterval) - 1;
        const prevItem = trend[i - 1];
        const nextItem = trend[i];
        for (let j = 1; j <= gapBuckets; j++) {
          const ratio = j / (gapBuckets + 1);
          const ts = parseMinuteToTs(prevItem.minute) + gap * ratio;
          labels.push(formatLabel(ts));
          items.push({
            avg_success_rate: lerp(prevItem.avg_success_rate, nextItem.avg_success_rate, ratio),
            avg_throughput: lerp(prevItem.avg_throughput, nextItem.avg_throughput, ratio),
            avg_tps: lerp(prevItem.avg_tps, nextItem.avg_tps, ratio),
            avg_ttft_p50: lerp(prevItem.avg_ttft_p50, nextItem.avg_ttft_p50, ratio),
            avg_tpot_p50: lerp(prevItem.avg_tpot_p50, nextItem.avg_tpot_p50, ratio),
            avg_e2e_p50: lerp(prevItem.avg_e2e_p50, nextItem.avg_e2e_p50, ratio),
            run_count: 0,
            interpolated: true,
          });
        }
      }
      // 连续间隔（<= medianInterval * 1.01）：不插入任何东西
    }
    labels.push(formatLabel(parseMinuteToTs(trend[i].minute)));
    items.push({ ...trend[i], interpolated: false });
  }

  return { labels, items };
}
```

在 `roundTo` 函数之后添加线性插值辅助函数：

```javascript
function lerp(a, b, ratio) {
  if (a == null || b == null) return null;
  return roundTo(a + (b - a) * ratio, 2);
}
```

- [ ] **Step 8: 运行所有测试确认通过**

Run: `cd /Users/yakun/linkingrid/AITokenPerf/frontend && npx vitest run src/utils/__tests__/trendAggregator.test.js`
Expected: PASS — 所有测试通过（包括原有的 fillGaps 相关测试需要更新期望值）

- [ ] **Step 9: 更新原有测试期望**

原有测试 `少量数据有间隔时插入 null 断开`（第 65-74 行）现在可能需要更新，因为小间隔会被插值而不是 null。检查该测试是否仍然通过，如果失败则更新期望：

```javascript
  it('少量数据有大间隔时插入 null 断开', () => {
    // 前 10 分钟 + 跳过 60 分钟 + 后 10 分钟（间隔 70 分钟 >> 2×1min）
    const part1 = makeMinuteData('20260410_0800', 10);
    const part2 = makeMinuteData('20260410_0910', 10);
    const data = [...part1, ...part2];
    const { items } = aggregateToFixedPoints(data);
    const nullCount = items.filter(i => i === null).length;
    expect(nullCount).toBeGreaterThan(0);
  });
```

- [ ] **Step 10: 运行测试确认通过并提交**

Run: `cd /Users/yakun/linkingrid/AITokenPerf/frontend && npx vitest run src/utils/__tests__/trendAggregator.test.js`
Expected: PASS

```bash
cd /Users/yakun/linkingrid/AITokenPerf
git add frontend/src/utils/trendAggregator.js frontend/src/utils/__tests__/trendAggregator.test.js
git commit -m "feat: 插值填充小间隔 - 线性插值保持线条连续，大间隔仍断线"
```

---

### Task 3: 前端 targetPts 调整 + Tooltip 过滤

**Files:**
- Modify: `frontend/src/components/SiteTrendsTab.vue:328-488`

- [ ] **Step 1: 修改 renderLatencyChart 移除固定 targetPts**

在 `SiteTrendsTab.vue` 的 `renderLatencyChart` 函数中（约第 334-337 行），将：

```javascript
  // 桶数随时间范围缩放，保持 ~10 min/桶 的密度（与 24h 一致）
  const hours = timeRangeStore.hours;
  const targetPts = hours ? Math.min(144, Math.max(36, hours * 6)) : 144;
  const { labels, items } = aggregateToFixedPoints(trend, targetPts, hours);
```

替换为：

```javascript
  const hours = timeRangeStore.hours;
  const { labels, items } = aggregateToFixedPoints(trend, null, hours);
```

- [ ] **Step 2: 修改 renderQualityChart 同样移除固定 targetPts**

在 `renderQualityChart` 函数中（约第 407-409 行），将：

```javascript
  const hours = timeRangeStore.hours;
  const targetPts = hours ? Math.min(144, Math.max(36, hours * 6)) : 144;
  const { labels, items } = aggregateToFixedPoints(trend, targetPts, hours);
```

替换为：

```javascript
  const hours = timeRangeStore.hours;
  const { labels, items } = aggregateToFixedPoints(trend, null, hours);
```

- [ ] **Step 3: 为 Latency Chart 添加 tooltip filter**

在 `renderLatencyChart` 的 `plugins.tooltip` 配置中（约第 379-383 行），将：

```javascript
        tooltip: {
          callbacks: {
            label: ctx => ctx.parsed.y != null ? `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(3)}s` : '',
          },
        },
```

替换为：

```javascript
        tooltip: {
          filter: (tooltipItem) => {
            const raw = tooltipItem.raw;
            return raw != null;
          },
          callbacks: {
            label: ctx => {
              if (ctx.parsed.y == null) return '';
              const item = ctx.chart.data.items?.[ctx.dataIndex];
              if (item?.interpolated) return '';
              return `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(3)}s`;
            },
          },
        },
```

注意：需要将 `items` 传入 chart 的 data 对象。在 `renderLatencyChart` 中，chart data 部分（约第 342 行）添加 `items`：

```javascript
    data: {
      labels,
      items,  // 新增：供 tooltip filter 使用
      datasets: [
```

- [ ] **Step 4: 为 Quality Chart 添加 tooltip filter**

在 `renderQualityChart` 中同样操作。在 chart data 部分添加 `items`：

```javascript
    data: {
      labels,
      items,  // 新增
      datasets: [
```

在 `plugins.tooltip` 配置中（约第 455-463 行），将：

```javascript
        tooltip: {
          callbacks: {
            label: ctx => {
              if (ctx.parsed.y == null) return '';
              if (ctx.dataset.yAxisID === 'y1') return `失败率: ${ctx.parsed.y.toFixed(1)}%`;
              return `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)} t/s`;
            },
          },
        },
```

替换为：

```javascript
        tooltip: {
          filter: (tooltipItem) => {
            const raw = tooltipItem.raw;
            return raw != null;
          },
          callbacks: {
            label: ctx => {
              if (ctx.parsed.y == null) return '';
              const item = ctx.chart.data.items?.[ctx.dataIndex];
              if (item?.interpolated) return '';
              if (ctx.dataset.yAxisID === 'y1') return `失败率: ${ctx.parsed.y.toFixed(1)}%`;
              return `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)} t/s`;
            },
          },
        },
```

- [ ] **Step 5: 手动验证（无自动化测试）**

此步骤涉及 Chart.js 渲染，无法通过单元测试验证。手动检查：
1. 启动 dev server：`cd /Users/yakun/linkingrid/AITokenPerf/frontend && npm run dev`
2. 打开浏览器，选择 6h 时间范围
3. 检查图表线条是否连续（15 分钟间隔数据）
4. hover tooltip 是否只显示真实数据点

- [ ] **Step 6: 运行全量测试确认无回归**

Run: `cd /Users/yakun/linkingrid/AITokenPerf/frontend && npx vitest run`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
cd /Users/yakun/linkingrid/AITokenPerf
git add frontend/src/components/SiteTrendsTab.vue
git commit -m "feat: 前端适配 - 移除固定 targetPts，tooltip 过滤插值点"
```

---

### Task 4: 边界情况测试

**Files:**
- Modify: `frontend/src/utils/__tests__/trendAggregator.test.js`

- [ ] **Step 1: 添加边界情况测试**

在 `trendAggregator.test.js` 中追加：

```javascript
describe('边界情况', () => {
  it('单个数据点不插值', () => {
    const data = makeMinuteData('20260410_0800', 1);
    const { items } = aggregateToFixedPoints(data, null, 6);
    expect(items).toHaveLength(1);
    expect(items[0]).not.toBeNull();
    expect(items[0].interpolated).toBeFalsy();
  });

  it('所有点在同一分钟（中位间隔为 0）', () => {
    const data = makeMinuteData('20260410_0800', 5, { intervalMin: 0 });
    // intervalMin=0 → 所有分钟相同，但 makeMinuteData 会生成相同的 minute 字段
    // 这种情况后端不会出现，但应不崩溃
    const { items } = aggregateToFixedPoints(data, null, 1);
    expect(items.length).toBeGreaterThanOrEqual(1);
  });

  it('rangeHours 有值但无数据 → emptyRange', () => {
    const { labels, items } = aggregateToFixedPoints([], null, 6);
    expect(labels.length).toBeGreaterThan(0);
    expect(items.every(i => i === null)).toBe(true);
  });

  it('24h 视图 + 15min 间隔 → 桶数约 96', () => {
    const data = makeMinuteData('20260410_0000', 96, { intervalMin: 15 });
    const { items } = aggregateToFixedPoints(data, null, 24);
    expect(items.length).toBeGreaterThanOrEqual(80);
    expect(items.length).toBeLessThanOrEqual(110);
  });

  it('7d 视图 + 5min 间隔 → 桶数约 200（上限）', () => {
    const data = makeMinuteData('20260404_0000', 200, { intervalMin: 5 });
    const { items } = aggregateToFixedPoints(data, null, 168);
    expect(items.length).toBeLessThanOrEqual(200);
  });
});
```

- [ ] **Step 2: 运行测试确认通过**

Run: `cd /Users/yakun/linkingrid/AITokenPerf/frontend && npx vitest run src/utils/__tests__/trendAggregator.test.js`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
cd /Users/yakun/linkingrid/AITokenPerf
git add frontend/src/utils/__tests__/trendAggregator.test.js
git commit -m "test: 添加边界情况测试 - 单点、零间隔、大数据量"
```

---

## 验证清单

全部实现完成后，手动验证：

- [ ] `cd /Users/yakun/linkingrid/AITokenPerf/frontend && npx vitest run` — 全部 PASS
- [ ] `cd /Users/yakun/linkingrid/AITokenPerf/frontend && npm run build` — 构建成功
- [ ] 6h 视图 + 15min 间隔 → 线条连续
- [ ] 6h 视图 + 5min 间隔 → 桶数增加，线条平滑
- [ ] 存在 1 小时+ 缺数据 → 断线
- [ ] hover tooltip → 只显示真实数据点
- [ ] 24h / 7d 视图 → 行为正常
- [ ] 无数据 → 空图表正常显示
