import { test, expect } from '@playwright/test';

// 单站点单模型。
// latest_results 的「最近一次」成功率 = 98/100 = 98.0%；
// 而可用率桶 series 覆盖整个时间范围、均值 = (100+100+50)/3 = 83.3%。
// 用这个差异验证「成功率取所选范围（与可用率柱同源）而非最近一次」。
const mockSitesSummary = {
  summary: [
    {
      profile: { name: 'site-A', base_url: 'https://api-a.example.com', models: ['gpt-4o'] },
      health: 'healthy',
      last_test_at: '20260605_100000',
      latest_results: [
        {
          config: { model: 'gpt-4o' },
          summary: { total_requests: 100, success_count: 98, token_throughput_tps: 45 },
          percentiles: { TTFT: { P50: 0.3 }, TPOT: { P50: 0.02 } },
          error_details: [],
        },
      ],
      // 长度 >= 2 才会渲染延迟趋势小图
      sparkline_data: { 'gpt-4o': [0.3, 0.4, 0.35] },
    },
  ],
};

const mockAvailability = {
  cells: [
    { profile: 'site-A', model: 'gpt-4o', series: [100, 100, 50, null] },
  ],
};

test.describe('站点健康看板修复（#70）', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('token', 'test-token');
      localStorage.setItem('user', JSON.stringify({
        username: 'testuser', role: 'admin', must_change_password: false,
      }));
    });
    // 兜底先注册（后注册的同名匹配优先）
    await page.route(/^https?:\/\/localhost:\d+\/api\//, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
    await page.route(/\/api\/sites\/summary/, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockSitesSummary) }));
    await page.route(/\/api\/sites\/availability/, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockAvailability) }));
  });

  test('#2 成功率取所选时间范围（可用率柱均值），而非最近一次', async ({ page }) => {
    await page.goto('/sites');
    const rate = page.locator('tr.site-row .rate').first();
    await expect(rate).toBeVisible();
    // 83.3%（series 均值），而不是 98.0%（最近一次）
    await expect(rate).toHaveText('83.3%');
  });

  test('#1 展开后站点行的可用率柱变浅（dim），模型行出现', async ({ page }) => {
    await page.goto('/sites');
    const siteBars = page.locator('tr.site-row .avail-bars').first();
    await expect(siteBars).toBeVisible();
    await expect(siteBars).not.toHaveClass(/dim/);
    await expect(page.locator('tr.model-row')).toHaveCount(0);

    await siteBars.click(); // 点击站点行展开
    await expect(page.locator('tr.model-row')).toHaveCount(1);
    await expect(siteBars).toHaveClass(/dim/);
  });

  test('#3 延迟趋势小图为统一中性色（var(--text-secondary)）', async ({ page }) => {
    await page.goto('/sites');
    await page.locator('tr.site-row .avail-bars').first().click();
    const poly = page.locator('tr.model-row polyline').first();
    await expect(poly).toBeVisible();
    await expect(poly).toHaveAttribute('stroke', 'var(--text-secondary)');
  });
});
