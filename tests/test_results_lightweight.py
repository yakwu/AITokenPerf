"""TDD 测试：/api/results 轻量模式 — 去掉大字段、传时间范围、children 不嵌套完整数据"""

import json
import pytest

from datetime import datetime, timedelta
from app.db import (
    save_result,
    get_results_aggregated,
    upsert_profile,
    create_scheduled_task,
)
from tests.conftest import auth_headers


# ---- 辅助函数 ----

def _ts(hours_ago: float = 0) -> str:
    dt = datetime.now() - timedelta(hours=hours_ago)
    return dt.strftime("%Y%m%d_%H%M%S")


def _config(base_url="https://api.example.com", model="claude-opus-4-6", profile_name="TestSite"):
    return json.dumps({"base_url": base_url, "model": model, "profile_name": profile_name})


def _summary(success=1, total=1, tps=50.0):
    return json.dumps({
        "success_count": success,
        "total_requests": total,
        "success_rate": (success / total * 100) if total else 0,
        "token_throughput_tps": tps,
        "successful_requests": success,
    })


def _percentiles(ttft=1.0):
    return json.dumps({"TTFT": {"P50": ttft, "P95": ttft * 2}, "TPOT": {"P50": 0.02}})


def _big_error_details(count=50):
    """生成一个大的 error_details_json，模拟真实场景"""
    details = []
    for i in range(count):
        details.append({
            "request_id": f"req-{i:04d}",
            "status_code": 503,
            "error": f"Service Unavailable: upstream connection timeout after 30s for request {i}",
            "duration": 30.0 + i * 0.1,
            "tokens_received": 0,
            "phase": "connection",
            "url": f"https://api.example.com/v1/chat/completions",
        })
    return json.dumps(details)


async def _seed_data(user_id=1):
    """插入测试数据：含大 error_details 的手动测试 + 定时任务组"""
    await upsert_profile(
        user_id=user_id, name="TestSite", base_url="https://api.example.com",
        api_key="sk-test", model="claude-opus-4-6", provider="anthropic",
    )

    # 3 条手动测试（最近 2 小时），带大 error_details
    for i in range(3):
        await save_result(
            user_id=user_id, test_id=f"manual-{i}", filename=f"manual_{i}.json",
            timestamp=_ts(hours_ago=i + 0.5),
            config_json=_config(), summary_json=_summary(),
            percentiles_json=_percentiles(),
            errors_json=json.dumps({"HTTP 503": 10}),
            error_details_json=_big_error_details(50),  # 每条 ~5KB
        )

    # 定时任务：5 条子结果
    task_id = await create_scheduled_task(
        user_id=user_id, name="TestSchedule", profile_ids=["TestSite"],
        configs_json={"model": "claude-opus-4-6"},
        schedule_type="interval", schedule_value="600",
    )
    for i in range(5):
        await save_result(
            user_id=user_id, test_id=f"sched-{i}", filename=f"sched_{i}.json",
            timestamp=_ts(hours_ago=i + 0.5),
            config_json=_config(), summary_json=_summary(),
            percentiles_json=_percentiles(),
            errors_json=json.dumps({"HTTP 500": 5}),
            error_details_json=_big_error_details(30),  # 每条 ~3KB
            scheduled_task_id=task_id,
        )

    # 5 条旧数据（25 小时前），测时间过滤
    for i in range(5):
        await save_result(
            user_id=user_id, test_id=f"old-{i}", filename=f"old_{i}.json",
            timestamp=_ts(hours_ago=25 + i),
            config_json=_config(), summary_json=_summary(),
            percentiles_json=_percentiles(),
            error_details_json=_big_error_details(20),
        )


# ==========================================
# 第一部分: lightweight 模式不返回大字段
# ==========================================

@pytest.mark.asyncio
async def test_lightweight_no_error_details():
    """lightweight=True 时，items 中不应包含 error_details 字段"""
    await _seed_data()
    result = await get_results_aggregated(user_id=1, limit=50, lightweight=True)
    for item in result["items"]:
        assert "error_details" not in item, "lightweight 模式不应返回 error_details"


@pytest.mark.asyncio
async def test_lightweight_no_percentiles():
    """lightweight=True 时，items 中不应包含 percentiles 字段"""
    await _seed_data()
    result = await get_results_aggregated(user_id=1, limit=50, lightweight=True)
    for item in result["items"]:
        assert "percentiles" not in item, "lightweight 模式不应返回 percentiles"


@pytest.mark.asyncio
async def test_lightweight_no_errors():
    """lightweight=True 时，items 中不应包含 errors 字段"""
    await _seed_data()
    result = await get_results_aggregated(user_id=1, limit=50, lightweight=True)
    for item in result["items"]:
        assert "errors" not in item, "lightweight 模式不应返回 errors"


@pytest.mark.asyncio
async def test_lightweight_keeps_essential_fields():
    """lightweight=True 仍应保留 summary、config、timestamp、filename 等必要字段"""
    await _seed_data()
    result = await get_results_aggregated(user_id=1, limit=50, lightweight=True)
    assert len(result["items"]) > 0
    for item in result["items"]:
        assert "summary" in item, "应保留 summary"
        assert "config" in item, "应保留 config"
        assert "timestamp" in item, "应保留 timestamp"
        assert "filename" in item, "应保留 filename"


