import { test, expect, login, resetDb } from './fixtures/auth';

test.describe('历史与对比', () => {
  test.beforeEach(async ({ page }) => {
    await resetDb(page);
    await login(page);
    await page.goto('/history');
  });

  test('历史记录页加载', async ({ page }) => {
    await expect(page.locator('.tab-bar')).toBeVisible();
    await expect(page.locator('.tab-btn.active')).toContainText('历史与对比');
  });

  test('时间范围筛选', async ({ page }) => {
    const timeRangePills = page.locator('.time-range-pill:not(.refresh-pill)');
    if (await timeRangePills.first().isVisible()) {
      await timeRangePills.first().click();
      await expect(timeRangePills.first()).toHaveClass(/active/);
    }
  });
});
