import pytest
from tests.conftest import auth_headers
from app.db import get_scheduled_task
from app import notifier


async def _make_profile(client, headers):
    await client.post("/api/profiles/save", json={
        "name": "s", "base_url": "https://api.example.com", "api_key": "sk-x",
        "api_key_action": "replace", "models": ["gpt-4o-mini"], "provider": "openai",
    }, headers=headers)


async def _make_notifier(client, headers, name="g", webhook="https://open.feishu.cn/hook/x"):
    resp = await client.post("/api/notifiers",
                             json={"name": name, "webhook": webhook}, headers=headers)
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_schedule_with_notifier(client):
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    nid = await _make_notifier(client, headers)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "schedule_value": "300",
        "alert_enabled": True, "alert_notifier_id": nid, "alert_threshold": 88,
    }, headers=headers)
    assert resp.status_code == 200
    sid = resp.json()["id"]
    row = await get_scheduled_task(sid)
    assert row["alert_notifier_id"] == nid and row["alert_threshold"] == 88


@pytest.mark.asyncio
async def test_create_schedule_rejects_foreign_notifier(client):
    from tests.conftest import login_and_get_token
    headers_a = await auth_headers(client)
    nid_a = await _make_notifier(client, headers_a)
    await client.post("/api/auth/register", json={
        "email": "b2@example.com", "password": "pw12345678", "display_name": "B2",
    })
    token_b = await login_and_get_token(client, "b2@example.com", "pw12345678")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    await _make_profile(client, headers_b)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "schedule_value": "300",
        "alert_enabled": True, "alert_notifier_id": nid_a,
    }, headers=headers_b)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_schedule_rejects_bad_threshold(client):
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "alert_threshold": 250,
    }, headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_schedule_accepts_minute_mode(client):
    """前端默认 alert_rules.mode='minute'，后端必须放行（否则用默认值就报错）。"""
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    nid = await _make_notifier(client, headers)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "schedule_value": "300",
        "alert_enabled": True, "alert_notifier_id": nid, "alert_threshold": 90,
        "alert_rules": {"mode": "minute", "value": 30, "fail_consecutive": 2,
                        "fail_in_window": 3, "recover_consecutive": 2},
    }, headers=headers)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_create_schedule_rejects_bad_mode(client):
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"],
        "alert_rules": {"mode": "weekly", "value": 1},
    }, headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_notifier_crud_api(client):
    headers = await auth_headers(client)
    r = await client.post("/api/notifiers",
                          json={"name": "群A", "webhook": "https://open.feishu.cn/hook/aaa"},
                          headers=headers)
    assert r.status_code == 200
    nid = r.json()["id"]
    items = (await client.get("/api/notifiers", headers=headers)).json()
    assert len(items) == 1
    assert items[0]["webhook"] != "https://open.feishu.cn/hook/aaa"
    assert "open.feishu.cn" in items[0]["webhook"]
    r2 = await client.put(f"/api/notifiers/{nid}", json={"name": "群A改"}, headers=headers)
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_notifier_create_rejects_bad_webhook(client):
    headers = await auth_headers(client)
    r = await client.post("/api/notifiers",
                          json={"name": "x", "webhook": "http://evil.com/h"},
                          headers=headers)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_notifier_create_rejects_duplicate_name(client):
    headers = await auth_headers(client)
    await client.post("/api/notifiers", json={"name": "dup", "webhook": "https://open.feishu.cn/hook/d1"}, headers=headers)
    r = await client.post("/api/notifiers", json={"name": "dup", "webhook": "https://open.feishu.cn/hook/d2"}, headers=headers)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_notifier_delete_guard(client):
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    nid = await _make_notifier(client, headers)
    await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "schedule_value": "300",
        "alert_enabled": True, "alert_notifier_id": nid,
    }, headers=headers)
    r = await client.delete(f"/api/notifiers/{nid}", headers=headers)
    assert r.status_code == 409
    assert r.json()["refs"] == 1


