# 告警器解耦 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把内联在定时任务里的飞书告警 webhook 抽成可复用的全局「告警器（notifier）」实体，任务改为引用 `alert_notifier_id`。

**Architecture:** 新增 `notifiers` 表（按 user 隔离）+ 一套 CRUD API；定时任务表新增 `alert_notifier_id` 列、停用旧 `alert_webhook` 列；调度器改为按 id 查告警器拿实时 webhook；前端两处任务表单的 webhook 输入框换成告警器下拉，新增告警器管理 UI。阈值/开关仍留任务上，触发逻辑不变。

**Tech Stack:** Python + FastAPI + SQLAlchemy(async) + SQLite/PostgreSQL；前端 Vue 3 + Vite；测试 pytest(async httpx client) + vitest(build)。

**设计文档：** `docs/superpowers/specs/2026-06-05-notifier-decoupling-design.md`

**关键约定（全程遵守）：**
- `alert_notifier_id INTEGER NOT NULL DEFAULT 0`，`0` = 未选告警器（主键从 1 起，0 安全作哨兵）。
- 删除告警器：被任务引用则拒绝，返回引用数（同事务内 COUNT+DELETE，避免 TOCTOU）。
- `GET /api/notifiers` 返回的 webhook **脱敏**（只回 host + 尾部打码）；编辑时 webhook 留空 = 不改。
- 旧 `alert_webhook` 列物理保留、停止读写（不做 DROP COLUMN）。
- notifier 函数在调用处 `import`（与现有 `_maybe_send_alert`/`alert_test` 一致，便于测试 monkeypatch）。

**测试运行：** 后端 `python -m pytest tests/ -v`；前端 `cd frontend && bun run build`（前端用 bun）。

---

## Task 1: notifiers 表 + alert_notifier_id 列（schema 与迁移）

**Files:**
- Modify: `app/db.py`（`_SQLITE_SCHEMA` ~42 行、`_PG_SCHEMA` ~142 行、`init_db()` 迁移段 ~311-330 行）
- Test: `tests/test_alert_db.py`

- [ ] **Step 1: 写失败测试 —— 建表后能插入/读取告警器，且任务有 alert_notifier_id 列**

在 `tests/test_alert_db.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_notifier_table_and_task_column_exist():
    from app.db import engine
    from sqlalchemy import text
    async with engine.connect() as conn:
        # notifiers 表可插入
        await conn.execute(text(
            "INSERT INTO notifiers (user_id, name, type, webhook) "
            "VALUES (1, 'n1', 'feishu', 'https://open.feishu.cn/x')"))
        # scheduled_tasks 有 alert_notifier_id 列（默认 0）
        cur = await conn.execute(text(
            "SELECT alert_notifier_id FROM scheduled_tasks LIMIT 0"))
        assert cur is not None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_alert_db.py::test_notifier_table_and_task_column_exist -v`
Expected: FAIL（`no such table: notifiers` 或 `no such column`）

- [ ] **Step 3: 加 notifiers 表到两套 schema**

在 `_SQLITE_SCHEMA` 里（紧跟 `scheduled_tasks` 表定义之后）加：

```sql
CREATE TABLE IF NOT EXISTS notifiers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    type       TEXT NOT NULL DEFAULT 'feishu',
    webhook    TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, name)
);
```

在 `_PG_SCHEMA` 里（紧跟 PG 的 `scheduled_tasks` 表定义之后）加：

```sql
CREATE TABLE IF NOT EXISTS notifiers (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    type       TEXT NOT NULL DEFAULT 'feishu',
    webhook    TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, name)
);
```

- [ ] **Step 4: 加 alert_notifier_id 列迁移到 init_db()**

在 `init_db()` 里 `scheduled_tasks 告警列：对已有表 ALTER TABLE` 那段（SQLite 与 PG 两个分支）各加一行：

SQLite 分支（与现有 `alert_webhook` 等并列，包在 try/except 里）：
```python
"ALTER TABLE scheduled_tasks ADD COLUMN alert_notifier_id INTEGER NOT NULL DEFAULT 0",
```

PG 分支：
```python
"ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS alert_notifier_id INTEGER NOT NULL DEFAULT 0",
```

> 注：新表 `CREATE TABLE IF NOT EXISTS` 由 `init_db()` 执行 schema 时自动建，无需额外迁移代码。`ON DELETE CASCADE` + 现有 `PRAGMA foreign_keys=ON`（db.py:34-38）保证删用户自动清理，`delete_user` 无需改。

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/test_alert_db.py::test_notifier_table_and_task_column_exist -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add app/db.py tests/test_alert_db.py
git commit -m "feat(db): 新增 notifiers 表与 scheduled_tasks.alert_notifier_id 列 (#33)"
```

---

## Task 2: db.py 告警器 CRUD 函数

**Files:**
- Modify: `app/db.py`（在 Profiles CRUD 段之后新增一段 Notifiers CRUD）
- Test: `tests/test_alert_db.py`

- [ ] **Step 1: 写失败测试 —— CRUD + 删除引用拦截**

在 `tests/test_alert_db.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_notifier_crud_and_delete_guard():
    from app.db import (create_user, create_notifier, list_notifiers,
                        get_notifier, update_notifier, delete_notifier,
                        create_scheduled_task, update_scheduled_task)
    uid = await create_user("ntf@example.com", "pw")
    nid = await create_notifier(uid, "运维群", "https://open.feishu.cn/hook/a")
    # list
    items = await list_notifiers(uid)
    assert len(items) == 1 and items[0]["name"] == "运维群"
    # get
    n = await get_notifier(nid)
    assert n["webhook"] == "https://open.feishu.cn/hook/a" and n["type"] == "feishu"
    # update
    await update_notifier(nid, name="新名", webhook="https://open.feishu.cn/hook/b")
    assert (await get_notifier(nid))["name"] == "新名"
    # update 留空 webhook = 不改
    await update_notifier(nid, webhook="")
    assert (await get_notifier(nid))["webhook"] == "https://open.feishu.cn/hook/b"
    # 未被引用可删
    ok, refs = await delete_notifier(nid)
    assert ok is True and refs == 0
    # 被任务引用则拒绝
    nid2 = await create_notifier(uid, "群2", "https://open.feishu.cn/hook/c")
    sid = await create_scheduled_task(uid, "t", ["s"], {}, "interval", "300")
    await update_scheduled_task(sid, alert_notifier_id=nid2)
    ok2, refs2 = await delete_notifier(nid2)
    assert ok2 is False and refs2 == 1
    assert await get_notifier(nid2) is not None  # 没被删
