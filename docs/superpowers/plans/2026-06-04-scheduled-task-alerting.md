# 定时拨测失败告警闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 定时拨测成功率低于阈值时，主动推送飞书卡片告警（含恢复通知），无需用户开着页面。

**Architecture:** 每个定时任务配 webhook+阈值（存 `scheduled_tasks` 新列）。`scheduler._run_scheduled_task` 跑完后，从落库结果聚合成功率，纯函数 `evaluate_alert` 判定状态翻转，仅翻转时发卡片并写回 `alert_state`。告警逻辑集中在新模块 `app/notifier.py`，best-effort、SSRF 限飞书域名、不影响拨测主流程。

**Tech Stack:** Python / FastAPI / SQLAlchemy(SQLite+Postgres 双模) / aiohttp / pytest / Vue 3。

**关联 spec:** `docs/superpowers/specs/2026-06-04-scheduled-task-alerting-design.md`（issue #30）

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `app/notifier.py`（新建） | 告警纯逻辑：`evaluate_alert` 状态机、`is_allowed_webhook` SSRF 校验、`build_feishu_card` 卡片构造、`send_webhook` 发送 |
| `app/db.py`（改） | `scheduled_tasks` 加 4 列（两处 DDL + 迁移）、`create_scheduled_task` 扩参、`update_scheduled_task` 白名单加列、新增 `get_run_success_rate` |
| `app/scheduler.py`（改） | `_maybe_send_alert` + 在 `_run_scheduled_task` 末尾接入（捕获 run_ids、try/except） |
| `app/server.py`（改） | create/update schedule 接收+校验告警字段、新增 `POST /api/schedules/{id}/alert-test` |
| `frontend/src/views/TasksView.vue`（改） | 任务表单告警配置区 + 测试按钮 |
| `frontend/src/components/SiteSchedulesTab.vue`（改） | 同上（另一入口） |
| `tests/test_notifier.py`、`tests/test_alert_db.py`、`tests/test_alert_scheduler.py`、`tests/test_alert_api.py`（新建） | 单测 |

约定：后端 TDD（pytest），每个 Task 末尾提交。前端 implement + `bun run build` 校验。

---

### Task 1: notifier — evaluate_alert 状态机

**Files:**
- Create: `app/notifier.py`
- Test: `tests/test_notifier.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_notifier.py
from app.notifier import evaluate_alert


def test_alert_fires_on_ok_to_abnormal():
    assert evaluate_alert("ok", 72.0, 90) == ("alerting", "alert")


def test_no_repeat_while_abnormal():
    assert evaluate_alert("alerting", 50.0, 90) == ("alerting", None)


def test_recover_on_abnormal_to_ok():
    assert evaluate_alert("alerting", 95.0, 90) == ("ok", "recover")


def test_no_action_while_ok():
    assert evaluate_alert("ok", 99.0, 90) == ("ok", None)


def test_threshold_boundary_is_normal():
    # rate == threshold 用 < 判定 → 视为正常
    assert evaluate_alert("ok", 90.0, 90) == ("ok", None)
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_notifier.py -q`
Expected: FAIL（`ModuleNotFoundError: app.notifier`）

- [ ] **Step 3: 实现**

```python
# app/notifier.py
#!/usr/bin/env python3
"""告警通知模块：状态机判定 + 飞书卡片 + webhook 发送（SSRF 限飞书域名）。"""

import logging
from typing import Optional, Tuple
from urllib.parse import urlparse

import aiohttp

log = logging.getLogger("notifier")

ALERT_OK = "ok"
ALERT_ALERTING = "alerting"
FEISHU_ALLOWED_HOSTS = {"open.feishu.cn", "open.larksuite.com"}


def evaluate_alert(prev_state: str, success_rate: float, threshold: int) -> Tuple[str, Optional[str]]:
    """返回 (新状态, 动作)。动作 ∈ {None, 'alert', 'recover'}。仅状态翻转时给动作。"""
    abnormal = success_rate < threshold
    if abnormal and prev_state != ALERT_ALERTING:
        return ALERT_ALERTING, "alert"
    if not abnormal and prev_state == ALERT_ALERTING:
        return ALERT_OK, "recover"
    return prev_state, None
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_notifier.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add app/notifier.py tests/test_notifier.py
git commit -m "feat(notifier): 告警状态机 evaluate_alert (#30)"
```

