import { test, expect } from '@playwright/test';

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
    await expect(page.locator('text=连通性')).toBeVisible();
    await expect(page.locator('text=流式传输')).toBeVisible();
    await expect(page.locator('text=多轮上下文')).toBeVisible();
    await expect(page.locator('text=工具调用')).toBeVisible();
    await expect(page.locator('text=结构化输出')).toBeVisible();
    await expect(page.locator('text=Prompt Cache')).toBeVisible();
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
    // 选择模型和类别
    await page.click('button:has-text("全选")');

    // 点击开始诊断
    await page.click('button:has-text("开始诊断")');

    // 等待诊断完成
    await expect(page.locator('.diag-result-card')).toBeVisible({ timeout: 60000 });

    // 点击类别卡片展开详情
    const categoryCard = page.locator('.diag-category-card').first();
    await categoryCard.click();

    // 验证探针详情显示
    await expect(page.locator('.diag-probes-detail')).toBeVisible();

    // 再次点击折叠
    await categoryCard.click();

    // 验证探针详情隐藏
    await expect(page.locator('.diag-probes-detail')).not.toBeVisible();
  });

  test('应该在移动端正确显示', async ({ page }) => {
    // 设置移动端视口
    await page.setViewportSize({ width: 375, height: 667 });

    // 验证类别选择器正确显示
    await expect(page.locator('.diag-category-grid')).toBeVisible();

    // 验证类别卡片垂直堆叠（移动端应该是单列）
    const cards = page.locator('.diag-category-option');
    const firstCard = await cards.first().boundingBox();
    const secondCard = await cards.nth(1).boundingBox();

    // 移动端应该是垂直堆叠（y 坐标不同）
    expect(firstCard?.y).not.toBe(secondCard?.y);
  });
});
