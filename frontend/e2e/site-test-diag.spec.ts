import { test, expect } from '@playwright/test';

// Mock API 响应数据 - 单模型诊断结果（categories 在顶层，匹配 DiagnosticCard props）
const mockDiagnosticsResponse = {
  model: 'claude-3-opus',
  status: 'passed',
  confidence: 0.95,
  overall_status: 'passed',
  categories: [
      {
        category: 'connectivity',
        displayName: '连通性',
        status: 'passed',
        score: 100,
        probes: [
          { name: '基础连接', status: 'passed', detail: '连接成功', latency_ms: 120000 },
        ],
      },
      {
        category: 'streaming',
        displayName: '流式传输',
        status: 'passed',
        score: 95,
        probes: [
          { name: '流式响应', status: 'passed', detail: '流式正常', latency_ms: 200000 },
        ],
      },
      {
        category: 'context',
        displayName: '多轮上下文',
        status: 'passed',
        score: 90,
        probes: [
          { name: '上下文保持', status: 'passed', detail: '上下文正常', latency_ms: 150000 },
        ],
      },
      {
        category: 'tool_use',
        displayName: '工具调用',
        status: 'passed',
        score: 80,
        probes: [
          { name: '函数调用', status: 'passed', detail: '调用正常', latency_ms: 300000 },
        ],
      },
      {
        category: 'structured',
        displayName: '结构化输出',
        status: 'passed',
        score: 85,
        probes: [
          { name: 'JSON 输出', status: 'passed', detail: 'JSON 格式正确', latency_ms: 180000 },
        ],
      },
      {
        category: 'cache',
        displayName: 'Prompt Cache',
        status: 'passed',
        score: 100,
        probes: [
          { name: '缓存命中', status: 'passed', detail: '缓存正常', latency_ms: 50000 },
        ],
      },
    ],
};

// Mock API 响应数据 - 多模型诊断结果
const mockDiagnosticsResponseModel2 = {
  model: 'claude-3-sonnet',
  status: 'passed',
  confidence: 0.88,
  overall_status: 'passed',
  categories: [
      {
        category: 'connectivity',
        displayName: '连通性',
        status: 'passed',
        score: 100,
        probes: [
          { name: '基础连接', status: 'passed', detail: '连接成功', latency_ms: 80000 },
        ],
      },
      {
        category: 'streaming',
        displayName: '流式传输',
        status: 'passed',
        score: 90,
        probes: [
          { name: '流式响应', status: 'passed', detail: '流式正常', latency_ms: 150000 },
        ],
      },
    ],
};

// Helper: 导航到站点详情页并切换到诊断 Tab
async function goToDiagTab(page: import('@playwright/test').Page) {
  await page.goto('/sites/test-site');
  await page.waitForLoadState('networkidle');
  await page.click('.site-test-internal-tab:has-text("诊断")');
  await page.waitForLoadState('networkidle');
}

// Helper: Mock 诊断 API 并执行诊断流程
async function mockDiagnosticsAndRun(
  page: import('@playwright/test').Page,
  response = mockDiagnosticsResponse,
) {
  await page.route('**/api/diagnostics**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response),
    });
  });
}

