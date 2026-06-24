#!/usr/bin/env python3
"""数据库初始化 + 增量 schema 迁移。

历史上本模块还负责从 config.yaml + results/*.json 一次性导入数据，
该逻辑已随数据全面入库而移除（issue #85）。现仅做：建表、增量加列/清列、
老数据回填、全新库建默认管理员。
"""

import logging

from app.auth import hash_password
from app.db import init_db, create_user, count_users

log = logging.getLogger("migrate")


async def migrate():
    """启动时初始化数据库并执行增量 schema 迁移。"""
    # 建表（CREATE TABLE IF NOT EXISTS）
    await init_db()

    # 增量 schema 迁移（为已有库补新列、清理废弃列、回填老数据）
    await _migrate_schema()

    # 全新库：创建默认管理员账号
    if await count_users() == 0:
        log.info("空数据库，创建默认管理员账号")
        await _create_default_admin()


async def _create_default_admin():
    """无旧数据时创建默认管理员"""
    admin_email = "admin@example.com"
    admin_password = "AITokenPerf#123"
    await create_user(admin_email, hash_password(admin_password), "Admin", "admin", must_change_password=True)
    log.info("管理员账号已创建: %s (首次登录后请尽快修改密码)", admin_email)


async def _migrate_schema():
    """增量迁移：为已有数据库添加新列/表"""
    from app.db import engine, _is_sqlite
    from sqlalchemy import text

    async with engine.begin() as conn:
        if _is_sqlite:
            cur = await conn.execute(text("PRAGMA table_info(results)"))
            rows = cur.fetchall()
            columns = {row[1] for row in rows}
        else:
            cur = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='results'")
            )
            rows = cur.fetchall()
            columns = {row[0] for row in rows}

        if "group_id" not in columns:
            await conn.execute(text("ALTER TABLE results ADD COLUMN group_id TEXT NOT NULL DEFAULT ''"))
            log.info("schema 迁移: results 表添加 group_id 列")

        if "scheduled_task_id" not in columns:
            await conn.execute(text("ALTER TABLE results ADD COLUMN scheduled_task_id INTEGER NOT NULL DEFAULT 0"))
            log.info("schema 迁移: results 表添加 scheduled_task_id 列")

        for col_name, ddl in [
            ("run_id", "ALTER TABLE results ADD COLUMN run_id TEXT NOT NULL DEFAULT ''"),
            ("task_id", "ALTER TABLE results ADD COLUMN task_id TEXT NOT NULL DEFAULT ''"),
            ("source", "ALTER TABLE results ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'"),
        ]:
            if col_name not in columns:
                await conn.execute(text(ddl))
                log.info("schema 迁移: results 表添加 %s 列", col_name)

    # profiles 表新增 provider + protocol 列
    async with engine.begin() as conn:
        if _is_sqlite:
            cur = await conn.execute(text("PRAGMA table_info(profiles)"))
            rows = cur.fetchall()
            columns = {row[1] for row in rows}
        else:
            cur = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='profiles'")
            )
            rows = cur.fetchall()
            columns = {row[0] for row in rows}

        if "provider" not in columns:
            await conn.execute(text("ALTER TABLE profiles ADD COLUMN provider TEXT NOT NULL DEFAULT ''"))
            log.info("schema 迁移: profiles 表添加 provider 列")

        if "protocol" not in columns:
            await conn.execute(text("ALTER TABLE profiles ADD COLUMN protocol TEXT NOT NULL DEFAULT ''"))
            log.info("schema 迁移: profiles 表添加 protocol 列")

        if "custom_endpoint" not in columns:
            await conn.execute(text("ALTER TABLE profiles ADD COLUMN custom_endpoint INTEGER NOT NULL DEFAULT 0"))
            log.info("schema 迁移: profiles 表添加 custom_endpoint 列")

    # scheduled_tasks 表新增 locked_until 列（分布式锁）
    async with engine.begin() as conn:
        if _is_sqlite:
            cur = await conn.execute(text("PRAGMA table_info(scheduled_tasks)"))
            rows = cur.fetchall()
            columns = {row[1] for row in rows}
        else:
            cur = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='scheduled_tasks'")
            )
            rows = cur.fetchall()
            columns = {row[0] for row in rows}

        if "locked_until" not in columns:
            await conn.execute(text("ALTER TABLE scheduled_tasks ADD COLUMN locked_until TEXT"))
            log.info("schema 迁移: scheduled_tasks 表添加 locked_until 列")

    # scheduled_tasks 表由 init_db 中的 CREATE TABLE IF NOT EXISTS 处理
    # 无需额外迁移

    # users 表新增 must_change_password 列
    async with engine.begin() as conn:
        if _is_sqlite:
            cur = await conn.execute(text("PRAGMA table_info(users)"))
            rows = cur.fetchall()
            columns = {row[1] for row in rows}
        else:
            cur = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='users'")
            )
            rows = cur.fetchall()
            columns = {row[0] for row in rows}

        if "must_change_password" not in columns:
            if _is_sqlite:
                await conn.execute(text("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0"))
            else:
                await conn.execute(text("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT FALSE"))
            log.info("schema 迁移: users 表添加 must_change_password 列")

    # user_settings 清理废弃列 output_dir（早期「本地导出结果」遗留，从未真正使用，issue #85）
    async with engine.begin() as conn:
        if _is_sqlite:
            cur = await conn.execute(text("PRAGMA table_info(user_settings)"))
            columns = {row[1] for row in cur.fetchall()}
        else:
            cur = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='user_settings'")
            )
            columns = {row[0] for row in cur.fetchall()}

        if "output_dir" in columns:
            # SQLite 3.35+ / PostgreSQL 均支持 DROP COLUMN；老 SQLite 失败则忽略（无害遗留列）
            try:
                await conn.execute(text("ALTER TABLE user_settings DROP COLUMN output_dir"))
                log.info("schema 迁移: user_settings 表删除废弃列 output_dir")
            except Exception as e:
                log.warning("删除 output_dir 列失败（忽略）: %s", e)

    # 迁移老数据：为 config_json 中缺少 profile_name 的 results 回填
    await _backfill_profile_name()


