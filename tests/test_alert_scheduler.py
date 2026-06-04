import json

import pytest

from app import notifier, scheduler
from app.db import create_scheduled_task, save_result, get_scheduled_task, update_scheduled_task


async def _seed(rate_pair, alert_state="ok", enabled=True):
    succ, tot = rate_pair
    sid = await create_scheduled_task(
        1, "t", ["SiteA"], {}, "interval", "300",
        alert_webhook="https://open.feishu.cn/x", alert_threshold=90, alert_enabled=enabled,
    )
    if alert_state != "ok":
        await update_scheduled_task(sid, alert_state=alert_state)
    await save_result(
        user_id=1, test_id="a", filename="a.json", timestamp="20260604_120000",
        config_json="{}", summary_json=json.dumps({"success_count": succ, "total_requests": tot}),
        percentiles_json="{}", run_id="run-1", scheduled_task_id=sid,
    )
    return sid


@pytest.mark.asyncio
async def test_alert_fires_and_writes_state(monkeypatch):
    sent = []
    async def fake_send(url, payload, timeout=10.0):
        sent.append(payload); return True
    monkeypatch.setattr(notifier, "send_webhook", fake_send)

    sid = await _seed((5, 10))  # 50% < 90%
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])

    assert len(sent) == 1
    assert (await get_scheduled_task(sid))["alert_state"] == "alerting"


@pytest.mark.asyncio
async def test_no_alert_when_disabled(monkeypatch):
    sent = []
    async def fake_send(url, payload, timeout=10.0):
        sent.append(payload); return True
    monkeypatch.setattr(notifier, "send_webhook", fake_send)

    sid = await _seed((5, 10), enabled=False)
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert sent == []


@pytest.mark.asyncio
async def test_recover_when_back_to_normal(monkeypatch):
    sent = []
    async def fake_send(url, payload, timeout=10.0):
        sent.append(payload); return True
    monkeypatch.setattr(notifier, "send_webhook", fake_send)

    sid = await _seed((10, 10), alert_state="alerting")  # 100% >= 90%, 之前告警中
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert len(sent) == 1
    assert (await get_scheduled_task(sid))["alert_state"] == "ok"
