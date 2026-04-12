"""TDD 测试：站点执行记录后端 base_url 过滤"""

import json
import pytest

from datetime import datetime, timedelta
from app.db import save_result, get_results_aggregated, upsert_profile
from tests.conftest import auth_headers


def _ts(hours_ago: float = 0) -> str:
    dt = datetime.now() - timedelta(hours=hours_ago)
    return dt.strftime("%Y%m%d_%H%M%S")


def _config(base_url="https://api.example.com", model="claude-opus-4-6"):
    return json.dumps({"base_url": base_url, "model": model})


def _summary():
    return json.dumps({"success_rate": 99.0, "token_throughput_tps": 50.0})


def _percentiles():
    return json.dumps({"TTFT": {"P50": 0.5}, "TPOT": {"P50": 0.02}})


async def _seed_multi_site_data(user_id=1):
    """插入多个站点的测试数据"""
    await upsert_profile(user_id, "SiteA", base_url="https://api-a.example.com", api_key="sk-a", model="gpt-4")
    await upsert_profile(user_id, "SiteB", base_url="https://api-b.example.com", api_key="sk-b", model="claude-opus-4-6")

    # SiteA: 3 条
    for i in range(3):
        await save_result(
            user_id=user_id, test_id=f"a-{i}", filename=f"a_{i}.json",
            timestamp=_ts(hours_ago=i),
            config_json=_config(base_url="https://api-a.example.com", model="gpt-4"),
            summary_json=_summary(), percentiles_json=_percentiles(),
        )

    # SiteB: 5 条
    for i in range(5):
        await save_result(
            user_id=user_id, test_id=f"b-{i}", filename=f"b_{i}.json",
            timestamp=_ts(hours_ago=i),
            config_json=_config(base_url="https://api-b.example.com", model="claude-opus-4-6"),
            summary_json=_summary(), percentiles_json=_percentiles(),
        )

    # SiteA with trailing slash: 2 条
    for i in range(2):
        await save_result(
            user_id=user_id, test_id=f"a-slash-{i}", filename=f"a_slash_{i}.json",
            timestamp=_ts(hours_ago=i),
            config_json=_config(base_url="https://api-a.example.com/", model="gpt-4"),
            summary_json=_summary(), percentiles_json=_percentiles(),
        )


# ==========================================
# 第一部分: get_results_aggregated base_url 过滤
# ==========================================

@pytest.mark.asyncio
async def test_results_aggregated_base_url_filter():
    """传 base_url 参数时，只返回该站点的结果"""
    await _seed_multi_site_data()
    result = await get_results_aggregated(user_id=1, limit=50, raw=True, base_url="https://api-a.example.com")
    # SiteA 有 3 + 2(trailing slash) = 5 条
    for item in result["items"]:
        config = item.get("config", {})
        assert config.get("base_url", "").rstrip("/") == "https://api-a.example.com", \
            f"应只含 SiteA 的结果，但得到: {config.get('base_url')}"


@pytest.mark.asyncio
async def test_results_aggregated_base_url_filter_total():
    """base_url 过滤后，total 只计该站点的数量"""
    await _seed_multi_site_data()
    result = await get_results_aggregated(user_id=1, limit=50, raw=True, base_url="https://api-b.example.com")
    assert result["total"] == 5, f"SiteB 应有 5 条，实际: {result['total']}"


@pytest.mark.asyncio
async def test_results_aggregated_base_url_trailing_slash():
    """base_url 尾斜杠兼容：查 'https://api-a.example.com' 也能命中 'https://api-a.example.com/'"""
    await _seed_multi_site_data()
    result = await get_results_aggregated(user_id=1, limit=50, raw=True, base_url="https://api-a.example.com")
    assert result["total"] == 5, f"含尾斜杠的结果也应被匹配，total 应为 5，实际: {result['total']}"


@pytest.mark.asyncio
async def test_results_aggregated_no_base_url_returns_all():
    """不传 base_url 时，返回所有站点的结果"""
    await _seed_multi_site_data()
    result = await get_results_aggregated(user_id=1, limit=50, raw=True)
    assert result["total"] == 10, f"不传 base_url 应返回全部 10 条，实际: {result['total']}"


# ==========================================
# 第二部分: API 端点测试
# ==========================================

@pytest.mark.asyncio
async def test_api_results_accepts_base_url_param(client):
    """/api/results?base_url=xxx 应过滤结果"""
    headers = await auth_headers(client)
    await _seed_multi_site_data()

    resp = await client.get(
        "/api/results?raw=true&limit=50&base_url=https://api-b.example.com",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    for item in data["items"]:
        assert item["config"]["base_url"].rstrip("/") == "https://api-b.example.com"


@pytest.mark.asyncio
async def test_api_results_without_base_url_returns_all(client):
    """/api/results 不带 base_url 返回全部"""
    headers = await auth_headers(client)
    await _seed_multi_site_data()

    resp = await client.get("/api/results?raw=true&limit=50", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 10