---

### Task 2: notifier — is_allowed_webhook（SSRF 校验）

**Files:**
- Modify: `app/notifier.py`
- Test: `tests/test_notifier.py`

- [ ] **Step 1: 追加失败测试**

```python
# tests/test_notifier.py 追加
from app.notifier import is_allowed_webhook


def test_feishu_https_allowed():
    assert is_allowed_webhook("https://open.feishu.cn/open-apis/bot/v2/hook/xxx") is True


def test_larksuite_allowed():
    assert is_allowed_webhook("https://open.larksuite.com/open-apis/bot/v2/hook/xxx") is True


def test_http_rejected():
    assert is_allowed_webhook("http://open.feishu.cn/x") is False


def test_localhost_rejected():
    assert is_allowed_webhook("https://localhost/x") is False


def test_internal_ip_rejected():
    assert is_allowed_webhook("https://169.254.169.254/latest/meta-data") is False


def test_other_domain_rejected():
    assert is_allowed_webhook("https://evil.com/x") is False


def test_empty_rejected():
    assert is_allowed_webhook("") is False
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_notifier.py -k is_allowed -q` → 实际是 import 失败/未定义。
Expected: FAIL（`cannot import name 'is_allowed_webhook'`）

- [ ] **Step 3: 实现（追加到 app/notifier.py）**

```python
def _safe_host(url: str) -> str:
    """日志脱敏：只取 host，绝不打印含 secret 的完整 URL。"""
    try:
        return urlparse(url).hostname or "?"
    except Exception:
        return "?"


def is_allowed_webhook(url: str) -> bool:
    """SSRF 防护：仅允许 https 的飞书域名。其余（http/内网/localhost/任意域名）一律拒绝。"""
    if not url:
        return False
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme != "https":
        return False
    return p.hostname in FEISHU_ALLOWED_HOSTS
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_notifier.py -q`
Expected: PASS（12 passed）

- [ ] **Step 5: 提交**

```bash
git add app/notifier.py tests/test_notifier.py
git commit -m "feat(notifier): SSRF 限飞书域名 is_allowed_webhook (#30)"
```

---

### Task 3: notifier — build_feishu_card

**Files:**
- Modify: `app/notifier.py`
- Test: `tests/test_notifier.py`

- [ ] **Step 1: 追加失败测试**

```python
# tests/test_notifier.py 追加
from app.notifier import build_feishu_card


def test_alert_card_red_header():
    card = build_feishu_card("alert", "主力渠道", "OpenAI-A", 72.0, 90, "2026-06-04 10:30")
    assert card["msg_type"] == "interactive"
    assert card["card"]["config"]["wide_screen_mode"] is True
    assert card["card"]["header"]["template"] == "red"
    assert "告警" in card["card"]["header"]["title"]["content"]
    flat = str(card)
    assert "72.0%" in flat and "90%" in flat and "主力渠道" in flat


def test_recover_card_green_header():
    card = build_feishu_card("recover", "主力渠道", "OpenAI-A", 95.0, 90, "2026-06-04 10:30")
    assert card["card"]["header"]["template"] == "green"
    assert "恢复" in card["card"]["header"]["title"]["content"]
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_notifier.py -k card -q`
Expected: FAIL（`cannot import name 'build_feishu_card'`）

- [ ] **Step 3: 实现（追加到 app/notifier.py）**

```python
def build_feishu_card(kind: str, task_name: str, profile: str,
                      rate: float, threshold: int, ts: str) -> dict:
    """构造飞书自定义机器人 interactive 卡片。kind ∈ {'alert','recover'}。"""
    if kind == "recover":
        template, title, color = "green", "✅ 已恢复", "green"
    else:
        template, title, color = "red", "🔴 拨测告警", "red"
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"template": template,
                       "title": {"tag": "plain_text", "content": title}},
            "elements": [
                {"tag": "div", "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**任务**\n{task_name}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**站点**\n{profile}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**成功率**\n<font color='{color}'>{rate:.1f}%</font>"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**阈值**\n{threshold}%"}},
                ]},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "lark_md", "content": f"⏰ {ts} · AITokenPerf"}]},
            ],
        },
    }
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_notifier.py -q`
Expected: PASS（14 passed）

- [ ] **Step 5: 提交**

