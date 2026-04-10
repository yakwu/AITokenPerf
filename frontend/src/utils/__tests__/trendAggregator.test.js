import { describe, it, expect } from 'vitest';
import { parseMinuteToTs, aggregateToFixedPoints } from '../trendAggregator.js';

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
