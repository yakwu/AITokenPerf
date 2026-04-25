import { test, expect, login, resetDb } from './fixtures/auth';

test.describe('目标站点', () => {
  test.beforeEach(async ({ page }) => {
    await resetDb(page);
    await login(page);
    await page.goto('/sites');
  });

  test('站点列表页加载', async ({ page }) => {
    await expect(page.locator('.tab-bar')).toBeVisible();
    await expect(page.locator('.tab-btn.active')).toContainText('目标站点');
  });

  test('添加新站点', async ({ page }) => {
    const addBtn = page.locator('button', { hasText: /添加|新建|\+/ }).first();
    if (await addBtn.isVisible()) {
      await addBtn.click();
      await expect(page.locator('.form-input, .modal, dialog')).toBeVisible();
    }
  });

  test('站点详情页', async ({ page }) => {
    const siteCard = page.locator('.site-card, .card').first();
    if (await siteCard.isVisible()) {
      await siteCard.click();
      await expect(page.url()).toContain('/sites/');
    }
  });
});