test.describe('SiteTestTab Diagnostics', () => {
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
            models: ['claude-3-opus', 'claude-3-sonnet'],
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
  });

  test('应该显示诊断 Tab 内容', async ({ page }) => {
    await goToDiagTab(page);

    // 验证说明文字可见
    await expect(page.locator('.create-form-notice')).toBeVisible();
    await expect(page.locator('.create-form-notice')).toContainText('仅支持 Anthropic 协议');

    // 验证类别网格可见
    await expect(page.locator('.diag-category-grid')).toBeVisible();

    // 验证有 6 个类别选项
    const categoryItems = page.locator('.diag-category-option');
    await expect(categoryItems).toHaveCount(6);

    // 验证开始诊断按钮可见
    await expect(page.locator('button:has-text("开始诊断")')).toBeVisible();

    // 验证全选/全不选按钮可见
    await expect(page.locator('button:has-text("全选")')).toBeVisible();
    await expect(page.locator('button:has-text("全不选")')).toBeVisible();
  });

  test('应该支持类别选择', async ({ page }) => {
    await goToDiagTab(page);

    // 点击第一个类别 checkbox
    const checkbox = page.locator('.diag-category-checkbox').first();
    await checkbox.check();

    // 验证 checkbox 被选中
    await expect(checkbox).toBeChecked();

    // 验证开始诊断按钮文本包含选中类别数
    await expect(page.locator('button:has-text("开始诊断")')).toContainText('个类别');
  });

  test('应该支持全选和全不选', async ({ page }) => {
    await goToDiagTab(page);

    // 点击全选
    await page.locator('button:has-text("全选")').click();

    // 验证所有 checkbox 都被选中
    const checkboxes = page.locator('.diag-category-checkbox');
    const count = await checkboxes.count();
    for (let i = 0; i < count; i++) {
      await expect(checkboxes.nth(i)).toBeChecked();
    }

    // 验证按钮文本包含所有类别
    await expect(page.locator('button:has-text("开始诊断")')).toContainText('6 个类别');

    // 点击全不选
    await page.locator('button:has-text("全不选")').click();

    // 验证所有 checkbox 都未选中
    for (let i = 0; i < count; i++) {
      await expect(checkboxes.nth(i)).not.toBeChecked();
    }

    // 验证开始诊断按钮被禁用
    await expect(page.locator('button:has-text("开始诊断")')).toBeDisabled();
  });

  test('应该显示诊断进度', async ({ page }) => {
    await goToDiagTab(page);

    // 使用延迟响应来捕获进度状态（先导航再注册，确保页面加载正常）
    await page.route('**/api/diagnostics**', async (route) => {
      // 延迟 500ms 模拟诊断耗时
      await new Promise((r) => setTimeout(r, 500));
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockDiagnosticsResponse),
      });
    });

    // 选择类别
    await page.locator('button:has-text("全选")').click();

    // 点击开始诊断
    await page.locator('button:has-text("开始诊断")').click();

    // 验证进度文本显示（诊断中）
    await expect(page.locator('button:has-text("诊断中")')).toBeVisible();
    await expect(page.locator('.result-loading-spinner').first()).toBeVisible();
  });

  test('应该显示诊断结果', async ({ page }) => {
    await goToDiagTab(page);
    await mockDiagnosticsAndRun(page);

    // 选择类别并开始诊断
    await page.locator('button:has-text("全选")').click();
    await page.locator('button:has-text("开始诊断")').click();

    // 等待诊断结果卡片出现
    await expect(page.locator('.diag-result-model-card').first()).toBeVisible({ timeout: 10000 });

    // 验证模型名称显示
    await expect(page.locator('.diag-result-model-card').first().locator('.diag-result-model-name')).toContainText('claude-3-opus');
  });

  test('应该支持多个模型诊断', async ({ page }) => {
    // 依次返回不同模型的诊断结果
    let callCount = 0;
    await page.route('**/api/diagnostics**', (route) => {
      callCount++;
      const response = callCount === 1 ? mockDiagnosticsResponse : mockDiagnosticsResponseModel2;
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(response),
      });
    });

    await goToDiagTab(page);

    // 选择类别并开始诊断
    await page.locator('button:has-text("全选")').click();
    await page.locator('button:has-text("开始诊断")').click();

    // 等待所有诊断完成（两个结果卡片）
    await expect(page.locator('.diag-result-model-card')).toHaveCount(2, { timeout: 120000 });

    // 验证第一个模型结果
    await expect(page.locator('.diag-result-model-card').first().locator('.diag-result-model-name')).toContainText('claude-3-opus');

    // 验证第二个模型结果
    await expect(page.locator('.diag-result-model-card').nth(1).locator('.diag-result-model-name')).toContainText('claude-3-sonnet');
  });

  // 移动端测试由 Playwright device projects（Mobile Chrome / Mobile Safari）处理
  // 在非 device project 中跳过此测试，无需手动 setViewportSize
  test('应该在移动端正确显示', async ({ page }) => {
    const project = test.info().project.name;
    if (!project.includes('Mobile')) {
      test.skip();
    }

    await goToDiagTab(page);

    // 验证类别网格可见
    await expect(page.locator('.diag-category-grid')).toBeVisible();

    // 验证类别选项可见
    await expect(page.locator('.diag-category-option').first()).toBeVisible();

    // 验证开始诊断按钮可见
    await expect(page.locator('button:has-text("开始诊断")')).toBeVisible();
  });
});
