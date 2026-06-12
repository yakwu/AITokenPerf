# 站点健康看板 · 阶段零（后端逐格可用性端点）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个后端能力——按 `(站点 profile, 模型)` 在最近时间窗内分等宽时间桶聚合成功率，并通过 `/api/sites/availability` 暴露，供前端"站点健康看板"的状态页式可用性柱使用。

**Architecture:** 纯后端、纯新增、不改任何现有函数/表。新增 1 个 DB 纯查询函数 `get_cell_availability_series`（Python 端解析 JSON + 分桶，跨 SQLite/PG 一致，分组口径与 #56 的 `get_run_success_rate_by_cell` 对齐）+ 1 个只读 FastAPI 路由。TDD：先写失败测试，再实现。

**Tech Stack:** Python · FastAPI · SQLAlchemy(async) · pytest / pytest-asyncio · SQLite（测试与本地）/ PostgreSQL（生产）双方言。

**工作目录：** 所有命令在本 worktree 根运行：`/Users/yakun/linkingrid/AITokenPerf/.claude/worktrees/issue-58-overview-health-board`（分支 `feat/issue-58-overview-health-board`，已基于含 #56 的最新 main）。

**关联设计：** `docs/superpowers/specs/2026-06-10-overview-health-board-ia-redesign-design.md` §5.3 / §8 / §9.1 / §10 阶段零。

---

## File Structure

- **Modify** `app/db.py`：在 `get_run_success_rate_by_cell`（结束于 `:877`）之后新增 `get_cell_availability_series`。职责：把窗口内的 `results` 行按 `(profile,model)` 分组、按 `timestamp` 落入等宽时间桶、每桶聚合成功率。
- **Modify** `app/server.py`：在 `/api/sites/trend` 路由（结束于 `:854`）之后新增 `GET /api/sites/availability`。职责：鉴权 + 调用上面的函数 + 把 `dict[tuple]` 序列化成 JSON 友好的 `{"cells":[...]}`。
- **Create** `tests/test_availability_db.py`：`get_cell_availability_series` 的单测（分桶/缺模型/空）。
- **Create** `tests/test_availability_api.py`：`/api/sites/availability` 端点冒烟测试（鉴权 + 200 + 形状）。

设计要点（口径对齐 #56，见 `app/db.py:846-877`）：
- 站点键 = `profile_name` 列（`save_result` 从 config 同源写入），空 → `"-"`。
- 模型键 = `json.loads(config_json).get("model")`，缺失 → `"-"`。
- 成功/总数 = `summary_json` 的 `success_count` / `total_requests`。
- 时间 = `results.timestamp`，格式 `"%Y%m%d_%H%M%S"`（如 `"20260609_120000"`），与现有 `cutoff = (now-timedelta(hours)).strftime("%Y%m%d_%H%M%S")` 过滤一致。

---

## Task 1: DB 函数 `get_cell_availability_series`

**Files:**
- Modify: `app/db.py`（在 `:877` 之后新增函数）
- Test: `tests/test_availability_db.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `tests/test_availability_db.py`，内容：

```python
import json
from datetime import datetime, timedelta

import pytest

from app.db import save_result


def _ts(minutes_ago: int) -> str:
    return (datetime.now() - timedelta(minutes=minutes_ago)).strftime("%Y%m%d_%H%M%S")


@pytest.mark.asyncio
async def test_availability_series_buckets():
    """近 4 小时分 4 桶（每桶 1h）：最旧桶 100%、最新桶 80%、中间两桶无数据=None。"""
    from app.db import get_cell_availability_series
    # 10 分钟前 → 落最新桶(idx3)，成功率 80%
    await save_result(
        user_id=1, test_id="avb1", filename="avb1.json", timestamp=_ts(10),
        config_json=json.dumps({"profile_name": "AvS", "model": "m"}),
        summary_json=json.dumps({"success_count": 8, "total_requests": 10}),
        percentiles_json="{}", run_id="avb",
    )
    # 3h10m 前 → 落最旧桶(idx0)，成功率 100%
    await save_result(
        user_id=1, test_id="avb2", filename="avb2.json", timestamp=_ts(190),
        config_json=json.dumps({"profile_name": "AvS", "model": "m"}),
        summary_json=json.dumps({"success_count": 10, "total_requests": 10}),
        percentiles_json="{}", run_id="avb",
    )
    cells = await get_cell_availability_series(1, hours=4, buckets=4)
    series = cells[("AvS", "m")]
    assert len(series) == 4
    assert series[0] == 100.0
    assert series[1] is None
    assert series[2] is None
    assert series[3] == 80.0


