import { test, expect, login, register, resetDb, ADMIN_EMAIL, ADMIN_PASSWORD } from './fixtures/auth';

test.describe('认证与用户生命周期', () => {
  test.beforeEach(async ({ page }) => {
    await resetDb(page);
  });

  test('首次登录强制改密', async ({ page }) => {
    await page.goto('/auth');
    await page.waitForSelector('.auth-card');
    await page.fill('input[type="email"]', ADMIN_EMAIL);
    await page.fill('input[type="password"]', ADMIN_PASSWORD);
    await page.click('.btn-primary');
    await expect(page.locator('text=首次登录，请修改默认密码')).toBeVisible();
    const passwordInputs = page.locator('input[type="password"]');
    await passwordInputs.nth(0).fill('NewPassword123!');
    await passwordInputs.nth(1).fill('NewPassword123!');
    await page.click('.btn-primary');
    await page.waitForURL('/');
    await expect(page.locator('.header')).toBeVisible();
  });

  test('正常登录和登出', async ({ page }) => {
    await login(page);
    await page.click('.user-avatar');
    await page.click('.user-dropdown-logout');
    await page.waitForURL('/auth');
    await expect(page.locator('.auth-card')).toBeVisible();
  });

  test('未登录访问保护页重定向到 /auth', async ({ page }) => {
    await page.goto('/auth');
    await page.evaluate(() => localStorage.clear());
    await page.goto('/sites');
    await page.waitForURL('/auth');
    await expect(page.locator('.auth-card')).toBeVisible();
  });

  test('注册新用户', async ({ page }) => {
    const newUserEmail = `test-${Date.now()}@example.com`;
    await register(page, newUserEmail, 'TestPassword123!', '测试用户');
    await page.waitForURL('/');
    await expect(page.locator('.header')).toBeVisible();
  });

  test('管理员访问用户管理页面', async ({ page }) => {
    await login(page);
    await page.goto('/settings/users');
    await expect(page.locator('.header')).toBeVisible();
  });

  test('管理员访问模型管理页面', async ({ page }) => {
    await login(page);
    await page.goto('/settings/models');
    await expect(page.locator('.header')).toBeVisible();
  });
});
