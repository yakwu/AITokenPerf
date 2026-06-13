import { test, expect } from '@playwright/test';

// 站点健康看板（Site×Model 表格）：收藏站点应置顶，并跨刷新持久化。
// 看板重构（#59）后旧的卡片 UI（.site-card / .collapse-healthy-toggle 等）已移除，
// 「折叠健康站点」也被「逐行展开模型」取代（展开行为见 sites-board-fixes.spec.ts）。
const mockLatest = [
  {
    config: { model: 'gpt-4o' },
    summary: { total_requests: 100, success_count: 98, token_throughput_tps: 45 },
    percentiles: { TTFT: { P50: 0.3 }, TPOT: { P50: 0.02 } },
    error_details: [],
  },
];

const mockSitesSummary = {
  summary: [
    { profile: { name: 'healthy-site-A', base_url: 'https://api-a.example.com', models: ['gpt-4o'] }, health: 'healthy', last_test_at: '20260605_100000', latest_results: mockLatest },
    { profile: { name: 'healthy-site-B', base_url: 'https://api-b.example.com', models: ['gpt-4o'] }, health: 'healthy', last_test_at: '20260605_090000', latest_results: mockLatest },
    { profile: { name: 'error-site-C', base_url: 'https://api-c.example.com', models: ['gpt-4o'] }, health: 'error', last_test_at: '20260605_080000', latest_results: mockLatest },
  ],
};

test.describe('站点看板：收藏置顶与持久化', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('token', 'test-token');
      localStorage.setItem('user', JSON.stringify({
        username: 'testuser', role: 'admin', must_change_password: false,
      }));
      // 不清除 site_favorites，由用例自行管理以验证持久化
    });
    // 兜底先注册（后注册的同名匹配优先）
    await page.route(/^https?:\/\/localhost:\d+\/api\//, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
    await page.route(/\/api\/sites\/summary/, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockSitesSummary) }));
    await page.route(/\/api\/sites\/availability/, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ cells: [] }) }));
  });

  test('收藏站点后置顶，reload 仍置顶', async ({ page }) => {
    await page.goto('/sites');
    const rows = page.locator('tr.site-row');
    await expect(rows.first()).toBeVisible();

    // 默认顺序：无收藏时 error 站点排最前
    await expect(rows.first().locator('.sname')).toHaveText('error-site-C');

    // 通过 UI 收藏 healthy-site-B
    await page.locator('tr.site-row', { hasText: 'healthy-site-B' }).locator('.fav').click();

    // localStorage 已记录收藏
    const favData = await page.evaluate(() => localStorage.getItem('site_favorites'));
    expect(favData).toContain('healthy-site-B');

    // reload 后仍置顶（验证持久化）
    await page.reload();
    await expect(page.locator('tr.site-row').first()).toBeVisible();
    await expect(page.locator('tr.site-row').first().locator('.sname')).toHaveText('healthy-site-B');
  });
});
