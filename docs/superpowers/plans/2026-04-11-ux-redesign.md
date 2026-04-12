# AITokenPerf UX 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 AITokenPerf 从「测试页+配置页+历史页」重构为以「目标站点」为核心的 4 Tab 导航结构（概览 / 目标站点 / 历史与对比 / 定时任务）

**Architecture:** 前端 Vue 3 + Pinia + Vue Router，后端 FastAPI + SQLAlchemy。核心思路是 Profile 升级为「目标站点」，测试/定时任务/历史趋势都围绕站点组织。后端已有大部分 API，需新增站点级聚合接口。

**Tech Stack:** Vue 3.5, Vue Router 4, Pinia, Chart.js 4.5, Vite, FastAPI, SQLAlchemy, aiosqlite

---

## Phase 1：页面结构重组

### Task 1.1：新增后端站点聚合 API

**Files:**
- Modify: `app/db.py` — 新增聚合查询函数
- Modify: `app/server.py` — 新增 API 路由

- [ ] **Step 1: 在 db.py 新增 `get_sites_summary` 函数**

在 `app/db.py` 末尾添加函数，查询每个 profile 的最新测试摘要：

```python
async def get_sites_summary(user_id: int):
    """获取用户所有站点的最新测试摘要"""
    profiles = await get_profiles(user_id)
    results = await get_results(user_id, limit=500)
    
    # 按 profile base_url 分组，聚合最新结果
    summary = {}
    for p in profiles:
        key = p["name"]
        summary[key] = {
            "profile": p,
            "latest_results": [],
            "health": "unknown",
            "last_test_at": None,
        }
    
    for r in results:
        config = r.get("config", {})
        profile_name = config.get("_profile_name", "")
        if profile_name in summary:
            summary[profile_name]["latest_results"].append(r)
    
    # 计算健康状态
    for key, val in summary.items():
        latest = val["latest_results"][:5]  # 最近 5 次
        if not latest:
            val["health"] = "untested"
            continue
        
        val["last_test_at"] = latest[0].get("timestamp", "")
        success_rates = []
        for r in latest:
            s = r.get("summary", {})
            if s.get("total_requests", 0) > 0:
                success_rates.append(s["successful_requests"] / s["total_requests"])
        
        avg_rate = sum(success_rates) / len(success_rates) if success_rates else 0
        val["health"] = "healthy" if avg_rate >= 0.95 else "error"
    
    return list(summary.values())
```

- [ ] **Step 2: 在 server.py 新增 `/api/sites/summary` 路由**

```python
@app.get("/api/sites/summary")
async def sites_summary(request):
    user_id = require_auth(request)
    summary = await get_sites_summary(user_id)
    return json_response(summary)
```

- [ ] **Step 3: 手动测试 API**

启动服务后用 curl 验证：
```bash
curl -H "Authorization: Bearer <token>" http://localhost:8080/api/sites/summary
```

- [ ] **Step 4: Commit**

```bash
git add app/db.py app/server.py
git commit -m "feat: 新增站点聚合摘要 API /api/sites/summary"
```

---

### Task 1.2：新增前端 API 函数

**Files:**
- Modify: `frontend/src/api/index.js` — 新增站点相关 API

- [ ] **Step 1: 在 api/index.js 新增站点 API**

```javascript
// 站点聚合
export const getSitesSummary = () => get('/sites/summary')

// 站点详情（复用现有 profile API）
// getProfiles() 已存在
// getResult(filename) 已存在
// getResults(params) 已存在
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/index.js
git commit -m "feat: 前端新增 getSitesSummary API"
```

---

### Task 1.3：更新路由配置

**Files:**
- Modify: `frontend/src/router.js` — 新路由结构

- [ ] **Step 1: 更新路由**

将 `frontend/src/router.js` 完整重写为：

```javascript
import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('../views/DashboardView.vue') },
  { path: '/sites', name: 'sites', component: () => import('../views/SitesView.vue') },
  { path: '/sites/:id', name: 'site-detail', component: () => import('../views/SiteDetailView.vue'), props: true },
  { path: '/history', name: 'history', component: () => import('../views/HistoryView.vue') },
  { path: '/tasks', name: 'tasks', component: () => import('../views/TasksView.vue') },
  { path: '/settings', name: 'settings', component: () => import('../views/SettingsView.vue') },
  { path: '/auth', name: 'auth', component: () => import('../views/AuthView.vue') },
  { path: '/admin-users', name: 'admin-users', component: () => import('../views/AdminUsersView.vue') },
  { path: '/models', name: 'models', component: () => import('../views/ModelsView.vue') },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/router.js
git commit -m "feat: 新路由结构 — 概览/目标站点/历史与对比/定时任务"
```

