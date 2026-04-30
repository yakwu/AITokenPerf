import { test, expect } from '@playwright/test';

// Mock API 响应数据 - 模拟 /api/results 返回
const mockResultsResponse = {
  total: 25,
  items: [
    {
      filename: 'result-20260430-001.json',
      test_id: 'tid-001',
      timestamp: '2026-04-30T10:00:00Z',
      config: {
        model: 'claude-3-opus',
        base_url: 'https://api.anthropic.com',
        concurrency: 5,
        mode: 'burst',
        profile_name: 'test-site-1',
      },
      summary: {
        success_rate: 98.5,
        throughput_rps: 45.2,
        cost_total_usd: 0.12,
        total_requests: 100,
        successful_requests: 98,
      },
      percentiles: {
        TTFT: { P50: 0.35, P95: 0.82, P99: 1.2 },
        E2E: { P50: 2.1, P95: 4.5, P99: 6.8 },
        TPOT: { P50: 0.045 },
      },
    },
    {
      filename: 'result-20260430-002.json',
      test_id: 'tid-002',
      timestamp: '2026-04-30T09:30:00Z',
      config: {
        model: 'claude-3-sonnet',
        base_url: 'https://api.anthropic.com',
        concurrency: 10,
        mode: 'sustained',
        profile_name: 'test-site-2',
      },
      summary: {
        success_rate: 100,
        throughput_rps: 62.8,
        cost_total_usd: 0.08,
        total_requests: 100,
        successful_requests: 100,
      },
      percentiles: {
        TTFT: { P50: 0.25, P95: 0.55, P99: 0.9 },
        E2E: { P50: 1.8, P95: 3.2, P99: 5.1 },
        TPOT: { P50: 0.035 },
      },
    },
    {
      filename: 'result-20260430-003.json',
      test_id: 'tid-003',
      timestamp: '2026-04-30T09:00:00Z',
      config: {
        model: 'claude-3-opus',
        base_url: 'https://api.anthropic.com',
        concurrency: 1,
        mode: 'burst',
      },
      summary: {
        success_rate: 75,
        throughput_rps: 12.1,
        cost_total_usd: 0.25,
        total_requests: 50,
        successful_requests: 37,
      },
      percentiles: {
        TTFT: { P50: 0.65, P95: 1.5, P99: 2.8 },
        E2E: { P50: 5.2, P95: 12.1, P99: 18.5 },
        TPOT: { P50: 0.08 },
      },
    },
  ],
};

