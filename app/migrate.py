#!/usr/bin/env python3
"""数据迁移脚本 — 从 config.yaml + results/*.json 迁移到 SQLite"""

import json
import logging
import shutil
import sys
from pathlib import Path

import yaml

from app.auth import hash_password
from app.db import (
    init_db, close_db,
    create_user, count_users,
    upsert_profile, save_settings,
    save_result as db_save_result,
    get_user_by_email,
)

log = logging.getLogger("migrate")

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"
RESULTS_DIR = BASE_DIR / "results"


async def migrate():
    """首次启动时自动迁移数据"""
    # 初始化 DB
    await init_db()

    # 增量 schema 迁移（处理已有数据库的新增列/表）
    await _migrate_schema()

    # 检查是否已有数据
    if await count_users() > 0:
        log.info("数据库已有数据，跳过迁移")
        return

    # 检查是否有旧数据
    has_config = CONFIG_PATH.exists()
    has_results = RESULTS_DIR.exists() and any(RESULTS_DIR.glob("bench_*.json"))

    if not has_config and not has_results:
        log.info("无旧数据需要迁移，创建默认管理员账号")
        await _create_default_admin()
        return

    log.info("检测到旧数据，开始迁移")

    # 1. 创建管理员用户
    admin_email = "admin@example.com"
    admin_password = "AITokenPerf#123"
    user_id = await create_user(admin_email, hash_password(admin_password), "Admin", "admin", must_change_password=True)
    log.info("管理员账号已创建: %s (首次登录后请尽快修改密码)", admin_email)

    # 2. 迁移 profiles
    if has_config:
        with open(CONFIG_PATH) as f:
            raw_config = yaml.safe_load(f) or {}

        profiles = raw_config.get("profiles", [])
        active_name = raw_config.get("active_profile", "")

        for p in profiles:
            name = p.get("name", "")
            if not name:
                continue
            is_active = name == active_name
            await upsert_profile(
                user_id, name,
                base_url=p.get("base_url", ""),
                api_key=p.get("api_key", ""),
                api_version=p.get("api_version", "2023-06-01"),
                model=p.get("model", ""),
                set_active=is_active,
            )
        log.info("迁移 %d 个 profiles", len(profiles))

        # 3. 迁移 benchmark 配置
        benchmark = raw_config.get("benchmark", {})
        if benchmark:
            output_dir = raw_config.get("output_dir", "./results")
            await save_settings(user_id, benchmark, output_dir)
            log.info("迁移 benchmark 配置")

    # 4. 迁移 results
    if has_results:
        count = 0
        for filepath in sorted(RESULTS_DIR.glob("bench_*.json")):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                await db_save_result(
                    user_id=user_id,
                    test_id=data.get("test_id", ""),
                    filename=filepath.name,
                    timestamp=data.get("timestamp", ""),
                    config_json=json.dumps(data.get("config", {})),
                    summary_json=json.dumps(data.get("summary", {})),
                    percentiles_json=json.dumps(data.get("percentiles", {})),
                    errors_json=json.dumps(data.get("errors", {})),
                    error_details_json=json.dumps(data.get("error_details", [])),
                )
                count += 1
            except (json.JSONDecodeError, IOError) as e:
                log.warning("跳过 %s: %s", filepath.name, e)
        log.info("迁移 %d 个历史结果", count)

    # 5. 备份 config.yaml
    if has_config:
        bak_path = CONFIG_PATH.with_suffix(".yaml.bak")
        shutil.copy2(CONFIG_PATH, bak_path)
        log.info("备份 config.yaml → %s", bak_path.name)

    log.info("数据迁移完成")


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
