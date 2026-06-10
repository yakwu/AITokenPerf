# 拨测告警「按站点×模型」细分 · 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把定时拨测告警从「任务级整体成功率」下沉到「每个 (站点 profile, 模型 model) 格子各自判断」，多格同时翻转时聚合成一条红卡/一条绿卡发飞书。

**Architecture:** 纯后端策略改动。新增按格子分组的成功率聚合 DB 助手；`alert_state` 列复用、值改存 JSON（`{站点:{模型:状态}}`，老裸值兼容为空）；重写 `_maybe_send_alert` 逐格跑现有 `evaluate_alert` 并聚合发卡；`build_feishu_card` 改吃格子列表。零 DDL、零数据迁移、前端不动。

**Tech Stack:** Python / asyncio / SQLAlchemy(async) / aiohttp / pytest+pytest-asyncio；测试用 SQLite（conftest autouse 重建表）。

**Notes for executor:**
- 工作目录是 worktree 根 `.claude/worktrees/issue-56-per-cell-alerting/`。
- 跑测试用项目虚拟环境：`python -m pytest ...`；若 `ModuleNotFoundError`，改用 `.venv/bin/python -m pytest ...`。
- 设计依据：`docs/superpowers/specs/2026-06-09-per-cell-alerting-design.md`。
- 提交 commit message 引用 `#56`，**不要**加 `Co-Authored-By`。

---

## 文件结构

| 文件 | 改动 |
|---|---|
| `app/db.py` | 新增 `get_run_success_rate_by_cell(run_ids)`；删除旧 `get_run_success_rate`（Task 3） |
| `app/notifier.py` | 新增 `import json` + `_load_alert_states(raw)`；`build_feishu_card` 改吃格子列表 |
| `app/scheduler.py` | 重写 `_maybe_send_alert`（分组 + 逐格判定 + 聚合发卡 + JSON 状态读写） |
| `tests/test_alert_db.py` | 新增 3 个分组测试；删 2 个旧 `get_run_success_rate` 测试 + 改顶部 import（Task 3） |
| `tests/test_notifier.py` | 新增 4 个 `_load_alert_states` 测试；改 2 个卡片测试为列表签名 |
| `tests/test_alert_scheduler.py` | 整体重写为 per-cell 场景 |

---

## Task 1: 按格子分组的成功率聚合（`get_run_success_rate_by_cell`）

**Files:**
- Modify: `app/db.py`（在 `get_run_success_rate` 之后新增函数，约 `db.py:867`）
- Test: `tests/test_alert_db.py`（文件末尾追加）

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_alert_db.py` 末尾：

```python
@pytest.mark.asyncio
async def test_success_rate_by_cell_groups():
    from app.db import get_run_success_rate_by_cell
    rows = [
        ("SiteA", "gpt-4o", 8, 10),
        ("SiteA", "gpt-4o", 9, 10),   # 同格第二并发档，应累加
        ("SiteA", "claude", 5, 10),
        ("SiteB", "gpt-4o", 10, 10),
    ]
    for i, (pf, model, succ, tot) in enumerate(rows):
        await save_result(
            user_id=1, test_id=f"c{i}", filename=f"c{i}.json", timestamp="20260609_120000",
            config_json=json.dumps({"profile_name": pf, "model": model}),
            summary_json=json.dumps({"success_count": succ, "total_requests": tot}),
            percentiles_json="{}", run_id="run-cell",
        )
    cells = await get_run_success_rate_by_cell(["run-cell"])
    assert cells[("SiteA", "gpt-4o")] == (17, 20)
    assert cells[("SiteA", "claude")] == (5, 10)
    assert cells[("SiteB", "gpt-4o")] == (10, 10)


@pytest.mark.asyncio
async def test_success_rate_by_cell_model_missing():
    from app.db import get_run_success_rate_by_cell
    await save_result(
        user_id=1, test_id="nm", filename="nm.json", timestamp="20260609_120000",
        config_json=json.dumps({"profile_name": "SiteA"}),  # 无 model
        summary_json=json.dumps({"success_count": 3, "total_requests": 4}),
        percentiles_json="{}", run_id="run-nm",
    )
    cells = await get_run_success_rate_by_cell(["run-nm"])
    assert cells[("SiteA", "-")] == (3, 4)