---

### Task 1.4：更新 App.vue 导航

**Files:**
- Modify: `frontend/src/App.vue` — 更新 Tab 栏和用户菜单

- [ ] **Step 1: 更新 App.vue 的 Tab 导航**

将现有 Tab 栏从 `总览/测试/历史记录/配置` 改为 `概览/目标站点/历史与对比/定时任务`。

关键修改点：
- `tabs` 数组改为：
```javascript
const tabs = [
  { name: '概览', path: '/' },
  { name: '目标站点', path: '/sites' },
  { name: '历史与对比', path: '/history' },
  { name: '定时任务', path: '/tasks' },
]
```
- 移除模型管理从导航 Tab，改为仅在用户下拉菜单中显示（仅管理员）
- 保留现有用户下拉菜单结构，确保 `模型管理` 链接指向 `/models`

- [ ] **Step 2: 验证导航和路由跳转正常**

启动前端 dev server，点击每个 Tab 确认路由正确。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.vue
git commit -m "feat: 导航栏改为概览/目标站点/历史与对比/定时任务"
```

---

### Task 1.5：创建目标站点页基础版

**Files:**
- Create: `frontend/src/views/SitesView.vue` — 目标站点列表页

- [ ] **Step 1: 创建 SitesView.vue 基础框架**

创建 `frontend/src/views/SitesView.vue`，功能包括：
- 顶部：站点计数 + 搜索框 + 状态筛选 pills（全部/健康/异常/未测试）+ 新建站点按钮
- 双列卡片网格，每张卡片显示：
  - 健康灯 + 站点名 + base_url + 状态标签 + 上次测试时间
  - 按模型拆分的指标表（每模型一行：模型名 / TTFT / TPOT / Token·s⁻¹ / 成功率）
  - 错误类型分布标签（如有）
  - 底部：「一键测试」按钮 + 「详情 →」按钮（跳转 `/sites/:id`）
- 调用 `getSitesSummary()` API 获取数据
- 调用 `getProfiles()` 作为数据源（profile name 作为站点 ID）
- 数据刷新按钮

模板结构参考：
```html
<template>
  <div class="main">
    <!-- 顶部操作栏 -->
    <div class="history-toolbar">
      <div style="display:flex;align-items:center;gap:12px">
        <span style="font-size:15px;font-weight:600;color:#666">全部站点</span>
        <span style="font-size:12px;color:#999">共 {{ sites.length }} 个</span>
        <div class="filter-chips">
          <button v-for="f in filters" ...>{{ f.label }}</button>
        </div>
      </div>
      <div style="display:flex;gap:8px">
        <input class="form-input" placeholder="搜索站点..." v-model="search">
        <button class="btn btn-primary btn-sm" @click="showCreate = true">+ 新建站点</button>
      </div>
    </div>

    <!-- 双列卡片网格 -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
      <div v-for="site in filteredSites" :key="site.profile.name" class="card" :class="cardClass(site)">
        <!-- 卡片头部：健康灯 + 站点名 + URL + 状态 -->
        <!-- 模型指标表 -->
        <!-- 错误标签 -->
        <!-- 底部操作 -->
      </div>
    </div>

    <!-- 新建站点弹窗（复用现有 Profile 创建逻辑） -->
  </div>
</template>
```

- [ ] **Step 2: 验证站点列表页渲染正常**

确保从 API 拿到数据后卡片正确渲染，筛选和搜索功能正常。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/SitesView.vue
git commit -m "feat: 新增目标站点页 — 双列卡片列表 + 搜索筛选"
```

---

### Task 1.6：创建站点详情页框架（4 Tab）

**Files:**
- Create: `frontend/src/views/SiteDetailView.vue` — 站点详情页

- [ ] **Step 1: 创建 SiteDetailView.vue 框架**

