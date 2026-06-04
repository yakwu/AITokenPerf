import pytest
from tests.conftest import auth_headers
from app.db import get_scheduled_task


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