@pytest.mark.asyncio
async def test_lightweight_children_not_embedded():
    """lightweight=True 时，定时任务聚合结果不应嵌套完整 children，只保留 children_count"""
    await _seed_data()
    result = await get_results_aggregated(user_id=1, limit=50, lightweight=True)
    for item in result["items"]:
        if item.get("scheduled_task_id"):
            assert "children" not in item, "lightweight 不应嵌套 children"
            assert "children_count" in item, "应保留 children_count"
            assert item["children_count"] > 0


# ==========================================
# 第二部分: full 模式（默认）保持兼容
# ==========================================

@pytest.mark.asyncio
async def test_full_mode_has_error_details():
    """默认 (lightweight=False) 应返回 error_details"""
    await _seed_data()
    result = await get_results_aggregated(user_id=1, limit=50)
    manual_items = [i for i in result["items"] if not i.get("scheduled_task_id")]
    assert len(manual_items) > 0
    assert "error_details" in manual_items[0]


@pytest.mark.asyncio
async def test_full_mode_has_children():
    """默认模式下定时任务聚合结果应包含 children"""
    await _seed_data()
    result = await get_results_aggregated(user_id=1, limit=50)
    sched_items = [i for i in result["items"] if i.get("scheduled_task_id")]
    assert len(sched_items) > 0
    assert "children" in sched_items[0]
    assert len(sched_items[0]["children"]) > 0


# ==========================================
# 第三部分: 时间范围过滤
# ==========================================

@pytest.mark.asyncio
async def test_aggregated_with_hours_filters():
    """get_results_aggregated(hours=6) 应排除 25h 前的旧数据"""
    await _seed_data()
    result = await get_results_aggregated(user_id=1, limit=50, hours=6)
    for item in result["items"]:
        # 旧数据的 filename 以 old_ 开头
        fn = item.get("filename", "")
        assert not fn.startswith("old_"), f"hours=6 不应包含旧数据: {fn}"


@pytest.mark.asyncio
async def test_aggregated_without_hours_includes_all():
    """不传 hours 应包含所有数据"""
    await _seed_data()
    result = await get_results_aggregated(user_id=1, limit=50)
    filenames = [i["filename"] for i in result["items"]]
    # 展开 children
    for item in result["items"]:
        for child in item.get("children", []):
            filenames.append(child["filename"])
    has_old = any(fn.startswith("old_") for fn in filenames)
    assert has_old, "无 hours 限制时应包含旧数据"


# ==========================================
# 第四部分: API 端点测试
# ==========================================

@pytest.mark.asyncio
async def test_api_results_supports_fields_param(client):
    """/api/results?fields=summary 应返回轻量数据"""
    headers = await auth_headers(client)

    # 先插入数据
    await save_result(
        user_id=1, test_id="field-test", filename="field_test.json",
        timestamp=_ts(), config_json=_config(),
        summary_json=_summary(), percentiles_json=_percentiles(),
        error_details_json=_big_error_details(10),
    )

    resp = await client.get("/api/results?fields=summary&limit=10", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) > 0, "应有数据"
    for item in data["items"]:
        assert "error_details" not in item, "fields=summary 不应返回 error_details"
        assert "percentiles" not in item, "fields=summary 不应返回 percentiles"
        assert "summary" in item, "应保留 summary"


@pytest.mark.asyncio
async def test_api_results_default_is_full(client):
    """/api/results 默认返回完整数据"""
    headers = await auth_headers(client)

    # 先插入一条有 error_details 的数据
    from app.db import save_result
    # 需要先获取 user_id
    resp = await client.get("/api/auth/me", headers=headers)
    # save_result 使用 user_id=1 (admin)
    await save_result(
        user_id=1, test_id="api-test", filename="api_test.json",
        timestamp=_ts(), config_json=_config(),
        summary_json=_summary(), percentiles_json=_percentiles(),
        error_details_json=_big_error_details(5),
    )

    resp = await client.get("/api/results?limit=10", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    if data["items"]:
        assert "error_details" in data["items"][0]


@pytest.mark.asyncio
async def test_api_results_with_hours(client):
    """/api/results?hours=6 应过滤数据"""
    headers = await auth_headers(client)
    resp = await client.get("/api/results?hours=6&limit=10", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


# ==========================================
# 第五部分: 数据量验证
# ==========================================

@pytest.mark.asyncio
async def test_lightweight_significantly_smaller():
    """lightweight 模式返回的数据序列化后应显著小于 full 模式"""
    await _seed_data()
    full = await get_results_aggregated(user_id=1, limit=50)
    light = await get_results_aggregated(user_id=1, limit=50, lightweight=True)

    full_size = len(json.dumps(full))
    light_size = len(json.dumps(light))

    # lightweight 应至少减少 50% 数据量
    assert light_size < full_size * 0.5, (
        f"lightweight ({light_size}B) 应比 full ({full_size}B) 小至少 50%"
    )