@pytest.mark.asyncio
async def test_success_rate_by_cell_empty():
    from app.db import get_run_success_rate_by_cell
    assert await get_run_success_rate_by_cell([]) == {}
    assert await get_run_success_rate_by_cell(["nope"]) == {}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_alert_db.py -k by_cell -v`
Expected: FAIL —— `ImportError: cannot import name 'get_run_success_rate_by_cell'`

- [ ] **Step 3: 实现函数**

在 `app/db.py` 的 `get_run_success_rate`（结尾约 866 行）之后新增：

```python
async def get_run_success_rate_by_cell(run_ids: list) -> dict:
    """按 (profile_name, model) 分组聚合本轮 result 行的 (success, total)。
    返回 {(profile, model): (success, total)}。无行返回 {}。"""
    if not run_ids:
        return {}
    placeholders = ",".join(f":r{i}" for i in range(len(run_ids)))
    params = {f"r{i}": rid for i, rid in enumerate(run_ids)}
    async with engine.connect() as conn:
        cur = await conn.execute(
            text(f"SELECT profile_name, config_json, summary_json FROM results "
                 f"WHERE run_id IN ({placeholders})"),
            params,
        )
        rows = cur.fetchall()
    cells: dict = {}
    for profile_name, config_json, summary_json in rows:
        try:
            cfg = json.loads(config_json) if config_json else {}
        except (json.JSONDecodeError, TypeError):
            cfg = {}
        try:
            s = json.loads(summary_json)
        except (json.JSONDecodeError, TypeError):
            continue
        profile = profile_name or cfg.get("profile_name", "") or "-"
        model = cfg.get("model") or "-"
        succ = int(s.get("success_count") or 0)
        tot = int(s.get("total_requests") or 0)
        cur_s, cur_t = cells.get((profile, model), (0, 0))
        cells[(profile, model)] = (cur_s + succ, cur_t + tot)
    return cells
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_alert_db.py -k by_cell -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add app/db.py tests/test_alert_db.py
git commit -m "feat: 新增 get_run_success_rate_by_cell 按格子分组聚合成功率 (#56)"
```

---

## Task 2: `alert_state` JSON 读取兼容（`_load_alert_states`）

**Files:**
- Modify: `app/notifier.py`（顶部加 `import json`；新增纯函数）
- Test: `tests/test_notifier.py`（文件末尾追加）

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_notifier.py` 末尾：

```python
def test_load_alert_states_valid_json():
    from app.notifier import _load_alert_states
    assert _load_alert_states('{"SiteA": {"gpt-4o": "alerting"}}') == {"SiteA": {"gpt-4o": "alerting"}}


def test_load_alert_states_legacy_scalar():
    from app.notifier import _load_alert_states
    assert _load_alert_states("ok") == {}
    assert _load_alert_states("alerting") == {}


def test_load_alert_states_empty_or_none():
    from app.notifier import _load_alert_states
    assert _load_alert_states("") == {}
    assert _load_alert_states(None) == {}


def test_load_alert_states_non_dict_json():
    from app.notifier import _load_alert_states
    assert _load_alert_states('"ok"') == {}
    assert _load_alert_states("123") == {}
    assert _load_alert_states("[1, 2]") == {}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_notifier.py -k load_alert_states -v`
Expected: FAIL —— `ImportError: cannot import name '_load_alert_states'`

- [ ] **Step 3: 实现**

在 `app/notifier.py` 顶部 import 区加（与现有 `import logging` 同组）：

```python
import json
```

在 `evaluate_alert` 之后新增：