```bash
git add app/notifier.py tests/test_notifier.py
git commit -m "feat(notifier): 飞书告警卡片 build_feishu_card (#30)"
```

---

### Task 4: notifier — send_webhook（异步，SSRF 守卫，日志脱敏）

**Files:**
- Modify: `app/notifier.py`
- Test: `tests/test_notifier.py`

- [ ] **Step 1: 追加失败测试**

```python
# tests/test_notifier.py 追加
import pytest
from app import notifier


@pytest.mark.asyncio
async def test_send_webhook_rejects_ssrf():
    # 非飞书域名直接拒绝，不发网络请求
    assert await notifier.send_webhook("https://evil.com/x", {"a": 1}) is False


@pytest.mark.asyncio
async def test_send_webhook_success(monkeypatch):
    class FakeResp:
        status = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class FakeSession:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def post(self, *a, **k): return FakeResp()

    monkeypatch.setattr(notifier.aiohttp, "ClientSession", FakeSession)
    ok = await notifier.send_webhook("https://open.feishu.cn/open-apis/bot/v2/hook/x", {"a": 1})
    assert ok is True


@pytest.mark.asyncio
async def test_send_webhook_non_2xx_returns_false(monkeypatch):
    class FakeResp:
        status = 500
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class FakeSession:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def post(self, *a, **k): return FakeResp()

    monkeypatch.setattr(notifier.aiohttp, "ClientSession", FakeSession)
    assert await notifier.send_webhook("https://open.feishu.cn/x", {"a": 1}) is False
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_notifier.py -k send_webhook -q`
Expected: FAIL（`module 'app.notifier' has no attribute 'send_webhook'`）

- [ ] **Step 3: 实现（追加到 app/notifier.py）**

```python
async def send_webhook(url: str, payload: dict, timeout: float = 10.0) -> bool:
    """best-effort 发送 webhook。先 SSRF 校验；失败只 log（不含完整 URL）、返回 False、不抛。"""
    if not is_allowed_webhook(url):
        log.warning("拒绝非法 webhook 目标 host=%s", _safe_host(url))
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status // 100 == 2:
                    return True
                log.warning("webhook 推送失败 host=%s status=%s", _safe_host(url), resp.status)
                return False
    except Exception as e:
        log.warning("webhook 推送异常 host=%s err=%s", _safe_host(url), type(e).__name__)
        return False
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_notifier.py -q`
Expected: PASS（17 passed）

- [ ] **Step 5: 提交**

```bash
git add app/notifier.py tests/test_notifier.py
git commit -m "feat(notifier): best-effort send_webhook + 日志脱敏 (#30)"
```

---

### Task 5: DB — scheduled_tasks 加 4 列（DDL + 迁移 + CRUD 白名单）

**Files:**
- Modify: `app/db.py`（两处 `CREATE TABLE scheduled_tasks`、迁移块、`create_scheduled_task`、`update_scheduled_task`）
- Test: `tests/test_alert_db.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_alert_db.py
import pytest
from app.db import create_scheduled_task, get_scheduled_task, update_scheduled_task


@pytest.mark.asyncio
async def test_alert_fields_roundtrip():
    sid = await create_scheduled_task(
        1, "t", [], {}, "interval", "300",
        alert_webhook="https://open.feishu.cn/x", alert_threshold=80, alert_enabled=True,
    )
    row = await get_scheduled_task(sid)
    assert row["alert_webhook"] == "https://open.feishu.cn/x"
    assert row["alert_threshold"] == 80
    assert bool(row["alert_enabled"]) is True
    assert row["alert_state"] == "ok"


@pytest.mark.asyncio
async def test_update_alert_state_persists():
    sid = await create_scheduled_task(1, "t2", [], {}, "interval", "300")
    await update_scheduled_task(sid, alert_state="alerting")
    row = await get_scheduled_task(sid)
    assert row["alert_state"] == "alerting"
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_alert_db.py -q`
Expected: FAIL（`create_scheduled_task() got an unexpected keyword argument 'alert_webhook'`）

- [ ] **Step 3a: 两处建表 DDL 加列**

`app/db.py` 的 `_SQLITE_SCHEMA` 中 `scheduled_tasks` 表，在 `run_count ...` 行后、`created_at` 前加：

