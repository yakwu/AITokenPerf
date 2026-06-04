import json

import pytest

from app.db import (
    create_scheduled_task,
    get_scheduled_task,
    update_scheduled_task,
    save_result,
    get_run_success_rate,
)


@pytest.mark.asyncio
async def test_alert_fields_roundtrip():
    sid = await create_scheduled_task(
        1, "t", [], {}, "interval", "300",
        alert_webhook="https://open.feishu.cn/x", alert_threshold=80, alert_enabled=True,
    )
    row = await get_scheduled_task(sid)
    assert row["alert_webhook"] == "https://open.feishu.cn/x"
    assert row["alert_threshold"] == 80
    assert bool(row["alert_enabled"]) is True
    assert row["alert_state"] == "ok"


@pytest.mark.asyncio
async def test_update_alert_enabled_roundtrip():
    sid = await create_scheduled_task(1, "t3", [], {}, "interval", "300")
    await update_scheduled_task(sid, alert_enabled=True, alert_webhook="https://open.feishu.cn/y")
    row = await get_scheduled_task(sid)
    assert bool(row["alert_enabled"]) is True
    assert row["alert_webhook"] == "https://open.feishu.cn/y"
    await update_scheduled_task(sid, alert_enabled=False)
    row2 = await get_scheduled_task(sid)
    assert bool(row2["alert_enabled"]) is False


@pytest.mark.asyncio
async def test_update_alert_state_persists():
    sid = await create_scheduled_task(1, "t2", [], {}, "interval", "300")
    await update_scheduled_task(sid, alert_state="alerting")
    row = await get_scheduled_task(sid)
    assert row["alert_state"] == "alerting"


@pytest.mark.asyncio
async def test_get_run_success_rate_aggregates():
    for i, (succ, tot) in enumerate([(8, 10), (5, 10)]):
        await save_result(
            user_id=1, test_id=f"t{i}", filename=f"f{i}.json", timestamp="20260604_120000",
            config_json="{}", summary_json=json.dumps({"success_count": succ, "total_requests": tot}),
            percentiles_json="{}", run_id="run-x",
        )
    assert await get_run_success_rate(["run-x"]) == (13, 20)


@pytest.mark.asyncio
async def test_get_run_success_rate_empty():
    assert await get_run_success_rate([]) == (0, 0)
    assert await get_run_success_rate(["nope"]) == (0, 0)