```python
def _load_alert_states(raw) -> dict:
    """读取 alert_state：合法 JSON dict 原样返回；裸值/空/非 dict 一律视为空（存量兼容）。"""
    if not raw:
        return {}
    try:
        v = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return v if isinstance(v, dict) else {}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_notifier.py -k load_alert_states -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add app/notifier.py tests/test_notifier.py
git commit -m "feat: 新增 _load_alert_states 兼容读取告警状态 JSON (#56)"
```

---

## Task 3: 切换到 per-cell（卡片列表版 + 重写 `_maybe_send_alert` + 删旧聚合函数）

> 本 task 是一次原子切换：`build_feishu_card` 签名变更跨 notifier/scheduler 两个文件，必须同改才能保持测试绿。task 内 step 仍按 TDD 推进，中间态测试红是正常的，**只要 Step 11 提交时全绿**。

**Files:**
- Modify: `app/notifier.py`（`build_feishu_card` 改签名）
- Modify: `app/scheduler.py`（重写 `_maybe_send_alert`，约 `scheduler.py:227-255`）
- Modify: `app/db.py`（删除 `get_run_success_rate`，约 `db.py:846-866`）
- Test: `tests/test_notifier.py`（改 2 个卡片测试）
- Test: `tests/test_alert_scheduler.py`（整体重写）
- Test: `tests/test_alert_db.py`（删 2 个旧测试 + 改顶部 import）

- [ ] **Step 1: 改卡片测试为列表签名**

把 `tests/test_notifier.py` 中 `test_alert_card_red_header` 和 `test_recover_card_green_header` 两个函数整体替换为：

```python
def test_alert_card_red_header():
    card = build_feishu_card("alert", "主力渠道",
                             [("OpenAI-A", "gpt-4o", 72.0), ("OpenAI-B", "claude", 65.0)],
                             90, "2026-06-09 10:30")
    assert card["msg_type"] == "interactive"
    assert card["card"]["config"]["wide_screen_mode"] is True
    assert card["card"]["header"]["template"] == "red"
    assert "告警" in card["card"]["header"]["title"]["content"]
    flat = str(card)
    assert "OpenAI-A" in flat and "gpt-4o" in flat and "72.0%" in flat
    assert "OpenAI-B" in flat and "claude" in flat and "65.0%" in flat
    assert "90%" in flat


def test_recover_card_green_header():
    card = build_feishu_card("recover", "主力渠道",
                             [("OpenAI-A", "gpt-4o", 95.0)], 90, "2026-06-09 10:30")
    assert card["card"]["header"]["template"] == "green"
    assert "恢复" in card["card"]["header"]["title"]["content"]
    flat = str(card)
    assert "OpenAI-A" in flat and "gpt-4o" in flat and "95.0%" in flat
```

- [ ] **Step 2: 跑卡片测试确认失败**

Run: `python -m pytest tests/test_notifier.py -k card -v`
Expected: FAIL（旧实现是单格 `profile`/`rate` 位置参数签名，传 list 会 TypeError 或断言失败）

- [ ] **Step 3: 改 `build_feishu_card` 为列表版**

把 `app/notifier.py` 的 `build_feishu_card` 整个函数替换为：

```python
def build_feishu_card(kind: str, task_name: str,
                      cells: list, threshold: int, ts: str) -> dict:
    """构造飞书自定义机器人 interactive 卡片。kind ∈ {'alert','recover'}。
    cells: [(profile, model, rate), ...] —— 本轮新翻转的格子。"""
    if kind == "recover":
        template, title, color = "green", "✅ 已恢复", "green"
    else:
        template, title, color = "red", "🔴 拨测告警", "red"
    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**任务**：{task_name}"}},
    ]
    for profile, model, rate in cells:
        elements.append({"tag": "div", "fields": [
            {"is_short": True, "text": {"tag": "lark_md", "content": f"**站点**\n{profile}"}},
            {"is_short": True, "text": {"tag": "lark_md", "content": f"**模型**\n{model}"}},
            {"is_short": True, "text": {"tag": "lark_md",
                "content": f"**成功率**\n<font color='{color}'>{rate:.1f}%</font>"}},
        ]})
    elements.append({"tag": "hr"})
    elements.append({"tag": "note", "elements": [
        {"tag": "lark_md", "content": f"阈值 {threshold}% · {ts} · AITokenPerf"}]})
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"template": template,
                       "title": {"tag": "plain_text", "content": title}},
            "elements": elements,
        },
    }
```

