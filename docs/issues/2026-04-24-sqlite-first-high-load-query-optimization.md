# SQLite-first 高负载数据保留与查询优化

## 背景

AITokenPerf 是开源本机产品，默认依赖应尽量轻量，避免要求用户本地安装 PostgreSQL。但在高频定时任务场景下，需要保证 SQLite 默认方案仍有可接受的查询性能，并保留 PostgreSQL 作为高负载或团队部署选项。

典型压力场景：

- 100 个定时任务
- 每 5 分钟执行一次
- 查询最近 7 天趋势和历史数据

最低数据量估算：

```text
100 * 12 * 24 * 7 = 201,600 条结果
```

如果每次任务按多个 model、profile 或 concurrency level 产生多条结果，7 天数据可能达到百万级。

## 当前风险

- `results` 常用筛选字段主要藏在 JSON 中，查询依赖 `json_extract`。
- `/api/results`、站点趋势、站点摘要存在拉大量结果到 Python 再聚合的路径。
- `results` 缺少面向 7 天查询、定时任务查询、站点趋势查询的索引。
- PostgreSQL 当前并非完全兼容，部分查询仍使用 SQLite 的 JSON 函数。
- 如果直接把 PostgreSQL 设为默认，会提高本机开源用户的部署门槛。

## 目标

- 默认继续使用 SQLite，保持本机开箱即用。
- 在 100 个任务、5 分钟周期、查询 7 天数据的场景下，SQLite 仍能稳定工作。
- PostgreSQL 作为可选高负载部署方案，而不是默认要求。
- 历史和趋势查询避免全表扫和大 JSON 全量加载。

## 建议方案

### 1. 冗余常用查询列

为 `results` 增加常用查询列，避免列表和趋势查询反复解析 JSON：

- `profile_name`
- `base_url`
- `model`
- `concurrency`
- `success_rate`
- `ttft_p50`
- `tpot_p50`
- `e2e_p50`
- `token_throughput_tps`

### 2. 增加 SQLite/PG 通用索引

建议增加以下索引：

- `(user_id, created_at)` 或 `(user_id, timestamp)`
- `(user_id, scheduled_task_id, created_at)`
- `(user_id, profile_name, created_at)`
- `(user_id, base_url, created_at)`

### 3. 调整查询路径

- 列表页默认只查询轻量字段，不解析大 JSON。
- 趋势接口只读普通列或预聚合数据。
- 详情页再加载完整 JSON。

### 4. 考虑增加聚合表

- 按 minute 或 hour 聚合站点趋势。
- 长期历史只保留聚合数据，原始明细按保留策略清理。

### 5. 增加数据保留策略

- 默认保留最近 7 或 30 天原始结果。
- 提供设置项或环境变量配置保留周期。

### 6. 修复 PostgreSQL 兼容

- SQLite 使用 `json_extract`。
- PostgreSQL 使用 `config_json::jsonb ->> ...`，或迁移后的普通列。

## 验收标准

- 默认 SQLite 部署不需要额外服务。
- 20 万级 `results` 数据下，最近 7 天历史列表、站点摘要、趋势查询响应可接受。
- 百万级数据下不会因为全量 JSON 加载导致明显卡死或内存飙升。
- PostgreSQL 部署下历史和趋势查询不再使用 SQLite-only SQL。
- 增加覆盖 SQLite 和 PostgreSQL 查询分支的测试，至少覆盖 7 天窗口、站点筛选、定时任务结果查询。

## 非目标

- 不把 PostgreSQL 变成默认必需依赖。
- 不要求本机用户部署额外数据库服务。
- 不一次性重写所有历史统计 UI。