```

> 注：若 `create_user` 签名不同，按 `tests/conftest.py` 里现有用法调整。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_alert_db.py::test_notifier_crud_and_delete_guard -v`
Expected: FAIL（`cannot import name 'create_notifier'`）

- [ ] **Step 3: 实现 CRUD 函数**

在 `app/db.py` 的 Profiles CRUD 段之后新增：

```python
# ---- Notifiers CRUD ----

def _row_to_notifier(row) -> dict:
    return dict(row._mapping)


async def create_notifier(user_id: int, name: str, webhook: str,
                          type: str = "feishu") -> int:
    async with engine.begin() as conn:
        cur = await conn.execute(
            text("""INSERT INTO notifiers (user_id, name, type, webhook)
                   VALUES (:uid, :name, :type, :wh)"""),
            {"uid": user_id, "name": name, "type": type, "wh": webhook},
        )
        if _is_sqlite:
            return cur.lastrowid
        result = await conn.execute(text("SELECT lastval()"))
        return (result.fetchone())[0]


async def list_notifiers(user_id: int) -> list[dict]:
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT * FROM notifiers WHERE user_id=:uid ORDER BY id"),
            {"uid": user_id},
        )
        return [_row_to_notifier(r) for r in cur.fetchall()]


async def get_notifier(notifier_id: int) -> Optional[dict]:
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT * FROM notifiers WHERE id=:id"), {"id": notifier_id}
        )
        row = cur.fetchone()
        return _row_to_notifier(row) if row else None


async def update_notifier(notifier_id: int, **fields):
    async with engine.begin() as conn:
        allowed = {"name", "webhook", "type"}
        set_parts = []
        values = {"id": notifier_id}
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "webhook" and (v is None or v == ""):
                continue  # 留空 = 不改 webhook（避免覆盖成空）
            set_parts.append(f"{k}=:{k}")
            values[k] = v
        if not set_parts:
            return
        set_parts.append(f"updated_at={_now_sql()}")
        await conn.execute(
            text(f"UPDATE notifiers SET {', '.join(set_parts)} WHERE id=:id"),
            values,
        )


async def delete_notifier(notifier_id: int) -> tuple[bool, int]:
    """同事务内先查引用再删，避免 TOCTOU。返回 (是否已删, 引用任务数)。"""
    async with engine.begin() as conn:
        cur = await conn.execute(
            text("SELECT COUNT(*) FROM scheduled_tasks WHERE alert_notifier_id=:id"),
            {"id": notifier_id},
        )
        refs = (cur.fetchone())[0]
        if refs > 0:
            return False, refs
        await conn.execute(
            text("DELETE FROM notifiers WHERE id=:id"), {"id": notifier_id}
        )
        return True, 0
```

> 检查文件顶部已 `from typing import Optional`（现有 `get_scheduled_task` 已用，无需新增）。`_now_sql()` 为现有 helper。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_alert_db.py::test_notifier_crud_and_delete_guard -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/db.py tests/test_alert_db.py
git commit -m "feat(db): 告警器 CRUD 函数与删除引用拦截 (#33)"
```

---

## Task 3: 任务 DB 函数改用 alert_notifier_id

**Files:**
- Modify: `app/db.py`（`create_scheduled_task` ~1126、`update_scheduled_task` allowed 集合 ~1201）
- Test: `tests/test_alert_db.py`

- [ ] **Step 1: 写失败测试 —— 创建任务时带 alert_notifier_id 并能读回**

在 `tests/test_alert_db.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_create_task_with_notifier_id():
    from app.db import create_user, create_notifier, create_scheduled_task, get_scheduled_task
    uid = await create_user("tnid@example.com", "pw")
    nid = await create_notifier(uid, "g", "https://open.feishu.cn/hook/z")
    sid = await create_scheduled_task(uid, "t", ["s"], {}, "interval", "300",
                                      alert_notifier_id=nid, alert_threshold=80,
                                      alert_enabled=True)
    row = await get_scheduled_task(sid)
    assert row["alert_notifier_id"] == nid
    assert row["alert_threshold"] == 80
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_alert_db.py::test_create_task_with_notifier_id -v`
Expected: FAIL（`create_scheduled_task() got an unexpected keyword argument 'alert_notifier_id'`）

- [ ] **Step 3: 改 create_scheduled_task —— 去掉 alert_webhook 形参/列，加 alert_notifier_id**

把 `create_scheduled_task`（db.py:1126-1144）整体替换为：

```python
async def create_scheduled_task(user_id: int, name: str, profile_ids: list,
                                configs_json: dict, schedule_type: str,
                                schedule_value: str, alert_notifier_id: int = 0,
                                alert_threshold: int = 90,
                                alert_enabled: bool = False) -> int:
    async with engine.begin() as conn:
        cur = await conn.execute(
            text("""INSERT INTO scheduled_tasks (user_id, name, profile_ids, configs_json,
                    schedule_type, schedule_value, alert_notifier_id, alert_threshold, alert_enabled)
                   VALUES (:uid, :name, :pids, :cj, :st, :sv, :ani, :at, :ae)"""),
            {"uid": user_id, "name": name, "pids": json.dumps(profile_ids),
             "cj": json.dumps(configs_json), "st": schedule_type, "sv": schedule_value,
             "ani": alert_notifier_id, "at": alert_threshold,
             "ae": (1 if alert_enabled else 0) if _is_sqlite else bool(alert_enabled)},
        )
        if _is_sqlite:
            return cur.lastrowid
        result = await conn.execute(text("SELECT lastval()"))
        return (result.fetchone())[0]
