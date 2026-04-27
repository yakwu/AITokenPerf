# 图表断线修复：自适应桶数 + 插值连线

## 问题

6h 视图固定生成 36 个桶（每桶 10 分钟），但 15 分钟间隔的数据只有 ~24 个点，导致约 12 个空桶，图表到处断线。

根本原因：桶数公式 `hours * 6` 假设 10 分钟间隔，不适应实际数据密度。

## 设计

### 1. 自适应桶数

**改动位置：** `frontend/src/utils/trendAggregator.js` — `aggregateToFixedPoints()`

计算逻辑：
```
medianInterval = 数据点之间时间差的中位数
bucketWidth = medianInterval（桶宽 = 中位间隔）
targetPoints = (lastTs - firstTs) / bucketWidth
clamp(targetPoints, 12, 200)
```

当 `rangeHours` 固定时：
- `lastTs = Date.now()`
- `firstTs = lastTs - rangeHours * 3600_000`

当无固定范围时：
- `firstTs / lastTs` 取自数据首尾

**注意：** 当调用方传入 `null` 时，函数内部根据数据密度自适应计算桶数。`targetPts` 参数保留用于向后兼容（如未来需要固定桶数的场景）。

### 2. 插值填充小间隔

**改动位置：** `frontend/src/utils/trendAggregator.js` — `aggregateToFixedPoints()` 桶遍历循环

当前空桶直接 `push(null)` 断线。改为：

```
对每个空桶 i：
  prevIdx = 向前找第一个非空桶
  nextIdx = 向后找第一个非空桶

  gapFromPrev = (i - prevIdx) * bucketWidth
  gapFromNext = (nextIdx - i) * bucketWidth

  if prevIdx 和 nextIdx 都存在
    且 max(gapFromPrev, gapFromNext) < gapThreshold：
      → 线性插值，标记 interpolated: true
  else：
      → null 断线（保持现有行为）
```

**gapThreshold** = `medianInterval * 2`（2 倍中位间隔）

线性插值公式（对每个数值字段）：
```
ratio = (i - prevIdx) / (nextIdx - prevIdx)
value = prevValue + (nextValue - prevValue) * ratio
```

### 3. 插值标记

插值点的数据结构：
```javascript
{
  avg_ttft_p50: 1.2,
  avg_tpot_p50: 0.05,
  // ... 其他字段
  interpolated: true,  // 新增字段
  run_count: 0,        // 插值点没有真实检测次数
}
```

真实数据点保持 `interpolated: false`（或不设此字段）。

### 4. Tooltip 过滤

**改动位置：** `frontend/src/components/SiteTrendsTab.vue` — Chart.js options

在两个图表（Latency / Quality）的 options 中添加 tooltip filter：

```javascript
plugins: {
  tooltip: {
    filter: (tooltipItem) => {
      const item = tooltipItem.raw;
      return item != null && !item.interpolated;
    },
    callbacks: {
      // title/label/body 回调保持现有逻辑，因 filter 已排除插值点
    }
  }
}
```

### 5. 前端 targetPts 调整

**改动位置：** `frontend/src/components/SiteTrendsTab.vue` — `renderLatencyChart()` / `renderQualityChart()`

当前：
```javascript
const targetPts = hours ? Math.min(144, Math.max(36, hours * 6)) : 144;
```

改为传入 `null`，让 `aggregateToFixedPoints` 自行计算：
```javascript
const { labels, items } = aggregateToFixedPoints(trend, null, hours);
```

`aggregateToFixedPoints` 内部根据数据密度自适应计算 `targetPoints`。

## 不改动的部分

- 后端 API（`/api/sites/trend`、`/api/schedules/{id}/trend`）不变
- 数据库 schema 不变
- HistoryView 的 bar chart 不受影响（不用 line chart）
- `fillGaps()` 路径保留（无 rangeHours 且数据少时仍走此路径），但同样加入插值逻辑以保持一致

## 边界情况

1. **单个数据点**：直接返回该点，不插值（无法插值）
2. **所有桶为空**：走 `emptyRange()` 逻辑，生成空时间轴
3. **中位间隔为 0**（所有点同一分钟）：使用 1 分钟作为 fallback 桶宽
4. **数据点时间范围极短**（< 2 个桶宽）：强制至少 12 个桶

## 文件清单

| 文件 | 改动 |
|------|------|
| `frontend/src/utils/trendAggregator.js` | 自适应桶数、插值逻辑、interpolated 标记 |
| `frontend/src/components/SiteTrendsTab.vue` | 移除固定 targetPts、添加 tooltip filter |

## 验证

1. 6h 视图 + 15min 间隔 → 线条连续，无断线
2. 6h 视图 + 5min 间隔 → 桶数增加（约 72），线条平滑
3. 存在 1 小时+ 缺数据 → 对应位置断线
4. hover tooltip → 只显示真实数据点
5. 24h / 7d 视图 → 行为一致，桶数自适应
6. 无数据时 → 空图表正常显示
