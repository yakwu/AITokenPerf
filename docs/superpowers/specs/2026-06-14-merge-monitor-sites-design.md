# 合并「监控总览」与「站点管理」为单一页面

- 日期：2026-06-14
- Issue：#81（Related #76）
- 状态：已批准设计，待写实现计划

## 问题

`监控总览`(/monitor) 与 `站点管理`(/sites) 两个页面内容高度重复：

- 两者主体都是同一个 `SiteHealthBoard` 组件（站点 × 模型健康大表格），数据源也相同
  （都调 `getSitesSummary` + `getCellAvailability`），所以打开后视觉几乎一样。
- 二者无共享缓存，在两页间来回切换 / 改时间范围会重复拉取完全相同的接口，属无谓负载。

差异仅在外围：

| | 监控总览 /monitor | 站点管理 /sites |
| --- | --- | --- |
| 定位 | 看（只读） | 管（增删改查） |
| 大表格 | 同一个 | 同一个 |
| 独有 | 顶部告警卡 + 底部跑批状态折叠 | 搜索/筛选、新建站点、直接发起测试 |
| 点「测试」 | 仅提示「去站点详情」 | 真实发起测试 |

这是 #76「监控为主着陆」IA 重构把监控与站点拆为两个入口后留下的重复。

## 决策

合并为单一页面，**大表格保持主角**（用户明确要大表格的直观性）。

放弃的备选：
- 「差异化两个页面」（总览收窄看板只显示异常站点）——与用户「不可用是常态、别一坏就标红」
  以及「要大表格直观」两条诉求冲突，且两页表格内容仍几乎一致，没真正消除重复。
- 「加共享缓存保留两页」——合并后只剩一页，跨页重复拉取问题自然消失，缓存成多余（YAGNI）。

## 设计

### 路由 & 导航

- `/` → 重定向 `/sites`
- `/sites` → SitesView（canonical，name `sites`）
- `/monitor` → 重定向 `/sites`（保留旧链接可达）
- 旧 `/tasks` → 重定向 `/sites`（原先指向 /monitor）
- `/sites/:id` → SiteDetailView **不变**
- 导航 tab：`监控总览` + `站点管理` 两个 tab 合并为单个 `站点监控`，path `/sites`，
  activeMatch 覆盖 `/`、`/sites*`、`/monitor*`。

### 页面布局（合并后单页）

```
健康条:  ●告警中 N   ●健康 N   ●未测 N        [可用/降级/不可用 图例]
告警卡区（有告警才显示；连续 2 轮低于阈值才翻红，恢复 1 次即消）
   ● 站点A × 模型X    连续 3 轮 · 所属某任务            [进站点 →]
工具栏:  共 N 站点   [🔍 搜索]   [全部|健康|异常|未测]        [+ 新建站点]
┌──────────────── 大表格 SiteHealthBoard（主角，全量）────────────────┐
│  站点 · 模型   │  可用性近24  │  平均 TTFT  │  …  │  [测试]  ⭐       │
└────────────────────────────────────────────────────────────────────┘
▸ 监控任务跑批状态（N）   ← 折叠，默认收起
```

### 实现取舍：以 SitesView 为底座

SitesView 已含表格 / 搜索 / 筛选 / 新建站点 / 真实发起测试。MonitorView 独有的只有
告警卡与跑批折叠。故合并 = 在 SitesView 上嫁接这两块，删除 MonitorView.vue。

需并入 SitesView 的内容（来自 MonitorView）：
- 健康条改为 `告警中 N · 健康 N · 未测 N`（采用 MonitorView 口径）：
  - `告警中` = 告警接口 `alerts.length`（连续 2 轮的持续性失败，是有意义的红色信号）。
  - **去掉 SitesView 原有的「异常 N」pill**：`异常`=最近一次测试失败（s.health==='error'），
    在「不可用是常态」的语境下会过度标红，故不进健康条。
  - `健康 / 未测` 仍来自 summary 的 s.health 计数。
- 注意：筛选 chips 仍保留 `全部 / 健康 / 异常 / 未测` 四个（含 `异常`），供需要下钻者按
  health 过滤——健康条（水位概览）与筛选 chips（下钻工具）口径不同是有意为之。
- 告警卡区：`getActiveAlerts`，无告警时不显示告警卡（保留现有 SitesView 顶部不变）。
- 底部「监控任务跑批状态」`<details>` 折叠：`getSchedules`，默认收起。

### 数据流

合并后单个 `loadData` 并发拉取 4 个接口：

```
Promise.all([
  getSitesSummary({ hours }),
  getCellAvailability({ hours, buckets: 24 }).catch(→ {cells:[]}),
  getActiveAlerts().catch(→ {alerts:[]}),
  getSchedules().catch(→ {schedules:[]}),
])
```

- 触发时机：进入 `/sites`（及 `/sites/:id` 返回）时、时间范围变化时。沿用 SitesView 现有 watch。
- 告警接口失败不影响表格渲染（各自 `.catch` 兜底）。
- **不引入共享缓存 store**。

### 行为（沿用 SitesView 现有实现，不回退）

- 发起测试：确认弹窗 → POST /api/runs → 轮询 → 完成 toast（保留 confirmTest / pollTestCompletion）。
- 新建站点：保留 SitesView 创建弹窗。
- 收藏 / 排序 / 筛选 / 搜索：保留 SitesView 现有逻辑（收藏置顶 → 异常 > 健康 > 未测 → 最近测试）。

### 收尾与回归

- 删除 MonitorView.vue 后，核对引用：router.js、App.vue tabs、以及 NotificationCenter.vue /
  TasksView.vue / HistoryView.vue 中对 `/monitor`、`/sites`、`站点管理` 文案与跳转的引用，
  确保跳转仍可达（多为跳 `/sites/:id`，路由保留即可）。
- **App.vue:128 登录成功后 `router.push('/monitor')` 一并改为 `/sites`**（否则虽走重定向但不干净）。
- **healthCounts 必须继续计算 `error`**：健康条 pill 不渲染「异常」，但筛选 chip「异常」仍按
  `s.health === 'error'` 过滤，故沿用 SitesView 现有 `healthCounts`（含 error），只是不渲染该 pill。
- **watch 沿用 SitesView 的 `route.path === '/sites'` 写法，不要照抄 MonitorView 的
  `route.name === 'monitor'`**（合并后该 name 不存在）。timeRangeStore watch 的现有条件保持不变。
- TasksView.vue 顶部「/tasks 已重定向到 /monitor」注释顺手更新为 `/sites`（非阻塞）。
- `store.refreshFn` 仍指向合并页的 `loadData`。
- 过 vitest + build（pre-push hook）。注意 4 个 pre-existing 失败的 tab_refactor 测试与本次无关，可忽略。

## 不做（YAGNI）

- 不加共享缓存 / TTL store。
- 不改 SiteHealthBoard 组件内部（收窄/聚合等）——它已用平均聚合反映真实水位。
- 不动站点详情页 SiteDetailView 及其 tab。
- 不改后端接口。

## 验收

- 导航只剩 `站点监控` + `历史与对比`（+ 设置齿轮）。
- `/monitor`、`/tasks` 访问自动落到 `/sites` 且页面正常。
- 合并页同时具备：告警卡（有告警时）、全量大表格、搜索/筛选/新建/测试、跑批折叠。
- 来回进出页面不再产生「为切页而重复拉取」的请求模式。
- vitest + build 通过。
