import { test, expect, login, resetDb } from './fixtures/auth';

test.describe('配置管理', () => {
  test.beforeEach(async ({ page }) => {
    await resetDb(page);
    await login(page);
  });

  test('配置页加载', async ({ page }) => {
    await page.goto('/config');
    await expect(page.locator('.header')).toBeVisible();
  });

  test('模型管理页加载（管理员）', async ({ page }) => {
    await page.goto('/settings/models');
    await expect(page.locator('.settings-subtab.router-link-active')).toContainText('模型库');
  });
});
