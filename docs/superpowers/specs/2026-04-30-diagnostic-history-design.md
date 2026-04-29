# 诊断历史回看功能设计

## 背景

缓存诊断（渠道诊断）结果在测试完成后无法回看。数据已持久化到 `channel_diagnostics` 表，API 端点已就绪，但前端没有浏览历史记录的入口。

## 目标

在 HistoryView 页面新增「诊断历史」Tab，让用户可以查看、筛选、回看所有历史诊断结果。

## 设计

### 入口位置

HistoryView 页面顶部增加 Tab 切换器：

```
基准测试 | 诊断历史
```

- 基准测试 Tab：现有 HistoryView 内容不变
- 诊断历史 Tab：新增的历史诊断列表

### 诊断状态枚举

后端 `compute_overall_status()` 产出以下状态值，前端需完整覆盖：

| 状态 | 含义 | 颜色 |
|------|------|------|
| `passed` | 缓存生效（supported / partial） | 绿 |
| `warning` | 结果存疑（breaker 也命中 / response cache） | 黄 |
| `no_usage_fields` | 渠道未返回缓存字段 | 蓝 |
| `no_cache` | 渠道返回缓存字段但值全为 0 | 黄 |
| `inconclusive` | 样本不足或关键 probe 失败 | 灰 |
| `error` | 诊断请求失败 | 红 |

注意：`critical` 在 HistoryView 旧 tooltip 中存在但后端不产出，需移除。

### 诊断历史 Tab 布局

**筛选栏**（顶部，三个下拉框并排）：
- 站点名称（profile_name）— 级联筛选：受当前 model 和 status 筛选影响
- 模型名称（model）— 级联筛选：受当前 profile_name 和 status 筛选影响
- 诊断状态（status）— 固定选项，按上述枚举

筛选逻辑：任一下拉框变化时，重新调用列表接口（传入所有当前筛选条件），同时刷新其他下拉框的可选值（通过 filter-options 接口传入当前筛选条件实现级联）。

**列表**：
- 每行显示：诊断时间、站点名称、模型、状态标签（带颜色）、置信度（命中率仅在展开详情中显示）
- 按时间倒序排列
- 底部「加载更多」按钮（每页 20 条），当 `has_more === false` 时隐藏

**点击展开**：
- 点击某行，下方展开完整诊断卡片
- 展开行为：
  1. 首次展开：显示 loading skeleton，调用 `GET /api/channel-diagnostics/{id}` 获取完整报告
  2. 成功：渲染诊断详情卡片
  3. 失败/超时：显示错误提示 + 「重试」按钮
  4. 已加载的详情缓存在前端内存中（keyed by id），再次展开无需重复请求
  5. 切换筛选条件或触发加载更多时，清空所有已展开状态和缓存

### 共享诊断卡片组件

当前诊断详情渲染逻辑分散在 SiteTestTab（模板内联）和 resultDetail.js（HTML 字符串拼接）中。本次需要抽取共享渲染逻辑：

- 新建 `frontend/src/components/DiagnosticCard.vue` — 封装诊断详情卡片（状态标签、命中率、探针详情、token 校验、代理缓存检测）
- 从 SiteTestTab 的 `.diag-result-card` 区域（第 169-282 行）提取
- props：`report`（完整报告 JSON 对象）
- HistoryView 和 SiteTestTab 都使用此组件
- 诊断状态颜色/文案映射函数（`diagStatusColor`、`diagStatusLabel`、`diagStatusTooltip`）也移入此组件或提取为共享 utils

### 数据架构改动

**后端 — `app/db.py`**

重写 `list_channel_diagnostics()` 查询：
- SELECT 只取摘要列：`id, profile_name, model, status, overall_risk, confidence, created_at`（不读 `report_json`）
- 命中率（cache_hit_rate）存储在 `report_json` 内部，不在摘要列中。列表行不显示命中率，只在展开详情中通过完整报告渲染
- 增加可选 WHERE 条件：`profile_name`、`model`、`status`
- 返回值改为 `(items: list[dict], total: int)`，其中 `total` 为满足筛选条件的总行数（独立 COUNT(*) 查询）

新增 `list_diagnostic_filter_options(user_id, profile_name=None, model=None, status=None)` 函数：
- 接受当前筛选条件（用于级联）
- 返回去重后的 `{ profile_names: [...], models: [...] }`，排除已被其他筛选条件过滤掉的选项

**后端 — `app/server.py`**

改造 `GET /api/channel-diagnostics`：
- 增加查询参数：`profile_name: Optional[str]`、`model: Optional[str]`、`status: Optional[str]`
- 响应格式改为 `{ items: [...], total: <int>, has_more: <bool> }`
  - `total`：满足筛选条件的总记录数
  - `has_more`：`offset + limit < total`

新增 `GET /api/channel-diagnostics/filter-options`：
- 查询参数：`profile_name: Optional[str]`、`model: Optional[str]`、`status: Optional[str]`（用于级联筛选）
- 响应：`{ profile_names: [...], models: [...] }`
- 仅返回当前用户的数据

**前端 — `frontend/src/api/index.js`**

- `listChannelDiagnostics(params)` — 支持 `profile_name`、`model`、`status`、`limit`、`offset` 参数
- 新增 `getDiagnosticFilterOptions(params)` — 调用 filter-options 端点

**前端 — `frontend/src/views/HistoryView.vue`**

新增：
- Tab 切换逻辑（`activeTab: 'bench' | 'diag'`）
- 诊断历史列表（表格式布局）
- 筛选栏（三个级联下拉框）
- 加载更多逻辑（基于 `has_more`）
- 点击展开/折叠逻辑（含 loading、error、缓存状态）
- 使用 `DiagnosticCard` 组件渲染详情

修复：
- `diagTooltip()` 中移除 `critical`，增加 `no_cache`

### 改动文件清单

| 文件 | 改动 |
|------|------|
| `app/db.py` | 重写列表查询（摘要列 + COUNT），增加筛选参数，新增 filter_options 函数 |
| `app/server.py` | 列表接口增加筛选 + total/has_more，新增 filter-options 端点 |
| `frontend/src/api/index.js` | 适配筛选参数，新增 filter-options 调用 |
| `frontend/src/components/DiagnosticCard.vue` | **新建**，从 SiteTestTab 提取诊断详情卡片组件 |
| `frontend/src/components/SiteTestTab.vue` | 改用 DiagnosticCard 组件 |
| `frontend/src/views/HistoryView.vue` | 新增诊断历史 Tab、筛选栏、列表、展开详情、修复 status 映射 |
| `frontend/src/utils/resultDetail.js` | 本次不迁移。仅统一 SiteTestTab 与诊断历史页的诊断详情渲染；History 结果详情中的诊断摘要区块保持现有 HTML 渲染方式 |
| `tests/test_channel_diagnostics_db.py` | 新增：组合筛选、COUNT 返回值、filter_options 级联、用户隔离 |
| `tests/test_channel_diagnostics_api.py` | 新增：筛选参数、total/has_more 响应格式、filter-options 端点、用户隔离 |

### 不做的事

- 不修改 SiteTestTab 的渠道诊断运行逻辑（只改详情渲染为引用新组件）
- 不将诊断结果关联到基准测试历史记录（YAGNI）
- 不添加删除诊断记录的功能（暂不需要）
- 不迁移 resultDetail.js 中的诊断摘要区块（保持现有 HTML 渲染，后续有需要再统一）
