"""TDD 测试：全局时间范围 — get_results(hours) 过滤 + /api/sites/summary?hours= 端点 + sparkline_data"""

import json
import pytest

from datetime import datetime, timedelta
from app.db import (
    save_result,
    get_results,
    get_sites_summary,
    upsert_profile,
    create_scheduled_task,
)
from tests.conftest import auth_headers


# ---- 辅助函数 ----

def _make_timestamp(hours_ago: float = 0) -> str:
    """生成 YYYYMMdd_HHMMSS 格式的时间戳"""
    dt = datetime.now() - timedelta(hours=hours_ago)
    return dt.strftime("%Y%m%d_%H%M%S")


def _config_json(base_url: str = "https://api.example.com", model: str = "claude-opus-4-6",
                 profile_name: str = "") -> str:
    d = {"base_url": base_url, "model": model}
    if profile_name:
        d["profile_name"] = profile_name
    return json.dumps(d)


def _summary_json(success_count: int = 1, total_requests: int = 1) -> str:
    return json.dumps({
        "success_count": success_count,
        "total_requests": total_requests,
        "success_rate": (success_count / total_requests * 100) if total_requests else 0,
        "token_throughput_tps": 50.0,
    })


def _percentiles_json(ttft_p50: float | None = 1.0, tpot_p50: float | None = 0.05) -> str:
    d = {}
    if ttft_p50 is not None:
        d["TTFT"] = {"P50": ttft_p50, "P95": ttft_p50 * 2, "P99": ttft_p50 * 3}
    if tpot_p50 is not None:
        d["TPOT"] = {"P50": tpot_p50, "P95": tpot_p50 * 2, "P99": tpot_p50 * 3}
    return json.dumps(d)


async def _seed_profile_and_results(user_id: int = 1):
    """
    创建一个 profile 和一组测试结果：
    - 12 条结果，分布在不同时间点
    - 最近 3 小时内有 3 条全部失败（无 TTFT）
    - 5-8 小时前有 4 条成功（有 TTFT）
    - 25-30 小时前有 5 条成功（有 TTFT）
    """
    await upsert_profile(
        user_id=user_id,
        name="TestSite",
        base_url="https://api.example.com",
        api_key="sk-test",
        model="claude-opus-4-6",
        provider="anthropic",
    )

    # 最近 3 小时：全部失败 (success=0, 无 TTFT)
    for i in range(3):
        await save_result(
            user_id=user_id,
            test_id=f"fail-{i}",
            filename=f"fail_{i}.json",
            timestamp=_make_timestamp(hours_ago=i + 0.5),
            config_json=_config_json(profile_name="TestSite"),
            summary_json=_summary_json(success_count=0, total_requests=1),
            percentiles_json=_percentiles_json(ttft_p50=None, tpot_p50=None),
            errors_json=json.dumps({"HTTP 503": 1}),
        )

    # 5-8 小时前：成功
    for i in range(4):
        await save_result(
            user_id=user_id,
            test_id=f"ok-recent-{i}",
            filename=f"ok_recent_{i}.json",
            timestamp=_make_timestamp(hours_ago=5 + i),
            config_json=_config_json(profile_name="TestSite"),
            summary_json=_summary_json(success_count=1, total_requests=1),
            percentiles_json=_percentiles_json(ttft_p50=1.0 + i * 0.1),
        )

    # 25-30 小时前：成功
    for i in range(5):
        await save_result(
            user_id=user_id,
            test_id=f"ok-old-{i}",
            filename=f"ok_old_{i}.json",
            timestamp=_make_timestamp(hours_ago=25 + i),
            config_json=_config_json(profile_name="TestSite"),
            summary_json=_summary_json(success_count=1, total_requests=1),
            percentiles_json=_percentiles_json(ttft_p50=2.0 + i * 0.1),
        )


# ==========================================
# 第一部分: get_results(hours) 时间过滤测试
# ==========================================

