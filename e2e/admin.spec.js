import { test, expect, login, resetDb } from './fixtures/auth';

test.describe('用户管理', () => {
  test.beforeEach(async ({ page }) => {
    await resetDb(page);
    await login(page);
  });

  test('管理员用户管理页加载', async ({ page }) => {
    await page.goto('/admin-users');
    await expect(page.locator('.header')).toBeVisible();
  });

  test('用户菜单显示管理入口', async ({ page }) => {
    await page.click('.user-avatar');
    await expect(page.locator('.user-dropdown')).toBeVisible();
    await expect(page.locator('text=用户管理')).toBeVisible();
  });
});