```

- [ ] **Step 4: 改 update_scheduled_task allowed 集合**

把 `update_scheduled_task`（db.py:1201-1203）的 `allowed` 集合：去掉 `"alert_webhook"`、加 `"alert_notifier_id"`：

```python
        allowed = {"name", "profile_ids", "configs_json", "schedule_type",
                   "schedule_value", "status", "last_run_at", "next_run_at", "run_count",
                   "alert_notifier_id", "alert_threshold", "alert_enabled", "alert_state"}
```

- [ ] **Step 5: 迁移依赖 alert_webhook 的既有 DB 用例**

既有用例直接传 `alert_webhook=` 给 `create_scheduled_task` / `update_scheduled_task`，去掉形参后会报错，必须改：

- 删除 `test_alert_fields_roundtrip`（tests/test_alert_db.py:14-24）—— 其 roundtrip 已被本 Task 的 `test_create_task_with_notifier_id` 覆盖。
- 改 `test_update_alert_enabled_roundtrip`（tests/test_alert_db.py:28-37）：去掉 `alert_webhook="..."` 入参与 `row["alert_webhook"]` 断言，只保留 `alert_enabled` 的开关 roundtrip：

```python
@pytest.mark.asyncio
async def test_update_alert_enabled_roundtrip():
    sid = await create_scheduled_task(1, "t3", [], {}, "interval", "300")
    await update_scheduled_task(sid, alert_enabled=True)
    assert bool((await get_scheduled_task(sid))["alert_enabled"]) is True
    await update_scheduled_task(sid, alert_enabled=False)
    assert bool((await get_scheduled_task(sid))["alert_enabled"]) is False
```

- [ ] **Step 6: 跑测试确认通过 + 全量告警 DB 测试不回归**

Run: `python -m pytest tests/test_alert_db.py -v`
Expected: PASS（含新用例与迁移后的既有用例）

- [ ] **Step 7: 提交**

```bash
git add app/db.py tests/test_alert_db.py
git commit -m "feat(db): 定时任务改用 alert_notifier_id (#33)"
```

---

## Task 4: server.py 入参校验改 notifier_id

**Files:**
- Modify: `app/server.py`（`_extract_alert_fields` ~2028、`create_schedule` ~2085-2093、`update_schedule` ~2124）
- Test: `tests/test_alert_api.py`

- [ ] **Step 1: 写失败测试 —— 任务收 alert_notifier_id 并校验归属**

替换 `tests/test_alert_api.py` 中 `test_create_schedule_with_alert`（15-29 行）为基于 notifier_id 的版本，并新增归属校验：

```python
async def _make_notifier(client, headers, name="g", webhook="https://open.feishu.cn/hook/x"):
    resp = await client.post("/api/notifiers",
                             json={"name": name, "webhook": webhook}, headers=headers)
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_schedule_with_notifier(client):
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    nid = await _make_notifier(client, headers)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "schedule_value": "300",
        "alert_enabled": True, "alert_notifier_id": nid, "alert_threshold": 88,
    }, headers=headers)
    assert resp.status_code == 200
    sid = resp.json()["id"]
    row = await get_scheduled_task(sid)
    assert row["alert_notifier_id"] == nid and row["alert_threshold"] == 88


@pytest.mark.asyncio
async def test_create_schedule_rejects_foreign_notifier(client):
    from tests.conftest import login_and_get_token
    headers_a = await auth_headers(client)
    nid_a = await _make_notifier(client, headers_a)
    headers_b = await login_and_get_token(client, "b2@example.com", "pw12345678")
    await _make_profile(client, headers_b)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "schedule_value": "300",
        "alert_enabled": True, "alert_notifier_id": nid_a,
    }, headers=headers_b)
    assert resp.status_code == 400
```

同时删除旧的 `test_create_schedule_rejects_bad_webhook`（31-40 行，webhook 校验已移到 notifier 层，Task 5 覆盖）。

> `login_and_get_token` 的参数与既有 `test_alert_test_rejects_other_user` 用法保持一致；邮箱用未注册过的。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_alert_api.py::test_create_schedule_with_notifier tests/test_alert_api.py::test_create_schedule_rejects_foreign_notifier -v`
Expected: FAIL（notifiers 端点不存在 / 未校验 notifier_id）

> 说明：此 Task 依赖 Task 5 的 `POST /api/notifiers` 端点。建议与 Task 5 连续实现；先在本 Task 写入服务端校验逻辑，端点在 Task 5 落地后这两个测试转 PASS。

- [ ] **Step 3: 改 _extract_alert_fields —— 加 user_id 参数 + notifier_id 校验，删 webhook 分支**

把 `_extract_alert_fields`（server.py:2028-2047）替换为：