@pytest.mark.asyncio
async def test_notifier_test_endpoint(client, monkeypatch):
    sent = {}

    async def fake_send(url, payload, timeout=10.0):
        sent["url"] = url
        return True

    monkeypatch.setattr(notifier, "send_webhook", fake_send)
    headers = await auth_headers(client)
    nid = await _make_notifier(client, headers)
    r = await client.post(f"/api/notifiers/{nid}/test", headers=headers)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert sent["url"].startswith("https://open.feishu.cn")


@pytest.mark.asyncio
async def test_notifier_rejects_other_user(client):
    from tests.conftest import login_and_get_token
    headers_a = await auth_headers(client)
    nid = await _make_notifier(client, headers_a)
    await client.post("/api/auth/register", json={
        "email": "b3@example.com", "password": "pw12345678", "display_name": "B3",
    })
    token_b = await login_and_get_token(client, "b3@example.com", "pw12345678")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    r = await client.delete(f"/api/notifiers/{nid}", headers=headers_b)
    assert r.status_code == 404
    r_put = await client.put(f"/api/notifiers/{nid}", json={"name": "x"}, headers=headers_b)
    assert r_put.status_code == 404
    r_test = await client.post(f"/api/notifiers/{nid}/test", headers=headers_b)
    assert r_test.status_code == 404


def test_aggregate_active_alerts_merges_by_cell():
    from app.notifier import aggregate_active_alerts
    tasks = [
        {"id": 1, "name": "任务A", "profile_ids": ["siteX"],
         "alert_state": '{"siteX": {"gpt-4": {"s": "alerting", "n": 2}, "gpt-3.5": {"s": "ok", "n": 0}}}'},
        {"id": 2, "name": "任务B", "profile_ids": ["siteX"],
         "alert_state": '{"siteX": {"gpt-4": {"s": "alerting", "n": 3}}}'},
        {"id": 3, "name": "任务C", "profile_ids": ["siteY"],
         "alert_state": '{"siteY": {"claude": {"s": "ok", "n": 0}}}'},
    ]
    out = aggregate_active_alerts(tasks)
    assert len(out) == 1
    cell = out[0]
    assert cell["profile"] == "siteX" and cell["model"] == "gpt-4"
    assert cell["fail_count"] == 3
    assert cell["task_count"] == 2
    assert {t["id"] for t in cell["tasks"]} == {1, 2}


def test_aggregate_active_alerts_filters_deleted_profiles():
    """valid_profiles 传入时，已删除站点遗留的告警格不再返回（自愈残留卡）。"""
    from app.notifier import aggregate_active_alerts
    tasks = [
        {"id": 1, "name": "任务A", "profile_ids": ["siteX"],
         "alert_state": '{"siteX": {"gpt-4": {"s": "alerting", "n": 2}},'
                        ' "deletedSite": {"gpt-4": {"s": "alerting", "n": 5}}}'},
    ]
    # 不传 valid_profiles：保持原行为，两个站点都返回
    assert len(aggregate_active_alerts(tasks)) == 2
    # 传入仅含 siteX：deletedSite 被过滤
    out = aggregate_active_alerts(tasks, valid_profiles={"siteX"})
    assert len(out) == 1 and out[0]["profile"] == "siteX"


def test_aggregate_active_alerts_handles_empty_and_legacy():
    from app.notifier import aggregate_active_alerts
    tasks = [
        {"id": 1, "name": "x", "profile_ids": ["s"], "alert_state": None},
        {"id": 2, "name": "y", "profile_ids": ["s"], "alert_state": '"ok"'},
        {"id": 3, "name": "z", "profile_ids": ["s"], "alert_state": '{"s": {"m": "alerting"}}'},
    ]
    out = aggregate_active_alerts(tasks)
    assert len(out) == 1 and out[0]["fail_count"] == 0