创建 `frontend/src/views/SiteDetailView.vue`，包含：
- 面包屑导航：`← 目标站点 / 站点名`
- 4 个内部 Tab：测试 / 定时任务 / 历史趋势 / 配置
- 通过路由 props `id` 获取 profile name
- 调用 `getProfiles()` 获取当前站点配置
- 配置 Tab（Phase 1 先实现这个）：迁移现有 ProfileView 的编辑功能
  - 站点名称 / Base URL / API Key（密码显示）/ 绑定模型 / Provider / Protocol
  - 保存配置 / 连通性测试 / 删除站点
- 其他 3 个 Tab 显示「开发中」占位

```html
<template>
  <div class="main">
    <!-- 面包屑 -->
    <div style="margin-bottom:12px">
      <router-link to="/sites" style="font-size:12px;color:var(--accent)">← 目标站点</router-link>
      <span style="margin:0 8px;color:#ddd">/</span>
      <span style="font-size:15px;font-weight:700">{{ profile?.name }}</span>
      <span style="margin-left:8px" :class="healthBadge">...</span>
    </div>

    <!-- 内部 Tab 栏 -->
    <div class="tab-bar" style="position:static;padding:0;margin-bottom:20px">
      <button v-for="tab in tabs" :key="tab.key"
        class="tab-btn" :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key">{{ tab.label }}</button>
    </div>

    <!-- Tab 内容 -->
    <div v-if="activeTab === 'test'">测试 Tab（Phase 2 实现）</div>
    <div v-if="activeTab === 'schedules'">定时任务 Tab（Phase 3 实现）</div>
    <div v-if="activeTab === 'trends'">历史趋势 Tab（Phase 4 实现）</div>
    <ConfigTab v-if="activeTab === 'config' && profile" :profile="profile" @saved="loadProfile" />
  </div>
</template>
```

- [ ] **Step 2: 抽取 SiteConfigTab 子组件**

创建 `frontend/src/components/SiteConfigTab.vue`，从现有 `ProfileView.vue` 提取配置编辑表单逻辑：
- 复用 ProfileView 中的表单字段（base_url, api_key, models, provider 等）
- 复用保存/删除/连通性测试 API 调用
- 删除站点后跳转回 `/sites`

- [ ] **Step 3: 验证站点详情页和配置编辑功能**

- 点击站点卡片「详情 →」跳转到 `/sites/:id`
- 配置 Tab 可以编辑和保存
- 连通性测试正常工作
- 删除站点后跳回列表

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/SiteDetailView.vue frontend/src/components/SiteConfigTab.vue
git commit -m "feat: 新增站点详情页框架（4 Tab）+ 配置编辑功能"
```

---

### Task 1.7：清理旧路由和冗余代码

**Files:**
- Modify: `frontend/src/App.vue` — 移除旧的 `/config` 和 `/bench` Tab 引用
- No delete: 保留 `ProfileView.vue` 和 `TestView.vue` 暂不删除（Phase 2 迁移完再删）

- [ ] **Step 1: 确认所有旧入口已移除**

- App.vue 的 Tab 栏不再有「测试」和「配置」
- 确认无其他地方引用 `/config` 或 `/bench` 路由

- [ ] **Step 2: 验证全站功能正常**

- 概览页可访问
- 目标站点页列表正常
- 站点详情页配置 Tab 可编辑保存
- 历史与对比页可访问（现有 HistoryView 暂不改）
- 定时任务页占位（Phase 3 实现）
- 用户菜单中模型管理可跳转

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor: Phase 1 完成 — 新导航结构上线，旧测试页/配置页路由移除"
```

---

## Phase 2：测试功能迁移

### Task 2.1：实现站点详情「测试 Tab」

**Files:**
- Modify: `frontend/src/views/SiteDetailView.vue` — 激活测试 Tab
- Create: `frontend/src/components/SiteTestTab.vue` — 测试功能组件

- [ ] **Step 1: 从 TestView.vue 提取测试逻辑到 SiteTestTab.vue**

核心逻辑迁移：
- 模型选择：combobox（复用现有模型列表 API `getModels()` + `getModelsConfig()`）
- 模式选择：Burst / Sustained 二选一 pill
- 并发级别：预设值 pill + 自定义
- 高级参数折叠行：请求数 / 超时 / Max Tokens / 提示词
- 开始测试 / Dry Run 按钮
- SSE 实时进度（复用 `useBenchSSE.js`）

