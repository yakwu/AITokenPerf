# 拨测告警「按站点×模型」细分策略 · 设计文档

> 日期：2026-06-09
> 关联：issue #56；在 #30（告警闭环）/ #33（告警器解耦）之上的策略增强
> 状态：设计已确认（方向/粒度/呈现/状态存储/阈值粒度均与用户对齐），待写 implementation plan

---

## 问题

现有告警（#30/#33）触发口径是**任务级整体成功率**：`_maybe_send_alert`
（`scheduler.py:227`）用 `get_run_success_rate(run_ids)`（`db.py:846`）把一轮**全部** result
行的 `success_count/total_requests` 揉成**一个**总数，跌破任务阈值才发飞书。

这带来**稀释漏报**：一个定时任务常绑多个站点（profile）、每站点测多个模型，一轮拨测其实是
「站点 × 模型」的矩阵。某个模型/某个站点挂了，会被其他正常格子的好成绩稀释，整体成功率仍在
阈值之上 → **该报没报**。这与产品近期「按模型看数据」的方向（切模型、按模型筛选趋势）也不一致。

## 目标

- 告警判定从「任务级整体」下沉到**每个「站点×模型」格子各自判断**，消除稀释漏报。
- 同一轮多个格子同时翻转时，**聚合成一条飞书卡**（新告警一条红卡、新恢复一条绿卡），不刷屏。
- 改动集中在后端策略层，**前端配置（开关/阈值/选告警器）与拨测主流程不动**。

## 非目标（YAGNI）

- 不做每模型/每站点单独阈值（阈值仍任务级共用一个）。
- 不做延迟/质量维度触发（本轮只把**成功率**这一维度细分；延迟突增、质量下降留后续）。
- 不做「连续 N 次才报」防抖（沿用单次跌破即翻转；以后要再加）。
- 不做前端「格子告警状态」面板。
- 不新建 `alert_states` 表（用 JSON 字段，见下）。
- 不动通知渠道（仍飞书；多渠道是另一条线）。

---

## 核心决策（已与用户对齐）

| 维度 | 决定 |
|---|---|
| 触发粒度 | 每个 **(站点 profile, 模型 model)** 格子独立判断 |
| 成功率口径 | 按格子分组：该格子本轮**跨所有并发档**的 `success/total` 累加 |
| 状态存储 | 复用 `scheduled_tasks.alert_state` 列（TEXT），值从单值改为 **JSON**：`{站点: {模型: 状态}}` |
| 阈值粒度 | **任务级共用一个**（`alert_threshold`，默认 90），所有格子同一阈值 |
| 判定逻辑 | 每格独立跑现有 `evaluate_alert`，**单次跌破即翻转**（不变） |
| 告警呈现 | **聚合**：本轮新转告警的格子汇成一条红卡；新恢复的汇成一条绿卡；无翻转不发 |
| 前端 | 不动（配置项语义不变） |

---

## 设计

### 1. 数据模型：`alert_state` JSON 化（不新增表、不新增列）

- 列定义不变：`scheduled_tasks.alert_state TEXT NOT NULL DEFAULT 'ok'`
  （SQLite `db.py:123`、PG `db.py:233`、迁移 `db.py:339/351`）——**无需 DDL 改动**。
- 值语义改变：由单值 `'ok'|'alerting'` → JSON 字符串，结构：
  ```json
  {"站点A": {"gpt-4o": "alerting", "claude": "ok"}, "站点B": {"gpt-4o": "ok"}}
  ```
- 写回白名单**已包含 `alert_state`**（`update_scheduled_task` 的 `allowed`，`db.py:1414`），
  无需改动。
- **读侧兼容**：新增纯函数 `_load_alert_states(raw) -> dict`：`json.loads`，若结果非 dict 或
  解析失败（存量任务的裸值 `'ok'`/`'alerting'` 会 `JSONDecodeError`）→ 返回 `{}`。
  存量任务首轮按当前格子重建，平滑过渡，无需数据迁移。
