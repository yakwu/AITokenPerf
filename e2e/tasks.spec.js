import { test, expect, login } from './fixtures/auth';

test.describe('定时任务', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto('/tasks');
  });

  test('定时任务页加载', async ({ page }) => {
    await expect(page.locator('.tab-bar')).toBeVisible();
    await expect(page.locator('.tab-btn.active')).toContainText('定时任务');
  });

  test('页面无 JS 错误', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (err) => errors.push(err.message));
    await page.waitForTimeout(1000);
    expect(errors).toEqual([]);
  });
});
