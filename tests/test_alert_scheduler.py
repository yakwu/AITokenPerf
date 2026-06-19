import json
from datetime import datetime, timedelta

import pytest

from app import notifier, scheduler
from app.db import (
    create_scheduled_task, save_result, get_scheduled_task,
    update_scheduled_task, create_notifier,
)


def _ts(minutes_ago: int) -> str:
    return (datetime.now() - timedelta(minutes=minutes_ago)).strftime("%Y%m%d_%H%M%S")


async def _seed_task(rounds, alert_state=None, enabled=True, notifier_id=None,
                     alert_rules=None):
    """rounds: [[(profile, model, succ, tot), ...], ...]，旧→新，每个内层 list 是一轮的多格。
    第 i 轮 run_id='run-i'，timestamp 旧→新递增（最后一轮约 5 分钟前，落在默认 1h 窗口内）。
    返回 (sid, [最后一轮 run_id])，后者作为 _maybe_send_alert 的「本轮」run_ids。"""
    if notifier_id is None:
        notifier_id = await create_notifier(1, "g", "https://open.feishu.cn/x")
    sid = await create_scheduled_task(
        1, "t", ["SiteA"], {}, "interval", "300",
        alert_notifier_id=notifier_id, alert_threshold=90, alert_enabled=enabled,
        alert_rules=json.dumps(alert_rules) if alert_rules else "",
    )
    if alert_state is not None:
        await update_scheduled_task(sid, alert_state=json.dumps(alert_state))
    n = len(rounds)
    for ri, cells in enumerate(rounds):
        ts = _ts(minutes_ago=(n - ri) * 5)
        for ci, (pf, model, succ, tot) in enumerate(cells):
            await save_result(
                user_id=1, test_id=f"r{ri}_{ci}", filename=f"r{ri}_{ci}.json", timestamp=ts,
                config_json=json.dumps({"profile_name": pf, "model": model}),
                summary_json=json.dumps({"success_count": succ, "total_requests": tot}),
                percentiles_json="{}", run_id=f"run-{ri}", scheduled_task_id=sid,
            )
    last_run = [f"run-{n - 1}"] if n else ["run-empty"]
    return sid, last_run


def _collector():
    sent = []
    async def fake_send(url, payload, timeout=10.0):
        sent.append(payload)
        return True
    return sent, fake_send


async def _eval(sid, run_ids):
    row = await get_scheduled_task(sid)
    await scheduler._maybe_send_alert(sid, row, run_ids)


# ---- 告警触发：连续 / 累计 ----

@pytest.mark.asyncio
async def test_consecutive_two_fails_alert(monkeypatch):
    """连续 2 个坏轮 → 告警（抓硬故障）。"""
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid, run = await _seed_task([
        [("SiteA", "gpt-4o", 0, 1)],
        [("SiteA", "gpt-4o", 0, 1)],
    ])
    await _eval(sid, run)
    assert len(sent) == 1
    assert sent[0]["card"]["header"]["template"] == "red"
    assert "gpt-4o" in str(sent[0])
    states = json.loads((await get_scheduled_task(sid))["alert_state"])
    assert states["SiteA"]["gpt-4o"]["s"] == "alerting"


@pytest.mark.asyncio
async def test_intermittent_three_in_window_alert(monkeypatch):
    """坏好坏好坏：不连续但窗口内累计 3 个坏轮 → 告警（抓间歇抖动）。"""
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid, run = await _seed_task([
        [("SiteA", "gpt-4o", 0, 1)],
        [("SiteA", "gpt-4o", 1, 1)],
        [("SiteA", "gpt-4o", 0, 1)],
        [("SiteA", "gpt-4o", 1, 1)],
        [("SiteA", "gpt-4o", 0, 1)],
    ])
    await _eval(sid, run)
    assert len(sent) == 1
    assert sent[0]["card"]["header"]["template"] == "red"