```python
async def _extract_alert_fields(body: dict, user_id: int):
    """从请求体提取并校验告警字段。返回 (fields, error)。error 非空表示校验失败。"""
    from app.db import get_notifier
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
    if "alert_notifier_id" in body:
        try:
            nid = int(body.get("alert_notifier_id") or 0)
        except (ValueError, TypeError):
            return None, "alert_notifier_id 非法"
        if nid:
            n = await get_notifier(nid)
            if not n or n["user_id"] != user_id:
                return None, "告警器不存在或无权使用"
        out["alert_notifier_id"] = nid
    return out, None
```

> 注意：函数从同步改为 `async`（因为要 `await get_notifier`）。

- [ ] **Step 4: 改两处调用点**

`create_schedule`（server.py:2085）改为 `await` 并传 user_id，并把 create 调用的 `alert_webhook=...` 换成 `alert_notifier_id=...`：

```python
    alert_fields, alert_err = await _extract_alert_fields(body, user_id)
    if alert_err:
        return JSONResponse({"error": alert_err}, status_code=400)

    sid = await create_scheduled_task(
        user_id, name, profile_ids, configs_json, schedule_type, schedule_value,
        alert_notifier_id=alert_fields.get("alert_notifier_id", 0),
        alert_threshold=alert_fields.get("alert_threshold", 90),
        alert_enabled=alert_fields.get("alert_enabled", False),
    )
```

`update_schedule`（server.py:2124）改为 `await` 并传 user_id：

```python
    alert_fields, alert_err = await _extract_alert_fields(body, user_id)
    if alert_err:
        return JSONResponse({"error": alert_err}, status_code=400)
    fields.update(alert_fields)
```

- [ ] **Step 5: 跑测试（依赖 Task 5 端点；先确认无语法/导入错误）**

Run: `python -m pytest tests/test_alert_api.py -v`
Expected: 与 notifier 端点相关的用例在 Task 5 完成后 PASS；本步先确认无 import/语法错误。

- [ ] **Step 6: 提交**

```bash
git add app/server.py tests/test_alert_api.py
git commit -m "feat(api): 任务告警入参改用 alert_notifier_id 并校验归属 (#33)"
```

---

## Task 5: server.py 告警器 CRUD + test 端点

**Files:**
- Modify: `app/server.py`（在 schedules 端点附近新增 notifiers 端点；改写 alert_test）
- Test: `tests/test_alert_api.py`

- [ ] **Step 1: 写失败测试 —— notifier CRUD + 脱敏 + 删除拦截 + test 端点**

替换 `tests/test_alert_api.py` 中 3 个旧 alert-test 用例（`test_alert_test_endpoint`/`test_alert_test_rejects_other_user`/`test_alert_test_requires_webhook`，51-99 行）为 notifier 级版本，并新增 CRUD/脱敏/删除拦截：

```python
@pytest.mark.asyncio
async def test_notifier_crud_api(client):
    headers = await auth_headers(client)
    # 创建
    r = await client.post("/api/notifiers",
                          json={"name": "群A", "webhook": "https://open.feishu.cn/hook/aaa"},
                          headers=headers)
    assert r.status_code == 200
    nid = r.json()["id"]
    # 列表：webhook 脱敏（不回明文全量）
    items = (await client.get("/api/notifiers", headers=headers)).json()
    assert len(items) == 1
    assert items[0]["webhook"] != "https://open.feishu.cn/hook/aaa"
    assert "open.feishu.cn" in items[0]["webhook"]
    # 更新
    r2 = await client.put(f"/api/notifiers/{nid}",
                          json={"name": "群A改"}, headers=headers)
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_notifier_create_rejects_bad_webhook(client):
    headers = await auth_headers(client)
    r = await client.post("/api/notifiers",
                          json={"name": "x", "webhook": "http://evil.com/h"},
                          headers=headers)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_notifier_delete_guard(client):
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    nid = await _make_notifier(client, headers)
    # 任务引用它
    await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "schedule_value": "300",
        "alert_enabled": True, "alert_notifier_id": nid,
    }, headers=headers)
    # 删除被拦截
    r = await client.delete(f"/api/notifiers/{nid}", headers=headers)
    assert r.status_code == 409
    assert "1" in str(r.json())


@pytest.mark.asyncio
async def test_notifier_test_endpoint(client, monkeypatch):
    sent = {}
    async def fake_send(url, payload, timeout=10.0):
        sent["url"] = url
        return True
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    headers = await auth_headers(client)
    nid = await _make_notifier(client, headers)
    r = await client.post(f"/api/notifiers/{nid}/test", headers=headers)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert sent["url"].startswith("https://open.feishu.cn")


@pytest.mark.asyncio
async def test_notifier_rejects_other_user(client):
    from tests.conftest import login_and_get_token
    headers_a = await auth_headers(client)
    nid = await _make_notifier(client, headers_a)
    headers_b = await login_and_get_token(client, "b3@example.com", "pw12345678")
    r = await client.delete(f"/api/notifiers/{nid}", headers=headers_b)
    assert r.status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_alert_api.py -k notifier -v`
Expected: FAIL（notifiers 端点 404/不存在）

- [ ] **Step 3: 实现脱敏 helper**

在 `app/server.py` 合适位置（靠近 `_extract_alert_fields`）新增：

```python
def _mask_webhook(url: str) -> str:
    """脱敏：保留 host + 路径尾 4 位，其余打码。不回明文全量。"""
    from urllib.parse import urlparse
    if not url:
        return ""
    try:
        p = urlparse(url)
        tail = url[-4:] if len(url) > 4 else ""
        return f"https://{p.hostname}/***{tail}"
    except Exception:
        return "***"
```

- [ ] **Step 4: 实现 notifier CRUD + test 端点**

