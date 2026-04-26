"""Run Center 安全与准入控制测试"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_run_uses_requested_profile_secret_not_active_profile(client):
    """非 active 站点测试必须使用该站点自己的密钥。"""
    headers = await auth_headers(client)

    await client.post("/api/profiles/save", json={
        "name": "site-a",
        "base_url": "https://a.example.com",
        "api_key": "sk-a",
        "api_key_action": "replace",
        "models": ["model-a"],
        "provider": "openai",
    }, headers=headers)
    await client.post("/api/profiles/save", json={
        "name": "site-b",
        "base_url": "https://b.example.com",
        "api_key": "sk-b",
        "api_key_action": "replace",
        "models": ["model-b"],
        "provider": "openai",
    }, headers=headers)
    await client.post("/api/profiles/switch", json={"name": "site-a"}, headers=headers)

    with patch("app.server._run_benchmark_task", new_callable=AsyncMock) as mock_run:
        resp = await client.post("/api/runs", json={
            "profile_name": "site-b",
            "models": ["model-b"],
            "concurrency_levels": [1],
        }, headers=headers)
        assert resp.status_code == 200
        await asyncio.sleep(0)

    cfg = mock_run.call_args.args[0]
    assert cfg["profile_name"] == "site-b"
    assert cfg["base_url"] == "https://b.example.com"
    assert cfg["api_key"] == "sk-b"
    assert cfg["model"] == "model-b"


@pytest.mark.asyncio
async def test_run_capacity_rejects_whole_multi_model_run(client, monkeypatch):
    """容量不足时整个 Run 返回 429，不启动部分模型。"""
    import app.server as server

    headers = await auth_headers(client)
    monkeypatch.setattr(server, "RUN_MAX_USER_SLOTS", 3)
    monkeypatch.setattr(server, "RUN_MAX_GLOBAL_SLOTS", 100)

    await client.post("/api/profiles/save", json={
        "name": "capacity-site",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "api_key_action": "replace",
        "models": ["model-a", "model-b"],
        "provider": "openai",
    }, headers=headers)

    with patch("app.server._run_benchmark_task", new_callable=AsyncMock) as mock_run:
        resp = await client.post("/api/runs", json={
            "profile_name": "capacity-site",
            "models": ["model-a", "model-b"],
            "concurrency_levels": [2],
        }, headers=headers)

    assert resp.status_code == 429
    data = resp.json()
    assert data["requested_slots"] == 4
    assert data["available_slots"] == 3
    assert mock_run.call_count == 0


@pytest.mark.asyncio
async def test_run_status_rejects_other_owner(client):
    """用户不能读取其他用户的 run 状态。"""
    headers = await auth_headers(client)
    await client.post("/api/profiles/save", json={
        "name": "owner-site",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "api_key_action": "replace",
        "models": ["model-a"],
        "provider": "openai",
    }, headers=headers)
    with patch("app.server._run_benchmark_task", new_callable=AsyncMock):
        resp = await client.post("/api/runs", json={
            "profile_name": "owner-site",
            "models": ["model-a"],
            "concurrency_levels": [1],
        }, headers=headers)
    run_id = resp.json()["run_id"]

    reg = await client.post("/api/auth/register", json={
        "email": "other@example.com",
        "password": "secret123",
    })
    other_headers = {"Authorization": f"Bearer {reg.json()['token']}"}

    resp = await client.get(f"/api/runs/{run_id}", headers=other_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_role_demotion_takes_effect_immediately(client):
    """管理员降权后，旧 token 不能继续访问 admin API。"""
    headers = await auth_headers(client)

    await client.post("/api/auth/register", json={
        "email": "ops@example.com",
        "password": "secret123",
    })
    users = (await client.get("/api/admin/users", headers=headers)).json()["users"]
    ops = next(u for u in users if u["email"] == "ops@example.com")

    await client.put(f"/api/admin/users/{ops['id']}/role", json={"role": "admin"}, headers=headers)
    login = await client.post("/api/auth/login", json={"email": "ops@example.com", "password": "secret123"})
    ops_headers = {"Authorization": f"Bearer {login.json()['token']}"}
    assert (await client.get("/api/admin/users", headers=ops_headers)).status_code == 200

    await client.put(f"/api/admin/users/{ops['id']}/role", json={"role": "user"}, headers=headers)
    assert (await client.get("/api/admin/users", headers=ops_headers)).status_code == 403