- **自动清残留**：每轮写回时**只保留本轮真实出现的格子**。任务增删站点/模型后，旧格子的
  key 自然不再带入 → 状态字典随当前矩阵收敛，不积累垃圾。

### 2. 成功率分组（`app/db.py`）

新增 DB 助手（旧 `get_run_success_rate` 仅 `scheduler.py:241` 一处调用，由新函数替代，
连同其单测一并移除，避免死代码）：

```python
async def get_run_success_rate_by_cell(run_ids: list) -> dict[tuple[str, str], tuple[int, int]]:
    """按 (profile_name, model) 分组聚合本轮 result 行的 (success, total)。"""
```

- SQL：`SELECT profile_name, config_json, summary_json FROM results WHERE run_id IN (...)`
  （沿用现有占位符参数化写法，跨 SQLite/PG）。
- 分组键：
  - 站点 = `profile_name` 独立列（`db.py:313` 迁移已加）；为空时回退 `config_json.get("profile_name")`。
  - 模型 = `json.loads(config_json).get("model")`（与 `db.py:1268/1716` 现有取法一致）；
    缺失归为 `"-"`，仍计入但模型名显示 `-`。
- 同一 (站点, 模型) 的多条并发档行累加，得该格子整体 success/total。
- 在 **Python 端**解析 JSON 分组（不依赖 `jsonb` 操作符），保证双方言一致。

### 3. 判定 + 聚合（重写 `scheduler._maybe_send_alert`，`scheduler.py:227-255`）

```
cells   = await get_run_success_rate_by_cell(run_ids)      # {(profile,model): (s,t)}
prev    = _load_alert_states(task_row.get("alert_state"))  # {profile:{model:state}}
thr     = int(task_row.get("alert_threshold") or 90)
new     = {}                       # 本轮写回的状态字典（只含本轮格子）
alerts, recovers = [], []          # 聚合：本轮新翻转的格子

for (profile, model), (s, t) in cells.items():
    p_state = prev.get(profile, {}).get(model, "ok")
    if t == 0:                     # 没真发出请求（容量不足/跳过）→ 不评估、保留旧态
        new.setdefault(profile, {})[model] = p_state
        continue
    rate = s / t * 100
    n_state, action = evaluate_alert(p_state, rate, thr)   # 复用 notifier 现有纯函数
    new.setdefault(profile, {})[model] = n_state
    if action == "alert":   alerts.append((profile, model, rate))
    elif action == "recover": recovers.append((profile, model, rate))
```

- 守卫照旧：`alert_enabled` 关 / `alert_notifier_id` 为 0 / 告警器查不到 webhook → 直接 return
  （`scheduler.py:233-240` 逻辑保留）。
- **发卡（聚合）**：`alerts` 非空 → 发一条红卡；`recovers` 非空 → 发一条绿卡。各最多一条。
- **写回**：`new` 序列化 JSON → `update_scheduled_task(task_id, alert_state=...)`；仅当
  `new != prev` 时写（省一次写）。
- **权衡保留**：先发卡、无论推送成功失败都按判定写回新状态（单次推送失败 → 那次漏报，下次
  翻转再发），不引入重试队列。与现状一致。
- **多 worker 安全**：`claim_scheduled_task` 保证同任务每轮单 worker，JSON 读-改-写无并发，
  与现状同构。

### 4. 飞书卡片（改 `notifier.build_feishu_card`，`notifier.py:48`）

现签名按单格设计：`build_feishu_card(kind, task_name, profile, rate, threshold, ts)`。
改为吃**格子列表**：

```python
def build_feishu_card(kind: str, task_name: str,
                      cells: list[tuple[str, str, float]],  # [(profile, model, rate), ...]
                      threshold: int, ts: str) -> dict:
```

