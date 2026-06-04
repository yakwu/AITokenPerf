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
| 聚合口径 | **任务级单状态**（已与用户确认：一个定时任务只绑一个渠道）。成功率聚合该任务本轮全部结果。多 profile 任务超出 v1 范围——若存在则按全量聚合（可能掩盖单站故障），文档注明 |

> **设计前提（用户确认）**：定时任务为「一个任务一个渠道」。因此任务级一个 `alert_state` 足够，无需 per-profile 状态。

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

**⚠️ 必须同步改的代码点（review 发现，遗漏任一功能即失效）**：
- 两处建表 DDL 都要加列：`db.py` 的 `_SQLITE_SCHEMA`（`scheduled_tasks` 约 107-122）与 `_PG_SCHEMA`（约 202）。
- `create_scheduled_task`（`db.py:1074`）的 INSERT 语句与函数签名要接收 `alert_webhook/alert_threshold/alert_enabled`。
- **`update_scheduled_task` 的 `allowed` 白名单（`db.py:1145`）必须加入 4 个 alert 列**——否则写回 `alert_state` 被静默丢弃，状态机永远翻不了车（这是会让功能完全失效的隐蔽漏点）。
- `update_schedule` 路由自己的 `allowed` 白名单（`server.py:2079`）也要加 `alert_webhook/alert_threshold/alert_enabled`。
- 读侧 `get_scheduled_task(s)` 用 `SELECT *`，新列自动带出，无需改。

### 2. 触发评估

挂在 `scheduler._run_scheduled_task` 完成处（`scheduler.py:350` 附近，已 `gather` 完所有 bench task）：

1. **算成功率**（⚠️ review 修正：不能用 bench task 的 `success_count/total_count`）：
   - 原因：`server.py:373-376` 每进入一个新并发 level 就把这些计数**清零**，任务跑完后它们只反映**最后一档并发**，不是全程。直接用会算错、发出错误告警。
   - 正确来源：**聚合本轮落库的 result 行**。`_run_scheduled_task` 已知本轮各 run 的 `run_id`（`_start_run_for_profile` 返回）与 bench task 的 `result_filenames`。新增 DB 助手 `get_run_success_rate(run_ids)`：读这些 run 的 result 行，从 `summary_json` 累加 `success_count` 与 `total_requests`，`success_rate = 总成功 / 总请求 * 100`（**百分比**，与 `alert_threshold` 同单位）。
   - **边界 `总请求 == 0`**（容量不足/无 profile 等没真正发出请求）：无法评估，**跳过评估、不改 `alert_state`、记一条 log**。不把"没跑成"误判为成功或失败。
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
3. 按动作发卡片，并用 `update_scheduled_task(task_id, alert_state=新状态)` 写回（依赖上面的白名单修正）。
4. 整段包在 try/except——**告警失败绝不影响拨测主流程与重调度**。放在 `_run_scheduled_task` 末尾、`_release_and_reschedule` 之前；与重调度操作不同列、各自独立事务，无冲突。
5. 仅当 `alert_enabled` 且 `alert_webhook` 非空时才评估。
6. **权衡（明确记录）**：先发卡片、无论成功失败都写回新 `alert_state`。这样网络抖动导致单次推送失败时，状态仍翻转、不会下一轮重发刷屏——代价是**那一次告警漏报**，要等下次状态再翻转才会再发。v1 接受此简化（不引入重试队列）。
7. **多 worker 安全**：`claim_scheduled_task`（`db.py:1222`）保证同一任务每轮只有一个 worker 执行，故评估也只跑一次，不会重复推送。

### 3. Webhook 推送（`app/notifier.py`）

构造与发送分离，便于单测：

- `build_feishu_card(kind, task_name, profile, rate, threshold, ts) -> dict`
  - `kind='alert'`：红色头部 `template:"red"`，标题「🔴 拨测告警」，成功率红色。
  - `kind='recover'`：绿色头部 `template:"green"`，标题「✅ 已恢复」，成功率绿色。
- `async def send_webhook(url, payload, timeout=10) -> bool`
  - **先做 SSRF 校验**（见下），再 aiohttp POST JSON，**best-effort**：超时/非 2xx/异常只 `log` 并返回 False，**不重试、不抛**。
  - **日志脱敏**：失败 log **不得打印完整 URL**（webhook URL 含 secret token），只记 host 或脱敏后的串。

