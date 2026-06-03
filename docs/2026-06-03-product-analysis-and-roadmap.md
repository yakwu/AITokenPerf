# AITokenPerf 产品全面分析与改进路线

> 日期：2026-06-03
> 范围：功能完整性、前端组件复用、用户体验流程
> 方法：三个独立 subagent 分维度审计真实代码（前端 12.3k 行 / 后端 7.6k 行），交叉验证后综合
> 定位基准：**无人值守的 LLM 定时拨测 + 质量监控产品**

---

## 执行摘要

代码工程质量中上，调度器（DB 锁 + 绝对时间）是全项目最高水准的模块。但以"质量监控产品"为标尺，最大的两个缺口都戳在产品命根上：

1. **告警完全不闭环** —— 出了问题没人通知得到（通知是纯前端内存态，关页面即丢）。
2. **核心指标 TPOT 可能算得不准** —— 受 SSE chunk 聚合污染，跨渠道对比不公平。

> 结论：这两件做完，产品才真正配得上"质量监控"的定位。其余（组件抽象、UX 打磨、死代码清理）是持续工程债，重要但不致命。**不应一次全做。**

两个独立 agent 在「告警不闭环」「truncated 截断不提示」上各自撞车 —— 收敛即强信号。

---

## 第一部分 · 值得新增/修改的功能

### 🔴 真缺口（影响产品能否成立）

#### F1. 拨测失败/质量下降的主动告警 —— 完全未闭环
- **现状**：
  - 通知系统是浏览器内存态 `ref([])`（`frontend/src/composables/useNotifications.js:3`），刷新即清空，无 localStorage / 无后端。
  - 告警依赖「页面开着 + `ScheduleIndicator` 每 5 秒轮询 `getRunningTasks` 侦测任务消失」（`frontend/src/components/ScheduleIndicator.vue:55-97`）；任务若在两次轮询间起止，或用户没开浏览器，通知永不产生。
  - 后端全局搜 `webhook/notify/alert/email/smtp/telegram/feishu/slack` **零命中**；`scheduler._run_scheduled_task` 失败只 `log_error`，不推送。
  - Dashboard 的"异常告警"（`DashboardView.vue:262`）是前端 `computed` 实时过滤，纯展示。
- **缺什么**：定时拨测的核心价值就是"无人值守时出问题能通知到人"，这条链路根本不存在。
- **建议**：① 新增 `notification_channels` 表（webhook / 邮件 / 飞书 / 钉钉）；② `_run_scheduled_task` 完成后按规则（成功率 < 阈值 / 连续失败 / 诊断 status 变 failed）触发推送；③ 每用户可配告警阈值。
- **价值**：高（定位与实现差距最大处）。

#### F2. TPOT / token 计数被 chunk 聚合污染 ⚠️（真 bug 级）
- **现状**：`RequestMetrics.tpot`（`app/client.py:48`）= `token_timestamps` 相邻间隔均值；但 `token_timestamps` 是**每个 SSE delta 事件**追加一个（`app/protocols/anthropic.py:86`、`app/protocols/openai_chat.py:101`），不是每 token。中转代理常把多 token 聚合进一个 chunk 下发 → delta 数 ≪ 实际 token 数 → **TPOT 被系统性高估**；`stats.py` 中 `tokens_received: len(token_timestamps)` 同样不准。
- **影响**：跨渠道对比不公平（原生逐 token 的渠道 TPOT 反而"更差"）。直接动摇核心指标可信度。
- **建议**：TPOT 改用 `(e2e - ttft) / max(output_tokens - 1, 1)`，以 usage 的 `output_tokens` 为分母；`token_timestamps` 仅用于 TTFT 和抖动分析。
- **价值**：高。
- **备注**：TTFT 计时点本身正确（`client.py:98` 在 `session.post` 前打 `start_time`，首个 text_delta 打 `first_token_time`，符合 TTFT 定义）。

