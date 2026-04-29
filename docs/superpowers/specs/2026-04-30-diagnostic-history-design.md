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

### 诊断历史 Tab 布局

**筛选栏**（顶部，三个下拉框并排）：
- 站点名称（profile_name）— 从已有诊断记录中动态提取
- 模型名称（model）— 从已有诊断记录中动态提取
- 诊断状态（status）— 固定选项：passed / warning / inconclusive / no_usage_fields / no_cache / error

**列表**：
- 每行显示：诊断时间、站点名称、模型、状态标签（带颜色）、命中率、置信度
- 按时间倒序排列
- 底部「加载更多」按钮（每页 20 条）

**点击展开**：
- 点击某行，下方展开完整诊断卡片
- 复用现有 `.diag-result-card` 样式
- 包含探针详情（cold/warm/breaker/identical）、token 校验、代理缓存检测等
- 通过 `GET /api/channel-diagnostics/{id}` 获取完整报告

### 数据架构改动

**后端 — `app/db.py`**

优化 `list_channel_diagnostics()` 查询：
- 不返回 `report_json` 字段（列表只需要摘要）
- 增加可选筛选参数：`profile_name`、`model`、`status`

新增 `list_diagnostic_filter_options()` 函数：
- 返回去重后的站点名称列表、模型名称列表（供前端下拉框使用）

**后端 — `app/server.py`**

`GET /api/channel-diagnostics` 增加查询参数：
- `profile_name: Optional[str]` — 按站点筛选
- `model: Optional[str]` — 按模型筛选
- `status: Optional[str]` — 按状态筛选

新增 `GET /api/channel-diagnostics/filter-options` 端点：
- 返回 `{ profile_names: [...], models: [...] }`（供下拉框使用）

**前端 — `frontend/src/api/index.js`**

更新 `listChannelDiagnostics(params)` 支持筛选参数传递。

**前端 — `frontend/src/views/HistoryView.vue`**

新增：
- Tab 切换逻辑（`activeTab: 'bench' | 'diag'`）
- 诊断历史列表组件
- 筛选栏（三个下拉框）
- 点击展开/折叠逻辑
- 诊断详情卡片（复用 SiteTestTab 的 `.diag-result-card` 样式）

### 样式

复用现有设计系统：
- 状态标签颜色：`diagStatusColor()` 函数（绿/黄/红/灰）
- 探针卡片样式：`.diag-probe-card`、`.diag-probe-badge`
- Token 校验：`.diag-token-verify`
- 整体风格与 HistoryView 现有表格保持一致

### 改动文件清单

| 文件 | 改动 |
|------|------|
| `app/db.py` | 优化列表查询，增加筛选参数，新增 filter_options 函数 |
| `app/server.py` | 列表接口增加筛选参数，新增 filter-options 端点 |
| `frontend/src/api/index.js` | 适配筛选参数 |
| `frontend/src/views/HistoryView.vue` | 新增诊断历史 Tab、筛选栏、列表、展开详情 |

### 不做的事

- 不修改 SiteTestTab 的渠道诊断 Tab（保持现状）
- 不将诊断结果关联到基准测试历史记录（YAGNI）
- 不添加删除诊断记录的功能（暂不需要）