在 `app/server.py` schedules 端点附近新增：

```python
@app.get("/api/notifiers")
async def list_notifiers_endpoint(user: dict = Depends(get_current_user)):
    from app.db import list_notifiers
    items = await list_notifiers(user["user_id"])
    return [
        {"id": n["id"], "name": n["name"], "type": n["type"],
         "webhook": _mask_webhook(n["webhook"])}
        for n in items
    ]


@app.post("/api/notifiers")
async def create_notifier_endpoint(request: Request, user: dict = Depends(get_current_user)):
    from app.db import create_notifier
    from app.notifier import is_allowed_webhook
    body = await request.json()
    name = (body.get("name") or "").strip()
    webhook = (body.get("webhook") or "").strip()
    if not name:
        return JSONResponse({"error": "名称不能为空"}, status_code=400)
    if not is_allowed_webhook(webhook):
        return JSONResponse({"error": "webhook 必须是 https 的飞书域名 (open.feishu.cn / open.larksuite.com)"}, status_code=400)
    try:
        nid = await create_notifier(user["user_id"], name, webhook)
    except Exception:
        return JSONResponse({"error": "创建失败：名称可能重复"}, status_code=400)
    return {"id": nid, "status": "created"}


@app.put("/api/notifiers/{notifier_id}")
async def update_notifier_endpoint(notifier_id: int, request: Request,
                                   user: dict = Depends(get_current_user)):
    from app.db import get_notifier, update_notifier
    from app.notifier import is_allowed_webhook
    n = await get_notifier(notifier_id)
    if not n or n["user_id"] != user["user_id"]:
        return JSONResponse({"error": "Not found"}, status_code=404)
    body = await request.json()
    fields = {}
    if "name" in body:
        nm = (body.get("name") or "").strip()
        if not nm:
            return JSONResponse({"error": "名称不能为空"}, status_code=400)
        fields["name"] = nm
    if "webhook" in body:
        wh = (body.get("webhook") or "").strip()
        if wh and not is_allowed_webhook(wh):
            return JSONResponse({"error": "webhook 必须是 https 的飞书域名"}, status_code=400)
        fields["webhook"] = wh  # 空串 = 不改（db 层 update_notifier 已处理）
    await update_notifier(notifier_id, **fields)
    return {"status": "updated"}


@app.delete("/api/notifiers/{notifier_id}")
async def delete_notifier_endpoint(notifier_id: int, user: dict = Depends(get_current_user)):
    from app.db import get_notifier, delete_notifier
    n = await get_notifier(notifier_id)
    if not n or n["user_id"] != user["user_id"]:
        return JSONResponse({"error": "Not found"}, status_code=404)
    ok, refs = await delete_notifier(notifier_id)
    if not ok:
        return JSONResponse({"error": f"还有 {refs} 个任务在用，先解绑再删", "refs": refs}, status_code=409)
    return {"status": "deleted"}


@app.post("/api/notifiers/{notifier_id}/test")
async def notifier_test(notifier_id: int, user: dict = Depends(get_current_user)):
    from app.db import get_notifier
    # notifier 函数内 import：保持 send_webhook 调用时解析，便于测试 monkeypatch，勿上移顶部
    from app.notifier import build_feishu_card, send_webhook, is_allowed_webhook
    from datetime import datetime
    n = await get_notifier(notifier_id)
    if not n or n["user_id"] != user["user_id"]:
        return JSONResponse({"error": "Not found"}, status_code=404)
    webhook = (n.get("webhook") or "").strip()
    if not webhook or not is_allowed_webhook(webhook):
        return JSONResponse({"error": "该告警器 webhook 非法"}, status_code=400)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    card = build_feishu_card("alert", n.get("name", ""), "测试", 0.0, 90, ts)
    card["card"]["header"]["title"]["content"] = "🔔 告警测试（这是一条测试消息）"
    ok = await send_webhook(webhook, card)
    return {"ok": ok}
```

- [ ] **Step 5: 删除旧的 alert_test 端点**

删除 `app/server.py` 的 `@app.post("/api/schedules/{task_id}/alert-test")` 端点及其 `alert_test` 函数（2205-2222 行）。

- [ ] **Step 6: 跑测试确认通过（含 Task 4 的两个用例）**

Run: `python -m pytest tests/test_alert_api.py -v`
Expected: PASS（全部，含 Task 4 的 `test_create_schedule_with_notifier` / `test_create_schedule_rejects_foreign_notifier`）

- [ ] **Step 7: 提交**

```bash
git add app/server.py tests/test_alert_api.py
git commit -m "feat(api): 告警器 CRUD + 测试端点，移除任务级 alert-test (#33)"
```

---

## Task 6: scheduler 改读告警器

**Files:**
- Modify: `app/scheduler.py`（`_maybe_send_alert` ~227-249）
- Test: `tests/test_alert_scheduler.py`

- [ ] **Step 1: 写失败测试 —— 引用告警器后跌破阈值能发；notifier_id=0 跳过**

查看 `tests/test_alert_scheduler.py` 现有用例的构造方式（如何造 task_row、如何 monkeypatch send_webhook），在末尾追加同风格用例：

