#!/usr/bin/env python3
"""数据库层 — SQLite (aiosqlite) / PostgreSQL (asyncpg) 双模"""

import json
import os
from pathlib import Path
from typing import Optional

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncConnection

from app.config import DATABASE_URL

# 判断当前数据库类型
_is_sqlite = DATABASE_URL.startswith("sqlite")

# SQLite：需要确保 data 目录存在
if _is_sqlite:
    _db_path = DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    Path(_db_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(Path(_db_path).parent, 0o700)
    except OSError:
        pass

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    **({} if not _is_sqlite else {"connect_args": {"check_same_thread": False}}),
)

# SQLite 默认不启用外键约束，需要每个连接都设置
if _is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

# SQLite schema（保持原样）
_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL DEFAULT '',
    role          TEXT NOT NULL DEFAULT 'user',
    must_change_password INTEGER NOT NULL DEFAULT 0,
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
    provider    TEXT NOT NULL DEFAULT '',
    protocol    TEXT NOT NULL DEFAULT '',
    custom_endpoint INTEGER NOT NULL DEFAULT 0,
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
    run_id             TEXT NOT NULL DEFAULT '',
    task_id            TEXT NOT NULL DEFAULT '',
    source             TEXT NOT NULL DEFAULT 'manual',
    profile_name       TEXT NOT NULL DEFAULT '',
    base_url           TEXT NOT NULL DEFAULT '',
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
    locked_until    TEXT,
    run_count       INTEGER NOT NULL DEFAULT 0,
    alert_webhook   TEXT NOT NULL DEFAULT '',
    alert_threshold INTEGER NOT NULL DEFAULT 90,
    alert_enabled   INTEGER NOT NULL DEFAULT 0,
    alert_state     TEXT NOT NULL DEFAULT 'ok',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS channel_diagnostics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_name  TEXT NOT NULL DEFAULT '',
    model         TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'not_run',
    overall_risk  TEXT NOT NULL DEFAULT 'unknown',
    confidence    REAL NOT NULL DEFAULT 0.0,
    report_json   TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

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
"""

# PostgreSQL schema
_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL DEFAULT '',
    role          TEXT NOT NULL DEFAULT 'user',
    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS profiles (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    base_url    TEXT NOT NULL DEFAULT '',
    api_key     TEXT NOT NULL DEFAULT '',
    api_version TEXT NOT NULL DEFAULT '2023-06-01',
    model       TEXT NOT NULL DEFAULT '',
    provider    TEXT NOT NULL DEFAULT '',
    protocol    TEXT NOT NULL DEFAULT '',
    is_active   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS results (
    id                 SERIAL PRIMARY KEY,
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
    run_id             TEXT NOT NULL DEFAULT '',
    task_id            TEXT NOT NULL DEFAULT '',
    source             TEXT NOT NULL DEFAULT 'manual',
    profile_name       TEXT NOT NULL DEFAULT '',
    base_url           TEXT NOT NULL DEFAULT '',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id        INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    benchmark_json TEXT NOT NULL DEFAULT '{}',
    output_dir     TEXT NOT NULL DEFAULT './data/results',
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    profile_ids     TEXT NOT NULL DEFAULT '[]',
    configs_json    TEXT NOT NULL DEFAULT '{}',
    schedule_type   TEXT NOT NULL DEFAULT 'interval',
    schedule_value  TEXT NOT NULL DEFAULT '300',
    status          TEXT NOT NULL DEFAULT 'active',
    last_run_at     TIMESTAMPTZ,
    next_run_at     TIMESTAMPTZ,
    locked_until    TIMESTAMPTZ,
    run_count       INTEGER NOT NULL DEFAULT 0,
    alert_webhook   TEXT NOT NULL DEFAULT '',
    alert_threshold INTEGER NOT NULL DEFAULT 90,
    alert_enabled   BOOLEAN NOT NULL DEFAULT FALSE,
    alert_state     TEXT NOT NULL DEFAULT 'ok',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS channel_diagnostics (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_name  TEXT NOT NULL DEFAULT '',
    model         TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'not_run',
    overall_risk  TEXT NOT NULL DEFAULT 'unknown',
    confidence    REAL NOT NULL DEFAULT 0.0,
    report_json   TEXT NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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
"""