#### F3. 历史页"假数据"风险
- **现状**：
  - 后端命中行数上限会返回 `truncated:true`（判定 `app/db.py:725`，返回 `db.py:810`，`server.py:976` 透传），但前端 grep `truncated` **零命中**，从不消费。
  - `HistoryView` 的过滤/搜索/下拉选项**只作用于当前页约 20 条**（`HistoryView.vue:333-402`），却让用户以为在全库筛选。
- **影响**：用户基于被静默截断 / 只筛 20 条的数据下质量结论 → 错误判断。
- **建议**：① 收到 `truncated` 时提示"仅显示最近 N 条，请用时间筛选"；② 过滤条件下推到后端查询，而非前端切片。
- **价值**：高（数据完整性的用户感知）。

#### F4. SLA / 可用率统计缺位
- **现状**：有单次 `success_rate`、`sites/summary`、趋势点，但无"周期可用率 %、P99 达标率、连续 N 次失败、MTBF"这类 SLA 聚合。Dashboard 的 `yesterdayRate`（`DashboardView.vue:212`）是前端按 timestamp 前缀粗算。
- **建议**：后端聚合按时间窗的 uptime %、违约时段，作为监控产品核心指标卡。
- **价值**：高（监控定位标配，目前缺位）。

### 🟡 工程债（低成本必做）

| # | 问题 | 证据 | 价值 |
|---|---|---|---|
| F5 | **SSE 断线无兜底**，可能永久卡"运行中" | `useBenchSSE.js:28` onerror 空函数；后端漏发 `bench:complete` 时前端 Promise 永不 resolve → `running` 永远 true | 中高 |
| F6 | **~600 行死代码** | `server.py:1599-2391` 的 `start_bench/dry_run/bench_stream` 等**无 `@app` 装饰器**、前端零调用（被 Run Center 取代）；`get_results`（`db.py:641`）只 import 不调用；前端 `openCompare/toggleSort`（`HistoryView.vue:702,490`）、`store.rerunConfig`（`app.js:19`）死代码 | 中 |
| F7 | **限流字典不清理** | `_ip_ban`（`server.py:237`）/`_rate_store`（`server.py:238`）key 只增不删，慢性内存泄漏（可挂进已有 `_periodic_task_cleanup`） | 中 |
| F8 | **数据导出缺失** | 无 `/api/results/export`、前端无导出 UI | 中（低成本高感知，可复用 raw 分页流式导出） |
| F9 | **"重测"名不副实** | `rerunAtSite/rerunResult`（`HistoryView.vue:537,600`）只跳转**不预填**原配置，`rerunConfig` 死字段 | 中 |

### 🟢 锦上添花（差异化，工程量大，排后）

- **降智检测 = 基线对比**：诊断现为单次绝对 pass/fail（`app/diagnostics/structured.py:72` 硬编码判定），无"与历史基线比 → 质量回退"。降智本质是相对退化（TTFT 突增、tool_use 成功率回落）。
- **多渠道横评 + 性价比排序**：同一模型在多渠道的 成功率 × P99 × 单位 token 成本 并排打分。
- **诊断探针多数表决**：单次请求受 LLM 随机性影响易误报，关键探针 2/3 表决。

---

## 第二部分 · 可抽象复用的组件

前端重复度偏高（最大热点在 SitesView / DashboardView / SiteTestTab / SiteSchedulesTab 之间）。

