import pytest
from tests.conftest import auth_headers
from app.db import get_scheduled_task
from app import notifier


async def _make_profile(client, headers):
    await client.post("/api/profiles/save", json={
        "name": "s", "base_url": "https://api.example.com", "api_key": "sk-x",
        "api_key_action": "replace", "models": ["gpt-4o-mini"], "provider": "openai",
    }, headers=headers)


@pytest.mark.asyncio
async def test_create_schedule_with_alert(client):
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "schedule_value": "300",
        "alert_enabled": True, "alert_threshold": 85,
        "alert_webhook": "https://open.feishu.cn/x",
    }, headers=headers)
    assert resp.status_code == 200
    sid = resp.json()["id"]
    row = await get_scheduled_task(sid)
    assert row["alert_threshold"] == 85
    assert row["alert_webhook"] == "https://open.feishu.cn/x"


@pytest.mark.asyncio
async def test_create_schedule_rejects_bad_webhook(client):
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "alert_webhook": "https://evil.com/x",
    }, headers=headers)
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
async def test_alert_test_endpoint(client, monkeypatch):
    sent = []

    async def fake_send(url, payload, timeout=10.0):
        sent.append(url)
        return True

    monkeypatch.setattr(notifier, "send_webhook", fake_send)

    headers = await auth_headers(client)
    await _make_profile(client, headers)
    resp = await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "alert_enabled": True,
        "alert_webhook": "https://open.feishu.cn/x",
    }, headers=headers)
    sid = resp.json()["id"]

    r = await client.post(f"/api/schedules/{sid}/alert-test", headers=headers)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_alert_test_rejects_other_user(client):
    from tests.conftest import login_and_get_token
    headers_a = await auth_headers(client)
    await _make_profile(client, headers_a)
    sid = (await client.post("/api/schedules", json={
        "name": "t", "profile_ids": ["s"], "alert_enabled": True,
        "alert_webhook": "https://open.feishu.cn/x",
    }, headers=headers_a)).json()["id"]

    await client.post("/api/auth/register", json={
        "email": "other@example.com", "password": "AITokenPerf#123", "display_name": "B",
    })
    token_b = await login_and_get_token(client, "other@example.com", "AITokenPerf#123")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    r = await client.post(f"/api/schedules/{sid}/alert-test", headers=headers_b)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_alert_test_requires_webhook(client):
    headers = await auth_headers(client)
    await _make_profile(client, headers)
    resp = await client.post("/api/schedules", json={"name": "t", "profile_ids": ["s"]}, headers=headers)
    sid = resp.json()["id"]
    r = await client.post(f"/api/schedules/{sid}/alert-test", headers=headers)
    assert r.status_code == 400