@pytest.mark.asyncio
async def test_two_in_window_not_alert(monkeypatch):
    """窗口内仅 2 个坏轮且不连续 → 容忍，不告警（默认累计阈值 3）。"""
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid, run = await _seed_task([
        [("SiteA", "gpt-4o", 0, 1)],
        [("SiteA", "gpt-4o", 1, 1)],
        [("SiteA", "gpt-4o", 0, 1)],
        [("SiteA", "gpt-4o", 1, 1)],
    ])
    await _eval(sid, run)
    assert sent == []


# ---- 冷启动 ----

@pytest.mark.asyncio
async def test_cold_start_single_round_no_alert(monkeypatch):
    """只有 1 轮（样本不足）→ 不评估、不告警。"""
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid, run = await _seed_task([[("SiteA", "gpt-4o", 0, 1)]])
    await _eval(sid, run)
    assert sent == []
    states = json.loads((await get_scheduled_task(sid))["alert_state"])
    assert states["SiteA"]["gpt-4o"]["s"] == "ok"


# ---- 恢复：需连续 N 个好轮 ----

@pytest.mark.asyncio
async def test_recover_needs_two_good(monkeypatch):
    """告警中，末尾连续 2 个好轮 → 恢复。"""
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid, run = await _seed_task(
        [
            [("SiteA", "gpt-4o", 0, 1)],
            [("SiteA", "gpt-4o", 0, 1)],
            [("SiteA", "gpt-4o", 1, 1)],
            [("SiteA", "gpt-4o", 1, 1)],
        ],
        alert_state={"SiteA": {"gpt-4o": "alerting"}},
    )
    await _eval(sid, run)
    assert len(sent) == 1
    assert sent[0]["card"]["header"]["template"] == "green"
    states = json.loads((await get_scheduled_task(sid))["alert_state"])
    assert states["SiteA"]["gpt-4o"]["s"] == "ok"


@pytest.mark.asyncio
async def test_recover_one_good_not_enough(monkeypatch):
    """告警中，末尾仅 1 个好轮 → 保持告警，不发恢复卡。"""
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid, run = await _seed_task(
        [
            [("SiteA", "gpt-4o", 0, 1)],
            [("SiteA", "gpt-4o", 0, 1)],
            [("SiteA", "gpt-4o", 1, 1)],
        ],
        alert_state={"SiteA": {"gpt-4o": "alerting"}},
    )
    await _eval(sid, run)
    assert sent == []
    states = json.loads((await get_scheduled_task(sid))["alert_state"])
    assert states["SiteA"]["gpt-4o"]["s"] == "alerting"


# ---- 多格子：只告警出问题的格子 ----

@pytest.mark.asyncio
async def test_per_cell_alert_only_failing_cell(monkeypatch):
    """gpt-4o 连续 2 坏告警；claude 一直好不告警。"""
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid, run = await _seed_task([
        [("SiteA", "gpt-4o", 0, 1), ("SiteA", "claude", 1, 1)],
        [("SiteA", "gpt-4o", 0, 1), ("SiteA", "claude", 1, 1)],
    ])
    await _eval(sid, run)
    assert len(sent) == 1
    flat = str(sent[0])
    assert "gpt-4o" in flat and "claude" not in flat
    states = json.loads((await get_scheduled_task(sid))["alert_state"])
    assert states["SiteA"]["gpt-4o"]["s"] == "alerting"
    assert states["SiteA"]["claude"]["s"] == "ok"


@pytest.mark.asyncio
async def test_simultaneous_alert_and_recover(monkeypatch):
    """同轮：gpt-4o 恢复(末尾2好)、claude 新告警(连续2坏) → 两张卡。"""
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid, run = await _seed_task(
        [
            [("SiteA", "gpt-4o", 0, 1), ("SiteA", "claude", 1, 1)],
            [("SiteA", "gpt-4o", 1, 1), ("SiteA", "claude", 0, 1)],
            [("SiteA", "gpt-4o", 1, 1), ("SiteA", "claude", 0, 1)],
        ],
        alert_state={"SiteA": {"gpt-4o": "alerting"}},
    )
    await _eval(sid, run)
    assert len(sent) == 2
    cards = {c["card"]["header"]["template"]: str(c) for c in sent}
    assert "claude" in cards["red"] and "gpt-4o" not in cards["red"]
    assert "gpt-4o" in cards["green"] and "claude" not in cards["green"]
    states = json.loads((await get_scheduled_task(sid))["alert_state"])
    assert states["SiteA"]["gpt-4o"]["s"] == "ok"
    assert states["SiteA"]["claude"]["s"] == "alerting"


