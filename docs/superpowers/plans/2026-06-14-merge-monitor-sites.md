# 合并监控总览与站点管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「监控总览」(MonitorView/`/monitor`) 与「站点管理」(SitesView/`/sites`) 合并为单一页面「站点监控」，以 SitesView 为底座、删除 MonitorView，消除重复。

**Architecture:** 以 SitesView 为底座（已含大表格 / 搜索 / 筛选 / 新建 / 真实测试），嫁接 MonitorView 独有的「告警卡区 + 告警中 pill + 跑批状态折叠」；`/monitor`、`/tasks`、`/` 全部重定向到 `/sites`；导航两个 tab 合并为单 tab。不引入共享缓存（合并后无跨页重复拉取）。

**Tech Stack:** Vue 3 `<script setup>`、vue-router 4、Pinia、Vitest + @vue/test-utils（jsdom）。前端用 **bun** 不用 npm。

参考设计文档：`docs/superpowers/specs/2026-06-14-merge-monitor-sites-design.md`

---

## File Structure

- `frontend/src/router.js` — 修改：`/` `/monitor` `/tasks` → 重定向 `/sites`；删除 `/monitor` 指向 MonitorView 的记录。
- `frontend/src/App.vue` — 修改：导航 tabs 两合一为「站点监控」；登录跳转 `/monitor`→`/sites`。
- `frontend/src/views/SitesView.vue` — 修改：loadData 增拉 alerts/schedules；模板加告警卡区、健康条「告警中」pill、跑批折叠；补 `siteOf` 与样式。
- `frontend/src/views/MonitorView.vue` — **删除**。
- `frontend/src/views/TasksView.vue` — 修改：顶部陈旧注释 `/tasks 已重定向到 /monitor` → `/sites`。
- `frontend/src/router.test.js` — 新建：路由重定向单测。
- `frontend/src/views/__tests__/SitesView.test.js` — 新建：合并页告警卡 + 跑批折叠单测。

> 已在分支 `feat/issue-81-merge-monitor-sites` 上。所有 `bun`/`git` 命令在仓库根目录执行。

---

### Task 1: 路由重定向

**Files:**
- Create: `frontend/src/router.test.js`
- Modify: `frontend/src/router.js:5-26`

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/router.test.js`：

```js
import { describe, it, expect } from 'vitest';
import router from './router';