关键区别：不需要再选 Profile（已经在站点详情里了），profile 配置自动注入到测试请求中。

- [ ] **Step 2: 实现测试结果区**

两列模型卡片布局：
- 上层：4 个核心指标大字（TTFT P50 / TPOT P50 / Token·s⁻¹ / 成功率）
- 下层：补充指标紧凑横排（TTFT P95/P99 / TPOT P99 / E2E / Output Tokens / 错误信息）
- 「详情 →」展开完整百分位表（复用现有 `resultDetail.js`）

- [ ] **Step 3: 验证测试全流程**

- 选模型 → 选参数 → 开始测试 → SSE 实时进度 → 结果展示
- Dry Run 正常
- 多模型并行测试正常

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/SiteDetailView.vue frontend/src/components/SiteTestTab.vue
git commit -m "feat: 站点详情「测试 Tab」— combobox 选模型 + 两列结果卡片"
```

---

### Task 2.2：目标站点页「一键测试」

**Files:**
- Modify: `frontend/src/views/SitesView.vue` — 一键测试按钮逻辑

- [ ] **Step 1: 实现卡片上的「一键测试」**

点击后用站点的默认配置（并发 10 / Burst / 模型选第一个）直接发起测试，结果通过 toast 提示，完成后卡片指标自动刷新。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/SitesView.vue
git commit -m "feat: 目标站点卡片「一键测试」功能"
```

---

## Phase 3：定时任务

### Task 3.1：站点详情「定时任务 Tab」

**Files:**
- Create: `frontend/src/components/SiteSchedulesTab.vue` — 站点内定时任务管理

- [ ] **Step 1: 实现定时任务列表**

- 调用 `getSchedules()` 获取当前站点的任务（按 profile_ids 过滤）
- 表格展示：任务名 / 状态 / 频率 / 模型 / 并发 / 上次结果 / 下次执行 / 操作
- 操作：暂停/恢复/立即执行/编辑/删除（复用现有 API）

- [ ] **Step 2: 实现新建任务表单**

- 只需填 3 项：任务名称 / 频率（下拉 + 自定义 Cron） / 模型
- 参数继承提示：「并发、模式、超时等参数继承自站点测试配置」

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SiteSchedulesTab.vue
git commit -m "feat: 站点详情「定时任务 Tab」— 任务管理 + 极简新建"
```

---

### Task 3.2：定时任务全局页

**Files:**
- Create: `frontend/src/views/TasksView.vue` — 全局定时任务管理页

- [ ] **Step 1: 实现 TasksView.vue**

- 筛选 pills：全部 / 运行中 / 已暂停 / 异常
- 全量任务表格（跨所有站点）：站点名（可点击跳转 `/sites/:id`） / 任务名 / 状态 / 频率 / 模型 / 并发 / 上次结果 / 下次执行 / 操作
- 调用 `getSchedules()` + `getSitesSummary()` 关联站点信息

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/TasksView.vue
git commit -m "feat: 定时任务全局管理页 /tasks"
```

---

### Task 3.3：顶部运行指示器浮层

**Files:**
- Create: `frontend/src/components/ScheduleIndicator.vue` — 运行指示器
- Modify: `frontend/src/App.vue` — 集成指示器到导航栏

- [ ] **Step 1: 实现 ScheduleIndicator.vue**

- 导航栏右侧小 pill：绿点 + `N 运行中`
- 点击展开浮层：所有运行中任务列表（任务名 / 站点 / 频率 / 最近成功率）
- 异常任务红色高亮
- 底部「查看全部 →」跳转 `/tasks`

- [ ] **Step 2: 集成到 App.vue**

