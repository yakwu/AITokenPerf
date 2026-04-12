"""TDD 测试：概览页及多页面优化 — raw 模式 + /api/bench/running 端点"""

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


def _config(base_url="https://api.example.com", model="gpt-4", profile_name="TestSite"):
    return json.dumps({"base_url": base_url, "model": model, "profile_name": profile_name})


def _summary(success=8, total=10, tps=50.0):
    return json.dumps({
        "success_count": success,
        "total_requests": total,
        "success_rate": (success / total * 100) if total else 0,
        "token_throughput_tps": tps,
    })


def _percentiles(ttft=0.5):
    return json.dumps({"TTFT": {"P50": ttft, "P95": ttft * 2}, "TPOT": {"P50": 0.02}})


async def _seed_scheduled_data(user_id=1):
    """插入：3 条手动 + 1 个定时任务含 5 条结果"""
    await upsert_profile(
        user_id=user_id, name="TestSite", base_url="https://api.example.com",
        api_key="sk-test", model="gpt-4", provider="openai",
    )

    # 3 条手动测试
    for i in range(3):
        await save_result(
            user_id=user_id, test_id=f"manual-{i}", filename=f"manual_{i}.json",
            timestamp=_ts(hours_ago=i * 0.5),
            config_json=_config(), summary_json=_summary(),
            percentiles_json=_percentiles(),
        )

    # 定时任务：5 条子结果
    task_id = await create_scheduled_task(
        user_id=user_id, name="ScheduledTest", profile_ids=["TestSite"],
        configs_json={"model": "gpt-4"},
        schedule_type="interval", schedule_value="600",
    )
    for i in range(5):
        await save_result(
            user_id=user_id, test_id=f"sched-{i}", filename=f"sched_{i}.json",
            timestamp=_ts(hours_ago=i * 0.3),
            config_json=_config(), summary_json=_summary(),
            percentiles_json=_percentiles(),
            scheduled_task_id=task_id,
        )

    return task_id


# ==========================================
# 第一部分: raw 模式 — DB 层测试
# ==========================================

@pytest.mark.asyncio
async def test_raw_returns_individual_records():
    """raw=True 时，定时任务的每条结果应独立返回，不聚合"""
    await _seed_scheduled_data()
    result = await get_results_aggregated(user_id=1, limit=50, raw=True)
    # 3 手动 + 5 定时 = 8 条
    assert result["total"] == 8, f"raw 模式应返回 8 条独立记录，实际 {result['total']}"


@pytest.mark.asyncio
async def test_raw_no_children_field():
    """raw=True 时，结果中不应有 children 或 children_count 字段"""
    await _seed_scheduled_data()
    result = await get_results_aggregated(user_id=1, limit=50, raw=True)
    for item in result["items"]:
        assert "children" not in item, f"raw 模式不应有 children: {item.get('filename')}"
        assert "children_count" not in item, f"raw 模式不应有 children_count: {item.get('filename')}"


@pytest.mark.asyncio
async def test_raw_preserves_schedule_name():
    """raw=True 时，定时任务结果仍应保留 schedule_name"""
    await _seed_scheduled_data()
    result = await get_results_aggregated(user_id=1, limit=50, raw=True)
    sched_items = [i for i in result["items"] if i.get("scheduled_task_id")]
    assert len(sched_items) == 5
    for item in sched_items:
        assert item.get("schedule_name") == "ScheduledTest"


@pytest.mark.asyncio
async def test_raw_sorted_by_time_desc():
    """raw=True 时，结果应按时间倒序排列"""
    await _seed_scheduled_data()
    result = await get_results_aggregated(user_id=1, limit=50, raw=True)
    timestamps = [i.get("timestamp", "") for i in result["items"]]
    assert timestamps == sorted(timestamps, reverse=True), "应按时间倒序"


@pytest.mark.asyncio
async def test_raw_with_pagination():
    """raw=True 支持 limit/offset 分页"""
    await _seed_scheduled_data()
    page1 = await get_results_aggregated(user_id=1, limit=3, offset=0, raw=True)
    page2 = await get_results_aggregated(user_id=1, limit=3, offset=3, raw=True)
    assert page1["total"] == 8
    assert len(page1["items"]) == 3
    assert len(page2["items"]) == 3
    # 两页不重复
    fns1 = {i["filename"] for i in page1["items"]}
    fns2 = {i["filename"] for i in page2["items"]}
    assert fns1.isdisjoint(fns2), "分页结果不应重复"