describe('router 重定向', () => {
  it('/ 解析到 /sites', () => {
    expect(router.resolve('/').path).toBe('/sites');
  });
  it('/monitor 解析到 /sites', () => {
    expect(router.resolve('/monitor').path).toBe('/sites');
  });
  it('/tasks 解析到 /sites', () => {
    expect(router.resolve('/tasks').path).toBe('/sites');
  });
  it('/sites 命中 SitesView 路由', () => {
    expect(router.resolve('/sites').name).toBe('sites');
  });
  it('/sites/:id 详情路由保留', () => {
    expect(router.resolve('/sites/abc').name).toBe('site-detail');
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && bun run vitest run src/router.test.js`
Expected: FAIL — `/` 当前解析到 `/monitor`（现状 `{ path: '/', redirect: '/monitor' }`），且 `/monitor` 命中 MonitorView 而非重定向。

- [ ] **Step 3: 改 router.js**

把 `frontend/src/router.js` 的 `routes` 数组前段（第 6-11 行）改为：

```js
    { path: '/', redirect: '/sites' },
    { path: '/sites', name: 'sites', component: () => import('./views/SitesView.vue') },
    { path: '/sites/:id', name: 'site-detail', component: () => import('./views/SiteDetailView.vue'), props: true },
    { path: '/monitor', redirect: '/sites' },
    { path: '/history', name: 'history', component: () => import('./views/HistoryView.vue') },
    { path: '/tasks', redirect: '/sites' },
```

（其余 settings / `/config` redirect `/sites` / `/auth` / 通配符保持不变。注意：原 `/monitor` 指向 `MonitorView.vue` 的那条记录被替换为 redirect，不再 import MonitorView。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && bun run vitest run src/router.test.js`
Expected: PASS（5 个用例全绿）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/router.js frontend/src/router.test.js
git commit -m "feat(frontend): 路由 / /monitor /tasks 统一重定向到 /sites (#81)"
```

---

### Task 2: 把告警卡 + 跑批折叠 + 告警中 pill 并入 SitesView

**Files:**
- Create: `frontend/src/views/__tests__/SitesView.test.js`
- Modify: `frontend/src/views/SitesView.vue`（模板 1-114、脚本 116-354、样式 414-423）

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/views/__tests__/SitesView.test.js`：

```js
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { setActivePinia, createPinia } from 'pinia';

vi.mock('../../api', () => ({
  api: vi.fn(),
  getSitesSummary: vi.fn(() => Promise.resolve({ summary: [
    { profile: { name: 'siteX', base_url: 'https://x', models: ['gpt-4'] }, health: 'healthy', last_test_at: '20260614_100000' },
  ] })),
  getCellAvailability: vi.fn(() => Promise.resolve({ cells: [] })),
  getActiveAlerts: vi.fn(() => Promise.resolve({ alerts: [
    { profile: 'siteX', model: 'gpt-4', streak: 3, task_count: 1, tasks: [{ id: 1, name: '巡检A' }] },
  ] })),
  getSchedules: vi.fn(() => Promise.resolve({ schedules: [
    { id: 9, name: '每日巡检', profile_ids: ['siteX'], status: 'idle' },
  ] })),
}));

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ path: '/sites' }),
}));

vi.mock('../../composables/useToast', () => ({ toast: vi.fn() }));

const routerLinkStub = { props: ['to'], template: '<a><slot /></a>' };

import SitesView from '../SitesView.vue';

function mountView() {
  return mount(SitesView, {
    global: {
      stubs: {
        'router-link': routerLinkStub,
        SiteHealthBoard: true,
        ModalOverlay: true,
        ModelSelector: true,
      },
    },
  });
}

describe('SitesView 合并页', () => {
  beforeEach(() => { setActivePinia(createPinia()); });

  it('有告警时渲染告警卡', async () => {
    const w = mountView();
    await flushPromises();
    expect(w.text()).toContain('siteX × gpt-4');
    expect(w.text()).toContain('连续 3 轮');
  });

  it('健康条显示「告警中」计数', async () => {
    const w = mountView();
    await flushPromises();
    expect(w.text()).toContain('告警中 1');
  });

  it('跑批状态折叠渲染调度', async () => {
    const w = mountView();
    await flushPromises();
    expect(w.text()).toContain('监控任务跑批状态（1）');
    expect(w.text()).toContain('每日巡检');
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && bun run vitest run src/views/__tests__/SitesView.test.js`
Expected: FAIL — 当前 SitesView 不拉 alerts/schedules，模板无告警卡/折叠，`告警中` 文案也不存在（现为「异常」）。

- [ ] **Step 3: 改脚本 —— import 与状态**

在 `frontend/src/views/SitesView.vue` 脚本里：

把第 120 行 import 改为（追加 `getActiveAlerts, getSchedules`）：

```js
import { api, getSitesSummary, getCellAvailability, getActiveAlerts, getSchedules } from '../api';
```

在第 139 行 `const availabilityLut = ref({});` 之后追加两个状态：

```js
const alerts = ref([]);
const schedules = ref([]);
function siteOf(s) { return (s.profile_ids && s.profile_ids[0]) || '-'; }
```

- [ ] **Step 4: 改脚本 —— loadData 并发拉 4 个接口**

把第 329-342 行的 `loadData` 整体替换为：

```js
async function loadData() {
  loading.value = true;
  try {
    const [summaryData, availData, alertData, schedData] = await Promise.all([
      getSitesSummary({ hours: timeRangeStore.hours }),
      getCellAvailability({ hours: timeRangeStore.hours, buckets: BUCKETS }).catch(() => ({ cells: [] })),
      getActiveAlerts().catch(() => ({ alerts: [] })),
      getSchedules().catch(() => ({ schedules: [] })),
    ]);
    sites.value = summaryData.summary || [];
    availabilityLut.value = buildAvailabilityLookup(availData.cells || []);
    alerts.value = alertData.alerts || [];
    schedules.value = schedData.schedules || [];
  } catch (e) {
    toast('加载站点数据失败: ' + e.message, 'error');
  }
  loading.value = false;
}
```

- [ ] **Step 5: 改模板 —— 告警卡区（工具栏之后）**

在工具栏 `</div>` 结束（第 21 行 `</div>` 之后、第 23 行 Loading 之前）插入：

```html
    <!-- 告警卡区（连续 2 轮才翻红；无告警不显示） -->
    <div v-if="alerts.length" class="alert-area">
      <div v-for="a in alerts" :key="a.profile + '/' + a.model" class="alert-card">
        <span class="dot d-error"></span>
        <strong>{{ a.profile }} × {{ a.model }}</strong>
        <span class="alert-meta">连续 {{ a.streak }} 轮 · {{ a.task_count > 1 ? ('所属 ' + a.task_count + ' 个任务') : ((a.tasks[0] && a.tasks[0].name) || '未命名任务') }}</span>
        <router-link class="btn btn-sm" :to="`/sites/${encodeURIComponent(a.profile)}`">进站点 →</router-link>
      </div>
    </div>
```

- [ ] **Step 6: 改模板 —— 健康条「异常」pill 换成「告警中」**

把第 36 行：

```html
        <span class="hb-pill err"><span class="dot d-error"></span>异常 {{ healthCounts.error }}</span>
```

改为：

```html
        <span class="hb-pill err"><span class="dot d-error"></span>告警中 {{ alerts.length }}</span>
```

（保留 `healthCounts` computed 不动——它仍含 `error`，供筛选 chip「异常」按 `s.health === 'error'` 过滤使用。只是健康条不再渲染 error 计数。）

- [ ] **Step 7: 改模板 —— 跑批状态折叠（board-wrap 之后）**

在主区结束 `</section>` 之前（即第 113 行 `</section>` 前、Modal 之外的位置不行——Modal 在 section 内）插入到第 50 行 `</div>`（board-wrap 结束）之后、第 52 行 Create Modal 之前：

```html
    <details class="tasks-fold">
      <summary>监控任务跑批状态（{{ schedules.length }}）</summary>
      <table class="board"><tbody>
        <tr v-for="s in schedules" :key="s.id">
          <td>{{ s.name }}</td><td>{{ siteOf(s) }}</td><td>{{ s.status }}</td>
        </tr>
      </tbody></table>
    </details>
```

- [ ] **Step 8: 改样式 —— 追加告警卡与折叠样式**

在 scoped `<style>` 内（第 422 行 `.dot.d-untested...` 之后）追加：

```css
.alert-area { display:flex; flex-direction:column; gap:8px; margin:14px 0; }
.alert-card { display:flex; align-items:center; gap:10px; padding:10px 14px; border:1px solid #f3c2c2; background:#fef6f6; border-radius:8px; }
.alert-meta { color:var(--text-tertiary); font-size:12px; }
.alert-card .btn { margin-left:auto; }
.tasks-fold { margin-top:18px; }
.tasks-fold summary { cursor:pointer; font-size:13px; color:var(--text-secondary); }
```

- [ ] **Step 9: 跑测试确认通过**

Run: `cd frontend && bun run vitest run src/views/__tests__/SitesView.test.js`
Expected: PASS（3 个用例全绿）

- [ ] **Step 10: 提交**

```bash
git add frontend/src/views/SitesView.vue frontend/src/views/__tests__/SitesView.test.js
git commit -m "feat(frontend): 站点管理页并入告警卡+跑批折叠+告警中计数 (#81)"
```

---

### Task 3: 导航 tabs 两合一 + 登录跳转

**Files:**
- Modify: `frontend/src/App.vue:84-88`（tabs）、`frontend/src/App.vue:128`（登录跳转）

> 此任务为配置式改动，无独立单测，靠 Task 5 的整体 vitest + build 兜底。

- [ ] **Step 1: 改 tabs 数组**

把 `frontend/src/App.vue` 第 84-88 行：

```js
const tabs = [
  { name: '监控总览', path: '/monitor', activeMatch: (p) => p === '/' || p.startsWith('/monitor') },
  { name: '站点管理', path: '/sites', activeMatch: (p) => p.startsWith('/sites') },
  { name: '历史与对比', path: '/history' },
];
```

改为：

```js
const tabs = [
  { name: '站点监控', path: '/sites', activeMatch: (p) => p === '/' || p.startsWith('/sites') || p.startsWith('/monitor') },
  { name: '历史与对比', path: '/history' },
];
```

- [ ] **Step 2: 改登录跳转**

把第 128 行 `router.push('/monitor');` 改为：

```js
      router.push('/sites');
```

- [ ] **Step 3: 构建确认无误**

Run: `cd frontend && bun run build`
Expected: 构建成功，无报错。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/App.vue
git commit -m "feat(frontend): 导航合并为单 tab 站点监控 + 登录跳 /sites (#81)"
```

---

### Task 4: 删除 MonitorView + 清理陈旧注释

**Files:**
- Delete: `frontend/src/views/MonitorView.vue`
- Modify: `frontend/src/views/TasksView.vue:1`（注释）

- [ ] **Step 1: 确认无残留引用**

Run: `grep -rn "MonitorView\|name: 'monitor'\|/monitor" frontend/src`
Expected: 仅剩 `router.js` 里 `/monitor` 的 redirect 与 `App.vue` 的 `startsWith('/monitor')`；**不应再有任何 `import MonitorView` 或 `name: 'monitor'` 路由**。若出现其它引用，先处理再继续。

- [ ] **Step 2: 删除 MonitorView.vue**

```bash
git rm frontend/src/views/MonitorView.vue
```

- [ ] **Step 3: 更新 TasksView 陈旧注释**

打开 `frontend/src/views/TasksView.vue` 第 1 行，把注释里的 `/tasks 已重定向到 /monitor` 改为 `/tasks 已重定向到 /sites`（仅改注释文字，逻辑不动）。

- [ ] **Step 4: 构建确认**

Run: `cd frontend && bun run build`
Expected: 构建成功（删除 MonitorView 后无断链）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/TasksView.vue
git commit -m "refactor(frontend): 删除 MonitorView，合并完成 (#81)"
```

---

### Task 5: 全量验证

**Files:** 无（仅运行）

- [ ] **Step 1: 跑全部前端单测**

Run: `cd frontend && bun run vitest run`
Expected: 新增的 router + SitesView 用例通过；既有 SiteHealthBoard / siteMetrics / trendAggregator / timeRange 用例不回归。

- [ ] **Step 2: 构建**

Run: `cd frontend && bun run build`
Expected: 成功。

- [ ] **Step 3: 人工核对（非阻塞，记录结果）**

确认：导航只剩「站点监控」+「历史与对比」（+设置齿轮）；访问 `/monitor`、`/tasks` 落到 `/sites` 页面正常；合并页同时有告警卡（有告警时）、全量大表格、搜索/筛选/新建/测试、跑批折叠。

> 注：根目录 `pytest` 里 4 个 tab_refactor 前端测试为 pre-existing 失败（ProfileView.vue 已移除），与本次无关，可忽略。

---

## Self-Review

**Spec coverage：**
- 路由重定向（`/` `/monitor` `/tasks`→`/sites`，`/sites/:id` 保留）→ Task 1 ✓
- 导航单 tab「站点监控」→ Task 3 ✓
- 告警卡 + 告警中 pill + 跑批折叠并入 → Task 2 ✓
- loadData 并发 4 接口、不加缓存 → Task 2 Step 4 ✓
- healthCounts 保留 error 供 chip → Task 2 Step 6 备注 ✓
- watch 沿用 `route.path === '/sites'`（SitesView 现状不动，未改 watch）✓
- App.vue:128 登录跳转 → Task 3 Step 2 ✓
- 删 MonitorView + TasksView 注释 → Task 4 ✓
- vitest + build → Task 5 ✓
- 行为（test/create/收藏/筛选）沿用 SitesView 现有实现，不改动 → 无需任务 ✓

**Placeholder scan：** 无 TBD/TODO，所有代码步骤含完整代码。

**Type/命名一致性：** alert 字段（profile/model/streak/task_count/tasks[].name）在测试 mock 与模板中一致；schedule 字段（id/name/profile_ids/status）一致；`siteOf` 定义与使用一致；`getActiveAlerts`/`getSchedules` 在 import、mock、loadData 三处命名一致。