在导航栏右侧、用户头像左边插入 ScheduleIndicator。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ScheduleIndicator.vue frontend/src/App.vue
git commit -m "feat: 顶部定时任务运行指示器 + 浮层"
```

---

## Phase 4：数据可视化增强

### Task 4.1：目标站点卡片增强（趋势迷你图 + 错误分布）

**Files:**
- Modify: `frontend/src/views/SitesView.vue` — 卡片增加趋势图和错误分布
- Modify: `app/server.py` — 新增站点级趋势聚合 API
- Modify: `app/db.py` — 新增趋势聚合查询

- [ ] **Step 1: 后端新增 `/api/sites/:name/trend` API**

返回该站点最近 7 天的按模型分组的分钟级趋势数据（复用 `get_schedule_results_trend` 的逻辑）。

- [ ] **Step 2: 卡片中每个模型行添加 SVG 迷你趋势图**

用 `<svg>` + `<polyline>` 渲染简单的 sparkline，颜色根据趋势方向（上升=绿、下降=红）。

- [ ] **Step 3: 卡片增加错误类型分布**

正常站点：错误标签横排（`429 × 3`）
异常站点：分布条 + 退化警告文字

- [ ] **Step 4: 实现异常溯源跳转**

- 点击错误标签 → 跳转 `/history` 带 query 参数
- 点击退化警告 → 跳转 `/sites/:id` 定位趋势 Tab

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: 站点卡片增强 — 趋势迷你图 + 错误分布 + 异常溯源跳转"
```

---

### Task 4.2：站点详情「历史趋势 Tab」

**Files:**
- Create: `frontend/src/components/SiteTrendsTab.vue` — 趋势图组件

- [ ] **Step 1: 实现趋势 Tab**

- 指标切换 pills：TTFT / TPOT / Token·s⁻¹ / 成功率
- 时间范围：1h / 24h / 7d / 30d
- Chart.js 折线图：按模型分线，异常点标注

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/SiteTrendsTab.vue
git commit -m "feat: 站点详情「历史趋势 Tab」— Chart.js 折线图"
```

---

### Task 4.3：概览页重构

**Files:**
- Modify: `frontend/src/views/DashboardView.vue` — 全面重构

- [ ] **Step 1: 重构 DashboardView**

- 顶部 5 汇总卡片（站点数/活跃任务/今日测试/成功率/覆盖模型）
- 左列：站点状态列表（健康灯 + 最新指标，异常红色高亮，可点击跳转站点详情）
- 右列上：异常告警（退化事件 + 错误标签，可点击溯源）
- 右列下：最近活动时间线（✓/✗ 标记，可点击跳转结果详情）

- [ ] **Step 2: 实现概览页异常溯源跳转**

按 spec 第 9 章「异常溯源跳转矩阵」中的概览页部分实现所有跳转。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/DashboardView.vue
git commit -m "feat: 概览页重构 — 汇总卡片 + 站点状态 + 异常告警 + 溯源跳转"
```

---

## Phase 5：历史与对比增强

### Task 5.1：历史与对比页新布局

**Files:**
- Modify: `frontend/src/views/HistoryView.vue` — 全面重构

- [ ] **Step 1: 重构筛选栏**

- 时间范围 pill 组：24h / 7d / 30d / 全部
- 站点下拉 / 模型下拉 / 来源下拉（定时/手动）

- [ ] **Step 2: 实现多选对比**

- 每行 checkbox
- 选中后顶部出现已选标签栏 + 「对比」按钮
- 对比视图：每列一条记录，行=指标，最优值绿色，差值标百分比

- [ ] **Step 3: 实现异常溯源跳转**

按 spec 第 9 章的历史页部分：异常记录行可点击展开错误明细，「重测」跳转站点测试 Tab。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/HistoryView.vue
git commit -m "feat: 历史与对比页增强 — 多选对比 + 异常溯源 + 新筛选栏"
```

---

### Task 5.2：最终清理

**Files:**
- Delete: `frontend/src/views/ProfileView.vue` — 功能已完全迁移到站点详情
- Delete: `frontend/src/views/TestView.vue` — 功能已完全迁移到站点详情
- Delete: `frontend/src/components/ProfileChips.vue` — 不再需要

- [ ] **Step 1: 确认无引用后删除旧文件**

全局搜索确认无组件引用 ProfileView、TestView、ProfileChips 后删除。

- [ ] **Step 2: 全功能回归测试**

逐一验证所有页面和功能：
- 概览页数据正确、跳转正常
- 目标站点页卡片、搜索、筛选、一键测试
- 站点详情 4 Tab 全部可用
- 定时任务全局页 + 浮层指示器
- 历史与对比页筛选、对比
- 所有异常溯源跳转

- [ ] **Step 3: Final Commit**

```bash
git add -A
git commit -m "refactor: UX 重构完成 — 旧视图清理 + 全功能迁移"
```
