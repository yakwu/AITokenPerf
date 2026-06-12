# 设置 hub · 阶段二 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。Steps use checkbox。

**Goal:** 新增顶栏 **⚙设置** 入口 → 设置 hub（顶部子标签：**告警渠道 / 模型库(admin) / 用户管理(admin) / 个人资料**），把模型库/用户管理从**头像下拉迁出**、告警渠道从 `SettingsView` 内嵌**抽出**为独立子页；头像下拉只留 **个人资料 + 退出登录**。解决设计稿痛点③（配置藏头像里难发现）、痛点⑤（告警渠道埋太深）。

**Architecture:** 纯前端。新增 `SettingsHub.vue`（容器=标题+顶部子标签+`<router-view>`，子页用一致的横向 tab）+ `NotifiersView.vue`（包 `NotifiersManager`）；`/settings` 改为**嵌套路由**，复用现有 `ModelsView`/`AdminUsersView`/`SettingsView`(瘦身后=个人资料) 作子页；`App.vue` 顶栏加 gear、头像瘦身。子标签布局＝顶部横向（与站点详情 tab 一致，用户已选）。

**Tech Stack:** Vue 3 + vue-router + Pinia；构建 `bun run build`，前端用 **bun**。

**工作目录：** `/Users/yakun/linkingrid/AITokenPerf/.claude/worktrees/issue-58-overview-health-board`（分支 `feat/issue-58-overview-health-board`）。

**关联设计：** `docs/superpowers/specs/2026-06-10-overview-health-board-ia-redesign-design.md` §6 / §10 阶段二 / §171（⚙=gear 图标）。

**口径决策（实现者须知）：**
- **模型库 + 用户管理都保持 admin-only**（沿用现状：头像里两者都 `v-if role==='admin'`）。非 admin 的设置 hub 只显示 告警渠道 + 个人资料。
- `/models`、`/admin-users` 旧扁平路由**删除**（仅 e2e + 头像引用，全部一并更新；不留兼容重定向）。
- `SettingsView.vue` 不改名（历史上 `ProfileView.vue` 已移除，避免再撞），瘦身后作为「个人资料」子页内容。

---

## File Structure
- **Create** `frontend/src/views/SettingsHub.vue`：hub 容器（标题 + 顶部子标签 + `<router-view>` + admin 子标签条件显示）。
- **Create** `frontend/src/views/NotifiersView.vue`：薄包装，渲染 `<NotifiersManager />`。
- **Modify** `frontend/src/views/SettingsView.vue`：删「告警器」卡片 + `NotifiersManager` import，瘦身为 个人资料+改密。
- **Modify** `frontend/src/router.js`：`/settings` 改嵌套路由 + 子路由；删 `/models`、`/admin-users` 扁平路由；beforeEach 加 admin 守卫。
- **Modify** `frontend/src/App.vue`：header-right 加 ⚙gear 入口；头像下拉删 用户管理/模型管理，个人资料指向 `/settings/profile`。
- **Modify** `e2e/admin.spec.js`、`e2e/config.spec.js`、`e2e/auth.spec.js`：`goto` 改新 hub URL。

---

## Task 1: 前置拆分 — SettingsView 瘦身 + NotifiersView

**Files:** Modify `frontend/src/views/SettingsView.vue`；Create `frontend/src/views/NotifiersView.vue`

- [ ] **Step 1: 从 SettingsView 删「告警器」卡片** — 删除这一段（约 54–59 行）：
```html
      <div class="card" style="margin-top:20px">
        <div class="card-header">
          <div class="card-title">告警器</div>
        </div>
        <NotifiersManager />
      </div>
```

- [ ] **Step 2: 删 NotifiersManager import** — 删除 `frontend/src/views/SettingsView.vue` 里这一行（约 69 行）：
```js
import NotifiersManager from '../components/NotifiersManager.vue';
```
（删后 SettingsView = 个人资料 + 修改密码两张卡，`<section class="tab-content active">` 根不变。）

- [ ] **Step 3: 新建 NotifiersView** — 创建 `frontend/src/views/NotifiersView.vue`：
```vue
<template>
  <div class="card">
    <div class="card-header">
      <div class="card-title">告警渠道</div>
    </div>
    <NotifiersManager />
  </div>
</template>

<script setup>
import NotifiersManager from '../components/NotifiersManager.vue';
</script>
```

- [ ] **Step 4: 构建** — `cd frontend && bun run build`，必须成功（SettingsView 不再引用 NotifiersManager 也不报未使用错）。

- [ ] **Step 5: 提交**
```bash
git add frontend/src/views/SettingsView.vue frontend/src/views/NotifiersView.vue
git commit -m "refactor(web): 告警渠道从个人资料页抽出为独立 NotifiersView，SettingsView 瘦身 (#58)"
```

---

## Task 2: SettingsHub 容器 + 嵌套路由

**Files:** Create `frontend/src/views/SettingsHub.vue`；Modify `frontend/src/router.js`

