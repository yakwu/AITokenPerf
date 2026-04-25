import { test, expect, login } from './fixtures/auth';

test.describe('配置管理', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('配置页加载', async ({ page }) => {
    await page.goto('/config');
    await expect(page.locator('.header')).toBeVisible();
  });

  test('模型管理页加载（管理员）', async ({ page }) => {
    await page.goto('/models');
    await expect(page.locator('.header')).toBeVisible();
  });
});