```sql
    alert_webhook   TEXT NOT NULL DEFAULT '',
    alert_threshold INTEGER NOT NULL DEFAULT 90,
    alert_enabled   INTEGER NOT NULL DEFAULT 0,
    alert_state     TEXT NOT NULL DEFAULT 'ok',
```

`_PG_SCHEMA` 的 `scheduled_tasks` 表同位置加：

```sql
    alert_webhook   TEXT NOT NULL DEFAULT '',
    alert_threshold INTEGER NOT NULL DEFAULT 90,
    alert_enabled   BOOLEAN NOT NULL DEFAULT FALSE,
    alert_state     TEXT NOT NULL DEFAULT 'ok',
```

- [ ] **Step 3b: 迁移（存量表加列）**

在 `init_db` 内、现有 results 列迁移之后，加 scheduled_tasks 列迁移。找到 `if _is_sqlite:` / `else:` 处理 results `ADD COLUMN` 的块，在其后追加：

```python
        # scheduled_tasks 告警列迁移
        if _is_sqlite:
            for col_def in [
                "ALTER TABLE scheduled_tasks ADD COLUMN alert_webhook TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE scheduled_tasks ADD COLUMN alert_threshold INTEGER NOT NULL DEFAULT 90",
                "ALTER TABLE scheduled_tasks ADD COLUMN alert_enabled INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE scheduled_tasks ADD COLUMN alert_state TEXT NOT NULL DEFAULT 'ok'",
            ]:
                try:
                    await conn.execute(text(col_def))
                except Exception:
                    pass
        else:
            for col_def in [
                "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS alert_webhook TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS alert_threshold INTEGER NOT NULL DEFAULT 90",
                "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS alert_enabled BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS alert_state TEXT NOT NULL DEFAULT 'ok'",
            ]:
                await conn.execute(text(col_def))
```

- [ ] **Step 3c: 扩展 create_scheduled_task**

替换 `create_scheduled_task` 为：

```python
async def create_scheduled_task(user_id: int, name: str, profile_ids: list,
                                 configs_json: dict, schedule_type: str,
                                 schedule_value: str, alert_webhook: str = "",
                                 alert_threshold: int = 90,
                                 alert_enabled: bool = False) -> int:
    async with engine.begin() as conn:
        cur = await conn.execute(
            text("""INSERT INTO scheduled_tasks (user_id, name, profile_ids, configs_json,
                    schedule_type, schedule_value, alert_webhook, alert_threshold, alert_enabled)
                   VALUES (:uid, :name, :pids, :cj, :st, :sv, :aw, :at, :ae)"""),
            {"uid": user_id, "name": name, "pids": json.dumps(profile_ids),
             "cj": json.dumps(configs_json), "st": schedule_type, "sv": schedule_value,
             "aw": alert_webhook, "at": alert_threshold,
             "ae": (1 if alert_enabled else 0) if _is_sqlite else bool(alert_enabled)},
        )
        if _is_sqlite:
            return cur.lastrowid
        result = await conn.execute(text("SELECT lastval()"))
        return (result.fetchone())[0]
```

- [ ] **Step 3d: update_scheduled_task 白名单加 4 列**

`update_scheduled_task` 的 `allowed` 集合改为：

```python
        allowed = {"name", "profile_ids", "configs_json", "schedule_type",
                   "schedule_value", "status", "last_run_at", "next_run_at", "run_count",
                   "alert_webhook", "alert_threshold", "alert_enabled", "alert_state"}
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_alert_db.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add app/db.py tests/test_alert_db.py
git commit -m "feat(db): scheduled_tasks 告警列 + CRUD 白名单 (#30)"
```

---

### Task 6: DB — get_run_success_rate 聚合助手

**Files:**
- Modify: `app/db.py`（新增函数）
- Test: `tests/test_alert_db.py`

> 说明：bench task 的 `success_count/total_count` 每换并发档会被清零（`server.py:373-376`），不可信。改为聚合本轮落库结果的 `summary_json`。

- [ ] **Step 1: 追加失败测试**