# PG 需要的辅助索引（email 大小写不敏感）
_PG_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_users_email_lower ON users (LOWER(email));
"""

# 用于 runtime UPDATE 的时间函数
def _now_sql() -> str:
    if _is_sqlite:
        return "datetime('now')"
    return "NOW()"


async def init_db():
    """初始化数据库，创建表结构"""
    schema = _SQLITE_SCHEMA if _is_sqlite else _PG_SCHEMA
    async with engine.begin() as conn:
        if _is_sqlite:
            for stmt in schema.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    await conn.execute(text(stmt))
        else:
            for stmt in schema.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    await conn.execute(text(stmt))
            # PG 额外索引
            for stmt in _PG_INDEXES.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    await conn.execute(text(stmt))
        # 定时任务调度索引
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_sched_status_next ON scheduled_tasks (status, next_run_at)"
        ))
        # results 表查询优化索引
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_results_user_time ON results (user_id, created_at DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_results_user_timestamp ON results (user_id, timestamp DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_results_user_sched_time ON results (user_id, scheduled_task_id, created_at DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_results_filename ON results (user_id, filename)"
        ))
        # 冗余列：对已有表 ALTER TABLE
        if _is_sqlite:
            for col_def in [
                "ALTER TABLE results ADD COLUMN profile_name TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE results ADD COLUMN base_url TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE results ADD COLUMN run_id TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE results ADD COLUMN task_id TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE results ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'",
            ]:
                try:
                    await conn.execute(text(col_def))
                except Exception:
                    pass  # 列已存在则忽略
        else:
            for col_def in [
                "ALTER TABLE results ADD COLUMN IF NOT EXISTS profile_name TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE results ADD COLUMN IF NOT EXISTS base_url TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE results ADD COLUMN IF NOT EXISTS run_id TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE results ADD COLUMN IF NOT EXISTS task_id TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE results ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual'",
            ]:
                await conn.execute(text(col_def))

        # scheduled_tasks 告警列：对已有表 ALTER TABLE
        if _is_sqlite:
            for col_def in [
                "ALTER TABLE scheduled_tasks ADD COLUMN alert_webhook TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE scheduled_tasks ADD COLUMN alert_threshold INTEGER NOT NULL DEFAULT 90",
                "ALTER TABLE scheduled_tasks ADD COLUMN alert_enabled INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE scheduled_tasks ADD COLUMN alert_state TEXT NOT NULL DEFAULT 'ok'",
                "ALTER TABLE scheduled_tasks ADD COLUMN alert_notifier_id INTEGER NOT NULL DEFAULT 0",
            ]:
                try:
                    await conn.execute(text(col_def))
                except Exception:
                    pass  # 列已存在则忽略
        else:
            for col_def in [
                "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS alert_webhook TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS alert_threshold INTEGER NOT NULL DEFAULT 90",
                "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS alert_enabled BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS alert_state TEXT NOT NULL DEFAULT 'ok'",
                "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS alert_notifier_id INTEGER NOT NULL DEFAULT 0",
            ]:
                await conn.execute(text(col_def))

        # 冗余列索引
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_results_user_profile_time ON results (user_id, profile_name, created_at DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_results_user_url_time ON results (user_id, base_url, created_at DESC)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_results_user_run_time ON results (user_id, run_id, created_at DESC)"
        ))

    # 修复定时任务结果缺失 profile_name 的历史数据
    await _migrate_schedule_results_profile_name()
    # 回填冗余列历史数据
    await _backfill_redundant_columns()


async def _migrate_schedule_results_profile_name():
    """补齐定时任务产生的结果中缺失的 profile_name（一次性迁移）"""
    async with engine.begin() as conn:
        if _is_sqlite:
            await conn.execute(text("""
                UPDATE results
                SET config_json = json_set(config_json, '$.profile_name',
                    (SELECT json_extract(st.profile_ids, '$[0]')
                     FROM scheduled_tasks st
                     WHERE st.id = results.scheduled_task_id))
                WHERE scheduled_task_id IS NOT NULL
                  AND (json_extract(config_json, '$.profile_name') IS NULL
                       OR json_extract(config_json, '$.profile_name') = '')
            """))
        else:
            # 先将 NULL 的 config_json 设为 '{}'，避免 jsonb_set 返回 NULL 违反约束
            await conn.execute(text("""
                UPDATE results SET config_json = '{}'
                WHERE scheduled_task_id IS NOT NULL
                  AND config_json IS NULL
            """))
            await conn.execute(text("""
                UPDATE results
                SET config_json = jsonb_set(config_json::jsonb, '{profile_name}',
                    to_jsonb((SELECT profile_ids::jsonb->>0
                              FROM scheduled_tasks st
                              WHERE st.id = results.scheduled_task_id)))::text
                WHERE scheduled_task_id IS NOT NULL
                  AND (config_json::jsonb->>'profile_name' IS NULL
                       OR config_json::jsonb->>'profile_name' = '')
            """))


async def _backfill_redundant_columns():
    """将 config_json 中的 profile_name/base_url 回填到冗余列（一次性迁移）"""
    async with engine.begin() as conn:
        if _is_sqlite:
            await conn.execute(text("""
                UPDATE results
                SET profile_name = COALESCE(json_extract(config_json, '$.profile_name'), ''),
                    base_url = COALESCE(json_extract(config_json, '$.base_url'), '')
                WHERE profile_name = '' OR base_url = ''
            """))
        else:
            await conn.execute(text("""
                UPDATE results
                SET profile_name = COALESCE(config_json::jsonb->>'profile_name', ''),
                    base_url = COALESCE(config_json::jsonb->>'base_url', '')
                WHERE profile_name = '' OR base_url = ''
            """))


async def close_db():
    """关闭数据库连接池"""
    await engine.dispose()


def _row_to_dict(row) -> dict:
    """将 SQLAlchemy Row 转为 dict"""
    if row is None:
        return None
    return dict(row._mapping)


def _rows_to_dicts(rows) -> list[dict]:
    return [dict(r._mapping) for r in rows]


# ---- Users CRUD ----

async def create_user(email: str, password_hash: str, display_name: str = "", role: str = "user", must_change_password: bool = False) -> int:
    mcp_val = 1 if _is_sqlite else must_change_password
    async with engine.begin() as conn:
        cur = await conn.execute(
            text("INSERT INTO users (email, password_hash, display_name, role, must_change_password) VALUES (:email, :password_hash, :display_name, :role, :mcp)"),
            {"email": email.lower(), "password_hash": password_hash, "display_name": display_name, "role": role, "mcp": mcp_val},
        )
        # SQLite 返回 lastrowid，PG 需要 RETURNING
        if _is_sqlite:
            return cur.lastrowid
        result = await conn.execute(text("SELECT lastval()"))
        return (result.fetchone())[0]


async def get_user_by_email(email: str) -> Optional[dict]:
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT * FROM users WHERE email=:email"), {"email": email.lower()}
        )
        row = cur.fetchone()
        return _row_to_dict(row)


async def get_user_by_id(user_id: int) -> Optional[dict]:
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT * FROM users WHERE id=:id"), {"id": user_id}
        )
        row = cur.fetchone()
        return _row_to_dict(row)


async def update_user_password(user_id: int, password_hash: str):
    mcp_val = 0 if _is_sqlite else False
    async with engine.begin() as conn:
        await conn.execute(
            text(f"UPDATE users SET password_hash=:pw, must_change_password=:mcp, updated_at={_now_sql()} WHERE id=:id"),
            {"pw": password_hash, "mcp": mcp_val, "id": user_id},
        )


async def count_users() -> int:
    async with engine.connect() as conn:
        cur = await conn.execute(text("SELECT COUNT(*) FROM users"))
        row = cur.fetchone()
        return row[0]


async def list_users() -> list[dict]:
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT id, email, display_name, role, created_at, updated_at FROM users ORDER BY id")
        )
        return _rows_to_dicts(cur.fetchall())


async def update_user_display_name(user_id: int, display_name: str):
    async with engine.begin() as conn:
        await conn.execute(
            text(f"UPDATE users SET display_name=:dn, updated_at={_now_sql()} WHERE id=:id"),
            {"dn": display_name, "id": user_id},
        )


async def update_user_role(user_id: int, role: str):
    async with engine.begin() as conn:
        await conn.execute(
            text(f"UPDATE users SET role=:role, updated_at={_now_sql()} WHERE id=:id"),
            {"role": role, "id": user_id},
        )


async def delete_user(user_id: int):
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM user_settings WHERE user_id=:id"), {"id": user_id})
        await conn.execute(text("DELETE FROM results WHERE user_id=:id"), {"id": user_id})
        await conn.execute(text("DELETE FROM profiles WHERE user_id=:id"), {"id": user_id})
        await conn.execute(text("DELETE FROM sessions WHERE user_id=:id"), {"id": user_id})
        await conn.execute(text("DELETE FROM users WHERE id=:id"), {"id": user_id})


# ---- Profiles CRUD ----

def _normalize_profile_models(p: dict):
    """将旧格式 model 字符串转为 models 列表，同时保留 model 字段向后兼容"""
    raw = p.get("model", "")
    if isinstance(raw, str) and raw.startswith("["):
        try:
            p["models"] = json.loads(raw)
        except json.JSONDecodeError:
            p["models"] = [raw] if raw else []
    elif raw:
        p["models"] = [raw]
    else:
        p["models"] = []
    # 保留 model 字段为第一个模型（向后兼容）
    p["model"] = p["models"][0] if p["models"] else ""
    # custom_endpoint: DB 存 0/1，API 返回 bool
    p["custom_endpoint"] = bool(p.get("custom_endpoint"))


async def get_profiles(user_id: int) -> list[dict]:
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT * FROM profiles WHERE user_id=:uid ORDER BY created_at DESC"), {"uid": user_id}
        )
        rows = _rows_to_dicts(cur.fetchall())
    for row in rows:
        _normalize_profile_models(row)
    return rows


async def get_active_profile(user_id: int) -> Optional[dict]:
    async with engine.connect() as conn:
        if _is_sqlite:
            cur = await conn.execute(
                text("SELECT * FROM profiles WHERE user_id=:uid AND is_active=1"), {"uid": user_id}
            )
        else:
            cur = await conn.execute(
                text("SELECT * FROM profiles WHERE user_id=:uid AND is_active=TRUE"), {"uid": user_id}
            )
        row = cur.fetchone()
        d = _row_to_dict(row)
    if d:
        _normalize_profile_models(d)
    return d


async def upsert_profile(user_id: int, name: str, base_url: str = "", api_key: str = "",
                          api_version: str = "2023-06-01", models: list = None,
                          model: str = "",  # 向后兼容
                          provider: str = "", protocol: str = "",
                          custom_endpoint: int = 0,
                          set_active: bool = True):
    # 向后兼容：如果传了 model 字符串，包装为列表
    if models is None and model:
        models = [model]
    elif models is None:
        models = []
    # 存储为 JSON 字符串
    model_json = json.dumps(models)
    async with engine.begin() as conn:
        if set_active:
            if _is_sqlite:
                await conn.execute(
                    text("UPDATE profiles SET is_active=0 WHERE user_id=:uid"), {"uid": user_id}
                )
            else:
                await conn.execute(
                    text("UPDATE profiles SET is_active=FALSE WHERE user_id=:uid"), {"uid": user_id}
                )

        active_val = 1 if _is_sqlite else True
        await conn.execute(
            text(f"""INSERT INTO profiles (user_id, name, base_url, api_key, api_version, model, provider, protocol, custom_endpoint, is_active)
                     VALUES (:uid, :name, :base_url, :api_key, :api_version, :model, :provider, :protocol, :custom_endpoint, :active)
                     ON CONFLICT(user_id, name) DO UPDATE SET
                       base_url=excluded.base_url, api_key=excluded.api_key,
                       api_version=excluded.api_version, model=excluded.model,
                       provider=excluded.provider, protocol=excluded.protocol,
                       custom_endpoint=excluded.custom_endpoint,
                       is_active=excluded.is_active, updated_at={_now_sql()}"""),
            {"uid": user_id, "name": name, "base_url": base_url, "api_key": api_key,
             "api_version": api_version, "model": model_json, "provider": provider,
             "protocol": protocol, "custom_endpoint": custom_endpoint, "active": active_val},
        )


async def switch_active_profile(user_id: int, name: str) -> bool:
    async with engine.begin() as conn:
        cur = await conn.execute(
            text("SELECT id FROM profiles WHERE user_id=:uid AND name=:name"),
            {"uid": user_id, "name": name},
        )
        if not cur.fetchone():
            return False
        if _is_sqlite:
            await conn.execute(text("UPDATE profiles SET is_active=0 WHERE user_id=:uid"), {"uid": user_id})
            await conn.execute(
                text("UPDATE profiles SET is_active=1 WHERE user_id=:uid AND name=:name"),
                {"uid": user_id, "name": name},
            )
        else:
            await conn.execute(text("UPDATE profiles SET is_active=FALSE WHERE user_id=:uid"), {"uid": user_id})
            await conn.execute(
                text("UPDATE profiles SET is_active=TRUE WHERE user_id=:uid AND name=:name"),
                {"uid": user_id, "name": name},
            )
        return True


async def delete_profile(user_id: int, name: str):
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM profiles WHERE user_id=:uid AND name=:name"),
            {"uid": user_id, "name": name},
        )


async def rename_profile(user_id: int, old_name: str, new_name: str) -> bool:
    """将用户的 profile 从 old_name 改为 new_name，并在一个事务中级联更新所有引用。

    返回 True 表示成功（包括 old==new 无需操作的情况）。
    抛出 ValueError:
      - new_name 为空
      - old_name 不存在
      - new_name 与该用户其它 profile 重名
    """
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValueError("新名称不能为空")

    # old == new：幂等，直接成功
    if old_name == new_name:
        return True

    async with engine.begin() as conn:
        # 校验 old_name 存在
        cur = await conn.execute(
            text("SELECT id FROM profiles WHERE user_id=:uid AND name=:name"),
            {"uid": user_id, "name": old_name},
        )
        if not cur.fetchone():
            raise ValueError(f"站点「{old_name}」不存在")

        # 校验 new_name 不与其它 profile 重名
        cur = await conn.execute(
            text("SELECT id FROM profiles WHERE user_id=:uid AND name=:name"),
            {"uid": user_id, "name": new_name},
        )
        if cur.fetchone():
            raise ValueError(f"名称「{new_name}」已存在，请换一个名称")

        # 1. profiles.name
        await conn.execute(
            text("UPDATE profiles SET name=:new WHERE user_id=:uid AND name=:old"),
            {"uid": user_id, "new": new_name, "old": old_name},
        )

        # 2. results.profile_name（独立列）
        await conn.execute(
            text("UPDATE results SET profile_name=:new WHERE user_id=:uid AND profile_name=:old"),
            {"uid": user_id, "new": new_name, "old": old_name},
        )

        # 3. results.config_json 内嵌的 profile_name（双方言）
        if _is_sqlite:
            await conn.execute(
                text("""
                    UPDATE results
                    SET config_json = json_set(config_json, '$.profile_name', :new)
                    WHERE user_id=:uid
                      AND json_extract(config_json, '$.profile_name') = :old
                """),
                {"uid": user_id, "new": new_name, "old": old_name},
            )
        else:
            await conn.execute(
                text("""
                    UPDATE results
                    SET config_json = jsonb_set(config_json::jsonb, '{profile_name}', to_jsonb(:new))::text
                    WHERE user_id=:uid
                      AND config_json::jsonb->>'profile_name' = :old
                """),
                {"uid": user_id, "new": new_name, "old": old_name},
            )

        # 4. scheduled_tasks.profile_ids（JSON 字符串数组，Python 解析后替换再写回）
        cur = await conn.execute(
            text("SELECT id, profile_ids FROM scheduled_tasks WHERE user_id=:uid"),
            {"uid": user_id},
        )
        tasks = cur.fetchall()
        for task_row in tasks:
            task_id, pids_raw = task_row[0], task_row[1]
            try:
                pids = json.loads(pids_raw) if pids_raw else []
            except (json.JSONDecodeError, TypeError):
                pids = []
            if old_name in pids:
                new_pids = [new_name if p == old_name else p for p in pids]
                await conn.execute(
                    text("UPDATE scheduled_tasks SET profile_ids=:pids WHERE id=:tid"),
                    {"pids": json.dumps(new_pids), "tid": task_id},
                )

        # 5. channel_diagnostics.profile_name
        await conn.execute(
            text("UPDATE channel_diagnostics SET profile_name=:new WHERE user_id=:uid AND profile_name=:old"),
            {"uid": user_id, "new": new_name, "old": old_name},
        )

        # 6. active profile：存在 profiles.is_active 列，随 profiles.name 一起在步骤 1 已经更新。
        # （is_active 列没有关联 old_name 文本，步骤 1 UPDATE 已经把整行的 name 改过来了，无需额外操作。）

    return True


# ---- Notifiers CRUD ----

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
        return _rows_to_dicts(cur.fetchall())


async def get_notifier(notifier_id: int) -> Optional[dict]:
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT * FROM notifiers WHERE id=:id"), {"id": notifier_id}
        )
        row = cur.fetchone()
        return _row_to_dict(row) if row else None


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


# ---- Results CRUD ----

async def save_result(user_id: int, test_id: str, filename: str, timestamp: str,
                       config_json: str, summary_json: str, percentiles_json: str,
                       errors_json: str = "{}", error_details_json: str = "[]",
                       group_id: str = "", scheduled_task_id: int = 0,
                       run_id: str = "", task_id: str = "", source: str = "manual"):
    # 从 config_json 提取冗余字段
    try:
        _cfg = json.loads(config_json)
    except (json.JSONDecodeError, TypeError):
        _cfg = {}
    _profile_name = _cfg.get("profile_name", "")
    _base_url = _cfg.get("base_url", "")

    async with engine.begin() as conn:
        await conn.execute(
            text("""INSERT INTO results (user_id, test_id, filename, timestamp, config_json,
                    summary_json, percentiles_json, errors_json, error_details_json, group_id,
                    scheduled_task_id, run_id, task_id, source, profile_name, base_url)
                   VALUES (:uid, :test_id, :filename, :timestamp, :config_json,
                    :summary_json, :percentiles_json, :errors_json, :error_details_json, :group_id,
                    :scheduled_task_id, :run_id, :task_id, :source, :profile_name, :base_url)"""),
            {"uid": user_id, "test_id": test_id, "filename": filename, "timestamp": timestamp,
             "config_json": config_json, "summary_json": summary_json,
             "percentiles_json": percentiles_json, "errors_json": errors_json,
             "error_details_json": error_details_json, "group_id": group_id,
             "scheduled_task_id": scheduled_task_id,
             "run_id": run_id or group_id, "task_id": task_id, "source": source or "manual",
             "profile_name": _profile_name, "base_url": _base_url},
        )


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


def _row_to_result_dict(row, lightweight: bool = False) -> dict:
    d = dict(row._mapping)
    d["config"] = json.loads(d["config_json"])
    d["summary"] = json.loads(d["summary_json"])
    if lightweight:
        # 轻量模式：不解析大字段，直接移除原始 JSON 列
        for key in ("percentiles_json", "errors_json", "error_details_json",
                     "config_json", "summary_json"):
            d.pop(key, None)
    else:
        d["percentiles"] = json.loads(d["percentiles_json"])
        d["errors"] = json.loads(d["errors_json"])
        d["error_details"] = json.loads(d["error_details_json"])
    if not d.get("schedule_name"):
        d["schedule_name"] = ""
    return d


async def get_results(user_id: int, hours: int | None = None) -> list[dict]:
    """返回用户所有测试结果。hours 可选，仅返回最近 N 小时内的数据。"""
    params: dict = {"uid": user_id}
    time_filter = ""
    if hours is not None:
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y%m%d_%H%M%S")
        time_filter = "AND r.timestamp >= :cutoff"
        params["cutoff"] = cutoff

    async with engine.connect() as conn:
        cur = await conn.execute(
            text(f"""SELECT r.*, st.name AS schedule_name
                   FROM results r
                   LEFT JOIN scheduled_tasks st ON r.scheduled_task_id = st.id
                   WHERE r.user_id=:uid {time_filter}
                   ORDER BY r.created_at DESC"""),
            params,
        )
        rows = cur.fetchall()
        return [_row_to_result_dict(row) for row in rows]


async def get_results_aggregated(user_id: int, limit: int = 50, offset: int = 0, hours: int | None = None, lightweight: bool = False, raw: bool = False, base_url: str | None = None, profile_name: str | None = None) -> dict:
    """返回历史记录。优先按 profile_name 精确过滤，回退到 base_url。"""
    params: dict = {"uid": user_id}
    time_filter = ""
    if hours is not None:
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y%m%d_%H%M%S")
        time_filter = "AND r.timestamp >= :cutoff"
        params["cutoff"] = cutoff

    site_filter = ""
    if profile_name:
        site_filter = "AND r.profile_name=:profile_name"
        params["profile_name"] = profile_name
    elif base_url:
        base_clean = base_url.rstrip("/")
        base_with_slash = base_clean + "/"
        site_filter = ("AND (r.base_url=:base_url"
                       " OR r.base_url=:base_url_slash)")
        params["base_url"] = base_clean
        params["base_url_slash"] = base_with_slash

    where = f"WHERE r.user_id=:uid {time_filter} {site_filter}"

    # raw 模式：分页下推到 SQL（COUNT + LIMIT/OFFSET），不再全表加载进内存
    if raw:
        async with engine.connect() as conn:
            cnt = await conn.execute(
                text(f"SELECT COUNT(*) FROM results r {where}"), params
            )
            total = cnt.scalar() or 0
            page_params = dict(params, _limit=limit, _offset=offset)
            cur = await conn.execute(
                text(f"""SELECT r.*, st.name AS schedule_name
                       FROM results r
                       LEFT JOIN scheduled_tasks st ON r.scheduled_task_id = st.id
                       {where}
                       ORDER BY r.timestamp DESC, r.id DESC
                       LIMIT :_limit OFFSET :_offset"""),
                page_params,
            )
            rows = cur.fetchall()
        items = [_row_to_result_dict(row, lightweight=lightweight) for row in rows]
        return {"total": total, "items": items}

    # 聚合模式：按设计需对每个定时任务的历史求平均，仍需多行；
    # 用 LIMIT 上限只加载最近 N 行，防止表膨胀后无界加载进内存。
    # 动态读取配置便于测试 monkeypatch。
    import app.config as _cfg
    cap = _cfg.RESULTS_QUERY_MAX_ROWS
    async with engine.connect() as conn:
        cur = await conn.execute(
            text(f"""SELECT r.*, st.name AS schedule_name
                   FROM results r
                   LEFT JOIN scheduled_tasks st ON r.scheduled_task_id = st.id
                   {where}
                   ORDER BY r.created_at DESC, r.id DESC
                   LIMIT :_cap"""),
            dict(params, _cap=cap + 1),  # 多取 1 行用于判定是否被截断
        )
        rows = cur.fetchall()
    truncated = len(rows) > cap
    if truncated:
        rows = rows[:cap]

    # 聚合
    manual_items = []
    scheduled_groups = {}
    for row in rows:
        d = _row_to_result_dict(row, lightweight=lightweight)
        sid = d.get("scheduled_task_id") or 0
        if sid == 0:
            manual_items.append(d)
        else:
            scheduled_groups.setdefault(sid, []).append(d)

    merged = list(manual_items)
    for sid, group in scheduled_groups.items():
        count = len(group)
        avg_summary = {}
        avg_percentiles = {}
        if count > 0:
            def _avg(key_chain):
                vals = []
                for g in group:
                    obj = g
                    for k in key_chain:
                        obj = obj.get(k) if isinstance(obj, dict) else None
                        if obj is None:
                            break
                    if obj is not None:
                        vals.append(float(obj))
                return sum(vals) / len(vals) if vals else None

            avg_summary = dict(group[0].get("summary", {}))
            for key in ["success_rate", "throughput_rps", "token_throughput_tps",
                        "avg_output_tokens"]:
                v = _avg(["summary", key])
                if v is not None:
                    avg_summary[key] = v

            # 总 token 数 + 费用求和
            for key in ["total_input_tokens", "total_output_tokens", "cost_total_usd"]:
                vals = []
                for g in group:
                    v = g.get("summary", {}).get(key)
                    if v is not None:
                        vals.append(float(v))
                if vals:
                    if key == "cost_total_usd":
                        avg_summary[key] = round(sum(vals), 8)
                    else:
                        avg_summary[key] = int(sum(vals))

            for sub_key in ["input_tokens", "output_tokens"]:
                sub_obj = {}
                for stat in ["Min", "P50", "P95", "P99", "Max", "Avg"]:
                    v = _avg(["summary", sub_key, stat])
                    if v is not None:
                        sub_obj[stat] = v
                if sub_obj:
                    avg_summary[sub_key] = sub_obj

            avg_percentiles = dict(group[0].get("percentiles", {}))
            for metric in ["TTFT", "TPOT", "E2E"]:
                metric_obj = {}
                for stat in ["Min", "P50", "P95", "P99", "Max", "Avg"]:
                    v = _avg(["percentiles", metric, stat])
                    if v is not None:
                        metric_obj[stat] = round(v, 6)
                if metric_obj:
                    avg_percentiles[metric] = metric_obj

        representative = dict(group[0])
        representative["summary"] = avg_summary
        if not lightweight:
            representative["percentiles"] = avg_percentiles
            representative["children"] = group
        representative["children_count"] = count
        merged.append(representative)

    merged.sort(key=lambda r: r.get("created_at") or r.get("timestamp") or "", reverse=True)

    total = len(merged)
    paged = merged[offset:offset + limit]

    return {"total": total, "items": paged, "truncated": truncated}


async def get_result_by_filename(user_id: int, filename: str) -> Optional[dict]:
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT * FROM results WHERE user_id=:uid AND filename=:fn"),
            {"uid": user_id, "fn": filename},
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row._mapping)
        d["config"] = json.loads(d["config_json"])
        d["summary"] = json.loads(d["summary_json"])
        d["percentiles"] = json.loads(d["percentiles_json"])
        d["errors"] = json.loads(d["errors_json"])
        d["error_details"] = json.loads(d["error_details_json"])
        return d


async def delete_result(user_id: int, filename: str):
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM results WHERE user_id=:uid AND filename=:fn"),
            {"uid": user_id, "fn": filename},
        )


async def delete_results_older_than(days: int) -> int:
    """删除 created_at 早于 N 天前的 results，返回删除行数。days<=0 表示关闭，不删除。"""
    if days <= 0:
        return 0
    async with engine.begin() as conn:
        if _is_sqlite:
            res = await conn.execute(
                text("DELETE FROM results WHERE created_at < datetime('now', :cutoff)"),
                {"cutoff": f"-{days} days"},
            )
        else:
            res = await conn.execute(
                text("DELETE FROM results WHERE created_at < NOW() - make_interval(days => :days)"),
                {"days": days},
            )
        return res.rowcount or 0


async def get_results_by_scheduled_task(user_id: int, scheduled_task_id: int, limit: int = 100, offset: int = 0, hours: int | None = None) -> dict:
    """返回定时任务的结果列表（分页）和总数。hours 可选，仅返回最近 N 小时的数据。"""
    params: dict = {"uid": user_id, "sid": scheduled_task_id, "limit": limit, "offset": offset}
    time_filter = ""
    if hours is not None:
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y%m%d_%H%M%S")
        time_filter = "AND r.timestamp >= :cutoff"
        params["cutoff"] = cutoff

    async with engine.connect() as conn:
        count_cur = await conn.execute(
            text(f"SELECT COUNT(*) FROM results r WHERE r.user_id=:uid AND r.scheduled_task_id=:sid {time_filter}"),
            params,
        )
        total = count_cur.scalar()

        cur = await conn.execute(
            text(f"""SELECT r.*, st.name AS schedule_name
                   FROM results r
                   LEFT JOIN scheduled_tasks st ON r.scheduled_task_id = st.id
                   WHERE r.user_id=:uid AND r.scheduled_task_id=:sid {time_filter}
                   ORDER BY r.created_at DESC
                   LIMIT :limit OFFSET :offset"""),
            params,
        )
        rows = cur.fetchall()
        results = []
        for row in rows:
            d = dict(row._mapping)
            d["config"] = json.loads(d["config_json"])
            d["summary"] = json.loads(d["summary_json"])
            d["percentiles"] = json.loads(d["percentiles_json"])
            d["errors"] = json.loads(d["errors_json"])
            d["error_details"] = json.loads(d["error_details_json"])
            if not d.get("schedule_name"):
                d["schedule_name"] = ""
            results.append(d)
        return {"results": results, "total": total}


async def get_schedule_results_trend(user_id: int, scheduled_task_id: int, hours: int | None = None) -> list[dict]:
    """按分钟聚合定时任务结果，用于趋势图展示（最多返回最近2000个点）。
    只查询需要的字段，在 Python 层聚合，兼容 SQLite 和 PostgreSQL。
    hours: 可选，仅返回最近 N 小时的数据。
    """
    params: dict = {"uid": user_id, "sid": scheduled_task_id}
    where_extra = ""
    if hours is not None:
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y%m%d_%H%M%S")
        where_extra = "AND timestamp >= :cutoff"
        params["cutoff"] = cutoff

    async with engine.connect() as conn:
        cur = await conn.execute(
            text(f"""SELECT timestamp, summary_json, percentiles_json
                   FROM results
                   WHERE user_id=:uid AND scheduled_task_id=:sid {where_extra}
                   ORDER BY timestamp DESC
                   LIMIT 20000"""),
            params,
        )
        rows = cur.fetchall()

    buckets = {}
    for row in rows:
        minute = row.timestamp[:13]  # e.g. "20260408_1820" (YYYYMMDD_HHMM)
        if minute not in buckets:
            buckets[minute] = {"minute": minute, "count": 0, "success_rates": [],
                               "throughputs": [], "tpses": [],
                               "ttft_p50s": [], "tpot_p50s": [], "e2e_p50s": []}
        b = buckets[minute]
        b["count"] += 1
        try:
            s = json.loads(row.summary_json)
            if s.get("success_rate") is not None:
                b["success_rates"].append(float(s["success_rate"]))
            if s.get("throughput_rps") is not None:
                b["throughputs"].append(float(s["throughput_rps"]))
            if s.get("token_throughput_tps") is not None:
                b["tpses"].append(float(s["token_throughput_tps"]))
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            p = json.loads(row.percentiles_json)
            ttft = p.get("TTFT", {})
            if ttft.get("P50") is not None:
                b["ttft_p50s"].append(float(ttft["P50"]))
            tpot = p.get("TPOT", {})
            if tpot.get("P50") is not None:
                b["tpot_p50s"].append(float(tpot["P50"]))
            e2e = p.get("E2E", {})
            if e2e.get("P50") is not None:
                b["e2e_p50s"].append(float(e2e["P50"]))
        except (json.JSONDecodeError, TypeError):
            pass

    result = []
    for minute in sorted(buckets.keys()):
        b = buckets[minute]
        result.append({
            "minute": minute,
            "run_count": b["count"],
            "avg_success_rate": round(sum(b["success_rates"]) / len(b["success_rates"]), 4) if b["success_rates"] else None,
            "avg_throughput": round(sum(b["throughputs"]) / len(b["throughputs"]), 2) if b["throughputs"] else None,
            "avg_tps": round(sum(b["tpses"]) / len(b["tpses"]), 2) if b["tpses"] else None,
            "avg_ttft_p50": round(sum(b["ttft_p50s"]) / len(b["ttft_p50s"]), 6) if b["ttft_p50s"] else None,
            "avg_tpot_p50": round(sum(b["tpot_p50s"]) / len(b["tpot_p50s"]), 6) if b["tpot_p50s"] else None,
            "avg_e2e_p50": round(sum(b["e2e_p50s"]) / len(b["e2e_p50s"]), 6) if b["e2e_p50s"] else None,
        })
    return result[-2000:]  # 最多2000个点


async def get_site_trend(user_id: int, base_url: str, hours: int | None = None, profile_name: str | None = None, model: str | None = None) -> list[dict]:
    """按站点聚合结果趋势。优先按 profile_name 精确过滤，回退到 base_url。
    指定 model 时只统计该模型的结果。"""
    params: dict = {"uid": user_id}
    time_filter = ""
    if hours is not None:
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y%m%d_%H%M%S")
        time_filter = "AND timestamp >= :cutoff"
        params["cutoff"] = cutoff

    if profile_name:
        site_filter = "AND profile_name=:profile_name"
        params["profile_name"] = profile_name
    else:
        base_clean = base_url.rstrip("/")
        base_with_slash = base_clean + "/"
        site_filter = ("AND (base_url=:base_url"
                       " OR base_url=:base_with_slash)")
        params["base_url"] = base_clean
        params["base_with_slash"] = base_with_slash

    async with engine.connect() as conn:
        cur = await conn.execute(
            text(f"""SELECT timestamp, summary_json, percentiles_json, config_json
                   FROM results
                   WHERE user_id=:uid
                     {site_filter}
                     {time_filter}
                   ORDER BY timestamp DESC
                   LIMIT 20000"""),
            params,
        )
        rows = cur.fetchall()

    buckets = {}
    for row in rows:
        if model:
            try:
                cfg = json.loads(row[3]) if row[3] else {}
            except (json.JSONDecodeError, TypeError):
                cfg = {}
            if cfg.get("model") != model:
                continue
        minute = row[0][:13]  # timestamp
        if minute not in buckets:
            buckets[minute] = {"minute": minute, "count": 0, "success_rates": [],
                               "tpses": [], "ttft_p50s": [], "tpot_p50s": []}
        b = buckets[minute]
        b["count"] += 1
        try:
            s = json.loads(row[1])  # summary_json
            if s.get("success_rate") is not None:
                b["success_rates"].append(float(s["success_rate"]))
            if s.get("token_throughput_tps") is not None:
                b["tpses"].append(float(s["token_throughput_tps"]))
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            p = json.loads(row[2])  # percentiles_json
            ttft = p.get("TTFT", {})
            if ttft.get("P50") is not None:
                b["ttft_p50s"].append(float(ttft["P50"]))
            tpot = p.get("TPOT", {})
            if tpot.get("P50") is not None:
                b["tpot_p50s"].append(float(tpot["P50"]))
        except (json.JSONDecodeError, TypeError):
            pass

    result = []
    for minute in sorted(buckets.keys()):
        b = buckets[minute]
        result.append({
            "minute": minute,
            "run_count": b["count"],
            "avg_success_rate": round(sum(b["success_rates"]) / len(b["success_rates"]), 4) if b["success_rates"] else None,
            "avg_tps": round(sum(b["tpses"]) / len(b["tpses"]), 2) if b["tpses"] else None,
            "avg_ttft_p50": round(sum(b["ttft_p50s"]) / len(b["ttft_p50s"]), 6) if b["ttft_p50s"] else None,
            "avg_tpot_p50": round(sum(b["tpot_p50s"]) / len(b["tpot_p50s"]), 6) if b["tpot_p50s"] else None,
        })
    return result[-2000:]


# ---- User Settings CRUD ----

async def get_settings(user_id: int) -> dict:
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT * FROM user_settings WHERE user_id=:uid"), {"uid": user_id}
        )
        row = cur.fetchone()
        if not row:
            return {}
        return json.loads(dict(row._mapping)["benchmark_json"])


async def save_settings(user_id: int, benchmark: dict, output_dir: str = "./results"):
    async with engine.begin() as conn:
        await conn.execute(
            text(f"""INSERT INTO user_settings (user_id, benchmark_json, output_dir)
                     VALUES (:uid, :bj, :od)
                     ON CONFLICT(user_id) DO UPDATE SET
                       benchmark_json=excluded.benchmark_json,
                       output_dir=excluded.output_dir,
                       updated_at={_now_sql()}"""),
            {"uid": user_id, "bj": json.dumps(benchmark), "od": output_dir},
        )


# ---- Scheduled Tasks CRUD ----

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


async def get_latest_result_ids_by_user(user_id: int) -> dict[int, str | None]:
    """批量返回该用户所有定时任务的最新一条结果的 test_id 或 filename。
    用一条 SQL + GROUP BY 替代 N 条单独查询。
    """
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("""SELECT r.scheduled_task_id, r.test_id, r.filename
                    FROM results r
                    INNER JOIN (
                        SELECT scheduled_task_id, MAX(created_at) AS max_at
                        FROM results
                        WHERE user_id = :uid AND scheduled_task_id IS NOT NULL
                        GROUP BY scheduled_task_id
                    ) latest ON r.scheduled_task_id = latest.scheduled_task_id
                             AND r.created_at = latest.max_at
                    WHERE r.user_id = :uid"""),
            {"uid": user_id},
        )
        rows = cur.fetchall()
    return {row[0]: (row[1] or row[2]) for row in rows}


async def get_scheduled_tasks(user_id: int) -> list[dict]:
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT * FROM scheduled_tasks WHERE user_id=:uid ORDER BY created_at DESC"),
            {"uid": user_id},
        )
        rows = cur.fetchall()
        results = []
        for row in rows:
            d = dict(row._mapping)
            d["profile_ids"] = json.loads(d["profile_ids"])
            d["configs"] = json.loads(d["configs_json"])
            results.append(d)
        return results


async def get_scheduled_task(task_id: int) -> Optional[dict]:
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT * FROM scheduled_tasks WHERE id=:id"), {"id": task_id}
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row._mapping)
        d["profile_ids"] = json.loads(d["profile_ids"])
        d["configs"] = json.loads(d["configs_json"])
        return d


async def update_scheduled_task(task_id: int, **fields):
    async with engine.begin() as conn:
        allowed = {"name", "profile_ids", "configs_json", "schedule_type",
                   "schedule_value", "status", "last_run_at", "next_run_at", "run_count",
                   "alert_threshold", "alert_enabled", "alert_state",
                   "alert_notifier_id"}
        set_parts = []
        values = {"id": task_id}
        for k, v in fields.items():
            if k in allowed:
                set_parts.append(f"{k}=:{k}")
                if k == "profile_ids" and isinstance(v, list):
                    v = json.dumps(v)
                elif k == "configs_json" and isinstance(v, dict):
                    v = json.dumps(v)
                elif k == "alert_enabled" and _is_sqlite:
                    v = 1 if v else 0  # SQLite 布尔归一，与 create_scheduled_task 一致
                values[k] = v
        if not set_parts:
            return
        set_parts.append(f"updated_at={_now_sql()}")
        await conn.execute(
            text(f"UPDATE scheduled_tasks SET {', '.join(set_parts)} WHERE id=:id"),
            values,
        )


async def delete_scheduled_task(task_id: int):
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM scheduled_tasks WHERE id=:id"), {"id": task_id}
        )


async def get_all_active_scheduled_tasks() -> list[dict]:
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT * FROM scheduled_tasks WHERE status='active' ORDER BY id")
        )
        rows = cur.fetchall()
        results = []
        for row in rows:
            d = dict(row._mapping)
            d["profile_ids"] = json.loads(d["profile_ids"])
            d["configs"] = json.loads(d["configs_json"])
            results.append(d)
        return results


async def get_due_scheduled_tasks(now, limit: int = 50) -> list[dict]:
    """只查询已到期的活跃定时任务，避免全表扫描"""
    async with engine.connect() as conn:
        if _is_sqlite:
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")
            cur = await conn.execute(
                text("""SELECT * FROM scheduled_tasks
                        WHERE status='active'
                          AND next_run_at IS NOT NULL
                          AND next_run_at <= :now
                        ORDER BY id
                        LIMIT :limit"""),
                {"now": now_str, "limit": limit},
            )
        else:
            cur = await conn.execute(
                text("""SELECT * FROM scheduled_tasks
                        WHERE status='active'
                          AND next_run_at IS NOT NULL
                          AND next_run_at <= :now
                        ORDER BY id
                        LIMIT :limit"""),
                {"now": now, "limit": limit},
            )
        rows = cur.fetchall()
        results = []
        for row in rows:
            d = dict(row._mapping)
            d["profile_ids"] = json.loads(d["profile_ids"])
            d["configs"] = json.loads(d["configs_json"])
            results.append(d)
        return results


async def claim_scheduled_task(task_id: int, lock_seconds: int = 3600,
                               max_global: int | None = None,
                               max_per_user: int | None = None) -> bool:
    """原子抢占定时任务锁。返回 True 表示成功获取锁。

    条件：任务未被锁定 或 锁已过期。
    多 worker/多实例同时调用时，只有一个能成功（DB 保证原子性）。
    可选：通过 max_global / max_per_user 在 DB 级做并发限制（跨实例安全）。
    """
    async with engine.begin() as conn:
        if _is_sqlite:
            sql = """UPDATE scheduled_tasks
                     SET locked_until = datetime('now', :lock_sec || ' seconds')
                     WHERE id = :tid
                       AND (locked_until IS NULL OR locked_until < datetime('now'))"""
            params: dict = {"tid": task_id, "lock_sec": str(lock_seconds)}
            if max_global is not None:
                sql = sql.replace(
                    "WHERE id = :tid",
                    """WHERE id = :tid
                       AND (SELECT COUNT(*) FROM scheduled_tasks
                            WHERE locked_until IS NOT NULL AND locked_until >= datetime('now')) < :max_global""",
                )
                params["max_global"] = max_global
            if max_per_user is not None:
                sql += """ AND (SELECT COUNT(*) FROM scheduled_tasks
                              WHERE locked_until IS NOT NULL AND locked_until >= datetime('now')
                                AND user_id = (SELECT user_id FROM scheduled_tasks WHERE id = :tid)) < :max_per_user"""
                params["max_per_user"] = max_per_user
            result = await conn.execute(text(sql), params)
        else:
            sql = """UPDATE scheduled_tasks
                     SET locked_until = NOW() + (:lock_sec || ' seconds')::interval
                     WHERE id = :tid
                       AND (locked_until IS NULL OR locked_until < NOW())"""
            params = {"tid": task_id, "lock_sec": str(lock_seconds)}
            if max_global is not None:
                sql = sql.replace(
                    "WHERE id = :tid",
                    """WHERE id = :tid
                       AND (SELECT COUNT(*) FROM scheduled_tasks
                            WHERE locked_until IS NOT NULL AND locked_until >= NOW()) < :max_global""",
                )
                params["max_global"] = max_global
            if max_per_user is not None:
                sql += """ AND (SELECT COUNT(*) FROM scheduled_tasks
                              WHERE locked_until IS NOT NULL AND locked_until >= NOW()
                                AND user_id = (SELECT user_id FROM scheduled_tasks WHERE id = :tid)) < :max_per_user"""
                params["max_per_user"] = max_per_user
            result = await conn.execute(text(sql), params)
        return result.rowcount > 0


async def release_scheduled_task(task_id: int):
    """释放定时任务锁"""
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE scheduled_tasks SET locked_until=NULL WHERE id=:tid"),
            {"tid": task_id},
        )


async def reschedule_scheduled_task(task_id: int, next_run_at, last_run_at, run_count: int):
    """原子更新调度时间，仅在任务仍为 active 时生效（防止竞态）"""
    async with engine.begin() as conn:
        if _is_sqlite:
            next_str = next_run_at.strftime("%Y-%m-%d %H:%M:%S")
            last_str = last_run_at.strftime("%Y-%m-%d %H:%M:%S")
        else:
            next_str = next_run_at
            last_str = last_run_at
        await conn.execute(
            text("""UPDATE scheduled_tasks
                    SET next_run_at=:next, last_run_at=:last, run_count=:rc,
                        updated_at={now}
                    WHERE id=:tid AND status='active'""".format(now=_now_sql())),
            {"tid": task_id, "next": next_str, "last": last_str, "rc": run_count},
        )


async def release_and_reschedule_scheduled_task(task_id: int, next_run_at, last_run_at, run_count: int):
    """原子释放锁并更新调度时间 — 合并 release + reschedule 防止竞态窗口"""
    async with engine.begin() as conn:
        if _is_sqlite:
            next_str = next_run_at.strftime("%Y-%m-%d %H:%M:%S")
            last_str = last_run_at.strftime("%Y-%m-%d %H:%M:%S")
        else:
            next_str = next_run_at
            last_str = last_run_at
        await conn.execute(
            text("""UPDATE scheduled_tasks
                    SET locked_until=NULL, next_run_at=:next, last_run_at=:last,
                        run_count=:rc, updated_at={now}
                    WHERE id=:tid AND status='active'""".format(now=_now_sql())),
            {"tid": task_id, "next": next_str, "last": last_str, "rc": run_count},
        )


async def count_user_scheduled_tasks(user_id: int) -> int:
    """统计用户拥有的定时任务数量"""
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT COUNT(*) FROM scheduled_tasks WHERE user_id=:uid"),
            {"uid": user_id},
        )
        return cur.fetchone()[0]


# ---- Sites Summary ----

async def get_sites_summary(user_id: int, hours: int | None = None) -> list[dict]:
    """获取用户所有站点的最新测试摘要。使用 SQL 查询避免全量加载。"""
    profiles = await get_profiles(user_id)
    if not profiles:
        return []

    params: dict = {"uid": user_id}
    time_filter = ""
    if hours is not None:
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y%m%d_%H%M%S")
        time_filter = "AND r.timestamp >= :cutoff"
        params["cutoff"] = cutoff

    summary = {}
    for p in profiles:
        key = p["name"]
        summary[key] = {
            "profile": p,
            "latest_results": [],
            "health": "unknown",
            "last_test_at": None,
            "sparkline_data": {},
        }

    # 构建 scheduled_task_id → profile name 查找表
    scheduled_tasks = await get_scheduled_tasks(user_id)
    task_to_profile = {}
    for st in scheduled_tasks:
        pids = st.get("profile_ids") or []
        if pids:
            task_to_profile[st["id"]] = pids[0]

    # 收集所有 profile_name 列表用于 SQL IN 子句
    profile_names = [p["name"] for p in profiles]
    if not profile_names:
        return list(summary.values())

    # SQL：获取每个 profile 的最近结果（用于健康计算 + sparkline）
    placeholders = ", ".join([f":pn_{i}" for i in range(len(profile_names))])
    pn_params = {f"pn_{i}": name for i, name in enumerate(profile_names)}
    all_params = {**params, **pn_params}

    async with engine.connect() as conn:
        cur = await conn.execute(
            text(f"""
                SELECT r.id, r.profile_name, r.timestamp, r.summary_json,
                       r.percentiles_json, r.config_json, r.scheduled_task_id
                FROM results r
                WHERE r.user_id=:uid
                  AND r.profile_name IN ({placeholders})
                  {time_filter}
                ORDER BY r.profile_name, r.created_at DESC
            """),
            all_params,
        )
        rows = cur.fetchall()

    # 分桶：每个 profile 最多保留最近 50 条（用于 sparkline），最近 5 条用于健康计算
    profile_rows: dict[str, list] = {}
    for row in rows:
        pn = row[1]  # profile_name
        if pn not in profile_rows:
            profile_rows[pn] = []
        if len(profile_rows[pn]) < 50:
            profile_rows[pn].append(row)

    for pn, prows in profile_rows.items():
        if pn not in summary:
            continue

        # 解析最近 5 条用于健康判断
        latest_results = []
        for r in prows[:5]:
            try:
                s = json.loads(r[3])  # summary_json
            except (json.JSONDecodeError, TypeError):
                s = {}
            try:
                p = json.loads(r[4]) if r[4] else {}  # percentiles_json
            except (json.JSONDecodeError, TypeError):
                p = {}
            latest_results.append({
                "timestamp": r[2],
                "summary": s,
                "percentiles": p,
                "config": json.loads(r[5]) if r[5] else {},
                "scheduled_task_id": r[6],
            })

        summary[pn]["latest_results"] = latest_results
        summary[pn]["last_test_at"] = prows[0][2] if prows else None

        # 健康计算：最近 5 条的成功率均值
        success_rates = []
        for lr in latest_results:
            s = lr["summary"]
            total = s.get("total_requests", 0)
            if total > 0:
                success = s.get("success_count", s.get("successful_requests", 0))
                success_rates.append(success / total)

        if not success_rates:
            summary[pn]["health"] = "unknown"
        else:
            avg_rate = sum(success_rates) / len(success_rates)
            summary[pn]["health"] = "healthy" if avg_rate >= 0.95 else "error"

        # sparkline：按 model 分组提取 TTFT P50
        model_ttfts: dict[str, list[tuple[str, float]]] = {}
        for r in prows:
            try:
                cfg = json.loads(r[5])  # config_json
                model = cfg.get("model", "-")
            except (json.JSONDecodeError, TypeError):
                model = "-"
            try:
                p_json = json.loads(r[4])  # percentiles_json
                ttft = p_json.get("TTFT", {}).get("P50")
            except (json.JSONDecodeError, TypeError):
                ttft = None
            if ttft is not None:
                ts = r[2]  # timestamp
                model_ttfts.setdefault(model, []).append((ts, float(ttft)))

        sparkline_data: dict[str, list[float]] = {}
        for model, pairs in model_ttfts.items():
            pairs.sort(key=lambda x: x[0])
            values = [v for _, v in pairs]
            if len(values) > 50:
                step = len(values) / 50
                values = [values[int(i * step)] for i in range(50)]
            sparkline_data[model] = values
        summary[pn]["sparkline_data"] = sparkline_data

    return list(summary.values())


# ---- Channel Diagnostics CRUD ----

def _diag_row_to_dict(row) -> dict:
    """将 channel_diagnostics 行转为 dict，自动解析 report_json"""
    d = dict(row._mapping)
    if "report_json" in d and isinstance(d["report_json"], str):
        try:
            d["report_json"] = json.loads(d["report_json"])
        except (json.JSONDecodeError, TypeError):
            pass
    return d


async def save_channel_diagnostic(
    user_id: int,
    profile_name: str,
    model: str,
    status: str,
    overall_risk: str,
    confidence: float,
    report_json: dict,
) -> int:
    """保存诊断记录，返回 ID"""
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                INSERT INTO channel_diagnostics (user_id, profile_name, model, status, overall_risk, confidence, report_json)
                VALUES (:user_id, :profile_name, :model, :status, :overall_risk, :confidence, :report_json)
            """),
            {
                "user_id": user_id,
                "profile_name": profile_name,
                "model": model,
                "status": status,
                "overall_risk": overall_risk,
                "confidence": confidence,
                "report_json": json.dumps(report_json),
            },
        )
        if _is_sqlite:
            return result.lastrowid
        else:
            row = await conn.execute(
                text("SELECT currval(pg_get_serial_sequence('channel_diagnostics', 'id'))")
            )
            return row.fetchone()[0]


