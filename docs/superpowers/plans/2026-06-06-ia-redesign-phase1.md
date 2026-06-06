# 信息架构重构 · 阶段一（导航收敛快赢） Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除孤儿重复页 `/config`，并给站点列表加"收藏置顶 + 折叠健康站点"，以最低风险先兑现易用性快赢。

**Architecture:** 纯前端 Vue 3 改动，不动后端、不动数据库。收藏/折叠状态用 `localStorage` 持久化（贴合真实量级，无需后端）。每个 Task 一个独立 PR、可独立上线回滚。

**Tech Stack:** Vue 3 + Vue Router + Pinia；测试用 Playwright E2E（`bun run test:e2e`）。前端包管理用 **bun**，不用 npm。

> **本计划的范围说明（重要）**：spec 阶段一原列 4 件事。代码核实后发现其中两件不是"零风险收敛"：
> - **砍"我的模型"中间层**：站点选模型走 `/api/pricing/models`，"我的模型"走 `/api/pricing/models-config`，两个后端来源是否耦合（自定义模型/价格覆盖是否被 ModelSelector 消费）尚未定死，需单独调研后端再做 → 列为**后续 PR ①**。
> - **概览全局任务只读总览 + 移除顶栏"定时任务"**：要改 `DashboardView` + `TasksView` 两个大视图，且"只读+轻操作总览"是新功能 → 列为**后续 PR ②**。
> 本计划只做两件已摸到代码级、零耦合的快赢。后续 PR 在落地本计划后另写细化计划。

---

## 关联事实（已核实，供执行者参考，勿重复假设）

- `/config` 路由：`frontend/src/router.js:13`，组件 `frontend/src/views/ProfileView.vue`。**全前端无任何 `router.push('/config')` / 链接 / `switchTab('config')`**（已 grep 确认）——它只能靠手敲 URL 到达。
- 站点连接编辑已由 `frontend/src/components/SiteConfigTab.vue` 完整覆盖（base_url、api_key 脱敏、ModelSelector、连通性验证、删除站点、保存走 `/api/profiles/save`）。删 `/config` 无功能损失。
- `frontend/src/stores/app.js:5` 有 `VALID_TABS` 数组含 `'config'`，但当前代码未用它做强校验（`switchTab` 不消费它）——可顺手清理。
- 站点列表 `frontend/src/views/SitesView.vue`：卡片网格 `filteredSites`（computed，行 209-230，含搜索/状态筛选/健康排序）；卡片头部行 42-53；metrics 区 v-if 行 56-105；工具栏行 4-21。站点唯一标识 `site.profile.name`，健康字段 `site.health`（取值 `healthy`/`error`/`untested`/`unknown`）。

---

## Task 1: 删除 /config 孤儿重复页

**Files:**
- Modify: `frontend/src/router.js:13`
- Delete: `frontend/src/views/ProfileView.vue`
- Modify: `frontend/src/stores/app.js:5`
- Test: `frontend/tests/e2e/config-redirect.spec.ts`（实际目录以 `playwright.config.ts` 的 `testDir` 为准）

- [ ] **Step 1: 确认 Playwright testDir 与登录辅助**

Run: `grep -E "testDir|baseURL" frontend/playwright.config.ts`
Expected: 输出 testDir（如 `./tests/e2e`）与 baseURL。把下方测试文件放到该 testDir 下；若已有登录 fixture/helper，沿用之。

- [ ] **Step 2: 写失败的 E2E 测试**

在 testDir 下新建 `config-redirect.spec.ts`：

```ts
import { test, expect } from '@playwright/test';

// 已登录态由项目既有 fixture 提供；若无，先按既有 spec 的登录写法补齐。
test('/config 被重定向到 /sites', async ({ page }) => {
  await page.goto('/config');
  await expect(page).toHaveURL(/\/sites$/);
});
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `cd frontend && bun run test:e2e -- config-redirect`
Expected: FAIL（当前 `/config` 渲染 ProfileView，URL 停在 `/config`，不会跳 `/sites`）

- [ ] **Step 4: 把 /config 路由改为重定向**

`frontend/src/router.js` 第 13 行：

```js
// 删除这一行：
//   { path: '/config', name: 'config', component: () => import('./views/ProfileView.vue') },
// 改为：
    { path: '/config', redirect: '/sites' },