- [ ] **Step 4: 跑卡片测试确认通过**

Run: `python -m pytest tests/test_notifier.py -k card -v`
Expected: 2 passed

- [ ] **Step 5: 重写 scheduler 测试**

把 `tests/test_alert_scheduler.py` **整个文件**替换为：

```python
import json

import pytest

from app import notifier, scheduler
from app.db import (
    create_scheduled_task, save_result, get_scheduled_task,
    update_scheduled_task, create_notifier,
)


async def _seed_task(cells, alert_state=None, enabled=True, notifier_id=None):
    """cells: [(profile, model, succ, tot)] 落 result 行（run-1）+ 建任务。
    alert_state: dict 或 None（None=保持默认）。notifier_id: None=新建有效告警器。"""
    if notifier_id is None:
        notifier_id = await create_notifier(1, "g", "https://open.feishu.cn/x")
    sid = await create_scheduled_task(
        1, "t", ["SiteA"], {}, "interval", "300",
        alert_notifier_id=notifier_id, alert_threshold=90, alert_enabled=enabled,
    )
    if alert_state is not None:
        await update_scheduled_task(sid, alert_state=json.dumps(alert_state))
    for i, (pf, model, succ, tot) in enumerate(cells):
        await save_result(
            user_id=1, test_id=f"r{i}", filename=f"r{i}.json", timestamp="20260609_120000",
            config_json=json.dumps({"profile_name": pf, "model": model}),
            summary_json=json.dumps({"success_count": succ, "total_requests": tot}),
            percentiles_json="{}", run_id="run-1", scheduled_task_id=sid,
        )
    return sid


def _collector():
    sent = []
    async def fake_send(url, payload, timeout=10.0):
        sent.append(payload)
        return True
    return sent, fake_send


@pytest.mark.asyncio
async def test_per_cell_alert_only_failing_cell(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid = await _seed_task([("SiteA", "gpt-4o", 2, 10), ("SiteA", "claude", 10, 10)])
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert len(sent) == 1                       # 只发一条红卡
    flat = str(sent[0])
    assert "gpt-4o" in flat and "claude" not in flat
    states = json.loads((await get_scheduled_task(sid))["alert_state"])
    assert states["SiteA"]["gpt-4o"] == "alerting"
    assert states["SiteA"]["claude"] == "ok"


@pytest.mark.asyncio
async def test_per_cell_simultaneous_alert_and_recover(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    # prev: gpt-4o 告警中、claude 正常；本轮 gpt-4o 恢复(100%)、claude 跌破(10%)
    sid = await _seed_task(
        [("SiteA", "gpt-4o", 10, 10), ("SiteA", "claude", 1, 10)],
        alert_state={"SiteA": {"gpt-4o": "alerting", "claude": "ok"}},
    )
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert len(sent) == 2
    cards = {c["card"]["header"]["template"]: str(c) for c in sent}
    assert "claude" in cards["red"] and "gpt-4o" not in cards["red"]
    assert "gpt-4o" in cards["green"] and "claude" not in cards["green"]
    states = json.loads((await get_scheduled_task(sid))["alert_state"])
    assert states["SiteA"]["gpt-4o"] == "ok"
    assert states["SiteA"]["claude"] == "alerting"


@pytest.mark.asyncio
async def test_no_alert_when_all_ok(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid = await _seed_task([("SiteA", "gpt-4o", 10, 10)])
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert sent == []


@pytest.mark.asyncio
async def test_disabled_no_alert(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid = await _seed_task([("SiteA", "gpt-4o", 0, 10)], enabled=False)
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert sent == []


@pytest.mark.asyncio
async def test_skips_when_notifier_id_zero(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid = await _seed_task([("SiteA", "gpt-4o", 0, 10)], notifier_id=0)
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert sent == []


@pytest.mark.asyncio
async def test_skips_when_notifier_missing(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid = await _seed_task([("SiteA", "gpt-4o", 0, 10)], notifier_id=999999)
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert sent == []


@pytest.mark.asyncio
async def test_no_results_no_alert(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid = await _seed_task([])   # 不造 result 行
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-empty"])
    assert sent == []


@pytest.mark.asyncio
async def test_zero_total_cell_skipped_preserves_state(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    # gpt-4o 本轮 total=0（未发出），claude 正常；prev gpt-4o=alerting → 保留
    sid = await _seed_task(
        [("SiteA", "gpt-4o", 0, 0), ("SiteA", "claude", 10, 10)],
        alert_state={"SiteA": {"gpt-4o": "alerting"}},
    )
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert sent == []                          # 无翻转
    states = json.loads((await get_scheduled_task(sid))["alert_state"])
    assert states["SiteA"]["gpt-4o"] == "alerting"   # 保留旧态
    assert states["SiteA"]["claude"] == "ok"
```