@pytest.mark.asyncio
async def test_raw_with_hours_filter():
    """raw=True 结合 hours 过滤"""
    await _seed_scheduled_data()
    # 插入一条旧数据
    await save_result(
        user_id=1, test_id="old-1", filename="old_1.json",
        timestamp=_ts(hours_ago=48),
        config_json=_config(), summary_json=_summary(),
        percentiles_json=_percentiles(),
    )
    result = await get_results_aggregated(user_id=1, limit=50, hours=6, raw=True)
    filenames = [i["filename"] for i in result["items"]]
    assert "old_1.json" not in filenames, "hours 过滤应排除旧数据"


@pytest.mark.asyncio
async def test_default_still_aggregates():
    """默认 raw=False 仍然聚合定时任务结果"""
    await _seed_scheduled_data()
    result = await get_results_aggregated(user_id=1, limit=50)
    # 3 手动 + 1 聚合 = 4 条
    assert result["total"] == 4, f"默认模式应聚合为 4 条，实际 {result['total']}"


# ==========================================
# 第二部分: raw 模式 — API 端点测试
# ==========================================

@pytest.mark.asyncio
async def test_api_results_raw_param(client):
    """/api/results?raw=true 应返回非聚合数据"""
    headers = await auth_headers(client)
    await _seed_scheduled_data()

    resp = await client.get("/api/results?raw=true&limit=50", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 8, f"API raw 应返回 8 条，实际 {data['total']}"


@pytest.mark.asyncio
async def test_api_results_default_aggregated(client):
    """/api/results 默认仍然聚合"""
    headers = await auth_headers(client)
    await _seed_scheduled_data()

    resp = await client.get("/api/results?limit=50", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4, f"API 默认应聚合为 4 条，实际 {data['total']}"


@pytest.mark.asyncio
async def test_api_results_raw_with_fields_summary(client):
    """/api/results?raw=true&fields=summary 两个参数可组合"""
    headers = await auth_headers(client)
    await _seed_scheduled_data()

    resp = await client.get("/api/results?raw=true&fields=summary&limit=50", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 8
    for item in data["items"]:
        assert "error_details" not in item, "fields=summary 不应返回 error_details"


# ==========================================
# 第三部分: /api/bench/running 端点测试
# ==========================================

@pytest.mark.asyncio
async def test_bench_running_empty(client):
    """/api/bench/running 无执行中任务时返回空列表"""
    headers = await auth_headers(client)
    resp = await client.get("/api/bench/running", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tasks"] == []


@pytest.mark.asyncio
async def test_bench_running_shows_running_tasks(client):
    """/api/bench/running 应返回当前 running 的 BenchTask"""
    headers = await auth_headers(client)

    from app.server import manager
    # 手动创建一个 running task
    task = manager.create_task("test-task-1", owner_id=1, profile_name="TestSite")
    task.status = "running"
    task.model_name = "gpt-4"
    task.done_count = 5
    task.total_count = 20
    task.success_count = 4
    task.failed_count = 1

    resp = await client.get("/api/bench/running", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tasks"]) == 1
    t = data["tasks"][0]
    assert t["task_id"] == "test-task-1"
    assert t["model"] == "gpt-4"
    assert t["profile_name"] == "TestSite"
    assert t["done"] == 5
    assert t["total"] == 20


@pytest.mark.asyncio
async def test_bench_running_excludes_idle_tasks(client):
    """/api/bench/running 不应返回 idle 状态的任务"""
    headers = await auth_headers(client)

    from app.server import manager
    task = manager.create_task("test-idle", owner_id=1, profile_name="TestSite")
    task.status = "idle"

    resp = await client.get("/api/bench/running", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tasks"]) == 0


@pytest.mark.asyncio
async def test_bench_running_only_own_tasks(client):
    """/api/bench/running 只返回当前用户的任务"""
    headers = await auth_headers(client)

    from app.server import manager
    # 创建属于其他用户的 running task
    task = manager.create_task("other-user-task", owner_id=999, profile_name="Other")
    task.status = "running"

    resp = await client.get("/api/bench/running", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tasks"]) == 0, "不应返回其他用户的任务"