```

- [ ] **Step 5: 删除 ProfileView 组件文件**

```bash
git rm frontend/src/views/ProfileView.vue
```

- [ ] **Step 6: 清理 VALID_TABS 里的 'config'**

`frontend/src/stores/app.js` 第 5 行：

```js
const VALID_TABS = ['dashboard', 'bench', 'history', 'settings', 'auth', 'admin-users', 'models'];
```

- [ ] **Step 7: 运行测试，确认通过**

Run: `cd frontend && bun run test:e2e -- config-redirect`
Expected: PASS

- [ ] **Step 8: 构建确认无残留引用**

Run: `cd frontend && bun run build`
Expected: 构建成功，无 "ProfileView" 未解析引用报错。

- [ ] **Step 9: 提交**

```bash
git add frontend/src/router.js frontend/src/stores/app.js frontend/tests
git rm frontend/src/views/ProfileView.vue
git commit -m "refactor(frontend): 删除孤儿页 /config，重定向到 /sites (#<issue>)"
```

---

## Task 2: 站点列表「收藏置顶 + 折叠健康站点」

**目标交互：**
- 每张站点卡片头部加 ☆/★ 收藏按钮，点击切换；收藏状态存 `localStorage`。
- `filteredSites` 排序：收藏的站点永远排在最前，组内仍按原健康度排序。
- 工具栏加一个「折叠健康站点」开关（默认开、存 `localStorage`）：开启时，**健康且未收藏**的卡片隐藏 metrics 表（只留头部+操作），让异常站点更突出；要看明细点「详情 →」。

**Files:**
- Modify: `frontend/src/views/SitesView.vue`
- Test: `frontend/tests/e2e/sites-favorite-collapse.spec.ts`

- [ ] **Step 1: 写失败的 E2E 测试**

在 testDir 下新建 `sites-favorite-collapse.spec.ts`：

```ts
import { test, expect } from '@playwright/test';

test('收藏的站点排到最前', async ({ page }) => {
  await page.goto('/sites');
  const cards = page.locator('.site-card');
  await expect(cards.first()).toBeVisible();
  // 收藏最后一张卡片
  const last = cards.last();
  const lastName = await last.locator('.site-name-link').innerText();
  await last.locator('.site-fav-btn').click();
  await page.reload();
  // 重新加载后，被收藏的应排在第一位
  await expect(page.locator('.site-card').first().locator('.site-name-link'))
    .toHaveText(lastName);
});

test('折叠健康站点开关隐藏健康卡片的指标表', async ({ page }) => {
  await page.goto('/sites');
  const toggle = page.locator('.collapse-healthy-toggle');
  await expect(toggle).toBeVisible();
  // 默认开启：健康卡片不显示 matrix-table
  const healthyCard = page.locator('.site-card--healthy').first();
  if (await healthyCard.count()) {
    await expect(healthyCard.locator('.matrix-table')).toHaveCount(0);
  }
});
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd frontend && bun run test:e2e -- sites-favorite-collapse`
Expected: FAIL（`.site-fav-btn`、`.collapse-healthy-toggle` 尚不存在）

- [ ] **Step 3: 在 `<script setup>` 加收藏与折叠状态**

`frontend/src/views/SitesView.vue`，在 `const statusFilter = ref('all')`（行 199）之后加入：

```js
// ---- 收藏（localStorage 持久化）----
const FAV_KEY = 'site_favorites';
function loadFavorites() {
  try { return new Set(JSON.parse(localStorage.getItem(FAV_KEY) || '[]')); }
  catch { return new Set(); }
}
const favorites = ref(loadFavorites());
function isFavorite(name) { return favorites.value.has(name); }
function toggleFavorite(name) {
  const next = new Set(favorites.value);
  next.has(name) ? next.delete(name) : next.add(name);
  favorites.value = next;
  localStorage.setItem(FAV_KEY, JSON.stringify([...next]));
}

// ---- 折叠健康站点（localStorage 持久化，默认开）----
const COLLAPSE_KEY = 'sites_collapse_healthy';
const collapseHealthy = ref(localStorage.getItem(COLLAPSE_KEY) !== '0');
function toggleCollapseHealthy() {
  collapseHealthy.value = !collapseHealthy.value;
  localStorage.setItem(COLLAPSE_KEY, collapseHealthy.value ? '1' : '0');
}
// 某卡片是否应折叠 metrics：开关开 且 健康 且 未收藏
function isCollapsed(site) {
  return collapseHealthy.value
    && site.health === 'healthy'
    && !isFavorite(site.profile.name);
}
```

- [ ] **Step 4: 排序里让收藏置顶**

`frontend/src/views/SitesView.vue` 的 `filteredSites`（行 222-228），把排序回调改成收藏优先：

```js
  // Sort: 收藏置顶 > error > healthy > untested，组内 by last_test_at desc
  const healthOrder = { error: 0, healthy: 1, untested: 2, unknown: 2 };
  list = [...list].sort((a, b) => {
    const fa = favorites.value.has(a.profile.name) ? 0 : 1;
    const fb = favorites.value.has(b.profile.name) ? 0 : 1;
    if (fa !== fb) return fa - fb;
    const ha = healthOrder[a.health] ?? 2;
    const hb = healthOrder[b.health] ?? 2;
    if (ha !== hb) return ha - hb;
    return (b.last_test_at || '').localeCompare(a.last_test_at || '');
  });
  return list;
