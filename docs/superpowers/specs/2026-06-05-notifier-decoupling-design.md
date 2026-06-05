# 告警器解耦设计（飞书告警重构）

日期：2026-06-05

## 背景与问题

当前飞书告警（PR #30/#32）把告警配置直接内联在每个定时任务（`scheduled_tasks`）这一行里：
`alert_webhook`、`alert_threshold`、`alert_enabled`、`alert_state` 四列。一个任务写死一个
webhook。这导致"通知发到哪"和"任务本身的配置"耦合在一起——同一个飞书群要在多个任务里重复
填 webhook，改群机器人地址要逐个任务改。

## 目标

把"通知配置"抽成一个可复用的全局实体——**告警器（notifier）**。创建/编辑定时任务时，从下拉里
**选**一个已有告警器，而不是填 webhook。这样"发到哪"（告警器，可复用）和"啥时候发"（开关 +
阈值，任务自己的）彻底分开。

## 决策（已与用户对齐）

1. **挂载层级**：告警器选择挂在**定时任务**上（不是站点 profile）。触发逻辑仍是任务级整体
   成功率，与现状一致，改动最小。
2. **阈值归属**：阈值（`alert_threshold`）**留在任务上**。告警器只管 webhook（"发到哪"），
   不带默认阈值。
3. **数据迁移**：**不迁移**老的内联 webhook。功能刚上线、生产几乎无真实配置，直接弃用老字段，
   用户重新建告警器并在任务里选。
4. **删除策略**：告警器**被任务引用时拦截删除**，返回还有几个任务在用，提示用户先解绑再删。
5. **作用域**：告警器按 `user_id` 隔离，与站点、定时任务一致。

## 数据模型

### 新增表 `notifiers`

每个用户管自己的告警器。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | PK（SQLite AUTOINCREMENT / PG SERIAL） | 主键 |
| `user_id` | INTEGER NOT NULL，外键 → `users(id)` ON DELETE CASCADE | 属于谁 |
| `name` | TEXT NOT NULL | 告警器名字（下拉显示），如"运维群飞书" |
| `type` | TEXT NOT NULL DEFAULT 'feishu' | 类型，当前固定 feishu，留字段供未来扩展 |
| `webhook` | TEXT NOT NULL DEFAULT '' | 飞书 webhook URL |
| `created_at` | 时间戳 | 创建时间 |
| `updated_at` | 时间戳 | 更新时间 |

约束：`UNIQUE(user_id, name)`（同一用户下告警器名字唯一，便于识别）。

建表落点：`notifiers` 表要同时加进 `app/db.py` 的 `_SQLITE_SCHEMA`（~42 行）和 `_PG_SCHEMA`
（~142 行）两份字符串（`CREATE TABLE IF NOT EXISTS`，`init_db()` 自动建表，无需额外迁移代码）。
`user_id ... ON DELETE CASCADE` + SQLite 的 `PRAGMA foreign_keys=ON`（db.py:34-38）已保证删用户
时自动清理 notifiers，`delete_user`（db.py:491）无需手动加 DELETE。

### 修改表 `scheduled_tasks`

- ➕ 新增列 `alert_notifier_id INTEGER NOT NULL DEFAULT 0`（0 = 未选告警器；指向
  `notifiers.id`）。0 作哨兵安全：SQLite AUTOINCREMENT / PG SERIAL 主键都从 1 起，不会发 0，
  与现有 `scheduled_task_id INTEGER DEFAULT 0` 同构。
  - 走现有迁移机制：`init_db()` 里把 ALTER 加进**两个列表**——SQLite 段（db.py:~313，逐列
    try/except）`ALTER TABLE scheduled_tasks ADD COLUMN alert_notifier_id INTEGER NOT NULL DEFAULT 0`；
    PG 段（db.py:~324）`... ADD COLUMN IF NOT EXISTS ...`。
  - 不做物理外键约束（与现有列风格一致，应用层校验归属），便于跨 SQLite/PG。
- ✅ 保留 `alert_threshold`、`alert_enabled`、`alert_state`（任务自己的触发规则与运行状态）。
- ⚠️ `alert_webhook` 列**物理保留但停用**（不读不写）。理由：SQLite DROP COLUMN 脆弱，且无需
  迁移老数据；留着不影响逻辑，后续可在独立清理中移除。

## 后端改动

### API（与 profiles 风格一致，挂在 `app/server.py`）

| 接口 | 作用 |
|------|------|
| `GET /api/notifiers` | 列出当前用户的告警器（任务表单下拉用） |
| `POST /api/notifiers` | 新建：校验 `name` 非空、`webhook` 走 `is_allowed_webhook` |
| `PUT /api/notifiers/{id}` | 改名/换 webhook（校验归属当前用户 + SSRF 校验） |
| `DELETE /api/notifiers/{id}` | 删除；**被任务引用则拒绝**（409/错误信息含引用数），否则删除 |
| `POST /api/notifiers/{id}/test` | 发飞书测试消息（从原任务级 `alert-test` 迁移到告警器级） |

GET/list 返回的 webhook 做**脱敏**（只回 host 或尾部打码，复用 `notifier.py:_safe_host` 思路），
不把完整 webhook 明文回前端列表。

