import { test, expect, login, resetDb } from './fixtures/auth';

const BASE_URL = 'http://localhost:8081';
const SITE_NAME = 'E2E-Test-Site';
const SITE_MODELS = ['gpt-4o-mini', 'gpt-4o', 'claude-3-haiku'];

/**
 * 从浏览器 localStorage 获取当前登录 token
 */
async function getBrowserToken(page) {
  return await page.evaluate(() => localStorage.getItem('token'));
}

/**
 * 通过 API 创建测试站点（使用浏览器 session 的 token）
 */
async function createTestSite(page) {
  const token = await getBrowserToken(page);
  const res = await page.request.post(`${BASE_URL}/api/profiles`, {
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    data: {
      name: SITE_NAME,
      base_url: 'https://api.openai.com/v1',
      api_key: 'sk-test-key',
      models: SITE_MODELS,
      provider: 'OpenAI',
      protocol: 'openai_chat',
    },
  });
  expect(res.ok()).toBeTruthy();
}

/**
 * 通过 API 创建定时任务（使用浏览器 session 的 token）
 */
async function createScheduleViaApi(page, overrides = {}) {
  const token = await getBrowserToken(page);
  const payload = {
    name: 'API 创建的任务',
    profile_ids: [SITE_NAME],
    configs_json: {
      concurrency_levels: [1],
      mode: 'burst',
      max_tokens: 512,
      timeout: 120,
      duration: 120,
      models: ['gpt-4o-mini'],
      system_prompt: 'You are a helpful assistant.',
      user_prompt: 'Say hello.',
    },
    schedule_type: 'interval',
    schedule_value: '300',
    ...overrides,
  };
  const res = await page.request.post(`${BASE_URL}/api/schedules`, {
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    data: payload,
  });
  expect(res.ok()).toBeTruthy();
  const data = await res.json();
  return data;
}

/**
 * 导航到站点详情页的定时任务 Tab
 */
async function goToScheduleTab(page) {
  // 直接导航到站点详情的定时任务 Tab
  await page.goto(`/sites/${encodeURIComponent(SITE_NAME)}?tab=schedule`);
  // 等待站点详情页加载完成
  await expect(page.locator('.site-schedules-tab')).toBeVisible({ timeout: 10000 });
  await page.waitForTimeout(300);
}

