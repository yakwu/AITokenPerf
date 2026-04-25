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


@pytest.mark.asyncio
async def test_backfill_redundant_columns():
    """历史数据的 profile_name/base_url 应从 config_json 回填"""
    # 直接插入一条只有 config_json 没有冗余列值的数据
    async with engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO results (user_id, test_id, filename, timestamp,
                config_json, summary_json, percentiles_json,
                profile_name, base_url)
            VALUES (1, 'bf-test', 'bf_test.json', '20260425_120000',
                '{"profile_name":"OldSite","base_url":"https://old.example.com"}',
                '{}', '{}', '', '')
        """))

    # 运行回填迁移
    from app.db import _backfill_redundant_columns
    await _backfill_redundant_columns()

    # 验证回填结果
    async with engine.connect() as conn:
        cur = await conn.execute(text(
            "SELECT profile_name, base_url FROM results WHERE test_id='bf-test'"
        ))
        row = cur.fetchone()
    assert row[0] == "OldSite", f"profile_name 应回填为 OldSite，实际为 {row[0]}"
    assert row[1] == "https://old.example.com", f"base_url 应回填，实际为 {row[1]}"


@pytest.mark.asyncio
async def test_save_result_populates_redundant_columns():
    """save_result 应从 config_json 提取 profile_name/base_url 写入冗余列"""
    import json
    from app.db import save_result
    config = json.dumps({"profile_name": "NewSite", "base_url": "https://new.example.com", "model": "gpt-4o"})
    await save_result(
        user_id=1, test_id="rc-test", filename="rc_test.json",
        timestamp="20260425_140000",
        config_json=config, summary_json="{}", percentiles_json="{}",
    )

    async with engine.connect() as conn:
        cur = await conn.execute(text(
            "SELECT profile_name, base_url FROM results WHERE test_id='rc-test'"
        ))
        row = cur.fetchone()
    assert row[0] == "NewSite", f"profile_name 应为 NewSite，实际为 {row[0]}"
    assert row[1] == "https://new.example.com", f"base_url 应为 https://new.example.com，实际为 {row[1]}"