任务创建/更新接口（`create_schedule`:2085 / `update_schedule`:2124）：
- 入参把 `alert_webhook` 换成 `alert_notifier_id`。
- 入参收口函数是 `_extract_alert_fields(body)`（server.py:2028，被两处共用），**不是**
  `_sanitize_alert_config`。改造：
  - 删掉 2042-2046 对 `alert_webhook` 走 `is_allowed_webhook` 的校验分支；
  - 新增 `alert_notifier_id` 分支：`int` 化 + 校验「为 0，或存在且归属当前用户」。
  - 归属校验需要 user_id，故**签名改为 `_extract_alert_fields(body, user_id)`**，两处调用点
    同步传入。
  - `alert_threshold`（0-100）、`alert_enabled`（布尔）校验照旧。

### DB 层（`app/db.py`）

- 新增告警器 CRUD 函数：`create_notifier` / `list_notifiers` / `get_notifier` /
  `update_notifier` / `delete_notifier`。
- `delete_notifier`：**在同一事务内**（`engine.begin()`）先 `SELECT COUNT(*) FROM
  scheduled_tasks WHERE alert_notifier_id = ?` 再决定删/不删，规避 check-then-delete 的
  TOCTOU 竞态；有引用则返回引用数、不删。
- `create_scheduled_task`（db.py:1126）：删掉 `alert_webhook` 形参与 INSERT 列（让该列走
  DEFAULT ''），改为接收并写入 `alert_notifier_id`。
- `update_scheduled_task`（db.py:1201-1203）：`allowed` 字段集合去掉 `alert_webhook`、加
  `alert_notifier_id`。

### 调度逻辑（`app/scheduler.py` 的 `_maybe_send_alert`）

- 现有判空 `not (task_row.get("alert_webhook") or "").strip()`（scheduler.py:233）改为：
  `alert_notifier_id` 为 0 / falsy 就直接 return（**开关开着但没选告警器 = 不发、不报错**）。
- 否则用 `task_row["alert_notifier_id"]` 查 `get_notifier(...)` 拿实时 `webhook`（注意取的是
  实时值而非任务启动时的快照，webhook 改了会用新值，这是期望行为）。
- 查不到（告警器已被删——删除虽被拦截，仍兜底）：跳过告警、不报错，与现有 best-effort 一致。
  被删后引用方任务的 `alert_notifier_id` 不回填、不清零，仅运行时跳过。
- `evaluate_alert` / `build_feishu_card` / `send_webhook` 逻辑不变。

## 前端改动

### 新增"告警器管理"页

放在全局设置区，与站点管理平级。功能：
- 列表展示用户的告警器（名字、类型、webhook 脱敏显示）。
- 新建 / 编辑表单（名字 + webhook）。
- "发送测试消息"按钮 → `POST /api/notifiers/{id}/test`。
- 删除按钮；被引用时后端拒绝，前端提示"还有 N 个任务在用，先解绑再删"。

### 改任务表单（**两处都要改**）

前端有两套独立的任务告警表单，都填 `alert_webhook`，**必须一起改**，否则漏改的页面会静默
失效（前端发废弃字段、后端忽略、用户以为配了告警）：

1. `frontend/src/components/SiteSchedulesTab.vue`：创建（~105）+ 编辑（~299）两处 webhook 输入框。
2. `frontend/src/views/TasksView.vue`：`/tasks` 活跃路由的创建表单 webhook 输入框（~239），及
   `createForm` 初始化里的 `alert_webhook`（315/324/512）。

改造内容（两处一致）：
- 把填 webhook 的输入框换成**告警器下拉选择**（选项来自 `GET /api/notifiers`），旁边放"管理
  告警器"链接；表单字段 `alert_webhook` → `alert_notifier_id`。
- 阈值输入框、启用开关保持不变。
- 原"发送测试消息"按钮从任务表单移除（测试改在告警器管理页做）。

### API 客户端（`frontend/src/api/index.js`）

- `alertTestApi`（index.js:61）原打 `/api/schedules/${id}/alert-test`，改为打
  `/api/notifiers/${id}/test`（参数语义从 task id 变 notifier id），由告警器管理页调用。
- 新增 notifier CRUD 的 API 封装。

## 测试

在现有 `tests/test_alert_db.py` / `test_alert_api.py` / `test_alert_scheduler.py` 上改：
- **DB**：告警器 CRUD；删除被引用时拒绝（同事务）；任务存取 `alert_notifier_id`。
- **API**：告警器增删改查鉴权（跨用户不可见/不可改）；SSRF 校验拒非飞书域名；删除拦截返回
  引用数；任务创建/更新收 `alert_notifier_id` 并校验归属；list 返回 webhook 已脱敏。
- **Scheduler**：任务引用告警器后，成功率跌破阈值能查到 webhook 并触发飞书发送；开关开着但
  `notifier_id=0` 安全跳过；告警器缺失时安全跳过。
- **需重写（非沿用）**：`test_alert_api.py:51-99` 的 3 个测试（`test_alert_test_endpoint` /
  `test_alert_test_rejects_other_user` / `test_alert_test_requires_webhook`）打的是已删除的任务级
  `/api/schedules/{id}/alert-test` 端点，需迁移改写到 notifier 级 `/api/notifiers/{id}/test`。

## 不做（YAGNI）

- 不做单站点级告警（仍是任务级整体成功率）。
- 不做钉钉/企微等其他渠道（仅留 `type` 字段占位）。
- 不迁移老 webhook 数据，不物理删除 `alert_webhook` 列。
- 告警器不带默认阈值。