| 优先 | 抽取目标 | 现状分散位置 | 收益 |
|---|---|---|---|
| 高 | **统一色彩阈值函数** | `formatters.js:49` 已导出并被 `resultDetail.js:14` 复用，但 7 个 view/component 仍各自内联重写未收口（`SiteTestTab:507`、`HistoryView:438`、`SitesView:262`（甚至手写同名 `latencyColorStyle`）、`DashboardView:356`、`TasksView:440`、`SiteTrendsTab:153`、`SiteSchedulesTab:505`），阈值魔数会漂移 | −60 行，单点维护，零成本 |
| 高 | **`ModelMultiSelect` 组件** | 模型多选 combobox 在 4 处近乎一致重写（`SiteTestTab`、`TasksView`、`SiteSchedulesTab` create/edit 两份）；已有 `ModelSelector.vue` 没复用 | −250+ 行 |
| 高 | **收口 `/api/runs` 到 api 层** | 启动 payload 在 4 处拼字符串（`SiteTestTab:523`、`SitesView:421`、`useConnectivityTest:47`、`TasksView:474`），默认值各处硬编码；部分调用绕过 `api/index.js` 直接拼字符串（如 `HistoryView:626` 未 encode filename） | encode/401 一致、默认值单点 |
| 中 | **`useClickOutside` composable** | 11 处手写 `addEventListener('mousedown'/'click')` | −11 份样板 |
| 中 | **拆分 `SiteTestTab.vue`（1401 行）** | 一个文件塞了 模型选择 + 压测配置 + SSE 进度 + 双列结果 + 诊断 5 种职责；CSS 占 606 行含死样式 | 拆成 ~200 行编排 + `BenchConfigForm`/`BenchResultGrid`/`ChannelDiagPanel` + `useTestRun` |
| 中 | **`useTestRun` composable** | 启动 + SSE/轮询 + progress 状态在 3-4 处重复（`SiteTestTab:660`、`useConnectivityTest:82`、`SitesView:451` 轮询版） | progress 结构单点 |
| 中 | **`relativeTime`/`fmtLocalTime` 进 formatters** | `SitesView:245` 与 `DashboardView:339` **逐字符完全相同** | −5 份时间格式化 |
| 中 | **`EmptyState` + `Pagination` + `SearchToolbar`** | 列表页骨架（toolbar+空态+分页）在 SitesView/TasksView/HistoryView/SiteTrendsTab 各写一套 | 列表页统一 |
| 低 | **`StatusBadge` 组件** | status-dot + label 在多页重复，含定时任务/健康两套映射 | — |

**已有好抽象**：`formatters`（fmt* 用得好）、`resultDetail`、`trendAggregator`（有单测）、`useBenchSSE`、`FilterDropdown`/`ModalOverlay`/`InlineConfirmDelete`。
**该用没用上**：`formatters` 的色彩函数（仅 `resultDetail.js` 用了，7 个 view 仍内联重写）、`ModelSelector`、`ModalOverlay`（SitesView 测试弹窗手写了一套 `.modal-overlay`）。
**脆弱耦合**：`window.showDetailOverlay` / `window.renderPercentilesChart`（`resultDetail.js:226` RAF 轮询全局函数）。

---

## 第三部分 · 用户体验流程卡点

> 导航：`App.vue` 顶栏只暴露 4 个 Tab（概览/目标站点/历史与对比/定时任务），其余从头像菜单进。`store.refreshFn` 是全局"当前页刷新"插槽，各页抢占式注册。

