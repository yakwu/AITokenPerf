"""TDD 测试：SQLite 高负载查询优化"""

import json

import pytest
from sqlalchemy import text

from app.db import engine, get_site_trend, get_sites_summary, upsert_profile, save_result


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


async def _seed_optimization_data():
    """为优化测试插入数据"""
    from app.db import save_result
    import json
    for i in range(5):
        await save_result(
            user_id=1, test_id=f"opt-a-{i}", filename=f"opt_a_{i}.json",
            timestamp=f"20260425_{10+i:02d}0000",
            config_json=json.dumps({"profile_name": "SiteA", "base_url": "https://a.com", "model": "gpt-4o"}),
            summary_json=json.dumps({"success_rate": 99.5, "token_throughput_tps": 100}),
            percentiles_json=json.dumps({"TTFT": {"P50": 0.5}}),
        )
    for i in range(3):
        await save_result(
            user_id=1, test_id=f"opt-b-{i}", filename=f"opt_b_{i}.json",
            timestamp=f"20260425_{12+i:02d}0000",
            config_json=json.dumps({"profile_name": "SiteB", "base_url": "https://b.com", "model": "claude-opus-4-6"}),
            summary_json=json.dumps({"success_rate": 95.0, "token_throughput_tps": 80}),
            percentiles_json=json.dumps({"TTFT": {"P50": 0.8}}),
        )


@pytest.mark.asyncio
async def test_aggregated_filter_by_profile_name():
    """get_results_aggregated 按 profile_name 过滤应只返回匹配数据"""
    from app.db import get_results_aggregated
    await _seed_optimization_data()
    result = await get_results_aggregated(user_id=1, limit=100, profile_name="SiteA")
    for item in result["items"]:
        assert item["config"].get("profile_name") == "SiteA", f"应只返回 SiteA，实际为 {item['config'].get('profile_name')}"
    assert result["total"] == 5, f"应有 5 条 SiteA 数据，实际为 {result['total']}"


@pytest.mark.asyncio
async def test_aggregated_filter_by_base_url():
    """get_results_aggregated 按 base_url 过滤应只返回匹配数据"""
    from app.db import get_results_aggregated
    await _seed_optimization_data()
    result = await get_results_aggregated(user_id=1, limit=100, base_url="https://b.com")
    for item in result["items"]:
        assert item["config"].get("profile_name") == "SiteB"
    assert result["total"] == 3


@pytest.mark.asyncio
async def test_site_trend_filter_by_profile_name():
    """get_site_trend 按 profile_name 过滤应只返回匹配站点的趋势"""
    await _seed_optimization_data()
    trend = await get_site_trend(user_id=1, base_url="", profile_name="SiteA")
    # SiteA 有 5 条数据，应全部出现在趋势中
    total_runs = sum(p["run_count"] for p in trend)
    assert total_runs == 5, f"SiteA 趋势应有 5 次运行，实际为 {total_runs}"


@pytest.mark.asyncio
async def test_sites_summary_returns_correct_health():
    """get_sites_summary 应正确计算每个站点的健康状态"""
    await upsert_profile(
        user_id=1, name="HealthySite", base_url="https://healthy.com",
        api_key="sk-test", model="gpt-4o", provider="openai",
    )
    await upsert_profile(
        user_id=1, name="ErrorSite", base_url="https://error.com",
        api_key="sk-test", model="gpt-4o", provider="openai",
    )

    # HealthySite: 5 条 100% 成功率
    for i in range(5):
        await save_result(
            user_id=1, test_id=f"hs-{i}", filename=f"hs_{i}.json",
            timestamp=f"20260425_{14+i:02d}0000",
            config_json=json.dumps({"profile_name": "HealthySite", "base_url": "https://healthy.com"}),
            summary_json=json.dumps({"success_count": 10, "total_requests": 10, "success_rate": 100.0}),
            percentiles_json=json.dumps({"TTFT": {"P50": 0.5}}),
        )

    # ErrorSite: 5 条 50% 成功率
    for i in range(5):
        await save_result(
            user_id=1, test_id=f"es-{i}", filename=f"es_{i}.json",
            timestamp=f"20260425_{14+i:02d}0000",
            config_json=json.dumps({"profile_name": "ErrorSite", "base_url": "https://error.com"}),
            summary_json=json.dumps({"success_count": 5, "total_requests": 10, "success_rate": 50.0}),
            percentiles_json=json.dumps({"TTFT": {"P50": 1.5}}),
        )

    summary = await get_sites_summary(user_id=1)
    by_name = {s["profile"]["name"]: s for s in summary}

    assert by_name["HealthySite"]["health"] == "healthy"
    assert by_name["ErrorSite"]["health"] == "error"
    assert by_name["HealthySite"]["last_test_at"] is not None


@pytest.mark.asyncio
async def test_sites_summary_sparkline_data():
    """get_sites_summary 应返回 sparkline_data"""
    await upsert_profile(
        user_id=1, name="SparkSite", base_url="https://spark.com",
        api_key="sk-test", model="gpt-4o", provider="openai",
    )
    for i in range(10):
        await save_result(
            user_id=1, test_id=f"sp-{i}", filename=f"sp_{i}.json",
            timestamp=f"20260425_{10+i:02d}0000",
            config_json=json.dumps({"profile_name": "SparkSite", "base_url": "https://spark.com", "model": "gpt-4o"}),
            summary_json=json.dumps({"success_count": 10, "total_requests": 10, "success_rate": 100.0}),
            percentiles_json=json.dumps({"TTFT": {"P50": 0.3 + i * 0.05}}),
        )

    summary = await get_sites_summary(user_id=1)
    by_name = {s["profile"]["name"]: s for s in summary}
    spark = by_name["SparkSite"]["sparkline_data"]
    assert "gpt-4o" in spark, "sparkline 应按 model 分组"
    assert len(spark["gpt-4o"]) == 10, f"应有 10 个点，实际为 {len(spark['gpt-4o'])}"