@pytest.mark.asyncio
async def test_get_results_without_hours_returns_all():
    """不传 hours 时应返回全部结果"""
    await _seed_profile_and_results()
    results = await get_results(user_id=1)
    assert len(results) == 12


@pytest.mark.asyncio
async def test_get_results_hours_6_filters_recent():
    """hours=6 只返回最近 6 小时内的结果"""
    await _seed_profile_and_results()
    results = await get_results(user_id=1, hours=6)
    # 最近 6 小时内应只有 3 条失败结果 (0.5h, 1.5h, 2.5h ago)
    # 5h-8h 前的 4 条中, 5h ago 的刚好在边界附近
    # 由于时间计算存在微小误差，至少应该有 3 条
    assert len(results) >= 3
    assert len(results) <= 7  # 不应包含 25h+ 的老数据


@pytest.mark.asyncio
async def test_get_results_hours_24_excludes_old():
    """hours=24 应排除 25h+ 前的数据"""
    await _seed_profile_and_results()
    results = await get_results(user_id=1, hours=24)
    # 25-30 小时前的 5 条应被排除
    assert len(results) <= 7  # 最多 3 + 4 = 7 条


@pytest.mark.asyncio
async def test_get_results_hours_168_returns_all():
    """hours=168 (7天) 应返回全部结果（没有超过 7 天的数据）"""
    await _seed_profile_and_results()
    results = await get_results(user_id=1, hours=168)
    assert len(results) == 12


# ==========================================
# 第二部分: /api/sites/summary?hours= 端点测试
# ==========================================

