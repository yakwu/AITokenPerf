"""测试 /api/runs 状态与 scheduled_task_id 归属"""

import pytest
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_run_status_returns_scheduled_task_id_for_manual_run(client):
    """手动发起的测试，scheduled_task_id 应为 0"""
    headers = await auth_headers(client)

    await client.post("/api/profiles/save", json={
        "name": "manual-site",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "api_key_action": "replace",
        "models": ["gpt-4o-mini"],
        "provider": "openai",
    }, headers=headers)

    resp = await client.post("/api/runs", json={
        "profile_name": "manual-site",
        "models": ["gpt-4o-mini"],
        "mode": "burst",
        "concurrency_levels": [1],
        "max_tokens": 10,
        "timeout": 30,
        "duration": 1,
    }, headers=headers)
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    resp = await client.get(f"/api/runs/{run_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["scheduled_task_id"] == 0
    assert data["tasks"][0]["scheduled_task_id"] == 0


@pytest.mark.asyncio
async def test_run_status_returns_scheduled_task_id_for_scheduled_run(client):
    """定时任务发起的测试，scheduled_task_id 应为定时任务 ID"""
    from app.db import create_scheduled_task
    from app.server import manager
    import uuid

    headers = await auth_headers(client)

    sched_id = await create_scheduled_task(
        user_id=1,
        name="test-sched",
        profile_ids=[],
        configs_json={},
        schedule_type="interval",
        schedule_value="60",
    )

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    manager.create_run(run_id, 1, profile_name="test", source="scheduled",
                       requested_slots=1, scheduled_task_id=sched_id)
    task = manager.create_task("sched-task", 1, profile_name="test",
                               group_id=run_id, run_id=run_id, source="scheduled")
    task.scheduled_task_id = sched_id
    task.status = "running"

    resp = await client.get(f"/api/runs/{run_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["scheduled_task_id"] == sched_id
    assert data["tasks"][0]["scheduled_task_id"] == sched_id


@pytest.mark.asyncio
async def test_run_running_empty(client):
    """空闲状态时 running 列表为空"""
    headers = await auth_headers(client)

    resp = await client.get("/api/runs/running", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["tasks"] == []
