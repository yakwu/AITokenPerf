# 定时拨测失败告警闭环 · 设计文档

> 日期：2026-06-04
> 关联：issue #30（F1，来自 `docs/2026-06-03-product-analysis-and-roadmap.md` 最高优先项）
> 状态：设计已确认，待转 implementation plan

---

## 问题

产品定位是「无人值守的 LLM 定时拨测 + 质量监控」，但告警**完全不闭环**：

- 通知是纯前端内存态 `ref([])`（`frontend/src/composables/useNotifications.js:3`），刷新即丢。
- 依赖「页面开着 + `ScheduleIndicator` 每 5 秒轮询侦测任务消失」才产生通知。
- 后端无任何 webhook/邮件推送；`scheduler._run_scheduled_task` 任务失败只 `log_error`。

结果：**关了浏览器，夜里渠道全挂也无人知晓。** 这是产品定位与实现差距最大的一处。

## 目标

- 定时拨测成功率低于阈值时，**主动推送告警到外部 IM**（无需用户开着页面）。
- 渠道恢复时推送恢复通知。
- 避免告警疲劳（拨测每 5 分钟一次，持续异常不刷屏）。

## 非目标（YAGNI，留二期）

- 邮件 / 多平台适配（v1 只做飞书 webhook）。
- 延迟突增（P99 超阈值）等更多触发维度。
- 告警历史持久化、重试队列。
- 替换现有的前端内存通知中心（本功能与之并存，不动它）。

---

## 核心决策（已确认）

| 维度 | 决定 |
|---|---|
| 通道 | 通用 Webhook，默认**飞书自定义机器人卡片**格式 |
| 配置粒度 | **每个定时任务单独配**（webhook URL + 阈值 + 开关） |
| 触发规则 | 成功率 < 阈值（默认 90%）视为异常；**仅状态翻转时推送**（正常→异常 发告警，异常→恢复 发恢复） |

---

## 设计

### 1. 数据模型

在 `scheduled_tasks` 表扩展 4 列（独立列而非塞进 `configs_json`，因 `alert_state` 每轮拨测后要更新）：

| 列 | 类型 | 默认 | 用途 |
|---|---|---|---|
| `alert_webhook` | TEXT | `''` | 飞书机器人 webhook URL，空=不告警 |
| `alert_threshold` | INTEGER | `90` | 成功率阈值（%），低于即异常 |
| `alert_enabled` | INTEGER(SQLite)/BOOLEAN(PG) | false | 告警总开关 |
| `alert_state` | TEXT | `'ok'` | 当前状态 `ok` / `alerting`，用于状态翻转去重 |

迁移：SQLite 用 `ALTER TABLE ... ADD COLUMN`（沿用 `db.py` 现有列迁移模式，try/except 忽略已存在）；Postgres 用 `ADD COLUMN IF NOT EXISTS`。双模兼容。

### 2. 触发评估

挂在 `scheduler._run_scheduled_task` 完成处（`scheduler.py:350` 附近，已 `gather` 完所有 bench task）：

1. **算成功率**：从 `manager.get_run_tasks(run_id)` 的 bench task 聚合 `success_rate = sum(success_count) / sum(total_count) * 100`（**百分比**，与 `alert_threshold` 同单位；运行中已维护这些字段，无需重查 DB）。
   - **边界 `total_count == 0`**（任务因容量不足/无 profile 等没真正发出请求）：无法评估成功率，**跳过告警评估、不改 `alert_state`、记一条 log**。不把"没跑成"误判为成功或失败。
2. **纯函数判定**：
   ```python
   def evaluate_alert(prev_state: str, success_rate: float, threshold: int) -> tuple[str, str | None]:
       """返回 (新状态, 动作)。动作 ∈ {None, 'alert', 'recover'}。"""
       abnormal = success_rate < threshold
       if abnormal and prev_state == 'ok':
           return 'alerting', 'alert'
       if not abnormal and prev_state == 'alerting':
           return 'ok', 'recover'
       return prev_state, None   # 状态未翻转 → 不推送（防刷屏）
   ```
