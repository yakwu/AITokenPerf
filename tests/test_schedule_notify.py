"""测试定时任务结果查询接口，为前端轮询通知提供数据支持"""

import json
from datetime import datetime, timezone

import pytest
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_get_schedule_results_returns_latest_first(client):
    """getScheduleResults 默认返回最新结果在前"""
    from app.db import create_scheduled_task, save_result

    headers = await auth_headers(client)

    # 创建定时任务
    sched_id = await create_scheduled_task(
        user_id=1,
        name="notify-test",
        profile_ids=[],
        configs_json={},
        schedule_type="interval",
        schedule_value="1h",
    )

    # 保存两个结果
    for i in range(2):
        await save_result(
            user_id=1,
            test_id=f"test_sched_{i}",
            filename=f"sched_{sched_id}_result_{i}.json",
            timestamp=datetime.now(timezone.utc).isoformat(),
            config_json=json.dumps({"model": "test-model"}),
            summary_json=json.dumps({"success_rate": 99.0}),
            percentiles_json=json.dumps({}),
            scheduled_task_id=sched_id,
        )

    # 查询结果，limit=1 应返回最新的
    resp = await client.get(
        f"/api/schedules/{sched_id}/results?limit=1",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert len(data["results"]) == 1
