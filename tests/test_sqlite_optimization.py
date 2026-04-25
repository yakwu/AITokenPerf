"""TDD 测试：SQLite 高负载查询优化"""

import pytest
from sqlalchemy import text

from app.db import engine


async def _get_indexes(table_name: str) -> set[str]:
    """获取表的所有索引名"""
    async with engine.connect() as conn:
        cur = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:t"),
            {"t": table_name},
        )
        return {row[0] for row in cur.fetchall()}


@pytest.mark.asyncio
async def test_results_table_has_indexes():
    """results 表应有覆盖主要查询路径的索引"""
    indexes = await _get_indexes("results")
    assert "idx_results_user_time" in indexes, "缺少 (user_id, created_at) 索引"
    assert "idx_results_user_sched_time" in indexes, "缺少 (user_id, scheduled_task_id, created_at) 索引"
    assert "idx_results_filename" in indexes, "缺少 filename 索引"


@pytest.mark.asyncio
async def test_results_table_has_redundant_columns():
    """results 表应有 profile_name 和 base_url 冗余列"""
    async with engine.connect() as conn:
        cur = await conn.execute(text("PRAGMA table_info(results)"))
        columns = {row[1] for row in cur.fetchall()}
    assert "profile_name" in columns, "缺少 profile_name 列"
    assert "base_url" in columns, "缺少 base_url 列"


@pytest.mark.asyncio
async def test_redundant_columns_have_indexes():
    """冗余列应有对应索引"""
    indexes = await _get_indexes("results")
    assert "idx_results_user_profile_time" in indexes, "缺少 (user_id, profile_name, created_at) 索引"
    assert "idx_results_user_url_time" in indexes, "缺少 (user_id, base_url, created_at) 索引"
