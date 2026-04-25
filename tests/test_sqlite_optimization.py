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