async def _backfill_profile_name():
    """为老数据回填 profile_name，无法唯一匹配的记录直接删除。"""
    import json as _json
    from app.db import engine, _is_sqlite
    from sqlalchemy import text

    async with engine.begin() as conn:
        # 1. 找出所有缺少 profile_name 的记录
        if _is_sqlite:
            cur = await conn.execute(text(
                """SELECT id, user_id, config_json FROM results
                   WHERE json_extract(config_json, '$.profile_name') IS NULL
                      OR json_extract(config_json, '$.profile_name') = ''"""
            ))
        else:
            cur = await conn.execute(text(
                """SELECT id, user_id, config_json FROM results
                   WHERE config_json::jsonb->>'profile_name' IS NULL
                      OR config_json::jsonb->>'profile_name' = ''"""
            ))
        orphan_rows = cur.fetchall()

        if not orphan_rows:
            return

        log.info("发现 %d 条缺少 profile_name 的老数据，开始回填", len(orphan_rows))

        # 2. 加载所有 profiles，按 (user_id, base_url) 分组
        cur = await conn.execute(text("SELECT user_id, name, base_url FROM profiles"))
        profile_rows = cur.fetchall()

        # {(user_id, base_url_clean): [profile_name, ...]}
        url_to_profiles: dict[tuple, list[str]] = {}
        for uid, pname, burl in profile_rows:
            key = (uid, burl.rstrip("/"))
            url_to_profiles.setdefault(key, []).append(pname)

        updated = 0
        deleted_ids = []

        for rid, uid, config_str in orphan_rows:
            try:
                config = _json.loads(config_str)
            except (_json.JSONDecodeError, TypeError):
                deleted_ids.append(rid)
                continue

            base_url = (config.get("base_url") or "").rstrip("/")
            if not base_url:
                deleted_ids.append(rid)
                continue

            candidates = url_to_profiles.get((uid, base_url), [])

            if len(candidates) == 1:
                # 唯一匹配，回填 profile_name
                config["profile_name"] = candidates[0]
                await conn.execute(
                    text("UPDATE results SET config_json=:cj WHERE id=:rid"),
                    {"cj": _json.dumps(config, ensure_ascii=False), "rid": rid},
                )
                updated += 1
            else:
                # 0 个或多个匹配 → 删除
                deleted_ids.append(rid)

        if deleted_ids:
            # 分批删除，避免 SQL 参数过多
            batch_size = 500
            for i in range(0, len(deleted_ids), batch_size):
                batch = deleted_ids[i:i + batch_size]
                placeholders = ",".join(str(x) for x in batch)
                await conn.execute(text(f"DELETE FROM results WHERE id IN ({placeholders})"))

        log.info("profile_name 回填完成: 更新 %d 条, 删除 %d 条歧义/无法匹配记录",
                 updated, len(deleted_ids))