| 卡点 | 旅程 | 位置 | 严重 |
|---|---|---|---|
| **失败告警不闭环**（同 F1）——监控产品却要求"有人开着页面" | 定时拨测 | `useNotifications.js:3`、`ScheduleIndicator.vue:55` | 高 |
| **概览空状态零引导**——新用户登录落到一片 0 的概览，无 CTA，不知去哪 | Onboarding | `DashboardView.vue:56,100` | 高 |
| **空态文案误导**——SitesView 空态写"请通过**配置页**创建新站点"，但根本没有独立配置页，创建入口就在本页按钮 | Onboarding | `SitesView.vue:30` | 中 |
| **建站时无法验证连通性**——填错 key 要等跑测试才发现（连通性测试只在已建好的站点的 Config/Test Tab） | 配置渠道 | `SitesView.vue:116-156` | 高 |
| **连通性验证必须先保存**——改了配置想验证被 `请先保存配置` 拦下，"试一下再决定存不存"做不到 | 配置渠道 | `SiteConfigTab.vue:173` | 中 |
| **历史过滤只筛当前页 + 截断不提示**（同 F3） | 看历史 | `HistoryView.vue:333,470` | 高 |
| **翻页清空展开/对比态**——`compareSet` 用当前页索引，翻页后错位失效 | 看历史 | `HistoryView.vue:481,515` | 中 |
| **SSE 断线卡死无反馈**（同 F5）；**快速测试走轮询全程无进度** | 跑压测 | `useBenchSSE.js:28`、`SitesView.vue:451` | 高/中 |
| **停止是软停且无确认**——`stopBench` 立刻置 `running=false`，但 SSE 仍可能在跑 | 跑压测 | `SiteTestTab.vue:736` | 中 |
| **启动失败信息一闪而过**——槽位不足等错误写进进度日志区，但失败时进度面板 `v-show=running` 立即隐藏 | 跑压测 | `SiteTestTab.vue:577,233` | 中 |
| **全站缺错误态**——接口失败只闪 toast 然后空白/残留旧数据，无"加载失败+重试"（仅诊断详情有重试，孤例） | 通用 | `DashboardView:465`、`SitesView:548`、`TasksView:549` | 高 |
| **任务"异常"无视觉状态**——连续失败的任务列表里仍显示绿色"运行中"（异常是前端算的，badge 只有 active/paused） | 定时拨测 | `TasksView.vue:366,75` | 中 |
| **"立即执行"无反馈闭环**——只 toast"已触发"，不刷新/不轮询/不跳转 | 定时拨测 | `TasksView.vue:519` | 中 |
| **token 过期无全局跳登录**——路由守卫只查 localStorage 有无 user，不校验 token；过期后到处 401→toast，体验是"莫名空白" | 通用 | `router.js:17`、`api/index.js` | 中 |
| **SSE 鉴权 token 走 URL query**——`/stream?token=xxx` 会进代理/服务器日志 | 通用 | `useBenchSSE.js:9` | 中 |
| **移动端历史表横向溢出**——窄屏只隐藏地址列，其余 12 列硬挤，固定像素列宽 | 通用 | `HistoryView.vue:980` | 中 |
| **删除确认三种风格并存**（行内3秒/行内文字/InlineConfirmDelete 组件） | 通用 | 多处 | 低 |

---

## 改进路线图（建议分阶段，不要一次全做）

### 阶段一 · 戳中命根（先做这两件，产品才配得上"质量监控"）
1. **F1 告警闭环**：后端告警通道表 + 失败规则 + webhook/邮件推送。
2. **F2 修 TPOT 计算**：改用 `output_tokens` 当分母，恢复核心指标可信度。

### 阶段二 · 低成本消隐患（顺手还债）
3. **F3 truncated 提示 + 过滤下推后端**。
4. **F6 删 ~600 行死代码** + `get_results` 死函数 + 前端死代码。
5. **F7 限流字典清理**（挂进已有清理循环）。
6. **F5 SSE 断线兜底**（超时 resolve + "连接断开"提示）。

### 阶段三 · 体验与可维护性
7. **Onboarding 引导** + 空态文案修正 + CTA。
8. **建站内联连通性验证** + 全站错误态/重试。
9. **F8 数据导出** + **F9 重测预填**。
10. **组件抽象**：色彩函数收口 → `ModelMultiSelect` → `/api/runs` 收口 → 拆分 `SiteTestTab` → `useClickOutside`/`EmptyState` 等。

### 阶段四 · 差异化能力（工程量大，按需）
11. **F4 SLA 可用率统计**、降智基线对比、多渠道横评、诊断多数表决。

---

## 附录 · 现有功能成熟度

| 功能 | 成熟度 |
|---|---|
| 压测 burst/sustained、多协议适配、多模型并行、Run Center | 成熟 |
| 定时拨测（DB 锁 + 绝对时间 + 容量预检） | 很成熟（全项目最高水准） |
| 数据保留清理（issue #24/#25 已修） | 成熟 |
| 渠道诊断 6 类、Prompt cache 探针 + 代理注入检测 | 中等（多为单次 pass/fail，无重试/基线） |
| 趋势/站点汇总、费用计算、历史对比、认证多租户、安全中间件 | 成熟 |
| 通知中心 | 薄弱（纯前端内存，刷新即丢） |

---

*本文档由代码审计生成，所有 file:line 引用基于 2026-06-03 main 分支（commit dae8417 之后）。落地前请对照当前代码复核。*
