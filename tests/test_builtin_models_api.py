"""TDD 测试：内置模型 API 端点"""

import json
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_get_vendors(client: AsyncClient):
    """GET /api/pricing/vendors 应返回厂商列表"""
    headers = await auth_headers(client)
    resp = await client.get("/api/pricing/vendors", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "vendors" in data
    ids = [v["id"] for v in data["vendors"]]
    assert "anthropic" in ids
    assert "openai" in ids


@pytest.mark.asyncio
async def test_get_models_returns_builtin(client: AsyncClient):
    """GET /api/pricing/models 应返回内置模型列表"""
    headers = await auth_headers(client)
    resp = await client.get("/api/pricing/models", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert len(data["models"]) > 0
    for m in data["models"]:
        assert "id" in m
        assert "vendor" in m
        assert "enabled" in m


@pytest.mark.asyncio
async def test_get_models_filter_by_vendor(client: AsyncClient):
    """GET /api/pricing/models?vendor=anthropic 应只返回 anthropic 模型"""
    headers = await auth_headers(client)
    resp = await client.get("/api/pricing/models?vendor=anthropic", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    for m in data["models"]:
        assert m["vendor"] == "anthropic"


@pytest.mark.asyncio
async def test_get_models_enabled_only(client: AsyncClient):
    """GET /api/pricing/models?enabled_only=true 应只返回启用的模型"""
    headers = await auth_headers(client)
    resp = await client.get("/api/pricing/models?enabled_only=true", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    for m in data["models"]:
        assert m["enabled"] is True


@pytest.mark.asyncio
async def test_get_models_config(client: AsyncClient):
    """GET /api/pricing/models-config 应返回完整配置"""
    headers = await auth_headers(client)
    resp = await client.get("/api/pricing/models-config", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "vendors" in data
    assert "models" in data


@pytest.mark.asyncio
async def test_put_models_config_add_model(client: AsyncClient):
    """PUT /api/pricing/models-config 应能添加模型"""
    headers = await auth_headers(client)

    resp = await client.get("/api/pricing/models-config", headers=headers)
    config = resp.json()
    original_count = len(config["models"])

    config["models"].append({
        "id": "test-custom-model",
        "vendor": "openai",
        "enabled": True,
        "custom": True,
    })
    resp = await client.put(
        "/api/pricing/models-config",
        json=config,
        headers=headers,
    )
    assert resp.status_code == 200

    resp = await client.get("/api/pricing/models-config", headers=headers)
    data = resp.json()
    ids = [m["id"] for m in data["models"]]
    assert "test-custom-model" in ids
    assert len(data["models"]) == original_count + 1


@pytest.mark.asyncio
async def test_get_library(client: AsyncClient):
    """GET /api/pricing/library 应返回 LiteLLM 全量数据"""
    headers = await auth_headers(client)
    resp = await client.get("/api/pricing/library", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_get_library_with_search(client: AsyncClient):
    """GET /api/pricing/library?search=claude 应过滤模型"""
    headers = await auth_headers(client)
    resp = await client.get("/api/pricing/library?search=claude", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    for m in data["models"]:
        assert "claude" in m["id"].lower()
