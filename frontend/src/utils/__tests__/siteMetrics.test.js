import { describe, it, expect } from 'vitest';
import { availabilityClass, buildAvailabilityLookup, siteAvgSeries, seriesAvg, latencyTrendColor } from '../siteMetrics';

describe('availabilityClass', () => {
  it('按阈值分三档 + 空值', () => {
    expect(availabilityClass(null)).toBe('na');
    expect(availabilityClass(100)).toBe('up');
    expect(availabilityClass(95)).toBe('up');
    expect(availabilityClass(94.9)).toBe('degraded');
    expect(availabilityClass(80)).toBe('degraded');
    expect(availabilityClass(79.9)).toBe('down');
    expect(availabilityClass(0)).toBe('down');
  });
});

describe('buildAvailabilityLookup', () => {
  it('cells 数组 → {profile:{model:series}}', () => {
    const lut = buildAvailabilityLookup([
      { profile: 'S', model: 'm', series: [100, null, 80] },
      { profile: 'S', model: 'n', series: [90] },
    ]);
    expect(lut.S.m).toEqual([100, null, 80]);
    expect(lut.S.n).toEqual([90]);
  });
  it('空/缺省安全', () => {
    expect(buildAvailabilityLookup()).toEqual({});
    expect(buildAvailabilityLookup([{ profile: 'A', model: 'x' }]).A.x).toEqual([]);
  });
});

describe('siteAvgSeries', () => {
  it('各模型同桶平均，忽略 null 空桶', () => {
    expect(siteAvgSeries([[100, null, null], [80, 60, null]])).toEqual([90, 60, null]);
  });
  it('空输入 → []', () => {
    expect(siteAvgSeries([])).toEqual([]);
    expect(siteAvgSeries([[], []])).toEqual([]);
  });
});

describe('seriesAvg', () => {
  it('非空桶的平均，忽略 null', () => {
    expect(seriesAvg([100, null, 80])).toBe(90);
    expect(seriesAvg([90])).toBe(90);
    expect(seriesAvg([100, 81])).toBe(90.5);
  });
  it('全空 / 空 / 缺省 → null', () => {
    expect(seriesAvg([null, null])).toBeNull();
    expect(seriesAvg([])).toBeNull();
    expect(seriesAvg()).toBeNull();
  });
});

describe('latencyTrendColor', () => {
  it('恒为统一中性色，不随涨跌变红/绿', () => {
    const neutral = 'var(--text-secondary)';
    expect(latencyTrendColor([1, 2, 3])).toBe(neutral);   // 上升
    expect(latencyTrendColor([3, 2, 1])).toBe(neutral);   // 下降
    expect(latencyTrendColor([2, 2, 2])).toBe(neutral);   // 持平
    expect(latencyTrendColor([5])).toBe(neutral);          // 数据不足
    expect(latencyTrendColor([])).toBe(neutral);
  });
});