```python
# tests/test_alert_db.py 追加
import json
from app.db import save_result, get_run_success_rate


@pytest.mark.asyncio
async def test_get_run_success_rate_aggregates():
    for i, (succ, tot) in enumerate([(8, 10), (5, 10)]):
        await save_result(
            user_id=1, test_id=f"t{i}", filename=f"f{i}.json", timestamp="20260604_120000",
            config_json="{}", summary_json=json.dumps({"success_count": succ, "total_requests": tot}),
            percentiles_json="{}", run_id="run-x",
        )
    assert await get_run_success_rate(["run-x"]) == (13, 20)


@pytest.mark.asyncio
async def test_get_run_success_rate_empty():
    assert await get_run_success_rate([]) == (0, 0)
    assert await get_run_success_rate(["nope"]) == (0, 0)
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_alert_db.py -k success_rate -q`
Expected: FAIL（`cannot import name 'get_run_success_rate'`）

- [ ] **Step 3: 实现（加到 app/db.py，紧邻其他 results 查询函数）**

```python
async def get_run_success_rate(run_ids: list) -> tuple:
    """聚合给定 run 的全部 result 行的 (success_count, total_requests)。返回 (success, total)。"""
    if not run_ids:
        return (0, 0)
    placeholders = ",".join(f":r{i}" for i in range(len(run_ids)))
    params = {f"r{i}": rid for i, rid in enumerate(run_ids)}
    async with engine.connect() as conn:
        cur = await conn.execute(
            text(f"SELECT summary_json FROM results WHERE run_id IN ({placeholders})"),
            params,
        )
        rows = cur.fetchall()
    success = total = 0
    for row in rows:
        try:
            s = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            continue
        success += int(s.get("success_count") or 0)
        total += int(s.get("total_requests") or 0)
    return (success, total)
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_alert_db.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add app/db.py tests/test_alert_db.py
git commit -m "feat(db): get_run_success_rate 聚合落库结果 (#30)"
```

---

### Task 7: scheduler — _maybe_send_alert 接入

**Files:**
- Modify: `app/scheduler.py`（新增模块函数 + `_run_scheduled_task` 末尾接入）
- Test: `tests/test_alert_scheduler.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_alert_scheduler.py
import json
import pytest
from app import notifier, scheduler
from app.db import create_scheduled_task, save_result, get_scheduled_task


async def _seed(rate_pair, alert_state="ok", enabled=True):
    succ, tot = rate_pair
    sid = await create_scheduled_task(
        1, "t", ["SiteA"], {}, "interval", "300",
        alert_webhook="https://open.feishu.cn/x", alert_threshold=90, alert_enabled=enabled,
    )
    if alert_state != "ok":
        from app.db import update_scheduled_task
        await update_scheduled_task(sid, alert_state=alert_state)
    await save_result(
        user_id=1, test_id="a", filename="a.json", timestamp="20260604_120000",
        config_json="{}", summary_json=json.dumps({"success_count": succ, "total_requests": tot}),
        percentiles_json="{}", run_id="run-1", scheduled_task_id=sid,
    )
    return sid


@pytest.mark.asyncio
async def test_alert_fires_and_writes_state(monkeypatch):
    sent = []
    async def fake_send(url, payload, timeout=10.0):
        sent.append(payload); return True
    monkeypatch.setattr(notifier, "send_webhook", fake_send)

    sid = await _seed((5, 10))  # 50% < 90%
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])

    assert len(sent) == 1
    assert (await get_scheduled_task(sid))["alert_state"] == "alerting"


@pytest.mark.asyncio
async def test_no_alert_when_disabled(monkeypatch):
    sent = []
    async def fake_send(url, payload, timeout=10.0):
        sent.append(payload); return True
    monkeypatch.setattr(notifier, "send_webhook", fake_send)

    sid = await _seed((5, 10), enabled=False)
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert sent == []


@pytest.mark.asyncio
async def test_recover_when_back_to_normal(monkeypatch):
    sent = []
    async def fake_send(url, payload, timeout=10.0):
        sent.append(payload); return True
    monkeypatch.setattr(notifier, "send_webhook", fake_send)

    sid = await _seed((10, 10), alert_state="alerting")  # 100% >= 90%, 之前在告警
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert len(sent) == 1
    assert (await get_scheduled_task(sid))["alert_state"] == "ok"
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_alert_scheduler.py -q`
Expected: FAIL（`module 'app.scheduler' has no attribute '_maybe_send_alert'`）

- [ ] **Step 3a: 新增 _maybe_send_alert（加到 app/scheduler.py 模块级，`_run_scheduled_task` 之前或之后均可）**