3. 按动作发卡片，并把新 `alert_state` 写回 DB。
4. 整段包在 try/except——**告警失败绝不影响拨测主流程与重调度**。
5. 仅当 `alert_enabled` 且 `alert_webhook` 非空时才评估。

### 3. Webhook 推送（`app/notifier.py`）

构造与发送分离，便于单测：

- `build_feishu_card(kind, task_name, profile, rate, threshold, ts) -> dict`
  - `kind='alert'`：红色头部 `template:"red"`，标题「🔴 拨测告警」，成功率红色。
  - `kind='recover'`：绿色头部 `template:"green"`，标题「✅ 已恢复」，成功率绿色。
- `async def send_webhook(url, payload, timeout=10) -> bool`
  - aiohttp POST JSON，**best-effort**：超时/非 2xx/异常只 `log` 并返回 False，**不重试、不抛**。

飞书卡片结构：

```json
{
  "msg_type": "interactive",
  "card": {
    "header": { "template": "red", "title": {"tag":"plain_text","content":"🔴 拨测告警"} },
    "elements": [
      { "tag": "div", "fields": [
        {"is_short": true, "text": {"tag":"lark_md","content":"**任务**\n<name>"}},
        {"is_short": true, "text": {"tag":"lark_md","content":"**站点**\n<profile>"}},
        {"is_short": true, "text": {"tag":"lark_md","content":"**成功率**\n<font color='red'>72%</font>"}},
        {"is_short": true, "text": {"tag":"lark_md","content":"**阈值**\n90%"}}
      ]},
      { "tag": "hr" },
      { "tag": "note", "elements": [{"tag":"lark_md","content":"⏰ 2026-06-04 10:30 · AITokenPerf"}] }
    ]
  }
}
```

### 4. 前端配置入口

- 定时任务创建/编辑表单（`TasksView.vue` 及/或 `SiteSchedulesTab.vue`）加「告警」折叠区：
  - 开关 `alert_enabled`
  - webhook URL 输入 `alert_webhook`
  - 阈值数字框 `alert_threshold`（默认 90）
  - 「发送测试消息」按钮
- 后端 `POST /api/schedules/{id}/alert-test`：用当前配置发一条测试飞书卡片，返回成功/失败，供前端验证 URL 通不通。
- 创建/更新定时任务的端点扩展，接收并持久化这 3 个配置字段。

### 5. 错误处理

- webhook 失败：`notifier.send_webhook` 吞掉异常、log、返回 False；不影响 `alert_state` 写回（即使推送失败也按判定结果更新状态，避免下轮重复尝试刷屏——可在文档注明此权衡）。
- 评估逻辑异常：被 `_run_scheduled_task` 完成处的 try/except 兜住，记 `log_error`，拨测照常重调度。

### 6. 测试策略

- **`evaluate_alert` 纯函数单测**：ok→abnormal 发 alert、持续 abnormal 不发、abnormal→ok 发 recover、持续 ok 不发、边界（rate==threshold 视为正常）。
- **`build_feishu_card` 单测**：alert 红头、recover 绿头、字段内容正确。
- **`send_webhook` 单测**：mock aiohttp，验证 POST payload、超时/非 2xx 返回 False 不抛。
- 不依赖真实网络。

---

## 影响面

- 改动文件：`app/db.py`（建表+迁移列）、`app/scheduler.py`（评估接入）、新增 `app/notifier.py`、`app/server.py`（任务 CRUD 扩展 + alert-test 端点）、前端 `TasksView.vue`/`SiteSchedulesTab.vue`、新增测试。
- 向后兼容：新列均有默认值，存量任务 `alert_enabled=false` 不受影响。

---

*实现前请对照当前代码复核 file:line（基于 2026-06-04 main）。*