**⚠️ SSRF 防护（review 发现的安全硬伤，必须做）**：
本服务是公网多租户（app.aitokenperf.com），用户可填任意 `alert_webhook`，后端会主动 POST。若不限制，攻击者可填内网地址（`http://169.254.169.254/...` 云元数据、`http://localhost:...` 内部服务）让服务端代为请求。v1 防护：
- **只允许飞书域名**：`open.feishu.cn` / `open.larksuite.com`，且必须 `https://`。其余一律拒绝（配置保存时校验 + 发送前再校验，双重）。
- 这同时收窄了 SSRF 面、又契合 v1「只做飞书」的范围。换平台时再扩白名单。

飞书卡片结构（含 `config.wide_screen_mode`，官方示例标配）：

```json
{
  "msg_type": "interactive",
  "card": {
    "config": { "wide_screen_mode": true },
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

> 颜色提示：`<font color='red'>` 在飞书 `lark_md` 不同客户端版本渲染不一致，可能原样显示标签。状态已由红/绿头部表达，成功率文字可保留 `<font>` 但**实现后需用真机器人验证**；不渲染则退化为纯文字，不影响功能。

### 4. 前端配置入口

- **两个入口都要改**（避免只改一处导致另一入口建的任务配不了告警）：定时任务创建/编辑表单在 `frontend/src/views/TasksView.vue`（约 289/297）与 `frontend/src/components/SiteSchedulesTab.vue`。加「告警」折叠区：
  - 开关 `alert_enabled`
  - webhook URL 输入 `alert_webhook`
  - 阈值数字框 `alert_threshold`（默认 90）
  - 「发送测试消息」按钮
- 后端 `POST /api/schedules/{id}/alert-test`：用当前配置发一条测试飞书卡片，返回成功/失败，供前端验证 URL 通不通。**必须照抄现有 schedules 路由的归属校验**（`Depends(get_current_user)` + `task_row["user_id"] != user_id` 拒绝，参 `server.py:2071-2078`）。
- 创建/更新定时任务的端点扩展，接收并持久化这 3 个配置字段。
- **输入校验**：`alert_threshold` 限 0–100；`alert_webhook` 非空时校验为合法 `https://` 飞书域名（与 SSRF 白名单一致），不合法则保存报错。

### 5. 错误处理

- webhook 失败：`notifier.send_webhook` 吞掉异常、log、返回 False；不影响 `alert_state` 写回（即使推送失败也按判定结果更新状态，避免下轮重复尝试刷屏——可在文档注明此权衡）。
- 评估逻辑异常：被 `_run_scheduled_task` 完成处的 try/except 兜住，记 `log_error`，拨测照常重调度。

### 6. 测试策略

- **`evaluate_alert` 纯函数单测**：ok→abnormal 发 alert、持续 abnormal 不发、abnormal→ok 发 recover、持续 ok 不发、边界（rate==threshold 视为正常）。
- **成功率聚合单测**：跨多档并发/多 result 行正确累加（覆盖 level 清零 bug 的回归）；总请求=0 跳过。
- **`build_feishu_card` 单测**：alert 红头、recover 绿头、字段内容正确、含 `wide_screen_mode`。
- **SSRF 校验单测**：飞书域名放行；`localhost`/私网 IP/非飞书域名/http 一律拒绝。
- **`send_webhook` 单测**：mock aiohttp，验证 POST payload、超时/非 2xx 返回 False 不抛、失败日志不含完整 URL。
- 不依赖真实网络。

---

## 影响面

- 改动文件：
  - `app/db.py`：两处建表 DDL 加列、迁移加列、`create_scheduled_task` INSERT+签名、**`update_scheduled_task` allowlist 加 4 列**、新增 `get_run_success_rate(run_ids)` 助手。
  - `app/scheduler.py`：`_run_scheduled_task` 末尾接入评估（用落库结果算成功率 + `evaluate_alert` + 写回 + 发卡片）。
  - 新增 `app/notifier.py`：`build_feishu_card` / `send_webhook`（含 SSRF 校验 + 日志脱敏）。
  - `app/server.py`：`create_schedule`/`update_schedule` 接收 alert 字段（**`update_schedule` allowlist 加 3 列** + 输入校验）、新增 `POST /api/schedules/{id}/alert-test`。
  - 前端 `TasksView.vue` + `SiteSchedulesTab.vue`：告警配置区 + 测试按钮。
  - 测试：`evaluate_alert` / 成功率聚合 / `build_feishu_card` / SSRF / `send_webhook`。
- 向后兼容：新列均有默认值，存量任务 `alert_enabled=false` 不受影响。

---

*实现前请对照当前代码复核 file:line（基于 2026-06-04 main）。*
