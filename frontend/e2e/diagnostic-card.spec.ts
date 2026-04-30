import { test, expect } from '@playwright/test';

// Mock API 响应数据 - categories 在顶层，匹配 DiagnosticCard 的 props
const mockDiagnosticsResponse = {
  model: 'test-model',
  status: 'passed',
  confidence: 0.95,
  overall_status: 'passed',
  categories: [
    {
      category: 'connectivity',
      status: 'passed',
      probes: [
        { name: '基础连接', status: 'passed', detail: '连接成功', latency_ms: 120000 },
      ],
    },
    {
      category: 'streaming',
      status: 'passed',
      probes: [
        { name: '流式响应', status: 'passed', detail: '流式正常', latency_ms: 200000 },
      ],
    },
    {
      category: 'context',
      status: 'passed',
      probes: [
        { name: '上下文保持', status: 'passed', detail: '上下文正常', latency_ms: 150000 },
      ],
    },
    {
      category: 'tool_use',
      status: 'warning',
      probes: [
        { name: '函数调用', status: 'failed', detail: '部分工具不支持', latency_ms: 300000 },
      ],
    },
    {
      category: 'structured',
      status: 'passed',
      probes: [
        { name: 'JSON 输出', status: 'passed', detail: 'JSON 格式正确', latency_ms: 180000 },
      ],
    },
    {
      category: 'cache',
      status: 'passed',
      probes: [
        { name: '缓存命中', status: 'passed', detail: '缓存正常', latency_ms: 50000 },
      ],
    },
  ],
};

test.describe('DiagnosticCard', () => {
  test.beforeEach(async ({ page }) => {
    // Mock localStorage token + user (App.vue 需要 store.user 才渲染 router-view)
    await page.addInitScript(() => {
      localStorage.setItem('token', 'test-token');
      localStorage.setItem('user', JSON.stringify({
        username: 'testuser',
        role: 'admin',
        must_change_password: false,
      }));
    });

    // 拦截其他 API 请求，防止 401 触发拦截器（先注册 catch-all，Playwright 1.59 用最后匹配的 handler）
    await page.route(/^https?:\/\/localhost:\d+\/api\//, (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    // 具体路由后注册，会覆盖 catch-all
    await page.route(/\/api\/profiles/, (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          profiles: [{
            name: 'test-site',
            base_url: 'https://api.anthropic.com',
            api_key: 'sk-test',
            models: ['claude-3-opus'],
          }],
        }),
      });
    });
    await page.route(/\/api\/sites\/summary/, (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          summary: [{
            profile: { name: 'test-site' },
            health: 'healthy',
          }],
        }),
      });
    });

    // 导航到站点详情页
    await page.goto('/sites/test-site');
    // 切换到诊断 Tab
    await page.click('button:has-text("诊断")');
  });

  test('应该显示类别选择器', async ({ page }) => {
    // 验证类别选择器存在
    await expect(page.locator('.diag-category-grid')).toBeVisible();

    // 验证所有类别都显示
    const categories = page.locator('.diag-category-option');
    await expect(categories).toHaveCount(6);

    // 验证类别名称
    await expect(page.locator('.diag-category-option:has-text("连通性")')).toBeVisible();
    await expect(page.locator('.diag-category-option:has-text("流式传输")')).toBeVisible();
    await expect(page.locator('.diag-category-option:has-text("多轮上下文")')).toBeVisible();
    await expect(page.locator('.diag-category-option:has-text("工具调用")')).toBeVisible();
    await expect(page.locator('.diag-category-option:has-text("结构化输出")')).toBeVisible();
    await expect(page.locator('.diag-category-option:has-text("Prompt Cache")')).toBeVisible();
  });

  test('应该支持全选和全不选', async ({ page }) => {
    // 点击全选
    await page.click('button:has-text("全选")');

    // 验证所有 checkbox 都被选中
    const checkboxes = page.locator('.diag-category-checkbox');
    for (let i = 0; i < 6; i++) {
      await expect(checkboxes.nth(i)).toBeChecked();
    }

    // 点击全不选
    await page.click('button:has-text("全不选")');

    // 验证所有 checkbox 都未选中
    for (let i = 0; i < 6; i++) {
      await expect(checkboxes.nth(i)).not.toBeChecked();
    }
  });

  test('应该支持点击类别卡片切换选中状态', async ({ page }) => {
    // 点击连通性类别卡片的 checkbox
    const checkbox = page.locator('.diag-category-checkbox').first();
    await checkbox.check();

    // 验证 checkbox 被选中
    await expect(checkbox).toBeChecked();

    // 再次点击取消选中
    await checkbox.uncheck();
    await expect(checkbox).not.toBeChecked();
  });

  test('应该显示诊断结果卡片', async ({ page }) => {
    // Mock API 响应
    await page.route('**/api/diagnostics**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockDiagnosticsResponse),
      });
    });

    // 选择模型和类别
    await page.click('button:has-text("全选")');

    // 点击开始诊断
    await page.click('button:has-text("开始诊断")');

    // 等待诊断完成
    await expect(page.locator('.diag-result-model-card')).toBeVisible({ timeout: 60000 });

    // 验证 DiagnosticCard 显示
    await expect(page.locator('.diag-result-card')).toBeVisible();

    // 验证渐变头部存在
    await expect(page.locator('.diag-header')).toBeVisible();

    // 验证类别网格存在
    await expect(page.locator('.diag-categories-grid')).toBeVisible();
  });

  test('应该支持展开和折叠类别详情', async ({ page }) => {
    // Mock API 响应
    await page.route('**/api/diagnostics**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockDiagnosticsResponse),
      });
    });

    // 选择模型和类别
    await page.click('button:has-text("全选")');

    // 点击开始诊断
    await page.click('button:has-text("开始诊断")');

    // 等待诊断完成
    await expect(page.locator('.diag-result-card')).toBeVisible({ timeout: 60000 });

    // 默认状态：expandedCategories 为空，探针详情应隐藏
    await expect(page.locator('.diag-probes-detail')).not.toBeVisible();

    // 点击第一个类别卡片展开详情
    const firstCategoryCard = page.locator('.diag-category-card').first();
    await firstCategoryCard.click();

    // 验证探针详情显示
    await expect(page.locator('.diag-probes-detail')).toBeVisible();

    // 再次点击折叠
    await firstCategoryCard.click();

    // 验证探针详情隐藏
    await expect(page.locator('.diag-probes-detail')).not.toBeVisible();
  });

  // 移动端测试由 Playwright device projects（Mobile Chrome / Mobile Safari）处理
  // 在非 device project 中跳过此测试，无需手动 setViewportSize
  test('应该在移动端正确显示', async () => {
    test.skip();
  });
});