@pytest.mark.asyncio
async def test_active_alerts_endpoint(client):
    from app.db import update_scheduled_task
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    nid = await _make_notifier(client, headers)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "schedule_value": "300",
        "alert_enabled": True, "alert_notifier_id": nid, "alert_threshold": 90,
    }, headers=headers)
    sid = resp.json()["id"]
    await update_scheduled_task(sid, alert_state='{"s": {"gpt-4o-mini": {"s": "alerting", "n": 2}}}')

    r = await client.get("/api/alerts/active", headers=headers)
    assert r.status_code == 200
    alerts = r.json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["profile"] == "s" and alerts[0]["model"] == "gpt-4o-mini"
    assert alerts[0]["fail_count"] == 2
    assert alerts[0]["task_count"] == 1


@pytest.mark.asyncio
async def test_ack_unack_marks_alert_acked(client):
    """ack → active 该条 acked=true（仍在列表里，前端据此归入已忽略）；unack → false。"""
    from app.db import update_scheduled_task
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    nid = await _make_notifier(client, headers)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "schedule_value": "300",
        "alert_enabled": True, "alert_notifier_id": nid, "alert_threshold": 90,
    }, headers=headers)
    sid = resp.json()["id"]
    await update_scheduled_task(sid, alert_state='{"s": {"gpt-4o-mini": {"s": "alerting", "n": 2}}}')

    # 初始未忽略
    alerts = (await client.get("/api/alerts/active", headers=headers)).json()["alerts"]
    assert len(alerts) == 1 and alerts[0]["acked"] is False

    # 忽略 → acked=true（仍在列表）
    r = await client.post("/api/alerts/ack", json={"profile": "s", "model": "gpt-4o-mini"}, headers=headers)
    assert r.status_code == 200
    alerts = (await client.get("/api/alerts/active", headers=headers)).json()["alerts"]
    assert len(alerts) == 1 and alerts[0]["acked"] is True

    # 取消忽略 → acked=false
    r = await client.post("/api/alerts/unack", json={"profile": "s", "model": "gpt-4o-mini"}, headers=headers)
    assert r.status_code == 200
    alerts = (await client.get("/api/alerts/active", headers=headers)).json()["alerts"]
    assert len(alerts) == 1 and alerts[0]["acked"] is False


@pytest.mark.asyncio
async def test_ack_rejects_empty_profile(client):
    headers = await auth_headers(client)
    r = await client.post("/api/alerts/ack", json={"model": "gpt-4o-mini"}, headers=headers)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_ack_idempotent(client):
    """重复忽略同一格幂等，不报错。"""
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    for _ in range(2):
        r = await client.post("/api/alerts/ack", json={"profile": "s", "model": "m"}, headers=headers)
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_active_alerts_empty_when_none(client):
    headers = await auth_headers(client)
    r = await client.get("/api/alerts/active", headers=headers)
    assert r.status_code == 200 and r.json()["alerts"] == []


@pytest.mark.asyncio
async def test_active_alerts_clears_after_profile_deleted(client):
    """删除站点后，其遗留告警卡应从 /api/alerts/active 消失（自愈残留卡）。"""
    from app.db import update_scheduled_task
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    nid = await _make_notifier(client, headers)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "schedule_value": "300",
        "alert_enabled": True, "alert_notifier_id": nid, "alert_threshold": 90,
    }, headers=headers)
    sid = resp.json()["id"]
    await update_scheduled_task(sid, alert_state='{"s": {"gpt-4o-mini": {"s": "alerting", "n": 2}}}')

    # 删除前：有一张告警卡
    r = await client.get("/api/alerts/active", headers=headers)
    assert len(r.json()["alerts"]) == 1

    # 删除站点
    await client.delete("/api/profiles/s", headers=headers)

    # 删除后：告警卡消失（valid_profiles 过滤 + delete_profile 已清 alert_state）
    r = await client.get("/api/alerts/active", headers=headers)
    assert r.json()["alerts"] == []

    # alert_state 里该站点 key 也已被清掉
    task = await get_scheduled_task(sid)
    import json as _json
    assert "s" not in _json.loads(task["alert_state"])
