import { test, expect, login, resetDb } from './fixtures/auth';

test.describe('用户管理', () => {
  test.beforeEach(async ({ page }) => {
    await resetDb(page);
    await login(page);
  });

  test('管理员可进入设置·用户管理子页', async ({ page }) => {
    await page.goto('/settings/users');
    await expect(page.locator('.settings-subtabs')).toBeVisible();
    // 真正落在「用户管理」子页：激活的子标签就是它
    await expect(page.locator('.settings-subtab.router-link-active')).toContainText('用户管理');
  });
});
