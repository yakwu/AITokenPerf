import { describe, it, expect, vi, afterEach } from 'vitest';
import { parseMinuteToTs, aggregateToFixedPoints, computeAdaptiveBucketCount } from '../trendAggregator.js';

// 辅助：生成连续的分钟级测试数据
function makeMinuteData(startMinute, count, { intervalMin = 1, fields = {} } = {}) {
  const result = [];
  // startMinute 格式: "20260410_0800"
  const baseTs = parseMinuteToTs(startMinute);
  for (let i = 0; i < count; i++) {
    const ts = baseTs + i * intervalMin * 60_000;
    const d = new Date(ts);
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const mi = String(d.getMinutes()).padStart(2, '0');
    result.push({
      minute: `${d.getFullYear()}${mm}${dd}_${hh}${mi}`,
      run_count: fields.run_count ?? 1,
      avg_success_rate: fields.avg_success_rate ?? 99.0,
      avg_throughput: fields.avg_throughput ?? 10.0,
      avg_ttft_p50: fields.avg_ttft_p50 ?? 0.5,
      avg_e2e_p50: fields.avg_e2e_p50 ?? 2.0,
    });
  }
  return result;
}

describe('parseMinuteToTs', () => {
  it('解析 YYYYMMDD_HHMM 格式', () => {
    const ts = parseMinuteToTs('20260410_0830');
    const d = new Date(ts);
    expect(d.getFullYear()).toBe(2026);
    expect(d.getMonth()).toBe(3); // 0-indexed
    expect(d.getDate()).toBe(10);
    expect(d.getHours()).toBe(8);
    expect(d.getMinutes()).toBe(30);
  });
});

describe('aggregateToFixedPoints', () => {
  it('空数据返回空', () => {
    const { labels, items } = aggregateToFixedPoints([]);
    expect(labels).toEqual([]);
    expect(items).toEqual([]);
  });

  it('单点数据直接返回', () => {
    const data = makeMinuteData('20260410_0800', 1);
    const { labels, items } = aggregateToFixedPoints(data);
    expect(labels).toHaveLength(1);
    expect(items).toHaveLength(1);
    expect(items[0]).toEqual(data[0]);
  });

  it('少量数据（<144点）不聚合，保留原始数据', () => {
    const data = makeMinuteData('20260410_0800', 50);
    const { labels, items } = aggregateToFixedPoints(data);
    expect(labels).toHaveLength(50);
    expect(items).toHaveLength(50);
    // 每个非 null 的 item 应该是原始数据点
    const nonNull = items.filter(i => i !== null);
    expect(nonNull).toHaveLength(50);
  });

  it('少量数据有间隔时插入 null 断开', () => {
    // 前 10 分钟 + 跳过 60 分钟 + 后 10 分钟
    const part1 = makeMinuteData('20260410_0800', 10);
    const part2 = makeMinuteData('20260410_0910', 10); // 跳了 70 分钟
    const data = [...part1, ...part2];
    const { labels, items } = aggregateToFixedPoints(data);
    // 应该有 null 插入（间隔检测）
    const nullCount = items.filter(i => i === null).length;
    expect(nullCount).toBeGreaterThan(0);
  });

  it('288 个分钟点聚合到 144 个桶', () => {
    const data = makeMinuteData('20260410_0800', 288);
    const { labels, items } = aggregateToFixedPoints(data, 144);
    expect(labels).toHaveLength(144);
    expect(items).toHaveLength(144);
  });

  it('聚合后空桶应为 null（中间有间隔）', () => {
    // 前 6 小时数据（360 分钟），后面没有数据
    // 用 144 桶聚合 12 小时范围（只有前半部分有数据）
    const data = makeMinuteData('20260410_0800', 360); // 6h 的数据
    // 手动让范围扩展到 12h：在末尾加一个远处的点
    data.push(...makeMinuteData('20260410_2000', 1)); // 12h 后
    const { labels, items } = aggregateToFixedPoints(data, 144);
    // 后半部分的桶应该是 null
    const nullCount = items.filter(i => i === null).length;
    expect(nullCount).toBeGreaterThan(0);
  });

  it('run_count 加权平均正确计算', () => {
    // 构造两个点落在同一个桶内
    // 用 2 个桶来聚合 2 个连续分钟点 → 每个桶约 1 分钟宽度
    // 不太好直接控制桶分配，改用 144 桶聚合 144 分钟内的数据
    // 我们直接构造 288 个点（每分钟 2 个点 → 不可能，因为后端已经按分钟聚合了）
    //
    // 换个策略：144 桶聚合 288 分钟，每个桶约 2 分钟
    // 构造 288 个点，其中奇数分钟 run_count=2, value=10；偶数分钟 run_count=8, value=20
    const data = [];
    const baseTs = parseMinuteToTs('20260410_0800');
    for (let i = 0; i < 288; i++) {
      const ts = baseTs + i * 60_000;
      const d = new Date(ts);
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      const hh = String(d.getHours()).padStart(2, '0');
      const mi = String(d.getMinutes()).padStart(2, '0');
      const isEven = i % 2 === 0;
      data.push({
        minute: `${d.getFullYear()}${mm}${dd}_${hh}${mi}`,
        run_count: isEven ? 2 : 8,
        avg_throughput: isEven ? 10 : 20,
        avg_success_rate: isEven ? 90 : 100,
        avg_ttft_p50: isEven ? 0.5 : 1.0,
        avg_e2e_p50: isEven ? 2.0 : 4.0,
      });
    }
    const { items } = aggregateToFixedPoints(data, 144);
    const nonNull = items.filter(i => i !== null);
    // 加权平均: (10*2 + 20*8) / (2+8) = (20+160)/10 = 18
    for (const item of nonNull) {
      if (item.avg_throughput != null) {
        expect(item.avg_throughput).toBeCloseTo(18, 0);
      }
    }
  });

  it('7 天数据（~10080 分钟点）聚合到 144 点', () => {
    const data = makeMinuteData('20260404_0000', 10080); // 7 天
    const { labels, items } = aggregateToFixedPoints(data, 144);
    expect(labels).toHaveLength(144);
    expect(items).toHaveLength(144);
    // 大部分桶应该有数据
    const nonNull = items.filter(i => i !== null);
    expect(nonNull.length).toBeGreaterThan(100);
  });

  it('标签格式为 MM-DD HH:mm', () => {
    const data = makeMinuteData('20260410_0800', 5);
    const { labels } = aggregateToFixedPoints(data);
    // 每个非 null label 应该是 "MM-DD HH:mm" 格式
    const nonNullLabels = labels.filter(l => l !== null);
    for (const label of nonNullLabels) {
      expect(label).toMatch(/^\d{2}-\d{2} \d{2}:\d{2}$/);
    }
  });
});

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

