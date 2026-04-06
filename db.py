#!/usr/bin/env python3
"""数据库层 — SQLite + aiosqlite"""

import json
from pathlib import Path
from typing import Optional

import aiosqlite

DB_PATH = Path(__file__).parent / "data" / "data.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL DEFAULT '',
    role          TEXT NOT NULL DEFAULT 'user',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS profiles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    base_url    TEXT NOT NULL DEFAULT '',
    api_key     TEXT NOT NULL DEFAULT '',
    api_version TEXT NOT NULL DEFAULT '2023-06-01',
    model       TEXT NOT NULL DEFAULT '',
    is_active   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS results (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    test_id            TEXT NOT NULL,
    filename           TEXT NOT NULL DEFAULT '',
    timestamp          TEXT NOT NULL,
    config_json        TEXT NOT NULL,
    summary_json       TEXT NOT NULL,
    percentiles_json   TEXT NOT NULL,
    errors_json        TEXT NOT NULL DEFAULT '{}',
    error_details_json TEXT NOT NULL DEFAULT '[]',
    group_id           TEXT NOT NULL DEFAULT '',
    scheduled_task_id  INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id        INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    benchmark_json TEXT NOT NULL DEFAULT '{}',
    output_dir     TEXT NOT NULL DEFAULT './data/results',
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    profile_ids     TEXT NOT NULL DEFAULT '[]',
    configs_json    TEXT NOT NULL DEFAULT '{}',
    schedule_type   TEXT NOT NULL DEFAULT 'interval',
    schedule_value  TEXT NOT NULL DEFAULT '300',
    status          TEXT NOT NULL DEFAULT 'active',
    last_run_at     TEXT,
    next_run_at     TEXT,
    run_count       INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_db: Optional[aiosqlite.Connection] = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(str(DB_PATH))
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def init_db():
    """初始化数据库，创建表结构"""
    db = await get_db()
    await db.executescript(_SCHEMA)
    await db.commit()


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None


# ---- Users CRUD ----

async def create_user(email: str, password_hash: str, display_name: str = "", role: str = "user") -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO users (email, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
        (email.lower(), password_hash, display_name, role),
    )
    await db.commit()
    return cur.lastrowid


async def get_user_by_email(email: str) -> Optional[dict]:
    db = await get_db()
    cur = await db.execute("SELECT * FROM users WHERE email=?", (email.lower(),))
    row = await cur.fetchone()
    return dict(row) if row else None


async def get_user_by_id(user_id: int) -> Optional[dict]:
    db = await get_db()
    cur = await db.execute("SELECT * FROM users WHERE id=?", (user_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def update_user_password(user_id: int, password_hash: str):
    db = await get_db()
    await db.execute(
        "UPDATE users SET password_hash=?, updated_at=datetime('now') WHERE id=?",
        (password_hash, user_id),
    )
    await db.commit()


async def count_users() -> int:
    db = await get_db()
    cur = await db.execute("SELECT COUNT(*) FROM users")
    row = await cur.fetchone()
    return row[0]


async def list_users() -> list[dict]:
    db = await get_db()
    cur = await db.execute("SELECT id, email, display_name, role, created_at, updated_at FROM users ORDER BY id")
    return [dict(r) for r in await cur.fetchall()]


async def update_user_display_name(user_id: int, display_name: str):
    db = await get_db()
    await db.execute(
        "UPDATE users SET display_name=?, updated_at=datetime('now') WHERE id=?",
        (display_name, user_id),
    )
    await db.commit()


async def delete_user(user_id: int):
    db = await get_db()
    await db.execute("DELETE FROM user_settings WHERE user_id=?", (user_id,))
    await db.execute("DELETE FROM results WHERE user_id=?", (user_id,))
    await db.execute("DELETE FROM profiles WHERE user_id=?", (user_id,))
    await db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    await db.execute("DELETE FROM users WHERE id=?", (user_id,))
    await db.commit()


# ---- Profiles CRUD ----

async def get_profiles(user_id: int) -> list[dict]:
    db = await get_db()
    cur = await db.execute("SELECT * FROM profiles WHERE user_id=? ORDER BY name", (user_id,))
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_active_profile(user_id: int) -> Optional[dict]:
    db = await get_db()
    cur = await db.execute("SELECT * FROM profiles WHERE user_id=? AND is_active=1", (user_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def upsert_profile(user_id: int, name: str, base_url: str = "", api_key: str = "",
                          api_version: str = "2023-06-01", model: str = "", set_active: bool = True):
    db = await get_db()
    if set_active:
        await db.execute("UPDATE profiles SET is_active=0 WHERE user_id=?", (user_id,))
    await db.execute(
        """INSERT INTO profiles (user_id, name, base_url, api_key, api_version, model, is_active)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(user_id, name) DO UPDATE SET
             base_url=excluded.base_url, api_key=excluded.api_key,
             api_version=excluded.api_version, model=excluded.model,
             is_active=excluded.is_active, updated_at=datetime('now')""",
        (user_id, name, base_url, api_key, api_version, model, int(set_active)),
    )
    await db.commit()


async def switch_active_profile(user_id: int, name: str) -> bool:
    db = await get_db()
    cur = await db.execute("SELECT id FROM profiles WHERE user_id=? AND name=?", (user_id, name))
    if not await cur.fetchone():
        return False
    await db.execute("UPDATE profiles SET is_active=0 WHERE user_id=?", (user_id,))
    await db.execute("UPDATE profiles SET is_active=1 WHERE user_id=? AND name=?", (user_id, name))
    await db.commit()
    return True


async def delete_profile(user_id: int, name: str):
    db = await get_db()
    await db.execute("DELETE FROM profiles WHERE user_id=? AND name=?", (user_id, name))
    await db.commit()


# ---- Results CRUD ----

async def save_result(user_id: int, test_id: str, filename: str, timestamp: str,
                       config_json: str, summary_json: str, percentiles_json: str,
                       errors_json: str = "{}", error_details_json: str = "[]",
                       group_id: str = "", scheduled_task_id: int = 0):
    db = await get_db()
    await db.execute(
        """INSERT INTO results (user_id, test_id, filename, timestamp, config_json,
            summary_json, percentiles_json, errors_json, error_details_json, group_id,
            scheduled_task_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, test_id, filename, timestamp, config_json, summary_json,
         percentiles_json, errors_json, error_details_json, group_id, scheduled_task_id),
    )
    await db.commit()


def _row_to_result_dict(row) -> dict:
    d = dict(row)
    d["_filename"] = d["filename"]
    d["config"] = json.loads(d["config_json"])
    d["summary"] = json.loads(d["summary_json"])
    d["percentiles"] = json.loads(d["percentiles_json"])
    d["errors"] = json.loads(d["errors_json"])
    d["error_details"] = json.loads(d["error_details_json"])
    if not d.get("schedule_name"):
        d["schedule_name"] = ""
    return d


async def get_results(user_id: int) -> list[dict]:
    db = await get_db()
    cur = await db.execute(
        """SELECT r.*, st.name AS schedule_name
           FROM results r
           LEFT JOIN scheduled_tasks st ON r.scheduled_task_id = st.id
           WHERE r.user_id=?
           ORDER BY r.created_at DESC""",
        (user_id,),
    )
    rows = await cur.fetchall()
    return [_row_to_result_dict(row) for row in rows]


async def get_results_aggregated(user_id: int, limit: int = 50, offset: int = 0) -> dict:
    """返回聚合后的历史记录，同一定时任务的结果聚合成一条。

    返回 {"total": int, "items": [...]} 格式。
    手动执行的结果（scheduled_task_id=0）各自独立展示。
    定时任务的结果按 scheduled_task_id 聚合，展示最新一条，附带执行次数。
    分页在聚合后执行。
    """
    db = await get_db()
    # 1) 获取所有结果（仍需全量用于聚合，后续可优化为 SQL 聚合）
    cur = await db.execute(
        """SELECT r.*, st.name AS schedule_name
           FROM results r
           LEFT JOIN scheduled_tasks st ON r.scheduled_task_id = st.id
           WHERE r.user_id=?
           ORDER BY r.created_at DESC""",
        (user_id,),
    )
    rows = await cur.fetchall()

    # 2) 聚合
    manual_items = []
    scheduled_groups = {}  # scheduled_task_id -> [result_dicts]
    for row in rows:
        d = _row_to_result_dict(row)
        sid = d.get("scheduled_task_id") or 0
        if sid == 0:
            manual_items.append(d)
        else:
            scheduled_groups.setdefault(sid, []).append(d)

    # 3) 构建聚合列表：手动的保持原样，定时任务的合并
    merged = list(manual_items)  # 手动结果已经是单条
    for sid, group in scheduled_groups.items():
        # group 已按 created_at DESC 排序，第一条是最新的
        representative = dict(group[0])
        representative["children_count"] = len(group)
        representative["children"] = group  # 全部子记录，展开时展示
        merged.append(representative)

    # 4) 按最新时间排序
    merged.sort(key=lambda r: r.get("created_at") or r.get("timestamp") or "", reverse=True)

    total = len(merged)
    paged = merged[offset:offset + limit]

    return {"total": total, "items": paged}


async def get_result_by_filename(user_id: int, filename: str) -> Optional[dict]:
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM results WHERE user_id=? AND filename=?", (user_id, filename)
    )
    row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["_filename"] = d["filename"]
    d["config"] = json.loads(d["config_json"])
    d["summary"] = json.loads(d["summary_json"])
    d["percentiles"] = json.loads(d["percentiles_json"])
    d["errors"] = json.loads(d["errors_json"])
    d["error_details"] = json.loads(d["error_details_json"])
    return d


async def delete_result(user_id: int, filename: str):
    db = await get_db()
    await db.execute("DELETE FROM results WHERE user_id=? AND filename=?", (user_id, filename))
    await db.commit()


async def get_results_by_scheduled_task(user_id: int, scheduled_task_id: int) -> list[dict]:
    db = await get_db()
    cur = await db.execute(
        """SELECT r.*, st.name AS schedule_name
           FROM results r
           LEFT JOIN scheduled_tasks st ON r.scheduled_task_id = st.id
           WHERE r.user_id=? AND r.scheduled_task_id=?
           ORDER BY r.created_at DESC""",
        (user_id, scheduled_task_id),
    )
    rows = await cur.fetchall()
    results = []
    for row in rows:
        d = dict(row)
        d["_filename"] = d["filename"]
        d["config"] = json.loads(d["config_json"])
        d["summary"] = json.loads(d["summary_json"])
        d["percentiles"] = json.loads(d["percentiles_json"])
        d["errors"] = json.loads(d["errors_json"])
        d["error_details"] = json.loads(d["error_details_json"])
        if not d.get("schedule_name"):
            d["schedule_name"] = ""
        results.append(d)
    return results


# ---- User Settings CRUD ----

async def get_settings(user_id: int) -> dict:
    db = await get_db()
    cur = await db.execute("SELECT * FROM user_settings WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    if not row:
        return {}
    return json.loads(dict(row)["benchmark_json"])


async def save_settings(user_id: int, benchmark: dict, output_dir: str = "./results"):
    db = await get_db()
    await db.execute(
        """INSERT INTO user_settings (user_id, benchmark_json, output_dir)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             benchmark_json=excluded.benchmark_json,
             output_dir=excluded.output_dir,
             updated_at=datetime('now')""",
        (user_id, json.dumps(benchmark), output_dir),
    )
    await db.commit()


# ---- Scheduled Tasks CRUD ----

async def create_scheduled_task(user_id: int, name: str, profile_ids: list,
                                 configs_json: dict, schedule_type: str,
                                 schedule_value: str) -> int:
    db = await get_db()
    cur = await db.execute(
        """INSERT INTO scheduled_tasks (user_id, name, profile_ids, configs_json,
            schedule_type, schedule_value)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, name, json.dumps(profile_ids), json.dumps(configs_json),
         schedule_type, schedule_value),
    )
    await db.commit()
    return cur.lastrowid


async def get_scheduled_tasks(user_id: int) -> list[dict]:
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM scheduled_tasks WHERE user_id=? ORDER BY created_at DESC",
        (user_id,),
    )
    rows = await cur.fetchall()
    results = []
    for row in rows:
        d = dict(row)
        d["profile_ids"] = json.loads(d["profile_ids"])
        d["configs"] = json.loads(d["configs_json"])
        results.append(d)
    return results


async def get_scheduled_task(task_id: int) -> Optional[dict]:
    db = await get_db()
    cur = await db.execute("SELECT * FROM scheduled_tasks WHERE id=?", (task_id,))
    row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["profile_ids"] = json.loads(d["profile_ids"])
    d["configs"] = json.loads(d["configs_json"])
    return d


async def update_scheduled_task(task_id: int, **fields):
    db = await get_db()
    allowed = {"name", "profile_ids", "configs_json", "schedule_type",
               "schedule_value", "status", "last_run_at", "next_run_at", "run_count"}
    set_parts = []
    values = []
    for k, v in fields.items():
        if k in allowed:
            set_parts.append(f"{k}=?")
            if k == "profile_ids" and isinstance(v, list):
                v = json.dumps(v)
            elif k == "configs_json" and isinstance(v, dict):
                v = json.dumps(v)
            values.append(v)
    if not set_parts:
        return
    set_parts.append("updated_at=datetime('now')")
    values.append(task_id)
    await db.execute(
        f"UPDATE scheduled_tasks SET {', '.join(set_parts)} WHERE id=?",
        values,
    )
    await db.commit()


async def delete_scheduled_task(task_id: int):
    db = await get_db()
    await db.execute("DELETE FROM scheduled_tasks WHERE id=?", (task_id,))
    await db.commit()


async def get_all_active_scheduled_tasks() -> list[dict]:
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM scheduled_tasks WHERE status='active' ORDER BY id"
    )
    rows = await cur.fetchall()
    results = []
    for row in rows:
        d = dict(row)
        d["profile_ids"] = json.loads(d["profile_ids"])
        d["configs"] = json.loads(d["configs_json"])
        results.append(d)
    return results
