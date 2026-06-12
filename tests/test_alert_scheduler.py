import json

import pytest

from app import notifier, scheduler
from app.db import (
    create_scheduled_task, save_result, get_scheduled_task,
    update_scheduled_task, create_notifier,
)


async def _seed_task(cells, alert_state=None, enabled=True, notifier_id=None):
    """cells: [(profile, model, succ, tot)] 落 result 行（run-1）+ 建任务。
    alert_state: dict 或 None（None=保持默认）。notifier_id: None=新建有效告警器。"""
    if notifier_id is None:
        notifier_id = await create_notifier(1, "g", "https://open.feishu.cn/x")
    sid = await create_scheduled_task(
        1, "t", ["SiteA"], {}, "interval", "300",
        alert_notifier_id=notifier_id, alert_threshold=90, alert_enabled=enabled,
    )
    if alert_state is not None:
        await update_scheduled_task(sid, alert_state=json.dumps(alert_state))
    for i, (pf, model, succ, tot) in enumerate(cells):
        await save_result(
            user_id=1, test_id=f"r{i}", filename=f"r{i}.json", timestamp="20260609_120000",
            config_json=json.dumps({"profile_name": pf, "model": model}),
            summary_json=json.dumps({"success_count": succ, "total_requests": tot}),
            percentiles_json="{}", run_id="run-1", scheduled_task_id=sid,
        )
    return sid


def _collector():
    sent = []
    async def fake_send(url, payload, timeout=10.0):
        sent.append(payload)
        return True
    return sent, fake_send


@pytest.mark.asyncio
async def test_per_cell_alert_only_failing_cell(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    # gpt-4o 已累积 1 次（streak=1），本轮再跌破 → 连续 2 次翻红；claude 正常
    sid = await _seed_task(
        [("SiteA", "gpt-4o", 2, 10), ("SiteA", "claude", 10, 10)],
        alert_state={"SiteA": {"gpt-4o": {"s": "ok", "n": 1}}},
    )
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert len(sent) == 1                       # 只发一条红卡
    flat = str(sent[0])
    assert "gpt-4o" in flat and "claude" not in flat
    states = json.loads((await get_scheduled_task(sid))["alert_state"])
    assert states["SiteA"]["gpt-4o"]["s"] == "alerting"
    assert states["SiteA"]["claude"]["s"] == "ok"


@pytest.mark.asyncio
async def test_per_cell_simultaneous_alert_and_recover(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    # prev: gpt-4o 告警中(旧裸字符串，测兼容)、claude 已累积 1 次；
    # 本轮 gpt-4o 恢复(100%)、claude 再跌破(10%) → 连续 2 次翻红
    sid = await _seed_task(
        [("SiteA", "gpt-4o", 10, 10), ("SiteA", "claude", 1, 10)],
        alert_state={"SiteA": {"gpt-4o": "alerting", "claude": {"s": "ok", "n": 1}}},
    )
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert len(sent) == 2
    cards = {c["card"]["header"]["template"]: str(c) for c in sent}
    assert "claude" in cards["red"] and "gpt-4o" not in cards["red"]
    assert "gpt-4o" in cards["green"] and "claude" not in cards["green"]
    states = json.loads((await get_scheduled_task(sid))["alert_state"])
    assert states["SiteA"]["gpt-4o"]["s"] == "ok"
    assert states["SiteA"]["claude"]["s"] == "alerting"


@pytest.mark.asyncio
async def test_no_alert_when_all_ok(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid = await _seed_task([("SiteA", "gpt-4o", 10, 10)])
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert sent == []


@pytest.mark.asyncio
async def test_disabled_no_alert(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid = await _seed_task([("SiteA", "gpt-4o", 0, 10)], enabled=False)
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert sent == []


@pytest.mark.asyncio
async def test_skips_when_notifier_id_zero(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid = await _seed_task([("SiteA", "gpt-4o", 0, 10)], notifier_id=0)
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert sent == []


@pytest.mark.asyncio
async def test_skips_when_notifier_missing(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid = await _seed_task([("SiteA", "gpt-4o", 0, 10)], notifier_id=999999)
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert sent == []


@pytest.mark.asyncio
async def test_no_results_no_alert(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid = await _seed_task([])   # 不造 result 行
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-empty"])
    assert sent == []


@pytest.mark.asyncio
async def test_zero_total_cell_skipped_preserves_state(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    # gpt-4o 本轮 total=0（未发出），claude 正常；prev gpt-4o=alerting → 保留
    sid = await _seed_task(
        [("SiteA", "gpt-4o", 0, 0), ("SiteA", "claude", 10, 10)],
        alert_state={"SiteA": {"gpt-4o": "alerting"}},
    )
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert sent == []                          # 无翻转
    states = json.loads((await get_scheduled_task(sid))["alert_state"])
    assert states["SiteA"]["gpt-4o"]["s"] == "alerting"   # 保留旧态
    assert states["SiteA"]["claude"]["s"] == "ok"


@pytest.mark.asyncio
async def test_single_abnormal_round_does_not_alert(monkeypatch):
    # 第一次跌破：不发卡，仅累积 streak=1（防抖）
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid = await _seed_task([("SiteA", "gpt-4o", 2, 10)])
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert sent == []
    states = json.loads((await get_scheduled_task(sid))["alert_state"])
    assert states["SiteA"]["gpt-4o"] == {"s": "ok", "n": 1}


@pytest.mark.asyncio
async def test_recovery_after_alert_single_good_round(monkeypatch):
    # 已告警，一次回到阈值即报恢复并清零
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid = await _seed_task(
        [("SiteA", "gpt-4o", 10, 10)],
        alert_state={"SiteA": {"gpt-4o": {"s": "alerting", "n": 2}}},
    )
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert len(sent) == 1
    assert sent[0]["card"]["header"]["template"] == "green"
    states = json.loads((await get_scheduled_task(sid))["alert_state"])
    assert states["SiteA"]["gpt-4o"] == {"s": "ok", "n": 0}


@pytest.mark.asyncio
async def test_streak_resets_on_good_round(monkeypatch):
    # 累积中(streak=1)遇到一次正常 → 清零，不告警
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid = await _seed_task(
        [("SiteA", "gpt-4o", 10, 10)],
        alert_state={"SiteA": {"gpt-4o": {"s": "ok", "n": 1}}},
    )
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, ["run-1"])
    assert sent == []
    states = json.loads((await get_scheduled_task(sid))["alert_state"])
    assert states["SiteA"]["gpt-4o"] == {"s": "ok", "n": 0}
