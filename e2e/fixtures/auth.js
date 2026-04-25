import { test as base, expect } from '@playwright/test';

// 测试用管理员凭据（与后端 conftest.py 一致）
export const ADMIN_EMAIL = 'admin@example.com';
export const ADMIN_PASSWORD = 'AITokenPerf#123';

/**
 * 登录 helper — 填写登录表单并提交
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

  // 等待登录成功跳转到仪表盘
  await page.waitForURL('/');
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
 * 带登录状态的测试 fixture
 */
export const test = base.extend({
  // 预登录的页面
  loggedInPage: async ({ page }, use) => {
    await login(page);
    await use(page);
  },
});

export { expect };
