"""TDD 测试：多模型 Profile"""

import json
import pytest
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_upsert_profile_with_multiple_models(client):
    """upsert 一个包含多个模型的 profile，读取时应返回列表"""
    headers = await auth_headers(client)

    # 创建多模型 profile
    resp = await client.post("/api/profiles/save", json={
        "name": "test-multi",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"],
        "provider": "anthropic",
    }, headers=headers)
    assert resp.status_code == 200

    # 读取 profiles 列表
    resp = await client.get("/api/profiles", headers=headers)
    assert resp.status_code == 200
    profiles = resp.json()["profiles"]
    assert len(profiles) == 1
    assert profiles[0]["models"] == ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"]
    assert profiles[0]["model"] == "claude-opus-4-6"


@pytest.mark.asyncio
async def test_upsert_profile_single_model_backward_compat(client):
    """旧格式 model 字符串应自动包装为单元素列表"""
    headers = await auth_headers(client)
    resp = await client.post("/api/profiles/save", json={
        "name": "test-single",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "model": "gpt-4o",
        "provider": "openai",
    }, headers=headers)
    assert resp.status_code == 200

    resp = await client.get("/api/profiles", headers=headers)
    profiles = resp.json()["profiles"]
    assert profiles[0]["models"] == ["gpt-4o"]
    assert profiles[0]["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_upsert_profile_empty_models(client):
    """空 models 应返回空列表"""
    headers = await auth_headers(client)
    resp = await client.post("/api/profiles/save", json={
        "name": "test-empty",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": [],
        "provider": "openai",
    }, headers=headers)
    assert resp.status_code == 200

    resp = await client.get("/api/profiles", headers=headers)
    profiles = resp.json()["profiles"]
    assert profiles[0]["models"] == []
    assert profiles[0]["model"] == ""


@pytest.mark.asyncio
async def test_update_profile_models(client):
    """更新 profile 的 models 列表"""
    headers = await auth_headers(client)
    # 创建
    await client.post("/api/profiles/save", json={
        "name": "test-update",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["model-a"],
        "provider": "openai",
    }, headers=headers)
    # 更新
    resp = await client.put("/api/profiles/test-update", json={
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["model-a", "model-b", "model-c"],
        "provider": "openai",
    }, headers=headers)
    assert resp.status_code == 200

    resp = await client.get("/api/profiles", headers=headers)
    profiles = resp.json()["profiles"]
    assert profiles[0]["models"] == ["model-a", "model-b", "model-c"]