- 红卡（`kind='alert'`）：头部 `template:"red"`，标题「🔴 拨测告警」；正文逐行列每个掉线格子
  `站点 / 模型 / 成功率`（红）；底部 note 标注 `阈值 {threshold}% · {ts} · AITokenPerf`。
- 绿卡（`kind='recover'`）：头部 `template:"green"`，标题「✅ 已恢复」；逐行列恢复的格子。
- 行用独立 `div`/`lark_md` 渲染，含 `config.wide_screen_mode`（沿用现有结构）。
- `evaluate_alert` / `send_webhook` / `is_allowed_webhook` / `_safe_host` **不变**。
- `scheduler.py:250` 的 `profiles_text` 拼接逻辑随之删除（卡片改逐格列）。

### 5. 边界 & 安全

- 某格 `total == 0`：不评估、保留旧态写回（见 §3），不把"没跑成"误判为成功/失败。
- 全轮无任何格子（`cells` 空）：不发、不写回（或写空字典，等价）。
- 告警评估整段仍由 `_run_scheduled_task` 末尾 try/except 兜底（`scheduler.py:389-393`），
  坏了只 `log_error`，不拖累拨测与重调度。
- SSRF（限飞书域名）、日志脱敏、best-effort 发送：**全部不变**。

### 6. 前端

**不动**。开关 `alert_enabled`、阈值 `alert_threshold`、告警器 `alert_notifier_id` 仍在任务级，
表单与语义不变（`SiteSchedulesTab.vue` / `TasksView.vue` / 告警器管理页均无需改）。

### 7. 测试策略

- **`get_run_success_rate_by_cell`**：多站点 × 多模型 × 多并发档正确分组累加；`profile_name`
  空回退 `config_json`；`model` 缺失归 `-`；空 run_ids 返回空。
- **`_load_alert_states`**：合法 JSON 正常解析；存量裸值 `'ok'`/`'alerting'` → `{}`；空串 → `{}`。
- **`_maybe_send_alert`（per-cell 聚合）**：
  - A 格挂、B 格好 → 只 `alerts` 含 A，红卡仅 A；
  - 同轮 A 恢复、B 挂 → 红卡含 B、绿卡含 A，各一条；
  - 全好且原全好 → 不发、不写回；
  - 某格 `total=0` → 跳过评估但保留旧态；
  - 写回 JSON 结构正确、旧格子被剔除。
- **`build_feishu_card`（列表版）**：红卡多行、绿卡多行、阈值/时间 note、`wide_screen_mode`。
- **回归**：`evaluate_alert` 现有纯函数单测不变（仍逐格调用）。
- 旧的 `build_feishu_card` 单格签名单测、`get_run_success_rate` 单测**迁移/移除**。
- 不依赖真实网络（沿用 monkeypatch `send_webhook`）。

---

## 影响面

- `app/db.py`：新增 `get_run_success_rate_by_cell`；移除旧 `get_run_success_rate`（仅一处引用）。
  **无 DDL / 白名单改动**（`alert_state` 列与白名单复用）。
- `app/scheduler.py`：重写 `_maybe_send_alert`（分组成功率 + 每格判定 + 聚合发卡 + JSON 状态
  读写）；删 `profiles_text` 拼接。
- `app/notifier.py`：`build_feishu_card` 改列表版 + 新增 `_load_alert_states`（或放 scheduler，
  就近即可）。`evaluate_alert`/`send_webhook`/SSRF 不变。
- 测试：`tests/test_alert_db.py` / `test_alert_scheduler.py` / `test_notifier.py` 相应增改。
- 前端：**无**。

## 向后兼容

- `alert_state` 列复用，存量裸值读时兼容为 `{}`，存量任务首轮重建，无需数据迁移。
- 阈值/开关/告警器语义不变，存量任务 `alert_enabled=false` 不受影响。

---

*实现前请对照当前代码复核 file:line（基于 2026-06-09 main）。*