```python
async def _maybe_send_alert(task_id: int, task_row: dict, run_ids: list):
    """按落库结果聚合成功率，状态翻转时发飞书卡片并写回 alert_state。全程不抛。"""
    from app.db import get_run_success_rate, update_scheduled_task
    from app.notifier import evaluate_alert, build_feishu_card, send_webhook

    if not task_row.get("alert_enabled") or not (task_row.get("alert_webhook") or "").strip():
        return
    success, total = await get_run_success_rate(run_ids)
    if total == 0:
        log.info("定时任务 #%d 本轮无有效请求，跳过告警评估", task_id)
        return
    rate = success / total * 100
    threshold = int(task_row.get("alert_threshold") or 90)
    prev = task_row.get("alert_state") or "ok"
    new_state, action = evaluate_alert(prev, rate, threshold)
    if action:
        profile = ", ".join(task_row.get("profile_ids", []) or []) or "-"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        card = build_feishu_card(action, task_row.get("name", ""), profile, rate, threshold, ts)
        await send_webhook(task_row["alert_webhook"], card)
    if new_state != prev:
        await update_scheduled_task(task_id, alert_state=new_state)
```

- [ ] **Step 3b: 在 _run_scheduled_task 捕获 run_ids 并接入**

在 `_run_scheduled_task` 中，`bench_tasks = []` 之后加 `run_ids = []`。在 `bench_tasks.extend(manager.get_run_tasks(result["run_id"]))` 之前加 `run_ids.append(result["run_id"])`。

在函数末尾 `log_bench("scheduler:complete", ...)` 之后追加：

```python
    # 失败告警评估（best-effort，绝不影响主流程）
    try:
        await _maybe_send_alert(task_id, task_row, run_ids)
    except Exception as e:
        log.error("定时任务 #%d 告警评估失败: %s", task_id, e)
        log_error("scheduler:alert_error", error=str(e), task_id=task_id)
```

（`task_row` 在 `_run_scheduled_task` 开头已 `get_scheduled_task` 取到，含新列；`datetime` 已在文件顶部导入。）

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_alert_scheduler.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add app/scheduler.py tests/test_alert_scheduler.py
git commit -m "feat(scheduler): 接入失败告警评估 _maybe_send_alert (#30)"
```

---

### Task 8: server — create/update schedule 接收+校验告警字段

**Files:**
- Modify: `app/server.py`（新增 `_extract_alert_fields` 助手 + `create_schedule` + `update_schedule`）
- Test: `tests/test_alert_api.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_alert_api.py
import pytest
from tests.conftest import auth_headers
from app.db import get_scheduled_task


async def _make_profile(client, headers):
    await client.post("/api/profiles/save", json={
        "name": "s", "base_url": "https://api.example.com", "api_key": "sk-x",
        "api_key_action": "replace", "models": ["gpt-4o-mini"], "provider": "openai",
    }, headers=headers)


@pytest.mark.asyncio
async def test_create_schedule_with_alert(client):
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "schedule_value": "300",
        "alert_enabled": True, "alert_threshold": 85,
        "alert_webhook": "https://open.feishu.cn/x",
    }, headers=headers)
    assert resp.status_code == 200
    sid = resp.json()["id"]
    row = await get_scheduled_task(sid)
    assert row["alert_threshold"] == 85
    assert row["alert_webhook"] == "https://open.feishu.cn/x"


@pytest.mark.asyncio
async def test_create_schedule_rejects_bad_webhook(client):
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "alert_webhook": "https://evil.com/x",
    }, headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_schedule_rejects_bad_threshold(client):
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "alert_threshold": 250,
    }, headers=headers)
    assert resp.status_code == 400
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_alert_api.py -q`
Expected: FAIL（创建带 alert 字段未持久化 / 非法值未被拒 → 断言失败）

- [ ] **Step 3a: 新增 _extract_alert_fields（加到 app/server.py 模块级，靠近其他 schedule 辅助函数）**

```python
def _extract_alert_fields(body: dict):
    """从请求体提取并校验告警字段。返回 (fields, error)。error 非空表示校验失败。"""
    from app.notifier import is_allowed_webhook
    out = {}
    if "alert_enabled" in body:
        out["alert_enabled"] = bool(body["alert_enabled"])
    if "alert_threshold" in body:
        try:
            t = int(body["alert_threshold"])
        except (ValueError, TypeError):
            return None, "alert_threshold 必须是 0-100 的整数"
        if not (0 <= t <= 100):
            return None, "alert_threshold 必须在 0-100 之间"
        out["alert_threshold"] = t
    if "alert_webhook" in body:
        wh = (body.get("alert_webhook") or "").strip()
        if wh and not is_allowed_webhook(wh):
            return None, "webhook 必须是 https 的飞书域名 (open.feishu.cn / open.larksuite.com)"
        out["alert_webhook"] = wh
    return out, None