- [ ] **Step 6: 跑 scheduler 测试确认失败**

Run: `python -m pytest tests/test_alert_scheduler.py -v`
Expected: FAIL（`_maybe_send_alert` 仍是旧单格逻辑：用 `get_run_success_rate` + 旧 `build_feishu_card` 签名，断言不符 / 抛错）

- [ ] **Step 7: 重写 `_maybe_send_alert`**

把 `app/scheduler.py` 的 `_maybe_send_alert` 整个函数（约 227-255 行）替换为：

```python
async def _maybe_send_alert(task_id: int, task_row: dict, run_ids: list):
    """按 (站点,模型) 格子聚合成功率，逐格状态翻转，聚合成红/绿卡发送。全程不抛。"""
    from app.db import get_run_success_rate_by_cell, get_notifier
    from app.notifier import (
        evaluate_alert, build_feishu_card, send_webhook, _load_alert_states,
    )

    notifier_id = task_row.get("alert_notifier_id") or 0
    if not task_row.get("alert_enabled") or not notifier_id:
        return  # 未开启 或 未选告警器：不发、不报错
    ntf = await get_notifier(notifier_id)
    webhook = (ntf or {}).get("webhook", "").strip()
    if not webhook:
        log.info("定时任务 #%d 告警器缺失或 webhook 空，跳过告警", task_id)
        return

    cells = await get_run_success_rate_by_cell(run_ids)
    if not cells:
        log.info("定时任务 #%d 本轮无有效请求，跳过告警评估", task_id)
        return

    threshold = int(task_row.get("alert_threshold") or 90)
    prev = _load_alert_states(task_row.get("alert_state"))
    new_states: dict = {}
    alerts, recovers = [], []
    for (profile, model), (succ, tot) in cells.items():
        p_state = prev.get(profile, {}).get(model, "ok")
        if tot == 0:                       # 没真发出请求 → 不评估、保留旧态
            new_states.setdefault(profile, {})[model] = p_state
            continue
        rate = succ / tot * 100
        n_state, action = evaluate_alert(p_state, rate, threshold)
        new_states.setdefault(profile, {})[model] = n_state
        if action == "alert":
            alerts.append((profile, model, rate))
        elif action == "recover":
            recovers.append((profile, model, rate))

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    name = task_row.get("name", "")
    if alerts:
        await send_webhook(webhook, build_feishu_card("alert", name, alerts, threshold, ts))
    if recovers:
        await send_webhook(webhook, build_feishu_card("recover", name, recovers, threshold, ts))

    if new_states != prev:
        await update_scheduled_task(
            task_id, alert_state=json.dumps(new_states, ensure_ascii=False))
```

> `app/scheduler.py` 顶部已 `import json`（line 5）与 `from datetime import datetime`（line 10），无需新增 import。

- [ ] **Step 8: 跑 scheduler 测试确认通过**