```python
@pytest.mark.asyncio
async def test_alert_uses_notifier_webhook(monkeypatch):
    from app import scheduler as sch
    from app.db import create_user, create_notifier
    sent = {}
    async def fake_send(url, payload, timeout=10.0):
        sent["url"] = url
        return True
    monkeypatch.setattr("app.notifier.send_webhook", fake_send)
    async def fake_rate(run_ids):
        return 0, 10  # 成功率 0%，必触发
    monkeypatch.setattr("app.db.get_run_success_rate", fake_rate)

    uid = await create_user("sch_ntf@example.com", "pw")
    nid = await create_notifier(uid, "g", "https://open.feishu.cn/hook/sch")
    task_row = {"alert_enabled": True, "alert_notifier_id": nid,
                "alert_threshold": 90, "alert_state": "ok",
                "name": "t", "profile_ids": ["s"]}
    await sch._maybe_send_alert(1, task_row, ["r1"])
    assert sent.get("url") == "https://open.feishu.cn/hook/sch"


@pytest.mark.asyncio
async def test_alert_skips_when_no_notifier(monkeypatch):
    from app import scheduler as sch
    called = {"n": 0}
    async def fake_send(url, payload, timeout=10.0):
        called["n"] += 1
        return True
    monkeypatch.setattr("app.notifier.send_webhook", fake_send)
    task_row = {"alert_enabled": True, "alert_notifier_id": 0,
                "alert_threshold": 90, "alert_state": "ok",
                "name": "t", "profile_ids": ["s"]}
    await sch._maybe_send_alert(1, task_row, ["r1"])
    assert called["n"] == 0
```

> 按 `tests/test_alert_scheduler.py` 现有 monkeypatch 目标路径微调（现有用例怎么打 send_webhook 就怎么打）。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_alert_scheduler.py::test_alert_uses_notifier_webhook tests/test_alert_scheduler.py::test_alert_skips_when_no_notifier -v`
Expected: FAIL（仍读 alert_webhook）

- [ ] **Step 3: 改 _maybe_send_alert**

把 `_maybe_send_alert`（scheduler.py:227-249）替换为：

```python
async def _maybe_send_alert(task_id: int, task_row: dict, run_ids: list):
    """按落库结果聚合成功率，状态翻转时发飞书卡片并写回 alert_state。全程不抛。"""
    from app.db import get_run_success_rate, get_notifier
    # notifier 在函数内 import：保持 send_webhook 在调用时解析，便于测试 monkeypatch
    from app.notifier import evaluate_alert, build_feishu_card, send_webhook

    notifier_id = task_row.get("alert_notifier_id") or 0
    if not task_row.get("alert_enabled") or not notifier_id:
        return  # 未开启 或 未选告警器：不发、不报错
    ntf = await get_notifier(notifier_id)
    webhook = (ntf or {}).get("webhook", "").strip() if ntf else ""
    if not webhook:
        log.info("定时任务 #%d 告警器缺失或 webhook 空，跳过告警", task_id)
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
        profiles_text = ", ".join(task_row.get("profile_ids", []) or []) or "-"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        card = build_feishu_card(action, task_row.get("name", ""), profiles_text, rate, threshold, ts)
        await send_webhook(webhook, card)
    if new_state != prev:
        await update_scheduled_task(task_id, alert_state=new_state)
```

- [ ] **Step 4: 迁移既有调度告警用例的 `_seed` helper**

`tests/test_alert_scheduler.py` 的 `_seed`（8-22 行）给 `create_scheduled_task` 传了 `alert_webhook=`，且所有调度告警用例都经它造 task_row。改 `_seed`：先建 notifier，把 `alert_webhook=...` 换成 `alert_notifier_id=`：

```python
async def _seed(rate_pair, alert_state="ok", enabled=True):
    from app.db import create_notifier
    succ, tot = rate_pair
    nid = await create_notifier(1, "g", "https://open.feishu.cn/x")
    sid = await create_scheduled_task(
        1, "t", ["SiteA"], {}, "interval", "300",
        alert_notifier_id=nid, alert_threshold=90, alert_enabled=enabled,
    )
    if alert_state != "ok":
        await update_scheduled_task(sid, alert_state=alert_state)
    await save_result(
        user_id=1, test_id="a", filename="a.json", timestamp="20260604_120000",
        config_json="{}", summary_json=json.dumps({"success_count": succ, "total_requests": tot}),
        percentiles_json="{}", run_id="run-1", scheduled_task_id=sid,
    )
    return sid
```

> 这样 `_maybe_send_alert` 经 `get_notifier(nid)` 拿到 `https://open.feishu.cn/x`，既有的 fire/recover/disabled/no-results 用例逻辑不变。`test_no_alert_when_disabled` 用 `enabled=False` 仍走「未开启即跳过」分支，通过。

- [ ] **Step 5: 跑测试确认通过 + 既有调度告警测试不回归**

Run: `python -m pytest tests/test_alert_scheduler.py -v`
Expected: PASS（含新用例与迁移后的既有用例）

- [ ] **Step 6: 全量后端测试**

Run: `python -m pytest tests/ -v`
Expected: PASS（全绿）

- [ ] **Step 7: 提交**

```bash
git add app/scheduler.py tests/test_alert_scheduler.py
git commit -m "feat(scheduler): 告警按 notifier_id 查实时 webhook (#33)"
```

---

## Task 7: 前端 API 客户端

**Files:**
- Modify: `frontend/src/api/index.js`（~47-61 Schedules 段）

- [ ] **Step 1: 新增 notifier API + 改 alertTestApi**

在 `frontend/src/api/index.js` 的 Schedules 段附近新增，并把 `alertTestApi`（61 行）改为 notifier 级：

