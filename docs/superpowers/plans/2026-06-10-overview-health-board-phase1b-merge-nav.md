# 站点健康看板 · 阶段一·b（合并概览 + 改导航）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development / executing-plans. Steps use checkbox.

**Goal:** 把「站点」健康看板变成默认落地页，退役旧「概览」(`DashboardView`)，主导航收敛为 **站点 / 历史与对比 / 定时任务**（去掉"概览"、"目标站点"改名"站点"）。消除"看数据散落"（设计 §4/§5.2 痛点④）。

**Architecture:** 纯前端、机械改动 5 处文件：路由 `/` 重定向到 `/sites`；导航 tab 收敛与改名；登录后跳转改 `/sites`；删 `DashboardView.vue`；修 1 个 e2e 断言。⚙设置 hub 属阶段二，不在本计划。

**Tech Stack:** Vue 3 + vue-router + Pinia；构建 `bun run build`（前端用 bun）。

**工作目录：** `/Users/yakun/linkingrid/AITokenPerf/.claude/worktrees/issue-58-overview-health-board`（分支 `feat/issue-58-overview-health-board`，已含阶段零 + 阶段一a 看板）。

---

## Task 1: 路由 + 导航 + 删 Dashboard（一次性，构建验证）

**Files:** `frontend/src/router.js`、`frontend/src/App.vue`、`frontend/src/views/AuthView.vue`、`frontend/src/stores/app.js`、删 `frontend/src/views/DashboardView.vue`、`e2e/dashboard.spec.js`

- [ ] **Step 1: 路由 `/` 重定向到 `/sites`** — `frontend/src/router.js`，把：
```js
    { path: '/', name: 'dashboard', component: () => import('./views/DashboardView.vue') },
```
改为：
```js
    { path: '/', redirect: '/sites' },
```

- [ ] **Step 2: 导航 tab 收敛 + 改名** — `frontend/src/App.vue`，把 `const tabs = [...]`（约 89–94 行）：
```js
const tabs = [
  { name: '概览', path: '/' },
  { name: '目标站点', path: '/sites', activeMatch: (p) => p.startsWith('/sites') },
  { name: '历史与对比', path: '/history' },
  { name: '定时任务', path: '/tasks' },
];
```
改为：
```js
const tabs = [
  { name: '站点', path: '/sites', activeMatch: (p) => p.startsWith('/sites') || p === '/' },
  { name: '历史与对比', path: '/history' },
  { name: '定时任务', path: '/tasks' },
];
```

- [ ] **Step 3: 登录后跳转改 `/sites`** — `frontend/src/App.vue`，把登录后那处（约 134 行）：
```js
      router.push('/');
```
改为：
```js
      router.push('/sites');
```

- [ ] **Step 4: AuthView 跳转改 sites** — `frontend/src/views/AuthView.vue`，两处（约 114、143 行）：
```js
    store.switchTab('dashboard');
```
都改为：
```js
    store.switchTab('sites');
```

- [ ] **Step 5: 简化 switchTab（去掉已无用的 dashboard 特例）** — `frontend/src/stores/app.js`，把（约 24 行）：
```js
    router.push(t === 'dashboard' ? '/' : '/' + t);
```
改为：
```js
    router.push('/' + t);
```

- [ ] **Step 6: 删除退役的概览页** — 删除文件 `frontend/src/views/DashboardView.vue`（已无任何引用：router 改成 redirect 后不再 import）。
```bash
git rm frontend/src/views/DashboardView.vue
```

- [ ] **Step 7: 修 e2e 断言** — `e2e/dashboard.spec.js`：把 `describe('仪表盘', ...)` 改 `describe('站点看板', ...)`；第一个 test 名 `'页面加载显示统计卡片'` 改 `'默认落地站点看板'`；断言行：
```js
    await expect(page.locator('.tab-btn.active')).toContainText('概览');
```
改为：
```js
    await expect(page.locator('.tab-btn.active')).toContainText('站点');
```
（时间范围、刷新两条 test 对看板仍有效，保持不变。）

- [ ] **Step 8: 构建验证** — `cd frontend && bun run build`，必须成功、无对 `DashboardView` 的未解析引用。再 grep 确认无残留：
```bash
grep -rn "DashboardView\|name: 'dashboard'\|switchTab('dashboard')\|name: '概览'" frontend/src || echo "无残留 OK"
```

- [ ] **Step 9: 提交**
```bash
git add frontend/src/router.js frontend/src/App.vue frontend/src/views/AuthView.vue frontend/src/stores/app.js e2e/dashboard.spec.js
git commit -m "feat(web): 概览并入站点看板，导航收敛为 站点/历史/定时任务，退役 DashboardView (#58)"
```

---

## Self-Review
- **Spec 覆盖**：`/`→`/sites`✓；"概览"tab 移除、"目标站点"→"站点"✓；登录落地看板✓；退役 DashboardView✓（设计 §5.2）。⚙设置 hub 不在本期（阶段二）。
- **断链检查**：`switchTab('dashboard')` 调用点（AuthView ×2）已改 'sites'；ternary 已去；router `/` redirect 兜住任何残留 `push('/')`。无 `name:'dashboard'` 具名跳转。
- **占位符**：每步给出精确 before→after。
- **测试**：`bun run build` 必过；e2e 断言已同步（e2e 不在 pre-push，但保持正确）。视觉确认（导航只剩 3 tab、默认进看板）需人工浏览器。
- **范围**：仅导航/路由/退役页；看板本身阶段一a 已完成。
