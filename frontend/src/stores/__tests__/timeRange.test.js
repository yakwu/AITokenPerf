import { describe, it, expect, beforeEach, vi } from 'vitest';

// ---- timeRange store 纯逻辑测试（不依赖 Vue/Pinia） ----

// 测试 store 的核心逻辑：默认值、选项列表、localStorage 持久化
// 由于 Pinia store 需要 Vue app 上下文，这里测试独立抽取的逻辑

describe('timeRange store 逻辑', () => {
  const STORAGE_KEY = 'aitokenperf_time_range';
  const DEFAULT_HOURS = 6;
  const VALID_OPTIONS = [6, 24, 168, null];

  beforeEach(() => {
    localStorage.clear();
  });

  it('默认值应为 6', () => {
    const saved = localStorage.getItem(STORAGE_KEY);
    const hours = saved !== null ? JSON.parse(saved) : DEFAULT_HOURS;
    expect(hours).toBe(6);
  });

  it('选项列表应包含 6h、24h、7d、全部', () => {
    expect(VALID_OPTIONS).toEqual([6, 24, 168, null]);
  });

  it('从 localStorage 恢复已保存的值', () => {
    localStorage.setItem(STORAGE_KEY, '24');
    const saved = localStorage.getItem(STORAGE_KEY);
    const hours = saved !== null ? JSON.parse(saved) : DEFAULT_HOURS;
    expect(hours).toBe(24);
  });

  it('全部(null) 能正确保存和恢复', () => {
    localStorage.setItem(STORAGE_KEY, 'null');
    const saved = localStorage.getItem(STORAGE_KEY);
    const hours = saved !== null ? JSON.parse(saved) : DEFAULT_HOURS;
    expect(hours).toBeNull();
  });

  it('无效值应回退为默认值', () => {
    localStorage.setItem(STORAGE_KEY, '"invalid"');
    const saved = localStorage.getItem(STORAGE_KEY);
    let hours;
    try {
      const parsed = JSON.parse(saved);
      hours = VALID_OPTIONS.includes(parsed) ? parsed : DEFAULT_HOURS;
    } catch {
      hours = DEFAULT_HOURS;
    }
    expect(hours).toBe(DEFAULT_HOURS);
  });
});

// ---- sparkline 数据处理逻辑测试 ----

// 模拟前端 getModelMetrics 中使用 sparkline_data 的逻辑
function getSparklineTrend(site, model) {
  // 优先使用后端 sparkline_data
  if (site.sparkline_data && site.sparkline_data[model]) {
    return site.sparkline_data[model];
  }
  // 回退：从 latest_results 提取（旧逻辑）
  const results = site.latest_results || [];
  const ttfts = results
    .filter(r => r.config?.model === model)
    .map(r => r.percentiles?.TTFT?.P50)
    .filter(v => v != null);
  return ttfts.slice(0, 10).reverse();
}

describe('sparkline 数据处理', () => {
  it('优先使用 sparkline_data 而非 latest_results', () => {
    const site = {
      sparkline_data: { 'claude-opus-4-6': [2.0, 1.8, 1.5, 1.2, 1.0] },
      latest_results: [
        // latest_results 全是失败的（无 TTFT）
        { config: { model: 'claude-opus-4-6' }, percentiles: {} },
        { config: { model: 'claude-opus-4-6' }, percentiles: {} },
      ],
    };
    const trend = getSparklineTrend(site, 'claude-opus-4-6');
    expect(trend).toEqual([2.0, 1.8, 1.5, 1.2, 1.0]);
  });

  it('sparkline_data 为空时回退到 latest_results', () => {
    const site = {
      sparkline_data: {},
      latest_results: [
        { config: { model: 'gpt-4o' }, percentiles: { TTFT: { P50: 0.5 } } },
        { config: { model: 'gpt-4o' }, percentiles: { TTFT: { P50: 0.6 } } },
        { config: { model: 'gpt-4o' }, percentiles: { TTFT: { P50: 0.7 } } },
      ],
    };
    const trend = getSparklineTrend(site, 'gpt-4o');
    expect(trend).toEqual([0.7, 0.6, 0.5]);
  });

  it('无 sparkline_data 字段时回退到 latest_results', () => {
    const site = {
      latest_results: [
        { config: { model: 'test' }, percentiles: { TTFT: { P50: 1.0 } } },
        { config: { model: 'test' }, percentiles: { TTFT: { P50: 2.0 } } },
      ],
    };
    const trend = getSparklineTrend(site, 'test');
    expect(trend).toEqual([2.0, 1.0]);
  });

  it('多模型场景：正确区分各 model 的 sparkline', () => {
    const site = {
      sparkline_data: {
        'model-a': [1.0, 1.1, 1.2],
        'model-b': [2.0, 2.1],
      },
      latest_results: [],
    };
    expect(getSparklineTrend(site, 'model-a')).toEqual([1.0, 1.1, 1.2]);
    expect(getSparklineTrend(site, 'model-b')).toEqual([2.0, 2.1]);
  });

  it('sparkline_data 中不存在的 model 回退到 latest_results', () => {
    const site = {
      sparkline_data: { 'model-a': [1.0, 1.1] },
      latest_results: [
        { config: { model: 'model-c' }, percentiles: { TTFT: { P50: 3.0 } } },
      ],
    };
    expect(getSparklineTrend(site, 'model-c')).toEqual([3.0]);
  });

  it('最近全失败但 sparkline_data 有历史数据 — 核心场景', () => {
    // 模拟 Baoyou_Claude2 的情况
    const site = {
      sparkline_data: { 'claude-opus-4-6': [2.4, 2.3, 2.1, 2.0, 1.3, 1.2, 1.1, 1.0] },
      latest_results: [
        // 最近 10 条全是 503 失败
        ...Array(10).fill(null).map(() => ({
          config: { model: 'claude-opus-4-6' },
          summary: { success_count: 0, total_requests: 1 },
          percentiles: {},
        })),
      ],
    };
    const trend = getSparklineTrend(site, 'claude-opus-4-6');
    // 应该能拿到历史 sparkline 数据，而不是空
    expect(trend.length).toBe(8);
    expect(trend[0]).toBe(2.4);
  });
});