```javascript
// Notifiers
export const getNotifiers = () => api('/api/notifiers');
export const createNotifierApi = (data) => api('/api/notifiers', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const updateNotifierApi = (id, data) => api(`/api/notifiers/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const deleteNotifierApi = (id) => api(`/api/notifiers/${id}`, { method: 'DELETE' });
export const notifierTestApi = (id) => api(`/api/notifiers/${id}/test`, { method: 'POST' });
```

删除旧的 `alertTestApi`（61 行）。

- [ ] **Step 2: 构建确认无引用错误**

Run: `cd frontend && bun run build`
Expected: 构建报错指出 `alertTestApi` 仍被 `SiteSchedulesTab.vue` 引用 —— 这是预期的，Task 9 修复。可先跳过验证，待 Task 9 后统一 build。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/index.js
git commit -m "feat(web): 告警器 API 客户端，alert-test 迁移到 notifier 级 (#33)"
```

---

## Task 8: 告警器管理 UI

**Files:**
- Create: `frontend/src/components/NotifiersManager.vue`
- Modify: `frontend/src/views/SettingsView.vue`（挂载新组件）

- [ ] **Step 1: 看 SettingsView 结构，确定挂载点**

Read: `frontend/src/views/SettingsView.vue` —— 确认其分区/卡片写法，把告警器管理作为一个新卡片/分区挂进去（沿用页面现有样式 class）。

- [ ] **Step 2: 新建 NotifiersManager.vue**

```vue
<template>
  <div class="notifiers-manager">
    <div class="nm-header">
      <h3>告警器</h3>
      <button class="btn btn-primary" @click="openCreate">新建告警器</button>
    </div>
    <div v-if="items.length === 0" class="form-hint">还没有告警器，点「新建」添加一个飞书机器人。</div>
    <ul class="nm-list">
      <li v-for="n in items" :key="n.id" class="nm-item">
        <div class="nm-meta">
          <span class="nm-name">{{ n.name }}</span>
          <span class="nm-type">{{ n.type }}</span>
          <span class="nm-webhook">{{ n.webhook }}</span>
        </div>
        <div class="nm-actions">
          <button class="btn btn-ghost" :disabled="testingId === n.id" @click="onTest(n)">{{ testingId === n.id ? '发送中...' : '测试' }}</button>
          <button class="btn btn-ghost" @click="openEdit(n)">编辑</button>
          <button class="btn btn-ghost" @click="onDelete(n)">删除</button>
        </div>
      </li>
    </ul>

    <div v-if="showForm" class="nm-form">
      <div class="form-group">
        <label class="form-label">名称</label>
        <input class="form-input" v-model.trim="form.name" placeholder="运维群飞书">
      </div>
      <div class="form-group">
        <label class="form-label">飞书 Webhook URL</label>
        <input class="form-input" v-model.trim="form.webhook" :placeholder="editingId ? '留空 = 不修改' : 'https://open.feishu.cn/open-apis/bot/v2/hook/...'">
      </div>
      <div class="btn-group">
        <button class="btn btn-primary" :disabled="saving" @click="onSave">保存</button>
        <button class="btn btn-ghost" @click="closeForm">取消</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { getNotifiers, createNotifierApi, updateNotifierApi, deleteNotifierApi, notifierTestApi } from '../api/index.js';
import { toast } from '../composables/useToast.js';

const items = ref([]);
const showForm = ref(false);
const editingId = ref(null);
const saving = ref(false);
const testingId = ref(null);
const form = ref({ name: '', webhook: '' });

async function load() {
  try { items.value = await getNotifiers(); } catch (e) { toast.error('加载告警器失败'); }
}
function openCreate() { editingId.value = null; form.value = { name: '', webhook: '' }; showForm.value = true; }
function openEdit(n) { editingId.value = n.id; form.value = { name: n.name, webhook: '' }; showForm.value = true; }
function closeForm() { showForm.value = false; }

async function onSave() {
  if (!form.value.name) { toast.error('名称不能为空'); return; }
  saving.value = true;
  try {
    if (editingId.value) {
      await updateNotifierApi(editingId.value, { name: form.value.name, webhook: form.value.webhook });
    } else {
      await createNotifierApi({ name: form.value.name, webhook: form.value.webhook });
    }
    showForm.value = false;
    await load();
    toast.success('已保存');
  } catch (e) { toast.error(e?.message || '保存失败'); }
  finally { saving.value = false; }
}

async function onTest(n) {
  testingId.value = n.id;
  try { const r = await notifierTestApi(n.id); toast[r.ok ? 'success' : 'error'](r.ok ? '测试消息已发送' : '发送失败'); }
  catch (e) { toast.error('发送失败'); }
  finally { testingId.value = null; }
}

async function onDelete(n) {
  if (!confirm(`删除告警器「${n.name}」？`)) return;
  try { await deleteNotifierApi(n.id); await load(); toast.success('已删除'); }
  catch (e) { toast.error(e?.message || '删除失败'); }
}

onMounted(load);
defineExpose({ load });
</script>
```

> `toast` 用法与 `SiteSchedulesTab.vue` 一致（`import { toast } from '../composables/useToast.js'`）。若 `api()` 抛错不带 message，则 toast 文案用兜底字符串即可。

- [ ] **Step 3: 挂载进 SettingsView**

在 `frontend/src/views/SettingsView.vue` 合适分区引入并渲染：

```javascript
import NotifiersManager from '../components/NotifiersManager.vue';
```
```html
<NotifiersManager />
```

- [ ] **Step 4: 构建验证**

