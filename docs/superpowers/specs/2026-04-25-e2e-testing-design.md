# E2E 测试与 Pre-push Hook 设计

## 目标

在每次 `git push` 前自动运行 E2E 测试，减少人工验证时间，防止回归问题推送到远程。

## 技术选型

- **E2E 框架：** Playwright Test
- **运行位置：** 本地 git pre-push hook
- **后端依赖：** 启动真实 FastAPI 服务（临时 SQLite 数据库）
- **Mock 策略：** 后端测试模式（`E2E_TEST_MODE=1`），拦截出站 AI API 请求返回模拟响应

## 架构

```
git push (pre-push hook)
    │
    ▼
scripts/e2e-run.sh
    │
    ├── 设置环境变量（DATABASE_URL, E2E_TEST_MODE, JWT_SECRET）
    ├── 清理旧临时数据库
    └── npx playwright test
            │
            ├── Playwright webServer 自动启动:
            │   ├── FastAPI 后端 (port 8081, 临时 SQLite)
            │   └── Vite 前端 dev server (port 5181)
            │
            ├── 运行所有 e2e 测试
            │
            └── 测试完成后自动清理服务
```

## 文件结构

```
AITokenPerf/
├── playwright.config.js          # Playwright 配置
├── e2e/
│   ├── fixtures/
│   │   └── auth.js               # 共享 fixture：登录、创建测试数据
│   ├── auth.spec.js              # 认证与用户生命周期
│   ├── dashboard.spec.js         # 仪表盘
│   ├── sites.spec.js             # 目标站点 + 详情
│   ├── history.spec.js           # 历史与对比
│   ├── tasks.spec.js             # 定时任务
│   ├── config.spec.js            # 配置管理
│   └── admin.spec.js             # 用户管理 + 模型管理
├── scripts/
│   └── e2e-run.sh                # pre-push hook 调用的脚本
└── .git/hooks/
    └── pre-push                  # git pre-push hook
```

## 测试场景

### 1. 认证与用户生命周期 (`auth.spec.js`)

| 场景 | 描述 |
|------|------|
| 注册新用户 | 填写邮箱 + 密码 → 注册成功 → 进入仪表盘 |
| 首次登录强制改密 | 使用默认密码登录 → 弹出改密表单 → 修改密码 → 进入仪表盘 |
| 正常登录/登出 | 输入邮箱密码 → 登录成功 → 点击退出 → 回到登录页 |
| 自助修改密码 | 进入设置 → 修改密码 → 重新登录验证 |
| Token 过期 | 模拟 token 过期 → 自动跳转登录页 |
| 未登录访问保护页 | 直接访问 `/sites` → 重定向到 `/auth` |
| 权限验证 | 普通用户访问 `/admin-users` → 被拒绝或重定向 |
| 管理员用户管理 | 管理员查看用户列表、修改用户角色 |

### 2. 仪表盘 (`dashboard.spec.js`)

| 场景 | 描述 |
|------|------|
| 页面加载 | 显示统计卡片和图表 |
| 时间范围切换 | 切换 1h/6h/24h/7d → 数据刷新 |
| 站点状态列表 | 正确渲染站点卡片 |

### 3. 目标站点 (`sites.spec.js`)

| 场景 | 描述 |
|------|------|
| 站点列表加载 | 页面显示站点列表 |
| 添加新站点 | 填写表单 → 提交 → 列表更新 |
| 编辑站点 | 修改站点配置 → 保存 → 验证更新 |
| 删除站点 | 点击删除 → 确认弹窗 → 删除 → 列表更新 |
| 站点详情页 | 点击站点 → 进入详情 → 显示信息和图表 |

### 4. 历史与对比 (`history.spec.js`)

| 场景 | 描述 |
|------|------|
| 历史记录列表 | 列表加载和渲染 |
| 筛选 | 按站点、时间范围筛选 |
| 结果详情 | 点击记录 → 弹出详情弹窗 |
| 记录对比 | 选择多条记录 → 对比视图 |

### 5. 定时任务 (`tasks.spec.js`)

| 场景 | 描述 |
|------|------|
| 任务列表加载 | 页面显示任务列表 |
| 创建定时任务 | 填写配置 → 创建 → 列表更新 |
| 编辑任务 | 修改任务配置 → 保存 |
| 删除任务 | 删除任务 → 列表更新 |

### 6. 配置管理 (`config.spec.js`)

| 场景 | 描述 |
|------|------|
| Profile 列表 | 加载和渲染 |
| 创建 Profile | 填写表单 → 创建 → 列表更新 |
| 编辑 Profile | 修改配置 → 保存 |
| 模型管理 | 管理员查看/添加/编辑模型 |

### 7. 用户管理 (`admin.spec.js`)

| 场景 | 描述 |
|------|------|
| 用户列表 | 管理员查看所有用户 |
| 修改角色 | 修改用户角色 → 验证更新 |
| 权限隔离 | 普通用户无法访问此页面 |

## 后端测试模式

### 环境变量

当 `E2E_TEST_MODE=1` 时，后端进入测试模式。

### 实现方式

在 `app/client.py` 的出站 HTTP 请求层添加拦截：

- 检测 `E2E_TEST_MODE` 环境变量
- 当启用时，所有发往 AI 模型 API 的请求返回预设模拟响应
- 模拟响应格式与真实 API 完全一致（OpenAI Chat Completions / Anthropic / Responses API）
- 固定延迟：50ms
- 固定 token 统计：100 prompt tokens, 50 completion tokens
- 其他所有逻辑（数据库、认证、路由、统计计算）保持真实运行

### 模拟响应示例

**OpenAI Chat Completions 格式：**
```json
{
  "choices": [{"message": {"content": "Test response"}, "finish_reason": "stop"}],
  "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
}
```

**Anthropic 格式：**
```json
{
  "content": [{"type": "text", "text": "Test response"}],
  "usage": {"input_tokens": 100, "output_tokens": 50}
}
```

## Pre-push Hook

### hook 脚本 (`.git/hooks/pre-push`)

```bash
#!/bin/bash
# 跳过 --no-verify
if echo "$@" | grep -q -- "--no-verify"; then
  exit 0
fi

# 只在 dev/main 分支运行
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" != "dev" && "$BRANCH" != "main" ]]; then
  exit 0
fi

exec bash scripts/e2e-run.sh
```

### e2e-run.sh 核心逻辑

1. 设置环境变量：
   - `DATABASE_URL=sqlite+aiosqlite:///tmp/e2e-test.db`
   - `E2E_TEST_MODE=1`
   - `JWT_SECRET=e2e-test-secret`
   - `LOG_MODE=stdout`
2. 清理旧的临时数据库文件
3. 运行 `npx playwright test`
4. 退出码传递给 git（0 = 允许推送，非 0 = 阻止推送）

### Playwright 配置 (`playwright.config.js`)

- `baseURL: http://localhost:5181`
- `webServer` 配置自动启动 FastAPI 后端 (port 8081) 和 Vite 前端 (port 5181)
- `retries: 0`（本地 hook 不重试，快速失败）
- `reporter: 'list'`（终端简洁输出）
- `timeout: 30000`（单个测试 30s 超时）
- `use.headless: true`（headless 模式运行）
- 只使用 Chromium 浏览器

## 依赖

### 新增 Node.js 依赖（devDependencies）

- `@playwright/test`（Playwright 测试框架，内置 webServer 管理）

### 浏览器安装

首次运行需执行：
```bash
npx playwright install chromium
```

## 跳过测试

- `git push --no-verify` 跳过 pre-push hook
- 非 dev/main 分支自动跳过
