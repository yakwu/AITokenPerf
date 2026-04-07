#!/usr/bin/env python3
"""数据迁移脚本 — 从 config.yaml + results/*.json 迁移到 SQLite"""

import glob
import json
import os
import secrets
import shutil
import sys
from pathlib import Path

import yaml

from auth import hash_password
from db import (
    init_db, close_db,
    create_user, count_users,
    upsert_profile, save_settings,
    save_result as db_save_result,
    get_user_by_email,
)

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
RESULTS_DIR = BASE_DIR / "results"


def _print_admin_password(email, password):
    """安全输出管理员密码 — 仅在 TTY 时打印明文"""
    print(f"\n  管理员账号已创建:")
    print(f"    邮箱: {email}")
    if sys.stdout.isatty():
        print(f"    密码: {password}")
    else:
        print(f"    密码: [已隐藏 — 请查看终端启动日志]")
    print(f"    (请登录后尽快修改密码)\n")


async def migrate():
    """首次启动时自动迁移数据"""
    # 初始化 DB
    await init_db()

    # 增量 schema 迁移（处理已有数据库的新增列/表）
    await _migrate_schema()

    # 检查是否已有数据
    if await count_users() > 0:
        print("  数据库已有数据，跳过迁移")
        return

    # 检查是否有旧数据
    has_config = CONFIG_PATH.exists()
    has_results = RESULTS_DIR.exists() and any(RESULTS_DIR.glob("bench_*.json"))

    if not has_config and not has_results:
        print("  无旧数据需要迁移，创建默认管理员账号...")
        await _create_default_admin()
        return

    print("  检测到旧数据，开始迁移...")

    # 1. 创建管理员用户
    admin_password = secrets.token_urlsafe(12)
    admin_email = "admin@local"
    user_id = await create_user(admin_email, hash_password(admin_password), "Admin", "admin")
    _print_admin_password(admin_email, admin_password)

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
        print(f"  迁移 {len(profiles)} 个 profiles")

        # 3. 迁移 benchmark 配置
        benchmark = raw_config.get("benchmark", {})
        if benchmark:
            output_dir = raw_config.get("output_dir", "./results")
            await save_settings(user_id, benchmark, output_dir)
            print(f"  迁移 benchmark 配置")

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
                print(f"  警告: 跳过 {filepath.name}: {e}")
        print(f"  迁移 {count} 个历史结果")

    # 5. 备份 config.yaml
    if has_config:
        bak_path = CONFIG_PATH.with_suffix(".yaml.bak")
        shutil.copy2(CONFIG_PATH, bak_path)
        print(f"  备份 config.yaml → {bak_path.name}")

    print("  数据迁移完成\n")


async def _create_default_admin():
    """无旧数据时创建默认管理员"""
    admin_password = secrets.token_urlsafe(12)
    admin_email = "admin@local"
    await create_user(admin_email, hash_password(admin_password), "Admin", "admin")
    _print_admin_password(admin_email, admin_password)


async def _migrate_schema():
    """增量迁移：为已有数据库添加新列/表"""
    from db import get_db
    db = await get_db()

    # 检查 results 表是否有 group_id 列
    cur = await db.execute("PRAGMA table_info(results)")
    columns = {row[1] for row in await cur.fetchall()}
    if "group_id" not in columns:
        await db.execute("ALTER TABLE results ADD COLUMN group_id TEXT NOT NULL DEFAULT ''")
        await db.commit()
        print("  schema 迁移: results 表添加 group_id 列")

    if "scheduled_task_id" not in columns:
        await db.execute("ALTER TABLE results ADD COLUMN scheduled_task_id INTEGER NOT NULL DEFAULT 0")
        await db.commit()
        print("  schema 迁移: results 表添加 scheduled_task_id 列")

    # scheduled_tasks 表由 init_db 中的 CREATE TABLE IF NOT EXISTS 处理
    # 无需额外迁移