Run: `cd frontend && bun run build`
Expected: 与 Task 9 一起完成后整体 PASS（此时 SiteSchedulesTab 仍引用旧 alertTestApi 会报错，留待 Task 9）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/NotifiersManager.vue frontend/src/views/SettingsView.vue
git commit -m "feat(web): 告警器管理页 (#33)"
```

---

## Task 9: SiteSchedulesTab 表单改下拉

**Files:**
- Modify: `frontend/src/components/SiteSchedulesTab.vue`（创建区 ~100-112、编辑区 ~296-312、script 387/427/504/608/655、onTestAlert 671、import 335）

- [ ] **Step 1: 创建区 webhook 输入 → 告警器下拉**

把创建区（~100-112）的 `<template v-if="createForm.alert_enabled">` 内的「飞书 Webhook URL」`form-group` 替换为：

```html
            <div class="form-group full">
              <label class="form-label">告警器</label>
              <select class="form-input" v-model.number="createForm.alert_notifier_id">
                <option :value="0">未选择</option>
                <option v-for="n in notifiers" :key="n.id" :value="n.id">{{ n.name }}</option>
              </select>
              <div class="form-hint">在「设置」页管理告警器</div>
            </div>
```

- [ ] **Step 2: 编辑区同样替换 + 删测试按钮**

把编辑区（~296-312）的「飞书 Webhook URL」`form-group` 替换为同样的下拉（`v-model.number="editForm.alert_notifier_id"`），并删除「发送测试消息」按钮那个 `form-group`（308-311 行，含 `onTestAlert`）。

- [ ] **Step 3: 改 script —— 字段、加载告警器列表、删 onTestAlert**

- 把 `alert_webhook: ''`（387/427 行的表单初始化）改为 `alert_notifier_id: 0`。
- 504 行 `alert_webhook: s.alert_webhook || ''` 改为 `alert_notifier_id: s.alert_notifier_id || 0`。
- 608/655 行提交 payload 里 `alert_webhook: f.alert_webhook || ''` 改为 `alert_notifier_id: f.alert_notifier_id || 0`。
- import（327-336）去掉 `alertTestApi`，加 `getNotifiers`。
- 删除 `alertTestLoading`（353）与 `onTestAlert`（671 起）。
- 新增告警器列表加载：

```javascript
const notifiers = ref([]);
async function loadNotifiers() {
  try { notifiers.value = await getNotifiers(); } catch { notifiers.value = []; }
}
```
在现有 `onMounted` 里调用 `loadNotifiers()`（与现有加载并列）。

- [ ] **Step 4: 构建验证（含 Task 7/8）**

Run: `cd frontend && bun run build`
Expected: PASS（无 `alertTestApi` 残留引用）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/SiteSchedulesTab.vue
git commit -m "feat(web): 任务表单(SiteSchedulesTab)告警器下拉 (#33)"
```

---

## Task 10: TasksView 表单改下拉

**Files:**
- Modify: `frontend/src/views/TasksView.vue`（告警区 ~236-247、import 263、createForm 315/324、submit 511-513）

- [ ] **Step 1: webhook 输入 → 告警器下拉**

把告警区（~236-247）`v-if="createForm.alert_enabled"` 内的「飞书 Webhook URL」`form-group` 替换为：

```html
            <div class="form-group">
              <label class="form-label">告警器</label>
              <select class="form-input" v-model.number="createForm.alert_notifier_id" style="width:280px">
                <option :value="0">未选择</option>
                <option v-for="n in notifiers" :key="n.id" :value="n.id">{{ n.name }}</option>
              </select>
              <div class="form-hint">在「设置」页管理告警器</div>
            </div>
```

- [ ] **Step 2: 改 script**

- import（263）加 `getNotifiers`。
- createForm 两处（315 reset、324 ref 初始化）把 `alert_webhook: ''` 改为 `alert_notifier_id: 0`。
- submit payload（512）`alert_webhook: f.alert_webhook || ''` 改为 `alert_notifier_id: f.alert_notifier_id || 0`。
- 新增并在 `onMounted` 调用：

```javascript
const notifiers = ref([]);
async function loadNotifiers() {
  try { notifiers.value = await getNotifiers(); } catch { notifiers.value = []; }
}
```

- [ ] **Step 3: 构建验证**

Run: `cd frontend && bun run build`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/TasksView.vue
git commit -m "feat(web): 任务表单(TasksView)告警器下拉 (#33)"
```

---

## Task 11: 全量验证 + 收尾

- [ ] **Step 1: 后端全量测试**

Run: `python -m pytest tests/ -v`
Expected: PASS（全绿）

- [ ] **Step 2: 前端构建**

Run: `cd frontend && bun run build`
Expected: PASS

- [ ] **Step 3: grep 残留检查**

Run: `grep -rn "alert_webhook\|alertTestApi\|alert-test" app/ frontend/src/`
Expected: 仅 `app/db.py` 里物理保留的 `alert_webhook` 列定义（schema 字符串）可残留；应用代码、前端、API 客户端均无引用。若有其他残留，回到对应 Task 清理。

- [ ] **Step 4: 推分支 + 开 PR**

```bash
git push -u origin worktree-feat+issue-33-notifier-decoupling
gh pr create --title "重构：飞书告警解耦为可复用「告警器」(#33)" --body "Closes #33"
```

---

## 自检覆盖对照（spec → task）

- notifiers 表 / alert_notifier_id 列 → Task 1
- 告警器 CRUD + 删除引用拦截（同事务） → Task 2、Task 5
- 任务 DB 改 notifier_id → Task 3
- `_extract_alert_fields` 加 user_id + 归属校验 → Task 4
- notifier CRUD/test 端点 + webhook 脱敏 + 移除任务级 alert-test → Task 5
- scheduler 查实时 webhook + notifier_id=0 安全跳过 → Task 6
- api/index.js + 告警器管理页 → Task 7、Task 8
- 两处任务表单（SiteSchedulesTab + TasksView）改下拉 → Task 9、Task 10
- 测试重写（旧 alert-test 用例迁移）→ Task 4、Task 5
- 不迁移老数据 / 旧列物理保留 → 全程不触碰 alert_webhook 列数据
