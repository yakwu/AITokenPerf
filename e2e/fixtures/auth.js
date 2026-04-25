import { test as base, expect } from '@playwright/test';

// 测试用管理员凭据（与后端 conftest.py 一致）
export const ADMIN_EMAIL = 'admin@example.com';
export const ADMIN_PASSWORD = 'AITokenPerf#123';
export const ADMIN_NEW_PASSWORD = 'NewPassword123!';

/**
 * 重置数据库 — 每个测试前调用，确保干净状态
 */
export async function resetDb(page) {
  const response = await page.request.post('http://localhost:8081/api/test/reset');
  const body = await response.json().catch(() => ({}));
  if (!response.ok()) {
    console.error('resetDb failed:', response.status(), body);
  }
  expect(response.ok()).toBeTruthy();
}

/**
 * 登录 helper — 填写登录表单并提交
 * 自动处理首次登录强制改密场景
 */
export async function login(page, email = ADMIN_EMAIL, password = ADMIN_PASSWORD) {
  await page.goto('/auth');
  await page.waitForSelector('.auth-card');

  // 确保在登录模式
  const loginTab = page.locator('.auth-tab', { hasText: '登录' });
  await loginTab.click();

  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);

  await page.click('.btn-primary');

  // 处理强制改密（首次登录时 must_change_password=true）
  const forceChangeVisible = await page.locator('text=首次登录，请修改默认密码').isVisible({ timeout: 3000 }).catch(() => false);
  if (forceChangeVisible) {
    const passwordInputs = page.locator('input[type="password"]');
    await passwordInputs.nth(0).fill(ADMIN_NEW_PASSWORD);
    await passwordInputs.nth(1).fill(ADMIN_NEW_PASSWORD);
    await page.click('.btn-primary');
  }

  // 等待登录成功跳转到仪表盘
  await page.waitForURL(/\/$/, { timeout: 15000 });
  await expect(page.locator('.header')).toBeVisible();
}

/**
 * 注册 helper — 填写注册表单并提交
 */
export async function register(page, email, password, displayName = '') {
  await page.goto('/auth');
  await page.waitForSelector('.auth-card');

  // 切换到注册模式
  const registerTab = page.locator('.auth-tab', { hasText: '注册' });
  await registerTab.click();

  if (displayName) {
    await page.fill('input[placeholder="可选"]', displayName);
  }
  await page.fill('input[type="email"]', email);
  // 注册表单有两个密码输入框
  const passwordInputs = page.locator('input[type="password"]');
  await passwordInputs.nth(0).fill(password);
  await passwordInputs.nth(1).fill(password);
  await page.click('.btn-primary');

  // 等待注册成功跳转
  await page.waitForURL('/');
}

/**
 * 带登录状态的测试 fixture（每个测试前自动重置数据库）
 */
export const test = base.extend({
  // 预登录的页面（自动重置数据库 + 登录）
  loggedInPage: async ({ page }, use) => {
    await resetDb(page);
    await login(page);
    await use(page);
  },
});

export { expect };
