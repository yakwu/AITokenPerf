import { test, expect, login, resetDb } from './fixtures/auth';

test.describe('仪表盘', () => {
  test.beforeEach(async ({ page }) => {
    await resetDb(page);
    await login(page);
  });

  test('页面加载显示统计卡片', async ({ page }) => {
    await expect(page.locator('.header')).toBeVisible();
    await expect(page.locator('.tab-bar')).toBeVisible();
    await expect(page.locator('.tab-btn.active')).toContainText('概览');
  });

  test('时间范围切换', async ({ page }) => {
    const timeRangePills = page.locator('.time-range-pill:not(.refresh-pill)');
    const count = await timeRangePills.count();
    expect(count).toBeGreaterThan(0);
    await timeRangePills.first().click();
    await expect(timeRangePills.first()).toHaveClass(/active/);
  });

  test('刷新按钮可点击', async ({ page }) => {
    const refreshBtn = page.locator('.refresh-pill');
    await expect(refreshBtn).toBeVisible();
    await refreshBtn.click();
    await expect(page.locator('.header')).toBeVisible();
  });
});
