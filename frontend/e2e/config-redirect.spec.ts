import { test, expect } from '@playwright/test';

test.describe('config 页重定向', () => {
  test.beforeEach(async ({ page }) => {
    // Mock localStorage token + user（App.vue 需要 store.user 才渲染 router-view）
    await page.addInitScript(() => {
      localStorage.setItem('token', 'test-token');
      localStorage.setItem('user', JSON.stringify({
        username: 'testuser',
        role: 'admin',
        must_change_password: false,
      }));
    });

    // 拦截所有 API 请求，防止 401 触发拦截器（catch-all 兜底）
    await page.route(/^https?:\/\/localhost:\d+\/api\//, (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
  });

  test('访问 /config 应被重定向到 /sites', async ({ page }) => {
    await page.goto('/config');
    await page.waitForURL('**/sites');

    // 验证最终 URL 精确匹配 /sites
    await expect(page).toHaveURL('http://localhost:5180/sites');
  });
});