@pytest.mark.asyncio
async def test_availability_series_missing_model_groups_to_dash():
    """config 无 model → 归 '-'（与 by_cell 口径一致）。"""
    from app.db import get_cell_availability_series
    await save_result(
        user_id=1, test_id="avnm", filename="avnm.json", timestamp=_ts(5),
        config_json=json.dumps({"profile_name": "AvNM"}),
        summary_json=json.dumps({"success_count": 4, "total_requests": 8}),
        percentiles_json="{}", run_id="avnm",
    )
    cells = await get_cell_availability_series(1, hours=4, buckets=4)
    assert cells[("AvNM", "-")][3] == 50.0


@pytest.mark.asyncio
async def test_availability_series_empty_for_fresh_user():
    """全新用户、窗口内无数据 → 空字典。"""
    from app.db import get_cell_availability_series, create_user
    uid = await create_user("avail-empty@example.com", "pw")
    assert await get_cell_availability_series(uid, hours=4, buckets=4) == {}
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_availability_db.py -v`
Expected: 3 个测试全部 FAIL，错误为 `ImportError: cannot import name 'get_cell_availability_series'`（或 `AttributeError`）。

- [ ] **Step 3: 实现函数**

在 `app/db.py` 的 `get_run_success_rate_by_cell` 函数之后（`:877` 空行后）插入：

```python
async def get_cell_availability_series(user_id: int, hours: int | None = None,
                                       buckets: int = 24) -> dict:
    """按 (profile_name, model) 把最近 `hours` 小时分成 `buckets` 个等宽时间桶，
    每桶聚合成功率，返回 {(profile, model): [rate|None, ...]}（长度=buckets，旧→新）。
    桶内无数据→None。hours 为空或<=0 时默认 24；buckets<=0 时默认 24。
    分组口径与 get_run_success_rate_by_cell 一致（profile_name 列；config.model 缺失归 '-'）。"""
    from datetime import datetime, timedelta
    window_h = hours if (hours and hours > 0) else 24
    if buckets <= 0:
        buckets = 24
    now = datetime.now()
    start = now - timedelta(hours=window_h)
    cutoff = start.strftime("%Y%m%d_%H%M%S")
    bucket_secs = (now - start).total_seconds() / buckets

    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT profile_name, config_json, summary_json, timestamp "
                 "FROM results WHERE user_id=:uid AND timestamp >= :cutoff"),
            {"uid": user_id, "cutoff": cutoff},
        )
        rows = cur.fetchall()

    # {(profile, model): [[succ, total] * buckets]}
    acc: dict = {}
    for profile_name, config_json, summary_json, ts in rows:
        try:
            cfg = json.loads(config_json) if config_json else {}
        except (json.JSONDecodeError, TypeError):
            cfg = {}
        try:
            s = json.loads(summary_json)
        except (json.JSONDecodeError, TypeError):
            continue
        try:
            dt = datetime.strptime(ts, "%Y%m%d_%H%M%S")
        except (ValueError, TypeError):
            continue
        idx = int((dt - start).total_seconds() // bucket_secs) if bucket_secs > 0 else 0
        if idx < 0:
            idx = 0
        elif idx >= buckets:
            idx = buckets - 1
        profile = profile_name or "-"
        model = cfg.get("model") or "-"
        succ = int(s.get("success_count") or 0)
        tot = int(s.get("total_requests") or 0)
        cell = acc.setdefault((profile, model), [[0, 0] for _ in range(buckets)])
        cell[idx][0] += succ
        cell[idx][1] += tot

    out: dict = {}
    for cell, series in acc.items():
        out[cell] = [round(s / t * 100, 1) if t > 0 else None for s, t in series]
    return out
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_availability_db.py -v`
Expected: 3 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add app/db.py tests/test_availability_db.py
git commit -m "feat: 新增 get_cell_availability_series 按(站点,模型)分时间桶聚合成功率 (#58)"
```

---

## Task 2: 端点 `GET /api/sites/availability`

**Files:**
- Modify: `app/server.py`（在 `:854` 之后新增路由）
- Test: `tests/test_availability_api.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `tests/test_availability_api.py`，内容：

```python
import pytest
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_sites_availability_smoke(client):
    """鉴权后返回 200 与 {"cells": [...]} 形状（新用户无数据 → 空列表）。"""
    headers = await auth_headers(client)
    r = await client.get("/api/sites/availability?hours=4&buckets=4", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "cells" in body
    assert isinstance(body["cells"], list)


@pytest.mark.asyncio
async def test_sites_availability_requires_auth(client):
    """未带鉴权头 → 401。"""
    r = await client.get("/api/sites/availability")
    assert r.status_code == 401
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_availability_api.py -v`
Expected: `test_sites_availability_smoke` FAIL（404，路由不存在）；`test_sites_availability_requires_auth` 可能已 PASS（无路由时 FastAPI 对未知路径返回 404 而非 401，故此条也可能 FAIL 为 404）——两条都应在实现后转为预期。

- [ ] **Step 3: 实现路由**

在 `app/server.py` 的 `/api/sites/trend` 处理函数之后（`get_site_trend_handler` 结束、`# ---- Profiles Routes ----` 之前，约 `:855`）插入：

```python
@app.get("/api/sites/availability")
async def sites_availability(hours: int | None = None, buckets: int = 24,
                             user: dict = Depends(get_current_user)):
    """看板用：每个 (站点,模型) 在最近窗口内分时间桶的成功率序列。
    返回 {"cells": [{"profile","model","series":[rate|None,...]}, ...]}。"""
    from app.db import get_cell_availability_series
    cells = await get_cell_availability_series(user["user_id"], hours=hours, buckets=buckets)
    return {"cells": [
        {"profile": p, "model": m, "series": s} for (p, m), s in cells.items()
    ]}
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_availability_api.py -v`
Expected: 2 个测试全部 PASS。

- [ ] **Step 5: 全量后端测试回归**

Run: `python -m pytest -q`
Expected: 全绿（新增 5 条通过；既有测试不受影响）。若有失败，应为本次新增以外的 pre-existing，请先确认非本改动引入。

- [ ] **Step 6: 提交**

```bash
git add app/server.py tests/test_availability_api.py
git commit -m "feat: 新增 /api/sites/availability 端点供看板可用性柱 (#58)"
```

---

## Self-Review（计划自审）

**Spec 覆盖（对照设计 §5.3 / §8 后端要求）：**
- ✅「按 (站点,模型) 分时间桶聚合成功率」的新 DB 函数 → Task 1。
- ✅「新端点暴露给前端」→ Task 2。
- ✅「分组口径借鉴 by_cell、函数另写」→ Task 1 实现复用口径但是独立函数。
- ✅「Python 端解析、跨方言一致」→ 实现纯 Python 分桶，不依赖 json_extract/jsonb。
- ✅「站点行平均由前端算」→ 本阶段只出 per-cell 序列，站点级平均留前端（阶段一），后端不掺和，边界清晰。
- 阶段一（前端看板消费）、阶段二（设置 hub）、阶段三（定时任务/告警就地建）不在本计划，将各自成计划。

**占位符扫描：** 无 TBD/TODO；每个代码步骤均含完整可粘贴代码与确切命令/预期。

**类型/命名一致性：**
- 函数名 `get_cell_availability_series` 在 db 实现、db 测试、server 路由、端点内 import 四处一致。
- 端点用 `user["user_id"]`（与 `sites_summary`/`get_site_trend_handler` 同款，已核 `server.py:838,853`）。
- 返回键 `cells` / `profile` / `model` / `series` 在端点与测试间一致。
- `save_result(...)` 调用参数与签名（`app/db.py:815-819`）一致：含 `percentiles_json`、`run_id`。

**边界：** 空 run/空窗口 → `{}`（Task1 测）；缺 model → `"-"`（Task1 测）；`timestamp` 解析失败 → 跳过该行（实现内 try/except）；`buckets`/`hours` 非法 → 兜底默认值。