async def get_channel_diagnostic(diag_id: int, user_id: int) -> dict | None:
    """按 ID 获取诊断记录（校验用户归属）"""
    async with engine.begin() as conn:
        row = await conn.execute(
            text("SELECT * FROM channel_diagnostics WHERE id = :id AND user_id = :uid"),
            {"id": diag_id, "uid": user_id},
        )
        r = row.fetchone()
        if not r:
            return None
        return _diag_row_to_dict(r)


_LIST_DIAG_COLS = "id, profile_name, model, status, overall_risk, confidence, created_at"


async def list_channel_diagnostics(
    user_id: int,
    limit: int = 20,
    offset: int = 0,
    profile_name: str | None = None,
    model: str | None = None,
    status: str | None = None,
) -> tuple[list[dict], int]:
    """按用户列出诊断记录（摘要），返回 (items, total)"""
    where = ["user_id = :uid"]
    params: dict = {"uid": user_id, "limit": limit, "offset": offset}
    if profile_name:
        where.append("profile_name = :pn")
        params["pn"] = profile_name
    if model:
        where.append("model = :model")
        params["model"] = model
    if status:
        where.append("status = :status")
        params["status"] = status
    where_sql = " AND ".join(where)

    async with engine.begin() as conn:
        count_row = await conn.execute(
            text(f"SELECT COUNT(*) FROM channel_diagnostics WHERE {where_sql}"),
            params,
        )
        total = count_row.fetchone()[0]

        rows = await conn.execute(
            text(f"""
                SELECT {_LIST_DIAG_COLS} FROM channel_diagnostics
                WHERE {where_sql}
                ORDER BY id DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
        items = [dict(r._mapping) for r in rows.fetchall()]

    return items, total


async def list_diagnostic_filter_options(
    user_id: int,
    profile_name: str | None = None,
    model: str | None = None,
    status: str | None = None,
) -> dict:
    """返回级联筛选后的去重选项"""
    where = ["user_id = :uid"]
    params: dict = {"uid": user_id}
    if profile_name:
        where.append("profile_name = :pn")
        params["pn"] = profile_name
    if model:
        where.append("model = :model")
        params["model"] = model
    if status:
        where.append("status = :status")
        params["status"] = status
    where_sql = " AND ".join(where)

    async with engine.begin() as conn:
        rows = await conn.execute(
            text(f"""
                SELECT DISTINCT profile_name FROM channel_diagnostics
                WHERE {where_sql} ORDER BY profile_name
            """),
            params,
        )
        profile_names = [r[0] for r in rows.fetchall()]

        rows = await conn.execute(
            text(f"""
                SELECT DISTINCT model FROM channel_diagnostics
                WHERE {where_sql} ORDER BY model
            """),
            params,
        )
        models = [r[0] for r in rows.fetchall()]

    return {"profile_names": profile_names, "models": models}
