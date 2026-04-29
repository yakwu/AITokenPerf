"""测试渠道诊断 API 端点"""

import json
import pytest
from unittest.mock import AsyncMock, patch
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_channel_diagnostics_requires_auth(client):
    """未认证请求应返回 401"""
    resp = await client.post("/api/channel-diagnostics", json={
        "profile_name": "test",
        "model": "claude-opus-4-6",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_channel_diagnostics_requires_profile_name(client):
    """缺少 profile_name 应返回 400"""
    headers = await auth_headers(client)
    resp = await client.post("/api/channel-diagnostics", json={
        "model": "claude-opus-4-6",
    }, headers=headers)
    assert resp.status_code == 400
    assert "profile_name" in resp.json()["error"]


@pytest.mark.asyncio
async def test_channel_diagnostics_profile_not_found(client):
    """不存在的 profile 应返回 404"""
    headers = await auth_headers(client)
    resp = await client.post("/api/channel-diagnostics", json={
        "profile_name": "nonexistent",
        "model": "claude-opus-4-6",
    }, headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_channel_diagnostics_success(client):
    """成功运行诊断"""
    headers = await auth_headers(client)

    await client.post("/api/profiles/save", json={
        "name": "diag-test",
        "base_url": "https://api.anthropic.com",
        "api_key": "sk-test-key",
        "api_key_action": "replace",
        "models": ["claude-opus-4-6"],
        "provider": "anthropic",
    }, headers=headers)

    from app.channel_diagnostics import CacheDiagnosticResult, ProbeResult

    mock_result = CacheDiagnosticResult(
        status="passed",
        overall_risk="low",
        confidence=0.85,
        probes=[
            ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=5000, latency_ms=2000),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=4000, cache_creation_tokens=0, latency_ms=800),
        ],
        report={
            "prompt_cache": {"status": "supported", "hit_rate": 0.8, "evidence": "usage_fields"},
            "response_cache": {"status": "not_detected"},
        },
    )

    with patch("app.server.run_cache_diagnostics", new_callable=AsyncMock, return_value=mock_result):
        resp = await client.post("/api/channel-diagnostics", json={
            "profile_name": "diag-test",
            "model": "claude-opus-4-6",
        }, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert "diagnostic_id" in data
    assert data["status"] == "passed"
    assert data["overall_risk"] == "low"
    assert data["cache_hit_rate"] == 0.8


@pytest.mark.asyncio
async def test_get_channel_diagnostic(client):
    """获取诊断详情"""
    headers = await auth_headers(client)

    await client.post("/api/profiles/save", json={
        "name": "diag-test2",
        "base_url": "https://api.anthropic.com",
        "api_key": "sk-test-key",
        "api_key_action": "replace",
        "models": ["claude-opus-4-6"],
        "provider": "anthropic",
    }, headers=headers)

    from app.channel_diagnostics import CacheDiagnosticResult, ProbeResult

    mock_result = CacheDiagnosticResult(
        status="passed", overall_risk="low", confidence=0.85,
        probes=[], report={"prompt_cache": {"status": "supported", "hit_rate": 0.8}},
    )

    with patch("app.server.run_cache_diagnostics", new_callable=AsyncMock, return_value=mock_result):
        resp = await client.post("/api/channel-diagnostics", json={
            "profile_name": "diag-test2",
            "model": "claude-opus-4-6",
        }, headers=headers)

    diag_id = resp.json()["diagnostic_id"]

    resp = await client.get(f"/api/channel-diagnostics/{diag_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == diag_id
    assert data["model"] == "claude-opus-4-6"
    assert data["report_json"]["dimensions"]["cache"]["prompt_cache"]["hit_rate"] == 0.8


@pytest.mark.asyncio
async def test_list_channel_diagnostics_with_filters(client):
    """列表端点支持筛选参数，返回 total/has_more"""
    headers = await auth_headers(client)

    # 创建 profile
    await client.post("/api/profiles/save", json={
        "name": "list-test", "base_url": "https://api.anthropic.com",
        "api_key": "sk-test", "api_key_action": "replace",
        "models": ["m1"], "provider": "anthropic",
    }, headers=headers)

    from app.channel_diagnostics import CacheDiagnosticResult

    mock_result = CacheDiagnosticResult(
        status="passed", overall_risk="low", confidence=0.85,
        probes=[], report={"prompt_cache": {"status": "supported", "hit_rate": 0.8}},
    )

    # 插入 2 条记录
    with patch("app.server.run_cache_diagnostics", new_callable=AsyncMock, return_value=mock_result):
        await client.post("/api/channel-diagnostics", json={"profile_name": "list-test", "model": "m1"}, headers=headers)
        mock_result.status = "warning"
        await client.post("/api/channel-diagnostics", json={"profile_name": "list-test", "model": "m1"}, headers=headers)

    # 无筛选
    resp = await client.get("/api/channel-diagnostics", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["has_more"] is False
    assert len(data["items"]) == 2

    # 按状态筛选
    resp = await client.get("/api/channel-diagnostics?status=warning", headers=headers)
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "warning"

    # 按模型筛选
    resp = await client.get("/api/channel-diagnostics?model=m1", headers=headers)
    data = resp.json()
    assert data["total"] == 2

    # 分页 has_more
    resp = await client.get("/api/channel-diagnostics?limit=1", headers=headers)
    data = resp.json()
    assert data["total"] == 2
    assert data["has_more"] is True
    assert len(data["items"]) == 1