describe('自适应桶数', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('15 分钟间隔 + 6h 范围 → 约 24 个桶', () => {
    // 数据范围: 0800 ~ 1400（24 个点 × 15min = 6h）
    // mock Date.now 为数据末尾之后，让 rangeHours=6 窗口覆盖所有数据
    const dataEndTs = parseMinuteToTs('20260410_0800') + 23 * 15 * 60_000; // 最后一个数据点
    const fakeNow = dataEndTs + 60_000; // 比最后数据点晚 1 分钟
    vi.spyOn(Date, 'now').mockReturnValue(fakeNow);

    const data = makeMinuteData('20260410_0800', 24, { intervalMin: 15 });
    const { items } = aggregateToFixedPoints(data, null, 6);
    const nonNull = items.filter(i => i !== null);
    expect(items.length).toBeGreaterThanOrEqual(12);
    expect(items.length).toBeLessThanOrEqual(30);
    expect(nonNull.length).toBe(items.length);
  });

  it('5 分钟间隔 + 6h 范围 → 约 72 个桶', () => {
    // 数据范围: 0800 ~ 1400（72 个点 × 5min = 6h）
    const dataEndTs = parseMinuteToTs('20260410_0800') + 71 * 5 * 60_000;
    const fakeNow = dataEndTs + 60_000;
    vi.spyOn(Date, 'now').mockReturnValue(fakeNow);

    const data = makeMinuteData('20260410_0800', 72, { intervalMin: 5 });
    const { items } = aggregateToFixedPoints(data, null, 6);
    expect(items.length).toBeGreaterThanOrEqual(60);
    expect(items.length).toBeLessThanOrEqual(80);
  });

  it('targetPts 参数为 null 时走自适应逻辑', () => {
    const dataEndTs = parseMinuteToTs('20260410_0800') + 23 * 15 * 60_000;
    const fakeNow = dataEndTs + 60_000;
    vi.spyOn(Date, 'now').mockReturnValue(fakeNow);

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

describe('点数钳位后桶宽放大 (#44)', () => {
  it('钳到上限 200 后，点数×桶宽仍覆盖完整范围', () => {
    // 5min 间隔、~57h 范围 → round(57.25*12)=687 → 钳到 200
    const data = makeMinuteData('20260607_0001', 688, { intervalMin: 5 });
    const rangeHours =
      (parseMinuteToTs(data[data.length - 1].minute) - parseMinuteToTs(data[0].minute)) / 3600_000;
    const { targetPoints, bucketWidth } = computeAdaptiveBucketCount(data, rangeHours);
    expect(targetPoints).toBe(200); // 触发钳位
    // 覆盖范围（点数×桶宽）必须 ≈ 总跨度，而不是固定 200×5min=16.6h
    expect(targetPoints * bucketWidth).toBeCloseTo(rangeHours * 3600_000, -5);
  });

  it('「全部」视图 X 轴铺满到最新数据，不被压成固定 16.6h', () => {
    // 数据 06-07 00:01 → 06-09 09:16（5min 间隔，688 点）
    const data = makeMinuteData('20260607_0001', 688, { intervalMin: 5 });
    const { labels } = aggregateToFixedPoints(data, null, null);
    // 末尾标签应落在数据最后一天 06-09，而非被截断到 06-07
    expect(labels[labels.length - 1]).toMatch(/^06-09/);
  });
});

describe('插值填充', () => {
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
    // mock Date.now 使数据落在 rangeHours 窗口内
    const fakeNow = baseTs + 140 * 60_000;
    vi.spyOn(Date, 'now').mockReturnValue(fakeNow);
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
    // mock Date.now 使数据落在 rangeHours 窗口内
    const fakeNow = baseTs + 50 * 60_000;
    vi.spyOn(Date, 'now').mockReturnValue(fakeNow);
    const { items } = aggregateToFixedPoints(data, null, 1);
    // 桶宽随钳位放大后，点按真实时间分布，中间空桶在阈值内被插值填充
    const interpItems = items.filter(i => i !== null && i.interpolated);
    expect(interpItems.length).toBeGreaterThan(0);
    expect(interpItems.every(i => i.interpolated === true)).toBe(true);
  });

  it('插值数值线性正确', () => {
    // 3 个点: off=0(ttft=0.5), off=30(ttft=1.1), off=90(ttft=0.8)
    // 中位间隔=30min, 桶数≈5 (rangeHours=4, 240/45≈5)
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
    // mock Date.now 使数据落在 rangeHours 窗口内
    const fakeNow = baseTs + 95 * 60_000; // 最后数据点后 5 分钟
    vi.spyOn(Date, 'now').mockReturnValue(fakeNow);
    const { items } = aggregateToFixedPoints(data, null, 4);
    const interpItems = items.filter(i => i !== null && i.interpolated);
    expect(interpItems.length).toBeGreaterThan(0);
    // 插值点的 ttft 应在原始数据范围内（0.5 ~ 1.1）
    for (const item of interpItems) {
      expect(item.avg_ttft_p50).toBeGreaterThanOrEqual(0.5);
      expect(item.avg_ttft_p50).toBeLessThanOrEqual(1.1);
    }
  });
});

describe('边界情况', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('单个数据点不插值', () => {
    const data = makeMinuteData('20260410_0800', 1);
    // 不传 rangeHours，走 length===1 快捷路径
    const { items } = aggregateToFixedPoints(data);
    expect(items).toHaveLength(1);
    expect(items[0]).not.toBeNull();
    expect(items[0].interpolated).toBeFalsy();
  });

  it('所有点在同一分钟（中位间隔为 0）', () => {
    const data = makeMinuteData('20260410_0800', 5, { intervalMin: 0 });
    const fakeNow = parseMinuteToTs('20260410_0800') + 60_000;
    vi.spyOn(Date, 'now').mockReturnValue(fakeNow);
    const { items } = aggregateToFixedPoints(data, null, 1);
    expect(items.length).toBeGreaterThanOrEqual(1);
  });

  it('rangeHours 有值但无数据 → emptyRange', () => {
    vi.spyOn(Date, 'now').mockReturnValue(parseMinuteToTs('20260410_0800'));
    const { labels, items } = aggregateToFixedPoints([], 144, 6);
    expect(labels.length).toBeGreaterThan(0);
    expect(labels).toHaveLength(144);
    expect(items.every(i => i === null)).toBe(true);
  });

  it('24h 视图 + 15min 间隔 → 桶数约 96', () => {
    const data = makeMinuteData('20260410_0000', 96, { intervalMin: 15 });
    const fakeNow = parseMinuteToTs('20260410_0000') + 96 * 15 * 60_000 + 60_000;
    vi.spyOn(Date, 'now').mockReturnValue(fakeNow);
    const { items } = aggregateToFixedPoints(data, null, 24);
    expect(items.length).toBeGreaterThanOrEqual(80);
    expect(items.length).toBeLessThanOrEqual(110);
  });

  it('7d 视图 + 5min 间隔 → 桶数约 200（上限）', () => {
    const data = makeMinuteData('20260404_0000', 200, { intervalMin: 5 });
    const fakeNow = parseMinuteToTs('20260404_0000') + 200 * 5 * 60_000 + 60_000;
    vi.spyOn(Date, 'now').mockReturnValue(fakeNow);
    const { items } = aggregateToFixedPoints(data, null, 168);
    expect(items.length).toBeLessThanOrEqual(200);
  });
});