test.describe('定时任务 CRUD — Issue #16 #17 #18', () => {
  test.beforeEach(async ({ page }) => {
    await resetDb(page);
    await login(page);
    await createTestSite(page);
  });

  // ==================== Issue #17: 创建表单 prompt 字段 ====================

  test.describe('Issue #17 — 创建表单含 system_prompt / user_prompt', () => {
    test('创建表单包含 System Prompt 和 User Prompt 输入框', async ({ page }) => {
      await goToScheduleTab(page);

      // 展开创建表单
      const createBtn = page.locator('button', { hasText: '新建任务' }).first();
      await createBtn.click();
      await page.waitForTimeout(300);

      const createForm = page.locator('.create-form');

      // 验证 prompt 字段存在
      await expect(createForm.locator('label', { hasText: 'System Prompt' })).toBeVisible();
      await expect(createForm.locator('label', { hasText: 'User Prompt' })).toBeVisible();

      // 验证 textarea 可见
      await expect(createForm.locator('textarea').nth(0)).toBeVisible();
      await expect(createForm.locator('textarea').nth(1)).toBeVisible();
    });

    test('创建表单 prompt 字段有默认值', async ({ page }) => {
      await goToScheduleTab(page);

      const createBtn = page.locator('button', { hasText: '新建任务' }).first();
      await createBtn.click();
      await page.waitForTimeout(300);

      // 验证默认值
      const textareas = page.locator('.create-form textarea');
      const systemPrompt = textareas.nth(0);
      const userPrompt = textareas.nth(1);

      await expect(systemPrompt).toHaveValue('You are a helpful assistant.');
      await expect(userPrompt).toHaveValue('Write a short essay about the future of artificial intelligence in exactly 200 words.');
    });

    test('创建定时任务 — 填写 prompt 并提交', async ({ page }) => {
      await goToScheduleTab(page);

      // 展开创建表单
      const createBtn = page.locator('button', { hasText: '新建任务' }).first();
      await createBtn.click();
      await page.waitForTimeout(300);

      // 填写任务名称
      await page.locator('.create-form input.form-input[placeholder*="快速巡检"]').fill('Prompt 测试任务');

      // 选择模型 — 输入模型名并回车
      const modelInput = page.locator('.create-form .model-tag-search');
      await modelInput.fill('gpt-4o-mini');
      await modelInput.press('Enter');

      // 修改 prompt
      const textareas = page.locator('.create-form textarea');
      await textareas.nth(0).clear();
      await textareas.nth(0).fill('Custom system prompt for testing');
      await textareas.nth(1).clear();
      await textareas.nth(1).fill('Custom user prompt for testing');

      // 提交
      const submitBtn = page.locator('.create-form .btn-primary', { hasText: '创建' });
      await submitBtn.click();

      // 验证创建成功（表格中出现新任务）
      await expect(page.locator('td', { hasText: 'Prompt 测试任务' })).toBeVisible({ timeout: 5000 });
    });
  });

  // ==================== Issue #18: 编辑表单完整字段 ====================

  test.describe('Issue #18 — 编辑表单字段对齐', () => {
    test('编辑弹窗包含所有可编辑字段', async ({ page }) => {
      // 先通过 API 创建一个任务
      await createScheduleViaApi(page);
      await goToScheduleTab(page);

      // 点击编辑按钮
      const editBtn = page.locator('button[title="编辑"]').first();
      await expect(editBtn).toBeVisible({ timeout: 5000 });
      await editBtn.click();
      await page.waitForTimeout(300);

      // 验证编辑弹窗中的所有字段
      const modal = page.locator('.modal-overlay, [class*="modal"]').first();
      await expect(modal).toBeVisible();

      // 基础字段
      await expect(modal.locator('label', { hasText: '任务名称' })).toBeVisible();
      await expect(modal.locator('label', { hasText: '执行频率' })).toBeVisible();
      await expect(modal.locator('label', { hasText: '选择模型' })).toBeVisible();

      // 测试参数字段
      await expect(modal.locator('label', { hasText: '并发数' })).toBeVisible();
      await expect(modal.locator('label', { hasText: '测试模式' })).toBeVisible();
      await expect(modal.locator('label', { hasText: '超时' })).toBeVisible();
      await expect(modal.locator('label', { hasText: '持续时长' })).toBeVisible();
      await expect(modal.locator('label', { hasText: '最大 Token' })).toBeVisible();

      // Prompt 字段
      await expect(modal.locator('label', { hasText: 'System Prompt' })).toBeVisible();
      await expect(modal.locator('label', { hasText: 'User Prompt' })).toBeVisible();
    });

    test('编辑弹窗回填已有配置值', async ({ page }) => {
      // 创建一个有完整配置的任务
      await createScheduleViaApi(page, {
        name: '完整配置任务',
        configs_json: {
          concurrency_levels: [3],
          mode: 'sustained',
          max_tokens: 1024,
          timeout: 60,
          duration: 300,
          models: ['gpt-4o'],
          system_prompt: 'Custom system prompt',
          user_prompt: 'Custom user prompt',
        },
      });
      await goToScheduleTab(page);

      // 点击编辑
      const editBtn = page.locator('button[title="编辑"]').first();
      await editBtn.click();
      await page.waitForTimeout(300);

      const modal = page.locator('.modal-overlay, [class*="modal"]').first();

      // 验证回填值
      await expect(modal.locator('input.form-input').first()).toHaveValue('完整配置任务');

      // 验证并发数回填
      const concurrencyInput = modal.locator('input[type="number"][min="1"]').first();
      await expect(concurrencyInput).toHaveValue('3');

      // 验证 prompt 回填
      const textareas = modal.locator('textarea');
      await expect(textareas.nth(0)).toHaveValue('Custom system prompt');
      await expect(textareas.nth(1)).toHaveValue('Custom user prompt');
    });

    test('编辑后保存 — 修改所有字段', async ({ page }) => {
      await createScheduleViaApi(page, { name: '原始任务' });
      await goToScheduleTab(page);

      // 编辑
      const editBtn = page.locator('button[title="编辑"]').first();
      await editBtn.click();
      await page.waitForTimeout(300);

      const modal = page.locator('.modal-overlay, [class*="modal"]').first();

      // 修改任务名称
      const nameInput = modal.locator('input.form-input').first();
      await nameInput.clear();
      await nameInput.fill('修改后的任务');

      // 修改 prompt
      const textareas = modal.locator('textarea');
      await textareas.nth(0).clear();
      await textareas.nth(0).fill('Updated system prompt');
      await textareas.nth(1).clear();
      await textareas.nth(1).fill('Updated user prompt');

      // 保存（模态框可能超出视口，用 JS 点击）
      await page.evaluate(() => {
        const modal = document.querySelector('.modal-overlay') || document.querySelector('[class*="modal"]');
        if (modal) {
          const btns = modal.querySelectorAll('.btn-primary');
          for (const btn of btns) {
            if (btn.textContent.includes('保存')) { btn.click(); break; }
          }
        }
      });

      // 验证保存成功
      await expect(page.locator('td', { hasText: '修改后的任务' })).toBeVisible({ timeout: 5000 });
    });
  });

  // ==================== Issue #16: 字段校验 ====================

  test.describe('Issue #16 — 字段校验', () => {
    test('创建任务 — 名称为空时提示', async ({ page }) => {
      await goToScheduleTab(page);

      const createBtn = page.locator('button', { hasText: '新建任务' }).first();
      await createBtn.click();
      await page.waitForTimeout(300);

      // 不填名称，直接选模型并提交
      const modelInput = page.locator('.create-form .model-tag-search');
      await modelInput.fill('gpt-4o-mini');
      await modelInput.press('Enter');

      const submitBtn = page.locator('.create-form .btn-primary', { hasText: '创建' });
      await submitBtn.click();

      // 验证出现提示 toast
      await expect(page.locator('.toast').filter({ hasText: /名称/ })).toBeVisible({ timeout: 3000 });
    });

    test('创建任务 — 未选模型时提示', async ({ page }) => {
      await goToScheduleTab(page);

      const createBtn = page.locator('button', { hasText: '新建任务' }).first();
      await createBtn.click();
      await page.waitForTimeout(300);

      // 填名称但不选模型
      await page.locator('.create-form input.form-input[placeholder*="快速巡检"]').fill('测试任务');

      const submitBtn = page.locator('.create-form .btn-primary', { hasText: '创建' });
      await submitBtn.click();

      // 验证出现提示
      await expect(page.locator('.toast').filter({ hasText: /模型/ })).toBeVisible({ timeout: 3000 });
    });
  });

  // ==================== Issue #18: 并发默认值 ====================

  test.describe('Issue #18 — 调度器并发默认值', () => {
    test('创建表单并发数默认值为 1', async ({ page }) => {
      await goToScheduleTab(page);

      const createBtn = page.locator('button', { hasText: '新建任务' }).first();
      await createBtn.click();
      await page.waitForTimeout(300);

      // 验证并发数输入框的 placeholder 为 1
      const concurrencyInput = page.locator('.create-form input[type="number"][min="1"]').first();
      await expect(concurrencyInput).toHaveAttribute('placeholder', '1');
    });

    test('创建任务 — 默认并发数为 1（非 100）', async ({ page }) => {
      // 拦截 API 请求，验证 payload
      let capturedPayload = null;
      await page.route('**/api/schedules', async (route) => {
        if (route.request().method() === 'POST') {
          capturedPayload = await route.request().postDataJSON();
        }
        await route.continue();
      });

      await goToScheduleTab(page);

      const createBtn = page.locator('button', { hasText: '新建任务' }).first();
      await createBtn.click();
      await page.waitForTimeout(300);

      // 填写必要字段
      await page.locator('.create-form input.form-input[placeholder*="快速巡检"]').fill('默认并发测试');
      const modelInput = page.locator('.create-form .model-tag-search');
      await modelInput.fill('gpt-4o-mini');
      await modelInput.press('Enter');

      // 提交
      const submitBtn = page.locator('.create-form .btn-primary', { hasText: '创建' });
      await submitBtn.click();
      await page.waitForTimeout(1000);

      // 验证 payload 中 concurrency_levels 为 [1]
      expect(capturedPayload).not.toBeNull();
      expect(capturedPayload.configs_json.concurrency_levels).toEqual([1]);
    });
  });
});