- [ ] **Step 1: 新建 SettingsHub.vue** — 创建 `frontend/src/views/SettingsHub.vue`：
```vue
<template>
  <section class="tab-content active">
    <h1 class="settings-hub-title">设置</h1>
    <nav class="settings-subtabs">
      <router-link to="/settings/notifiers" class="settings-subtab">告警渠道</router-link>
      <router-link v-if="isAdmin" to="/settings/models" class="settings-subtab">模型库</router-link>
      <router-link v-if="isAdmin" to="/settings/users" class="settings-subtab">用户管理</router-link>
      <router-link to="/settings/profile" class="settings-subtab">个人资料</router-link>
    </nav>
    <div class="settings-hub-body">
      <router-view />
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue';
import { useAppStore } from '../stores/app';
const store = useAppStore();
const isAdmin = computed(() => store.user?.role === 'admin');
</script>

<style scoped>
.settings-hub-title { font-size: 20px; font-weight: 700; margin: 0 0 16px; }
.settings-subtabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
.settings-subtab {
  padding: 10px 16px; font-size: 13px; font-weight: 600;
  color: var(--text-secondary); text-decoration: none;
  border-bottom: 2px solid transparent; margin-bottom: -1px;
}
.settings-subtab:hover { color: var(--text-primary); }
.settings-subtab.router-link-active { color: var(--accent); border-bottom-color: var(--accent); }
/* 子页（含复用的 ModelsView/AdminUsersView 自带的 .tab-content）不再重复页面内边距 */
.settings-hub-body :deep(.tab-content) { padding: 0; }
</style>
```
> 说明：`router-link-active` 是 vue-router 默认激活类；子标签用它高亮。`:deep(.tab-content){padding:0}` 中和子页自带的页面内边距，避免双重留白（hub 外层 `.tab-content` 已提供页面内边距）。

- [ ] **Step 2: router.js 改嵌套路由** — 把这三行（约 11、12、15）：
```js
    { path: '/settings', name: 'settings', component: () => import('./views/SettingsView.vue') },
    { path: '/models', name: 'models', component: () => import('./views/ModelsView.vue') },
```
和
```js
    { path: '/admin-users', name: 'admin-users', component: () => import('./views/AdminUsersView.vue') },
```
替换为**一个嵌套路由**（放在 `/tasks` 之后、`/config` 之前的位置即可）：
```js
    {
      path: '/settings',
      component: () => import('./views/SettingsHub.vue'),
      children: [
        { path: '', redirect: '/settings/notifiers' },
        { path: 'notifiers', name: 'settings-notifiers', component: () => import('./views/NotifiersView.vue') },
        { path: 'models', name: 'settings-models', component: () => import('./views/ModelsView.vue') },
        { path: 'users', name: 'settings-users', component: () => import('./views/AdminUsersView.vue') },
        { path: 'profile', name: 'settings-profile', component: () => import('./views/SettingsView.vue') },
      ],
    },
```
（确保删掉了旧的 `/models`、`/admin-users` 两行，避免重复 name。）

- [ ] **Step 3: beforeEach 加 admin 守卫** — 把现有 `router.beforeEach((to) => {...})` 改为：
```js
router.beforeEach((to) => {
  if (to.path === '/auth') return;
  const userStr = localStorage.getItem('user');
  if (!userStr) return;
  try {
    const user = JSON.parse(userStr);
    if (user.must_change_password) return '/auth';
    if ((to.path.startsWith('/settings/users') || to.path.startsWith('/settings/models'))
        && user.role !== 'admin') {
      return '/settings/notifiers';
    }
  } catch {}
});
```

- [ ] **Step 4: 构建** — `cd frontend && bun run build`，必须成功（无未解析组件、无重复 route name）。

- [ ] **Step 5: 提交**
```bash
git add frontend/src/views/SettingsHub.vue frontend/src/router.js
git commit -m "feat(web): /settings 改为设置 hub 容器 + 嵌套子路由（告警渠道/模型库/用户管理/个人资料）(#58)"
```

---

## Task 3: 顶栏 ⚙ 入口 + 头像下拉瘦身

**Files:** Modify `frontend/src/App.vue`

- [ ] **Step 1: header-right 加 ⚙gear 入口** — 在 `<div class="user-menu" ...>`（约 15 行）**之前**插入：
```html
        <router-link to="/settings" class="settings-gear" :class="{ active: $route.path.startsWith('/settings') }" title="设置">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.32 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
        </router-link>
```

- [ ] **Step 2: 个人资料 改指向 /settings/profile + 换人像图标** — 把头像下拉里「个人资料」按钮（约 24–27 行）整段替换为：
```html
          <button class="user-dropdown-item" @click="store.switchTab('settings/profile'); userMenuOpen = false">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            个人资料
          </button>
```
（`switchTab('settings/profile')` → `router.push('/settings/profile')`，无需改 store。）

