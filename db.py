#!/usr/bin/env python3
"""数据库层 — SQLite + aiosqlite"""

import json
from pathlib import Path
from typing import Optional

import aiosqlite

DB_PATH = Path(__file__).parent / "data.db"

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
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id        INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    benchmark_json TEXT NOT NULL DEFAULT '{}',
    output_dir     TEXT NOT NULL DEFAULT './results',
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_db: Optional[aiosqlite.Connection] = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
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
                       errors_json: str = "{}", error_details_json: str = "[]"):
    db = await get_db()
    await db.execute(
        """INSERT INTO results (user_id, test_id, filename, timestamp, config_json,
            summary_json, percentiles_json, errors_json, error_details_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, test_id, filename, timestamp, config_json, summary_json,
         percentiles_json, errors_json, error_details_json),
    )
    await db.commit()


async def get_results(user_id: int) -> list[dict]:
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM results WHERE user_id=? ORDER BY created_at DESC", (user_id,)
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
        results.append(d)
    return results


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
