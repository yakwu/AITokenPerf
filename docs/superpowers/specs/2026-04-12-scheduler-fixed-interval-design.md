# 定时任务调度器重构：固定间隔执行

## 背景

当前定时任务调度器存在以下问题：

1. **next_run_at 在任务完成后才更新** — 如果 `_release_and_reschedule` 失败，next_run_at 停留在过去，导致任务每 5 秒被 poll 循环重复触发
2. **不是真正的固定间隔** — 执行时间影响下次调度时间
3. **锁时长固定 3600 秒** — 与任务超时不匹配，存在锁过期但任务还在跑导致重复执行的风险
4. **jitter 积累漂移** — 当前没有 jitter，但如果加到 next_run_at 上会导致长期漂移

## 目标

- 固定间隔执行（wall-clock interval），不受任务执行时间影响
- 防突发：多任务同时到期时错开 0-10 秒启动
- 杜绝"循环触发"的 bug
- 多 worker 安全

## 设计

### 核心变更：Claim 时推进 next_run_at

**当前流程（有问题）**：
```
poll → claim(只拿锁) → 执行 → 完成后 reschedule(设 next_run_at) + 释放锁
```

**新流程**：
```
poll → claim_and_advance(拿锁 + 推进 next_run_at) → sleep(jitter) → 执行 → release(只释放锁)
```

#### claim_and_advance_scheduled_task

单条原子 SQL UPDATE：

```sql
UPDATE scheduled_tasks
SET locked_until = NOW() + :timeout_seconds + 30,
    next_run_at = next_run_at + :interval_seconds,
    updated_at = NOW()
WHERE id = :tid
  AND status = 'active'
  AND (locked_until IS NULL OR locked_until < NOW())
  AND (/* 全局并发限制 */)
  AND (/* 用户并发限制 */)
RETURNING next_run_at, schedule_value, ...
```

关键点：
- `next_run_at = next_run_at + interval`（基于当前存储值，不依赖任何运行时计算）
- `locked_until = now + timeout + 30秒缓冲`
- DB 保证原子性，多 worker 只有一个能成功
- 即使后续所有步骤失败，next_run_at 已经指向未来，不会循环触发

#### 执行前 Jitter

claim 成功后，执行前加随机延迟：

```python
await asyncio.sleep(random.uniform(0, 10))
```

- jitter 不写入 DB，不影响 next_run_at
- 仅影响实际启动时刻，防止多个任务同时发起 API 请求

#### 执行完成后

只需要：
- 释放锁：`locked_until = NULL`
- 更新统计：`last_run_at = now`, `run_count += 1`
- **不需要 reschedule**（next_run_at 已经在 claim 时设好了）

### 超时时间

- 默认 120 秒，可自定义
- 约束：`timeout <= interval`
- 如果 interval < 120 秒，timeout 自动降为 interval 值
- 创建/编辑 API 端校验此约束

#### DB Schema 变更

`scheduled_tasks` 表新增字段：

```sql
timeout TEXT NOT NULL DEFAULT '120'
```

#### 锁时长计算

```
locked_until = now + timeout + 30秒缓冲
```

| 间隔     | 超时  | 锁时长 |
| -------- | ----- | ------ |
| 5 分钟   | 120s  | 150s   |
| 1 小时   | 120s  | 150s   |
| 60 秒    | 60s   | 90s    |

### 并发超限处理

当全局或用户并发达到上限时：
- 跳过本次执行（claim SQL 的 WHERE 子句直接过滤）
- 记录日志（log_error）
- 通过 ScheduleIndicator 组件通知用户

通知格式：`"定时任务 '任务名' 因并发超限被跳过（10:08），将在 10:13 正常执行"`

### 边界情况

| 场景               | 处理方式                                                     |
| ------------------ | ------------------------------------------------------------ |
| 服务重启           | next_run_at 为空的任务设为 `now`（现有逻辑保留）             |
| 暂停后恢复         | `next_run_at = now`（从恢复时间开始新周期）                  |
| run-now            | 单独 claim（不推进 next_run_at），额外执行一次               |
| claim 失败（已锁） | 跳过，等下个周期                                             |
| 多 worker 同时 poll | DB 原子 UPDATE 保证只有一个 worker 拿到锁                    |
| reschedule 后 next_run_at 仍在过去 | 不可能发生（claim 时 next_run_at 已推进到未来） |

### 删除的代码

- `_release_and_reschedule` 方法 — 不再需要
- `release_and_reschedule_scheduled_task` DB 函数 — 不再需要

### 新增/修改的代码

| 文件 | 变更 |
| --- | --- |
| `app/db.py` | 新增 `claim_and_advance_scheduled_task`，新增 `release_and_update_scheduled_task`（只释放锁+更新统计），schema 新增 timeout 字段 |
| `app/scheduler.py` | 重构 `_run` 循环调用新 claim 函数，删除 `_release_and_reschedule`，执行前加 jitter |
| `app/server.py` | 创建/编辑 API 校验 timeout <= interval，run-now 使用不推进 next_run_at 的 claim |
| `frontend` | 创建/编辑表单增加超时配置（可选），跳过通知展示 |