- [ ] **Step 3: 删头像下拉里「用户管理」「模型管理」** — 删除这两段（约 28–35 行）：
```html
          <button class="user-dropdown-item" v-if="store.user?.role === 'admin'" @click="store.switchTab('admin-users'); userMenuOpen = false">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>
            用户管理
          </button>
          <button class="user-dropdown-item" v-if="store.user?.role === 'admin'" @click="store.switchTab('models'); userMenuOpen = false">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
            模型管理
          </button>
```
（删后头像下拉只剩：邮箱/角色 + 个人资料 + 分隔线 + 退出登录。）

- [ ] **Step 4: 加 gear 的 scoped 样式** — 在 `App.vue` 的 `<style scoped>` 里加（若无 scoped 块则在文件末尾新增一个）：
```css
.settings-gear {
  display: inline-flex; align-items: center; justify-content: center;
  width: 34px; height: 34px; border-radius: 8px;
  color: var(--text-secondary); text-decoration: none; transition: background .15s, color .15s;
}
.settings-gear:hover { background: var(--border-subtle); color: var(--text-primary); }
.settings-gear.active { color: var(--accent); background: var(--border-subtle); }
```
> 注：若 `App.vue` 现有样式是非 scoped 的全局块，则把上面规则加进去即可，类名不冲突。

- [ ] **Step 5: 构建 + 残留检查** — `cd frontend && bun run build` 必过；再确认头像里不再有模型/用户管理：
```bash
grep -n "switchTab('models')\|switchTab('admin-users')\|模型管理" frontend/src/App.vue || echo "头像已瘦身 OK"
```

- [ ] **Step 6: 提交**
```bash
git add frontend/src/App.vue
git commit -m "feat(web): 顶栏新增设置入口，模型/用户管理迁入设置 hub，头像下拉瘦身 (#58)"
```

---

## Task 4: e2e URL 更新

**Files:** Modify `e2e/admin.spec.js`、`e2e/config.spec.js`、`e2e/auth.spec.js`

> 旧 `/models`、`/admin-users` 路由已删，e2e 直达 URL 要改到 hub 子路由。读这三个文件，按下表改 `page.goto(...)`；改完检查同测试内的断言：若断言的是页面里仍存在的文本（如表格、"用户管理"/"模型库" 子标签），保持；若断言了已不存在的旧页面标题，则改为断言 hub 子标签可见（如 `await expect(page.locator('.settings-subtab.router-link-active')).toContainText('用户管理')`）。

- [ ] **Step 1: admin.spec.js** — `page.goto('/admin-users')`（约 10 行）改为 `page.goto('/settings/users')`。断言 `text=用户管理` 保持（hub 子标签即含该文本）。

- [ ] **Step 2: config.spec.js** — `page.goto('/models')`（约 15 行）改为 `page.goto('/settings/models')`。读该 test 的断言：若断言了"模型管理"等旧文案而 hub/ModelsView 里实际是"模型库"，改断言为页面可见的真实文本（hub 子标签"模型库"或 ModelsView 内"我的模型/模型库"）。

- [ ] **Step 3: auth.spec.js** — `page.goto('/admin-users')`（约 48 行）改 `/settings/users`；`page.goto('/models')`（约 54 行）改 `/settings/models`。两条「管理员访问 X 页面」断言保持其对可见内容的检查（必要时同上调整为 hub 子标签可见）。

- [ ] **Step 4: 提交**
```bash
git add e2e/admin.spec.js e2e/config.spec.js e2e/auth.spec.js
git commit -m "test(e2e): 模型/用户管理 URL 迁移到设置 hub 子路由 (#58)"
```

---

## Self-Review
- **Spec 覆盖（§6/§10 阶段二）**：⚙设置入口(gear,§171)✓ Task3；hub 子页 告警渠道/模型库/用户管理(admin)/个人资料 ✓ Task1+2；告警渠道从 SettingsView 抽出 ✓ Task1；模型/用户从头像迁出、头像只留个人资料+退出 ✓ Task3；`/settings` 改 hub+子路由 ✓ Task2。阶段三（定时任务/告警就地建）不在本计划。
- **断链检查**：旧 `/models`、`/admin-users` 引用＝router(删)+头像(删)+e2e(改) 全覆盖；`switchTab('models'/'admin-users')` 删除；`switchTab('settings/profile')` 经 `router.push('/'+t)` 命中嵌套路由 `/settings/profile`✓。`NotifiersManager` 仍被 `NotifiersView` 引用（不悬空）。
- **admin 守卫**：模型库/用户管理 子标签 `v-if isAdmin` 隐藏 + beforeEach 路由守卫双保险，保持现状 admin-only 行为。
- **占位符**：Task1–3 全给精确增删代码；Task4 给出确切 URL 替换 + 断言调整规则（e2e 原断言需读文件，已说明判断标准）。
- **样式**：`:deep(.tab-content){padding:0}` 中和复用子页双内边距；gear 激活态 `$route.path.startsWith('/settings')`。
- **测试门槛**：每个前端 Task 以 `bun run build` 通过为准；视觉确认（gear 可达、四子页切换、头像瘦身、非 admin 只见两子页）需人工浏览器；e2e 不在 pre-push。