test.describe('HistoryView', () => {
  test.beforeEach(async ({ page }) => {
    // Mock localStorage token (组件需要 token 才会加载数据)
    await page.addInitScript(() => {
      localStorage.setItem('token', 'test-token');
    });

    // Mock API 响应
    await page.route('**/api/results?**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockResultsResponse),
      });
    });

    await page.route('**/api/results/**', (route) => {
      if (route.request().method() === 'DELETE') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true }),
        });
      } else {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockResultsResponse.items[0]),
        });
      }
    });

    // 导航到历史记录页面
    await page.goto('/history');
    // 等待页面加载完成
    await page.waitForLoadState('networkidle');
  });

  test('应该显示历史记录卡片列表', async ({ page }) => {
    // 验证卡片容器存在
    await expect(page.locator('.history-cards-container')).toBeVisible();

    // 验证至少有一条记录
    const cards = page.locator('.history-card');
    await expect(cards.first()).toBeVisible();
  });

  test('应该显示关键指标', async ({ page }) => {
    // 等待卡片加载
    await expect(page.locator('.history-card').first()).toBeVisible();

    // 验证关键指标显示
    const firstCard = page.locator('.history-card').first();
    await expect(firstCard.locator('.history-card-metric-label:has-text("成功率")')).toBeVisible();
    await expect(firstCard.locator('.history-card-metric-label:has-text("TTFT P50")')).toBeVisible();
    await expect(firstCard.locator('.history-card-metric-label:has-text("吞吐量")')).toBeVisible();
  });

  test('应该支持搜索功能', async ({ page }) => {
    // 输入搜索关键词
    await page.fill('.search-input-wrap input.form-input', 'claude-3-opus');

    // 等待筛选结果
    await page.waitForTimeout(500);

    // 验证所有显示的卡片都包含搜索关键词
    const cards = page.locator('.history-card');
    const count = await cards.count();
    for (let i = 0; i < count; i++) {
      const text = await cards.nth(i).textContent();
      expect(text?.toLowerCase()).toContain('claude-3-opus');
    }
  });

  test('应该支持筛选功能', async ({ page }) => {
    // 点击模型筛选下拉
    await page.locator('.filter-dropdown-btn:has-text("全部模型")').click();

    // 选择一个模型
    await page.locator('.combobox-option:has-text("claude-3-opus")').click();

    // 等待筛选结果
    await page.waitForTimeout(500);

    // 验证所有显示的卡片都是选中的模型
    const cards = page.locator('.history-card');
    const count = await cards.count();
    for (let i = 0; i < count; i++) {
      await expect(cards.nth(i).locator('.history-card-model-name')).toContainText('claude-3-opus');
    }
  });

  test('应该支持分页功能', async ({ page }) => {
    // 验证分页信息存在
    await expect(page.locator('.pagination-info:has-text("共")')).toBeVisible();

    // 如果有多页，测试翻页
    const nextButton = page.locator('.pagination button:has-text("下一页")');
    if (await nextButton.isEnabled()) {
      // 点击下一页
      await nextButton.click();

      // 等待页面变化
      await page.waitForTimeout(500);

      // 验证页码变化
      await expect(page.locator('.pagination button.btn-primary:has-text("2")')).toBeVisible();
    }
  });

  test('应该支持对比功能', async ({ page }) => {
    // 选择两条记录
    const checkboxes = page.locator('.compare-check');
    await checkboxes.first().check();
    await checkboxes.nth(1).check();

    // 点击对比按钮
    await page.locator('.compare-bar button.btn-primary:has-text("对比")').click();

    // 验证对比视图显示
    await expect(page.locator('.compare-table')).toBeVisible();
  });

  test('应该支持展开详情', async ({ page }) => {
    // 点击第一条记录
    await page.locator('.history-card').first().click();

    // 验证详情展开
    await expect(page.locator('.history-card-detail').first()).toBeVisible();

    // 再次点击折叠
    await page.locator('.history-card').first().click();

    // 验证详情折叠
    await expect(page.locator('.history-card-detail').first()).not.toBeVisible();
  });

  test('应该支持删除功能', async ({ page }) => {
    // 点击删除按钮
    await page.locator('.history-card').first().locator('.del-btn').click();

    // 验证确认删除提示
    await expect(page.locator('.delete-undo:has-text("确认删除")')).toBeVisible();

    // 等待 3 秒后自动取消
    await page.waitForTimeout(3500);

    // 验证确认删除提示消失
    await expect(page.locator('.delete-undo:has-text("确认删除")')).not.toBeVisible();
  });

  // 移动端测试由 Playwright device projects（Mobile Chrome / Mobile Safari）处理
  // 在非 device project 中跳过此测试，无需手动 setViewportSize
  test('应该在移动端正确显示', async ({ page }) => {
    // 仅在非移动端 device project 中跳过
    const project = test.info().project.name;
    if (!project.includes('Mobile')) {
      test.skip();
    }

    // 验证卡片正确显示
    await expect(page.locator('.history-card').first()).toBeVisible();

    // 验证关键指标垂直排列
    const firstCard = page.locator('.history-card').first();
    const metrics = firstCard.locator('.history-card-metric');
    const firstMetric = await metrics.first().boundingBox();
    const secondMetric = await metrics.nth(1).boundingBox();

    // 移动端应该是垂直排列（y 坐标不同）
    expect(firstMetric?.y).not.toBe(secondMetric?.y);
  });
});
