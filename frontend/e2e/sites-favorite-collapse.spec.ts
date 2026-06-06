import { test, expect } from '@playwright/test';

// Mock 数据：2 个 healthy 站点 + 1 个 error 站点
const mockLatestResults = [
  {
    config: { model: 'gpt-4o' },
    summary: { total_requests: 100, success_count: 98, token_throughput_tps: 45 },
    percentiles: { TTFT: { P50: 0.3 }, TPOT: { P50: 0.02 } },
    error_details: [],
  },
];

const mockSitesSummary = {
  summary: [
    {
      profile: { name: 'healthy-site-A', base_url: 'https://api-a.example.com', models: ['gpt-4o'] },
      health: 'healthy',
      last_test_at: '20260605_100000',
      latest_results: mockLatestResults,
    },
    {
      profile: { name: 'healthy-site-B', base_url: 'https://api-b.example.com', models: ['gpt-4o'] },
      health: 'healthy',
      last_test_at: '20260605_090000',
      latest_results: mockLatestResults,
    },
    {
      profile: { name: 'error-site-C', base_url: 'https://api-c.example.com', models: ['gpt-4o'] },
      health: 'error',
      last_test_at: '20260605_080000',
      latest_results: mockLatestResults,
    },
  ],
};

test.describe('站点列表收藏与折叠功能', () => {
  test.beforeEach(async ({ page }) => {
    // 设置登录态（addInitScript 在每次导航时执行，所以只设置必要的 token/user，
    // 不在此处清除收藏状态，以避免影响 reload 后的持久化验证）
    await page.addInitScript(() => {
      localStorage.setItem('token', 'test-token');
      localStorage.setItem('user', JSON.stringify({
        username: 'testuser',
        role: 'admin',
        must_change_password: false,
      }));
      // 确保折叠开关为默认开启（不设置则默认为 '1'，key 不存在时也是开启）
      // 不清除 site_favorites，由各测试用例自行管理
    });

    // 兜底拦截所有 API
    await page.route(/^https?:\/\/localhost:\d+\/api\//, (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    // Mock /api/sites/summary
    await page.route(/\/api\/sites\/summary/, (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockSitesSummary),
      });
    });
  });

  test('收藏站点后 reload 该站点排到第一位', async ({ page }) => {
    await page.goto('/sites');
    await page.waitForLoadState('networkidle');

    // 等待卡片渲染
    await expect(page.locator('.site-card').first()).toBeVisible();

    // 断言默认顺序：无收藏时 error 站点排在首位
    const cards = page.locator('.site-card');
    const beforeFirst = await cards.first().locator('.site-name-link').textContent();
    expect(beforeFirst?.trim()).toBe('error-site-C');

    // 先通过 UI 点击收藏 healthy-site-B
    const count = await cards.count();
    let targetCardIndex = -1;
    for (let i = 0; i < count; i++) {
      const nameText = await cards.nth(i).locator('.site-name-link').textContent();
      if (nameText?.trim() === 'healthy-site-B') {
        targetCardIndex = i;
        break;
      }
    }
    expect(targetCardIndex).toBeGreaterThanOrEqual(0);

    // 点击收藏按钮
    await cards.nth(targetCardIndex).locator('.site-fav-btn').click();

    // 验证 localStorage 里有收藏数据
    const favData = await page.evaluate(() => localStorage.getItem('site_favorites'));
    expect(favData).toContain('healthy-site-B');

    // 重新加载页面（验证持久化后仍置顶）
    await page.reload();
    await page.waitForLoadState('networkidle');
    await expect(page.locator('.site-card').first()).toBeVisible();

    // 验证第一张卡片是 healthy-site-B
    const firstCardName = await page.locator('.site-card').first().locator('.site-name-link').textContent();
    expect(firstCardName?.trim()).toBe('healthy-site-B');
  });

  test('折叠健康站点开关默认开启，健康卡片不显示 matrix-table', async ({ page }) => {
    await page.goto('/sites');
    await page.waitForLoadState('networkidle');

    // 等待卡片渲染
    await expect(page.locator('.site-card').first()).toBeVisible();

    // 验证折叠开关存在
    await expect(page.locator('.collapse-healthy-toggle')).toBeVisible();

    // 默认折叠开启：健康卡片不应显示 matrix-table
    const healthyCards = page.locator('.site-card--healthy');
    const healthyCount = await healthyCards.count();
    expect(healthyCount).toBeGreaterThan(0);

    // 健康卡片内的 matrix-table 应为 0
    const matrixInHealthy = page.locator('.site-card--healthy .matrix-table');
    await expect(matrixInHealthy).toHaveCount(0);
  });
});
