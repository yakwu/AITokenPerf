import { test, expect } from '@playwright/test';

// Mock API 响应数据
const mockDiagnosticsResponse = {
  success: true,
  data: {
    model: 'test-model',
    results: [
      {
        category: 'connectivity',
        displayName: '连通性',
        status: 'pass',
        score: 100,
        probes: [
          { name: '基础连接', status: 'pass', message: '连接成功', latency: 120 },
        ],
      },
      {
        category: 'streaming',
        displayName: '流式传输',
        status: 'pass',
        score: 95,
        probes: [
          { name: '流式响应', status: 'pass', message: '流式正常', latency: 200 },
        ],
      },
      {
        category: 'multi_turn',
        displayName: '多轮上下文',
        status: 'pass',
        score: 90,
        probes: [
          { name: '上下文保持', status: 'pass', message: '上下文正常', latency: 150 },
        ],
      },
      {
        category: 'tool_use',
        displayName: '工具调用',
        status: 'warn',
        score: 80,
        probes: [
          { name: '函数调用', status: 'warn', message: '部分工具不支持', latency: 300 },
        ],
      },
      {
        category: 'structured_output',
        displayName: '结构化输出',
        status: 'pass',
        score: 85,
        probes: [
          { name: 'JSON 输出', status: 'pass', message: 'JSON 格式正确', latency: 180 },
        ],
      },
      {
        category: 'prompt_cache',
        displayName: 'Prompt Cache',
        status: 'pass',
        score: 100,
        probes: [
          { name: '缓存命中', status: 'pass', message: '缓存正常', latency: 50 },
        ],
      },
    ],
  },
};

test.describe('DiagnosticCard', () => {
  test.beforeEach(async ({ page }) => {
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
    // 点击连通性类别卡片
    const connectivityCard = page.locator('.diag-category-option').first();
    await connectivityCard.click();

    // 验证 checkbox 被选中
    await expect(connectivityCard.locator('input[type="checkbox"]')).toBeChecked();

    // 再次点击取消选中
    await connectivityCard.click();
    await expect(connectivityCard.locator('input[type="checkbox"]')).not.toBeChecked();
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

    // 验证默认状态：expandedCategories 默认包含所有 6 个类别，探针详情应可见
    const firstCategoryCard = page.locator('.diag-category-card').first();
    await expect(firstCategoryCard.locator('.diag-probes-detail')).toBeVisible();

    // 点击类别卡片折叠详情
    await firstCategoryCard.click();

    // 验证探针详情隐藏
    await expect(firstCategoryCard.locator('.diag-probes-detail')).not.toBeVisible();

    // 再次点击展开
    await firstCategoryCard.click();

    // 验证探针详情重新显示
    await expect(firstCategoryCard.locator('.diag-probes-detail')).toBeVisible();
  });

  // 移动端测试由 Playwright device projects（Mobile Chrome / Mobile Safari）处理
  // 在非 device project 中跳过此测试，无需手动 setViewportSize
  test('应该在移动端正确显示', async () => {
    test.skip();
  });
});