```

- [ ] **Step 3b: create_schedule 接入**

在 `create_schedule` 内，`schedule_value` 校验之后、`create_scheduled_task(...)` 调用之前加：

```python
    alert_fields, alert_err = _extract_alert_fields(body)
    if alert_err:
        return JSONResponse({"error": alert_err}, status_code=400)
```

并把建任务调用改为：

```python
    sid = await create_scheduled_task(
        user_id, name, profile_ids, configs_json, schedule_type, schedule_value,
        alert_webhook=alert_fields.get("alert_webhook", ""),
        alert_threshold=alert_fields.get("alert_threshold", 90),
        alert_enabled=alert_fields.get("alert_enabled", False),
    )
```

- [ ] **Step 3c: update_schedule 接入**

在 `update_schedule` 内，构造 `fields` 之后加：

```python
    alert_fields, alert_err = _extract_alert_fields(body)
    if alert_err:
        return JSONResponse({"error": alert_err}, status_code=400)
    fields.update(alert_fields)
```

（`update_scheduled_task` 白名单已在 Task 5 包含这些列。）

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_alert_api.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add app/server.py tests/test_alert_api.py
git commit -m "feat(server): 定时任务 CRUD 接收+校验告警字段 (#30)"
```

---

### Task 9: server — POST /api/schedules/{id}/alert-test

**Files:**
- Modify: `app/server.py`（新增端点）
- Test: `tests/test_alert_api.py`

- [ ] **Step 1: 追加失败测试**

```python
# tests/test_alert_api.py 追加
from app import notifier


@pytest.mark.asyncio
async def test_alert_test_endpoint(client, monkeypatch):
    sent = []
    async def fake_send(url, payload, timeout=10.0):
        sent.append(url); return True
    monkeypatch.setattr(notifier, "send_webhook", fake_send)

    headers = await auth_headers(client)
    await _make_profile(client, headers)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "alert_enabled": True,
        "alert_webhook": "https://open.feishu.cn/x",
    }, headers=headers)
    sid = resp.json()["id"]

    r = await client.post(f"/api/schedules/{sid}/alert-test", headers=headers)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_alert_test_requires_webhook(client):
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    resp = await client.post("/api/schedules", json={"name": "t", "profile_ids": ["s"]}, headers=headers)
    sid = resp.json()["id"]
    r = await client.post(f"/api/schedules/{sid}/alert-test", headers=headers)
    assert r.status_code == 400
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_alert_api.py -k alert_test -q`
Expected: FAIL（404/405，端点不存在）

- [ ] **Step 3: 实现（加到 app/server.py，靠近其他 schedules 路由）**

