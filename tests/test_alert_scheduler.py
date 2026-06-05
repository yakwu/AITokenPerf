import json

import pytest

from app import notifier, scheduler
from app.db import create_scheduled_task, save_result, get_scheduled_task, update_scheduled_task, create_notifier


async def _seed(rate_pair, alert_state="ok", enabled=True):
    succ, tot = rate_pair
    nid = await create_notifier(1, "g", "https://open.feishu.cn/x")
    sid = await create_scheduled_task(
        1, "t", ["SiteA"], {}, "interval", "300",
        alert_notifier_id=nid, alert_threshold=90, alert_enabled=enabled,
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
async def test_no_alert_when_no_results(monkeypatch):
    # 本轮无有效请求（run_ids 无对应 result 行）→ total==0，跳过评估、不发、不改状态
    sent = []
    async def fake_send(url, payload, timeout=10.0):
        sent.append(payload); return True
    monkeypatch.setattr(notifier, "send_webhook", fake_send)

    nid = await create_notifier(1, "g", "https://open.feishu.cn/x")
    sid = await create_scheduled_task(
        1, "t", ["SiteA"], {}, "interval", "300",
        alert_notifier_id=nid, alert_threshold=90, alert_enabled=True,
    )
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-empty"])
    assert sent == []
    assert (await get_scheduled_task(sid))["alert_state"] == "ok"


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


@pytest.mark.asyncio
async def test_alert_uses_notifier_webhook(monkeypatch):
    sent = {}
    async def fake_send(url, payload, timeout=10.0):
        sent["url"] = url
        return True
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid = await _seed((0, 10))  # 0% < 90% 必触发
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert sent.get("url") == "https://open.feishu.cn/x"


@pytest.mark.asyncio
async def test_alert_skips_when_no_notifier(monkeypatch):
    sent = []
    async def fake_send(url, payload, timeout=10.0):
        sent.append(url)
        return True
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    # alert_enabled 但没选告警器（notifier_id=0）→ 不发
    sid = await create_scheduled_task(1, "tn", ["SiteA"], {}, "interval", "300",
                                      alert_notifier_id=0, alert_threshold=90, alert_enabled=True)
    await save_result(user_id=1, test_id="b", filename="b.json", timestamp="20260604_120000",
                      config_json="{}", summary_json=json.dumps({"success_count": 0, "total_requests": 10}),
                      percentiles_json="{}", run_id="run-2", scheduled_task_id=sid)
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-2"])
    assert sent == []


@pytest.mark.asyncio
async def test_alert_skips_when_notifier_missing(monkeypatch):
    sent = []
    async def fake_send(url, payload, timeout=10.0):
        sent.append(url)
        return True
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    # 指向一个不存在的告警器 id（如被删）→ 安全跳过
    sid = await create_scheduled_task(1, "tm", ["SiteA"], {}, "interval", "300",
                                      alert_notifier_id=999999, alert_threshold=90, alert_enabled=True)
    await save_result(user_id=1, test_id="c", filename="c.json", timestamp="20260604_120000",
                      config_json="{}", summary_json=json.dumps({"success_count": 0, "total_requests": 10}),
                      percentiles_json="{}", run_id="run-3", scheduled_task_id=sid)
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-3"])
    assert sent == []