```

- [ ] **Step 5: 工具栏加「折叠健康站点」开关**

`frontend/src/views/SitesView.vue` 模板，在 `filter-chips`（行 11-13）之后、`sites-toolbar-left` 关闭 `</div>`（行 14）之前插入：

```html
        <label class="collapse-healthy-toggle" :class="{ active: collapseHealthy }" @click="toggleCollapseHealthy">
          <input type="checkbox" :checked="collapseHealthy" @click.prevent>
          <span>折叠健康站点</span>
        </label>
```

- [ ] **Step 6: 卡片头部加收藏星标**

`frontend/src/views/SitesView.vue` 模板，在 `site-card-title-row`（行 43-47）里、`site-health-dot` 之前插入星标按钮：

```html
            <button class="site-fav-btn" :class="{ active: isFavorite(site.profile.name) }"
                    @click.stop="toggleFavorite(site.profile.name)"
                    :title="isFavorite(site.profile.name) ? '取消收藏' : '收藏'">
              {{ isFavorite(site.profile.name) ? '★' : '☆' }}
            </button>
```

- [ ] **Step 7: 折叠时隐藏 metrics 区**

`frontend/src/views/SitesView.vue`，把 metrics 块（行 61）的 `v-else` 条件加上未折叠判断。当前是：

```html
        <div v-else class="site-card-metrics">
```

改为：

```html
        <div v-else-if="!isCollapsed(site)" class="site-card-metrics">
```

并在其后补一个折叠占位（让健康卡片仍显示一行摘要，不至于空荡）：

```html
        <div v-else class="site-card-collapsed-hint">
          健康 · 已折叠明细
        </div>
```

- [ ] **Step 8: 加样式**

`frontend/src/views/SitesView.vue` 的 `<style scoped>` 末尾追加：

```css
.site-fav-btn {
  background: none; border: none; cursor: pointer;
  font-size: 15px; line-height: 1; padding: 0 2px;
  color: var(--text-tertiary); flex-shrink: 0;
}
.site-fav-btn.active { color: #f5a623; }
.collapse-healthy-toggle {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--text-secondary); cursor: pointer;
  user-select: none;
}
.collapse-healthy-toggle.active { color: var(--accent); }
.site-card-collapsed-hint {
  font-size: 12px; color: var(--text-tertiary); padding: 8px 0;
}
```

- [ ] **Step 9: 运行测试，确认通过**

Run: `cd frontend && bun run test:e2e -- sites-favorite-collapse`
Expected: PASS

- [ ] **Step 10: 构建**

Run: `cd frontend && bun run build`
Expected: 构建成功。

- [ ] **Step 11: 提交**

```bash
git add frontend/src/views/SitesView.vue frontend/tests
git commit -m "feat(sites): 站点列表收藏置顶 + 折叠健康站点 (#<issue>)"
```

---

## 后续 PR（待本计划落地后另写细化计划）

**后续 PR ①：模型库砍"我的模型"中间层**
- 先调研：`/api/pricing/models`（ModelSelector 数据源）是否消费 `/api/pricing/models-config`（自定义模型/价格覆盖）。读 `app/server.py:2393-2434` 与 `app/pricing.py`、`app/builtin_models.py`。
- 若不消费 → 安全删除 `ModelsView` 的"我的模型"tab，仅留"模型库"参考字典（自定义模型管理若有价值则并入库 tab）。
- 若消费 → 需保留自定义模型的录入路径，仅重命名/收敛 UI，不删数据通道。

**后续 PR ②：概览全局任务"只读+轻操作"总览 + 移除顶栏「定时任务」**
- 把 `TasksView` 的任务列表（只读 + 暂停/立即执行/去编辑轻操作）嵌入 `DashboardView` 一个区块，默认按站点折叠或只显示异常任务。
- 移除 `App.vue:93` 顶栏 `{ name: '定时任务', path: '/tasks' }`；`/tasks` 路由保留为只读或重定向到概览锚点。
- 需读 `frontend/src/views/DashboardView.vue`、`frontend/src/views/TasksView.vue` 后再细化。

---

## Self-Review（已自检）

- **Spec 覆盖**：本计划对应 spec §3「删 /config」与 §4.1「站点收藏置顶 + 健康折叠」。spec §3「移顶栏定时任务」「模型库砍中间层」明确移交后续 PR ①②，无遗漏（已在文档标注移交原因）。
- **占位扫描**：无 TBD；测试代码、改动代码均为可执行内容；`testDir`/登录 fixture 以"运行命令确认"形式给出精确命令，非占位。
- **类型/命名一致**：`favorites`/`isFavorite`/`toggleFavorite`/`collapseHealthy`/`isCollapsed`、CSS 类 `.site-fav-btn`/`.collapse-healthy-toggle`/`.site-card-collapsed-hint` 在测试与实现中一致；站点标识统一用 `site.profile.name`。