@pytest.mark.asyncio
async def test_sites_summary_endpoint_accepts_hours(client):
    """端点应接受 hours 查询参数"""
    headers = await auth_headers(client)
    resp = await client.get("/api/sites/summary?hours=6", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data


@pytest.mark.asyncio
async def test_sites_summary_endpoint_without_hours(client):
    """不传 hours 时端点应正常工作（向后兼容）"""
    headers = await auth_headers(client)
    resp = await client.get("/api/sites/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data


# ==========================================
# 第三部分: sparkline_data 字段测试
# ==========================================

@pytest.mark.asyncio
async def test_sites_summary_contains_sparkline_data():
    """summary 结果应包含 sparkline_data 字段"""
    await _seed_profile_and_results()
    summary = await get_sites_summary(user_id=1)
    assert len(summary) > 0
    site = summary[0]
    assert "sparkline_data" in site


@pytest.mark.asyncio
async def test_sparkline_data_grouped_by_model():
    """sparkline_data 应按 model 分组"""
    await _seed_profile_and_results()
    summary = await get_sites_summary(user_id=1)
    site = summary[0]
    sparkline = site["sparkline_data"]
    assert isinstance(sparkline, dict)
    assert "claude-opus-4-6" in sparkline


@pytest.mark.asyncio
async def test_sparkline_data_contains_ttft_values():
    """sparkline_data 中每个 model 对应一个 TTFT P50 数值列表"""
    await _seed_profile_and_results()
    summary = await get_sites_summary(user_id=1)
    site = summary[0]
    values = site["sparkline_data"]["claude-opus-4-6"]
    assert isinstance(values, list)
    assert len(values) > 0
    # 所有值应为 float
    for v in values:
        assert isinstance(v, (int, float))


@pytest.mark.asyncio
async def test_sparkline_data_chronological_order():
    """sparkline_data 中的值应按时间正序排列（旧 → 新）"""
    await _seed_profile_and_results()
    # hours=168 获取全部数据
    summary = await get_sites_summary(user_id=1, hours=168)
    site = summary[0]
    values = site["sparkline_data"]["claude-opus-4-6"]
    # 老数据的 TTFT 是 2.0~2.4，新数据是 1.0~1.3
    # 正序排列：前面应该是较大的值（老数据），后面较小（近期数据）
    assert len(values) >= 2
    assert values[0] > values[-1]


@pytest.mark.asyncio
async def test_sparkline_data_with_hours_6_only_recent():
    """hours=6 时 sparkline_data 只包含 6 小时内有 TTFT 的数据"""
    await _seed_profile_and_results()
    summary = await get_sites_summary(user_id=1, hours=6)
    site = summary[0]
    sparkline = site["sparkline_data"]
    # 最近 6 小时的 3 条全是失败的（无 TTFT），5-6h 前可能有 1 条成功的
    model_data = sparkline.get("claude-opus-4-6", [])
    # 不应包含 25h+ 前的数据（那些 TTFT 值是 2.0+）
    for v in model_data:
        assert v < 2.0  # 老数据 TTFT >= 2.0，不应出现


@pytest.mark.asyncio
async def test_sparkline_data_with_hours_24_includes_recent_success():
    """hours=24 时应包含 5-8 小时前的成功数据"""
    await _seed_profile_and_results()
    summary = await get_sites_summary(user_id=1, hours=24)
    site = summary[0]
    values = site["sparkline_data"].get("claude-opus-4-6", [])
    # 5-8 小时前有 4 条成功数据 (TTFT 1.0-1.3)
    assert len(values) >= 4


@pytest.mark.asyncio
async def test_sparkline_data_max_50_points():
    """sparkline_data 每个 model 最多 50 个采样点"""
    await upsert_profile(
        user_id=1, name="BusySite", base_url="https://api.busy.com",
        api_key="sk-test", model="gpt-4o", provider="openai",
    )
    # 插入 200 条成功结果
    for i in range(200):
        await save_result(
            user_id=1,
            test_id=f"busy-{i}",
            filename=f"busy_{i}.json",
            timestamp=_make_timestamp(hours_ago=i * 0.5),
            config_json=_config_json(base_url="https://api.busy.com", model="gpt-4o", profile_name="BusySite"),
            summary_json=_summary_json(),
            percentiles_json=_percentiles_json(ttft_p50=1.0 + i * 0.01),
        )
    summary = await get_sites_summary(user_id=1, hours=168)
    site = [s for s in summary if s["profile"]["name"] == "BusySite"][0]
    values = site["sparkline_data"].get("gpt-4o", [])
    assert len(values) <= 50


@pytest.mark.asyncio
async def test_sparkline_data_multi_model():
    """同一个 profile 下多个 model 的 sparkline_data 分别正确"""
    await upsert_profile(
        user_id=1, name="MultiModel", base_url="https://api.multi.com",
        api_key="sk-test", model="model-a", provider="openai",
    )
    # model-a: 5 条
    for i in range(5):
        await save_result(
            user_id=1, test_id=f"ma-{i}", filename=f"ma_{i}.json",
            timestamp=_make_timestamp(hours_ago=i + 1),
            config_json=_config_json(base_url="https://api.multi.com", model="model-a", profile_name="MultiModel"),
            summary_json=_summary_json(),
            percentiles_json=_percentiles_json(ttft_p50=1.0),
        )
    # model-b: 3 条
    for i in range(3):
        await save_result(
            user_id=1, test_id=f"mb-{i}", filename=f"mb_{i}.json",
            timestamp=_make_timestamp(hours_ago=i + 1),
            config_json=_config_json(base_url="https://api.multi.com", model="model-b", profile_name="MultiModel"),
            summary_json=_summary_json(),
            percentiles_json=_percentiles_json(ttft_p50=2.0),
        )
    summary = await get_sites_summary(user_id=1, hours=24)
    site = [s for s in summary if s["profile"]["name"] == "MultiModel"][0]
    sparkline = site["sparkline_data"]
    assert "model-a" in sparkline
    assert "model-b" in sparkline
    assert len(sparkline["model-a"]) == 5
    assert len(sparkline["model-b"]) == 3


@pytest.mark.asyncio
async def test_latest_results_still_truncated_to_10():
    """sparkline_data 改动不影响 latest_results 仍然截断为 10 条"""
    await _seed_profile_and_results()
    summary = await get_sites_summary(user_id=1, hours=168)
    site = summary[0]
    assert len(site["latest_results"]) <= 10
