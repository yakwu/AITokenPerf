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
