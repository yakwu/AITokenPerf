# 站点监控首页「告警卡区」折叠 / 限高 / 可忽略

- Issue: #111
- 日期: 2026-06-23
- 状态: 已评审（subagent），可进入实现

## 问题

站点监控首页 `frontend/src/views/SitesView.vue`（23-31 行）顶部「告警卡区」直接平铺
`GET /api/alerts/active` 返回的全部 `(站点×模型)` 告警，**无折叠、无上限、无法消除**。
多站点多模型时一堆红卡占满屏，把下方健康看板挤没（15 站点可铺出十几张红卡）。

这与项目设计基线「AI 站点不可用是常态」冲突：已知挂掉的站点不该长期占据视觉焦点，
也不能用异常驱动的方式让真故障被淹没。

## 目标 / 非目标

**目标**：告警卡区不再无限平铺；告警水位仍真实可查；真故障不被静音漏看。

**非目标**：
- 不做「fail_count 恶化（如 7→9 次）时自动解除静音」——违背用户拍板的「静音到恢复」语义，
  且需存 ack 时基线再比对，YAGNI。
- 不改告警判定/滑动窗口逻辑本身。

## 产品语义（用户已确认）

**忽略 = 静音该 `(站点×模型)` 告警，直到它「恢复一次」后重新告警才再出现。**
- 一直不恢复 → 一直静音。
- 前端**永远**能「显示」找回被静音的告警，并逐条「取消忽略」。

## 设计

### 数据：新表 `alert_acks`

```
alert_acks(
  user_id    INTEGER/… NOT NULL,
  profile    TEXT      NOT NULL,
  model      TEXT      NOT NULL DEFAULT '',   -- 必须 NOT NULL：否则 PG 下 NULL 列 UNIQUE 不约束，ON CONFLICT 失效
  created_at … ,
  UNIQUE(user_id, profile, model)
)
```

- 项目**无迁移版本机制**：`init_db`（`app/db.py:276`）跑 `CREATE TABLE IF NOT EXISTS`，
  SQLite 用 `_SQLITE_SCHEMA`、Postgres 用 `_PG_SCHEMA`（`app/db.py:278`）。
  新表照 `app/db.py:76`（`UNIQUE(user_id,name)` 范式）在**两段 schema 各加一份 `CREATE TABLE IF NOT EXISTS alert_acks(...)`**。
- 粒度对齐：profile 名「用户内唯一」（`UNIQUE(user_id,name)`，`app/db.py:76`），故 ack 唯一键
  必须含 `user_id`，三元组 `(user_id, profile, model)`。

### 后端 API

| 接口 | 行为 |
|------|------|
| `POST /api/alerts/ack` `{profile, model}` | `INSERT … ON CONFLICT(user_id,profile,model) DO NOTHING`（幂等，参照 `app/db.py:604` 的双库 upsert 写法、`_now_sql()` `app/db.py:609`） |
| `POST /api/alerts/unack` `{profile, model}` | 删除该行（「显示 / 取消忽略」用） |
| `GET /api/alerts/active`（改） | 查当前用户 ack 集合，给每条聚合结果打 `acked: bool`。**不在后端过滤**——前端需要全量来支持「找回」 |

`active_alerts`（`app/server.py:2120`）已 `get_scheduled_tasks(user["user_id"])` 按用户拉，
天然 user 隔离，ack 同维度，无多用户串台。

### 后端：恢复自动清除 ack

`app/scheduler.py:_maybe_send_alert`（225 行起）：
- `task_row` 含 `user_id`（`_run_scheduled_task` 在 `scheduler.py:324` 取 `task_row["user_id"]`，
  并在 `scheduler.py:439` 把同一 task_row 传入 `_maybe_send_alert`）。
- recover 分支（`scheduler.py:272-279`）拿到 `(profile, model)` 时，删除 `(user_id, profile, model)` 的 ack 行。
- **必须独立执行**，不能塞进 `new_states != prev`（`scheduler.py:302-304`）分支——否则
  state 恰好未变的 recover 会漏删 ack。

### 后端：站点删除 / 改名联动

- 删除站点（`app/db.py:645` 清 alert_state 处旁）：**删除** 该 `(user_id, profile)` 的所有 ack 行。
- 改名站点（`app/db.py:749` 迁移 alert_state 处旁）：**迁移**而非删除——
  `UPDATE alert_acks SET profile=:new WHERE user_id=:uid AND profile=:old`，否则改名后静音全丢。

### 前端 `SitesView.vue`

告警卡区改为受控折叠组件（`const alertExpanded = ref(false)`，**不用原生 `<details>`**——
多状态联动撑不住；注意别和 `SitesView.vue:62` 已有的 `<details class="tasks-fold">` 混淆）。

数据分组：`alerts` 全量 → `visibleAlerts = alerts.filter(a => !a.acked)`、
`mutedAlerts = alerts.filter(a => a.acked)`。

1. **默认折叠**：摘要条 `⚠ 告警中 {{ N }}（站点×模型） ▸`，`N=0` 时整块不显示。
   - **N 口径钉死**：`N = alerts.length`（全量，含已忽略），与顶部健康条 `告警中`（`SitesView.vue:46`，
     当前 `alerts.length`）口径一致。「已忽略 K」是 N 的子集说明，**不是 N−K**。
2. **展开后限高**：展开后 `visibleAlerts` 默认渲染前 5 条；超出显示「还有 M 条 ▾」，
   可「展开全部 / 收起」（再加一个 `showAllVisible` ref）。
3. **逐条忽略**：每张卡加「忽略」按钮 → `POST /api/alerts/ack` → 乐观把该条 `acked` 置 true（移出 visible、进 muted）。
   失败则回滚（恢复 `acked=false` + toast）。
4. **找回（极简）**：摘要条尾部 `· 已忽略 {{ mutedAlerts.length }} 条 · 显示`（纯链接，`showMuted` ref）。
   点「显示」→ 平铺 `mutedAlerts`，每条带「取消忽略」→ `POST /api/alerts/unack` → `acked=false` 回到 visible。
   不做独立面板、不做独立列表 API。
5. **卡片 `:key`**：去掉数组下标 `i`（当前 `SitesView.vue:25` 是 `a.profile+'/'+a.model+'/'+i`），
   改 `a.profile + '/' + a.model`（同格唯一），避免乐观移除后 Vue diff 错乱。
6. 轮询/刷新（`loadStatic`，`SitesView.vue:367`）整体替换 `alerts`，acked 由后端回带，最省心。

## 测试

**后端**
- ack → `/api/alerts/active` 该条 `acked=true`；unack → `acked=false`。
- recover 动作清除对应 ack 行（state 未变也清）。
- 删除站点清 ack；改名站点迁移 ack（新名下仍静音）。
- `ON CONFLICT DO NOTHING` 重复 ack 幂等、不报错。
- model 为空字符串时 ack 唯一键正常约束（不插重复）。

**前端**
- `N=0` 整块不显示；默认折叠。
- 展开限高前 5 条 + 「还有 M 条」展开/收起。
- 忽略乐观移除、失败回滚。
- 「已忽略 K · 显示」平铺 + 取消忽略回到 visible。
- 摘要条 N == 顶部健康条 `告警中`（含已忽略）。