```python
@app.post("/api/schedules/{task_id}/alert-test")
async def alert_test(task_id: int, user: dict = Depends(get_current_user)):
    from app.db import get_scheduled_task
    from app.notifier import build_feishu_card, send_webhook, is_allowed_webhook
    from datetime import datetime
    task_row = await get_scheduled_task(task_id)
    if not task_row or task_row["user_id"] != user["user_id"]:
        return JSONResponse({"error": "Not found"}, status_code=404)
    webhook = (task_row.get("alert_webhook") or "").strip()
    if not webhook or not is_allowed_webhook(webhook):
        return JSONResponse({"error": "请先配置合法的飞书 webhook"}, status_code=400)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    card = build_feishu_card("alert", task_row.get("name", ""), "测试",
                             0.0, int(task_row.get("alert_threshold") or 90), ts)
    card["card"]["header"]["title"]["content"] = "🔔 告警测试（这是一条测试消息）"
    ok = await send_webhook(webhook, card)
    return {"ok": ok}
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_alert_api.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: 运行全量后端回归**

Run: `python -m pytest tests/ -q`
Expected: PASS（全绿）

- [ ] **Step 6: 提交**

```bash
git add app/server.py tests/test_alert_api.py
git commit -m "feat(server): 告警测试端点 /api/schedules/{id}/alert-test (#30)"
```

---

### Task 10: 前端 — TasksView 告警配置区

**Files:**
- Modify: `frontend/src/views/TasksView.vue`
- Modify: `frontend/src/api/index.js`（加 alertTest 调用）

> 说明：照搬现有任务表单（约 TasksView.vue:289/297）的字段绑定与样式风格，加一段「告警」配置。不引入新组件，复用现有 input/switch 样式。

- [ ] **Step 1: api 层加调用**

在 `frontend/src/api/index.js` 加：

```javascript
export const alertTestApi = (id) => api(`/api/schedules/${id}/alert-test`, { method: 'POST' })
```

- [ ] **Step 2: 表单 state 加字段**

在创建/编辑任务的响应式表单对象里加：`alert_enabled: false, alert_webhook: '', alert_threshold: 90`。编辑时从任务行回填这三个字段。

- [ ] **Step 3: 模板加告警区**

在任务表单合适位置（高级参数附近）加：

```html
<div class="form-section">
  <label class="form-switch">
    <input type="checkbox" v-model="form.alert_enabled" />
    <span>启用失败告警（飞书）</span>
  </label>
  <template v-if="form.alert_enabled">
    <label>飞书 Webhook URL</label>
    <input v-model.trim="form.alert_webhook" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." />
    <label>成功率阈值（%）</label>
    <input type="number" v-model.number="form.alert_threshold" min="0" max="100" />
    <button type="button" class="btn-secondary" :disabled="!editingId || !form.alert_webhook" @click="onTestAlert">发送测试消息</button>
  </template>
</div>
```

- [ ] **Step 4: 提交 payload 带上三字段 + 测试按钮处理**

保存任务的 `create`/`update` 请求体里带上 `alert_enabled / alert_webhook / alert_threshold`。加方法：

```javascript
async function onTestAlert() {
  try {
    const r = await alertTestApi(editingId.value)
    showToast(r.ok ? '测试消息已发送，请检查飞书' : '发送失败，请检查 URL', r.ok ? 'success' : 'error')
  } catch (e) {
    showToast('发送失败：' + (e.message || e), 'error')
  }
}
```
（`alertTestApi` 从 `@/api` 导入；`showToast`/`editingId` 用页面现有的。测试按钮要求任务已保存——`editingId` 存在时才可点。）

- [ ] **Step 5: 构建校验**

Run: `cd frontend && bun run build`
Expected: 构建成功无报错。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/TasksView.vue frontend/src/api/index.js
git commit -m "feat(web): 定时任务表单告警配置区 + 测试 (#30)"
```

---

### Task 11: 前端 — SiteSchedulesTab 告警配置区

**Files:**
- Modify: `frontend/src/components/SiteSchedulesTab.vue`

> 与 Task 10 同款配置区，加到 SiteSchedulesTab 的创建/编辑表单。复用 Task 10 的 `alertTestApi`。

- [ ] **Step 1: 表单 state 加字段**

创建/编辑表单对象加 `alert_enabled: false, alert_webhook: '', alert_threshold: 90`，编辑时回填。

- [ ] **Step 2: 模板加告警区**（同 Task 10 Step 3 的模板片段，绑定到本组件表单对象）

- [ ] **Step 3: 保存 payload 带上三字段；如有「发送测试」按钮，复用 `alertTestApi(id)`（仅已保存任务可用）**

- [ ] **Step 4: 构建校验**

Run: `cd frontend && bun run build`
Expected: 构建成功。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/SiteSchedulesTab.vue
git commit -m "feat(web): SiteSchedulesTab 告警配置区 (#30)"
```

---

## 收尾

- [ ] 全量后端测试 `python -m pytest tests/ -q` 全绿
- [ ] 前端 `cd frontend && bun run build` 成功
- [ ] 推送分支 `feat/issue-30-failure-alerting`，`gh pr create`（body 含 `Closes #30`）
- [ ] 真机验证（部署后）：配一个飞书机器人 webhook，跑一次低成功率拨测确认收到红色告警卡片、恢复收到绿色卡片；确认 `<font color>` 渲染是否正常。
</content>