# ---- 窗口模式：次数 ----

@pytest.mark.asyncio
async def test_count_window_truncates_old_rounds(monkeypatch):
    """count 模式 value=3：老的 2 个坏轮被截断，最近 3 轮只 1 坏 → 不告警。"""
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid, run = await _seed_task(
        [
            [("SiteA", "gpt-4o", 0, 1)],
            [("SiteA", "gpt-4o", 0, 1)],
            [("SiteA", "gpt-4o", 0, 1)],
            [("SiteA", "gpt-4o", 1, 1)],
            [("SiteA", "gpt-4o", 1, 1)],
        ],
        alert_rules={"mode": "count", "value": 3},
    )
    await _eval(sid, run)
    assert sent == []


# ---- 单轮成功率阈值生效（多请求场景）----

@pytest.mark.asyncio
async def test_threshold_marks_bad_round_with_multi_requests(monkeypatch):
    """多请求：单轮成功率 8/10=80% < 90% 阈值 → 连续 2 轮记坏 → 告警。"""
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid, run = await _seed_task([
        [("SiteA", "gpt-4o", 8, 10)],
        [("SiteA", "gpt-4o", 8, 10)],
    ])
    await _eval(sid, run)
    assert len(sent) == 1
    assert sent[0]["card"]["header"]["template"] == "red"


# ---- 全好 / 关闭 / 告警器缺失 ----

@pytest.mark.asyncio
async def test_no_alert_when_all_ok(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid, run = await _seed_task([
        [("SiteA", "gpt-4o", 1, 1)],
        [("SiteA", "gpt-4o", 1, 1)],
    ])
    await _eval(sid, run)
    assert sent == []


@pytest.mark.asyncio
async def test_disabled_no_alert(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid, run = await _seed_task([
        [("SiteA", "gpt-4o", 0, 1)],
        [("SiteA", "gpt-4o", 0, 1)],
    ], enabled=False)
    await _eval(sid, run)
    assert sent == []


@pytest.mark.asyncio
async def test_skips_when_notifier_id_zero(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid, run = await _seed_task([
        [("SiteA", "gpt-4o", 0, 1)],
        [("SiteA", "gpt-4o", 0, 1)],
    ], notifier_id=0)
    await _eval(sid, run)
    assert sent == []


@pytest.mark.asyncio
async def test_skips_when_notifier_missing(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid, run = await _seed_task([
        [("SiteA", "gpt-4o", 0, 1)],
        [("SiteA", "gpt-4o", 0, 1)],
    ], notifier_id=999999)
    await _eval(sid, run)
    assert sent == []


@pytest.mark.asyncio
async def test_no_results_no_alert(monkeypatch):
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid, _ = await _seed_task([])
    await _eval(sid, ["run-empty"])
    assert sent == []


@pytest.mark.asyncio
async def test_zero_total_round_preserves_alerting(monkeypatch):
    """本轮 total=0（未发出请求）且无历史有效轮 → 保留旧 alerting 态、不翻转。"""
    sent, fake_send = _collector()
    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    sid, run = await _seed_task(
        [[("SiteA", "gpt-4o", 0, 0)]],
        alert_state={"SiteA": {"gpt-4o": "alerting"}},
    )
    await _eval(sid, run)
    assert sent == []
    states = json.loads((await get_scheduled_task(sid))["alert_state"])
    assert states["SiteA"]["gpt-4o"]["s"] == "alerting"