Run: `python -m pytest tests/test_alert_scheduler.py -v`
Expected: 8 passed

- [ ] **Step 9: 删除旧 `get_run_success_rate` 及其测试**

1. 删除 `app/db.py` 中的 `get_run_success_rate` 函数（约 846-866 行，即 `async def get_run_success_rate(run_ids: list) -> tuple:` 整段，保留其后的 `get_run_success_rate_by_cell`）。
2. 在 `tests/test_alert_db.py` 顶部 import 去掉 `get_run_success_rate`：

```python
from app.db import (
    create_scheduled_task,
    get_scheduled_task,
    update_scheduled_task,
    save_result,
)
```

3. 删除 `tests/test_alert_db.py` 中 `test_get_run_success_rate_aggregates` 和 `test_get_run_success_rate_empty` 两个函数。

- [ ] **Step 10: 跑全部告警相关测试确认通过**

Run: `python -m pytest tests/test_alert_db.py tests/test_notifier.py tests/test_alert_scheduler.py -v`
Expected: 全 passed（无 `get_run_success_rate` 残留引用报错）

- [ ] **Step 11: 提交**

```bash
git add app/notifier.py app/scheduler.py app/db.py tests/test_notifier.py tests/test_alert_scheduler.py tests/test_alert_db.py
git commit -m "feat: 告警按「站点×模型」逐格判定并聚合发卡 (#56)"
```

---

## Task 4: 全量回归

**Files:** 无代码改动，仅验证。

- [ ] **Step 1: 跑整库测试**

Run: `python -m pytest tests/ -q`
Expected: 全 passed（重点确认 `tests/test_alert_api.py` 等未受影响 —— 本计划未碰 API/前端）。
若有失败：定位是否因 `build_feishu_card` 签名或 `get_run_success_rate` 删除波及的其它引用，按报错修复后重跑。

- [ ] **Step 2: 确认无遗留引用**

Run: `grep -rn "get_run_success_rate\b" app/ tests/`
Expected: 无输出（旧函数已彻底移除，新函数名为 `get_run_success_rate_by_cell` 不匹配 `\b` 边界后接 `(`）。
注：若 grep 命中 `get_run_success_rate_by_cell`，属正常（用 `grep -rn "get_run_success_rate(" app/ tests/` 复查应无输出）。

---

## 自审记录（writing-plans self-review）

**Spec 覆盖：**
- §1 alert_state JSON 化 → Task 2（读）+ Task 3 Step 7（写 `json.dumps`）+ Step 9（列复用、无 DDL）。✓
- §2 成功率分组 → Task 1。✓
- §3 逐格判定 + 聚合 → Task 3 Step 7。✓（守卫、total=0 保留、`new!=prev` 才写、权衡保留）
- §4 卡片列表版 → Task 3 Step 3。✓
- §5 边界（total=0 / cells 空 / try-except 兜底）→ Task 3 测试 `test_zero_total_cell_skipped`/`test_no_results_no_alert`；`_run_scheduled_task` 末尾 try/except 未改动，保留。✓
- §6 前端不动 → 计划无前端任务。✓
- §7 测试策略 → Task 1/2/3 测试逐条对应；旧测试迁移/删除在 Task 3 Step 1/9。✓

**占位扫描：** 无 TBD/TODO；每个改码 step 均含完整代码或精确删除指令。✓

**类型/签名一致性：**
- `get_run_success_rate_by_cell(run_ids) -> dict[(profile,model)->(s,t)]`：Task 1 定义，Task 3 Step 7 消费，键解构一致。✓
- `build_feishu_card(kind, task_name, cells, threshold, ts)`：Task 3 Step 3 定义，Step 7 调用（`alerts`/`recovers` 均为 `[(profile,model,rate)]`）一致。✓
- `_load_alert_states(raw) -> dict`：Task 2 定义，Task 3 Step 7 消费。✓
- `alert_state` 写为 `json.dumps(dict)`，读为 `_load_alert_states` —— 往返一致。✓
