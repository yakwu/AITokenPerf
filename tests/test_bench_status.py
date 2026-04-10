"""测试 /api/bench/status 返回 scheduled_task_id"""

import pytest
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_bench_status_returns_scheduled_task_id_for_manual_task(client):
    """手动发起的测试，scheduled_task_id 应为 0"""
    headers = await auth_headers(client)

    # 手动启动一个 benchmark
    resp = await client.post("/api/bench/start", json={
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test",
        "model": "gpt-4o-mini",
        "mode": "burst",
        "concurrency_levels": [1],
        "max_tokens": 10,
        "timeout": 30,
        "duration": 1,
    }, headers=headers)
    assert resp.status_code == 200

    # 查询状态
    resp = await client.get("/api/bench/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["scheduled_task_id"] == 0


@pytest.mark.asyncio
async def test_bench_status_returns_scheduled_task_id_for_scheduled_task(client):
    """定时任务发起的测试，scheduled_task_id 应为定时任务 ID"""
    from app.db import create_scheduled_task
    from app.server import manager
    import uuid

    headers = await auth_headers(client)

    # 创建定时任务
    sched_id = await create_scheduled_task(
        user_id=1,
        name="test-sched",
        profile_ids=[],
        configs_json={},
        schedule_type="interval",
        schedule_value="1h",
    )

    # 手动模拟一个定时任务创建的 bench task
    tid = uuid.uuid4().hex[:12]
    task = manager.create_task(tid, 1, profile_name="test", group_id=f"sched_{tid}")
    task.scheduled_task_id = sched_id
    task.status = "running"

    # 查询状态
    resp = await client.get("/api/bench/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["scheduled_task_id"] == sched_id


@pytest.mark.asyncio
async def test_bench_status_idle_returns_zero_scheduled_task_id(client):
    """空闲状态时 scheduled_task_id 应为 0"""
    headers = await auth_headers(client)

    resp = await client.get("/api/bench/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "idle"
    assert data["scheduled_task_id"] == 0
