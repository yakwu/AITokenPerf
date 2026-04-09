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


@pytest.mark.asyncio
async def test_profile_api_returns_models_field(client):
    """Profile API 返回应包含 models 数组和 model 兼容字段"""
    headers = await auth_headers(client)
    await client.post("/api/profiles/save", json={
        "name": "api-test",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["gpt-4o", "gpt-4o-mini"],
        "provider": "openai",
    }, headers=headers)

    resp = await client.get("/api/profiles", headers=headers)
    p = resp.json()["profiles"][0]
    assert "models" in p
    assert p["models"] == ["gpt-4o", "gpt-4o-mini"]
    assert p["model"] == "gpt-4o"  # 向后兼容


@pytest.mark.asyncio
async def test_switch_profile_returns_models(client):
    """切换 profile 返回的 config 应包含 models"""
    headers = await auth_headers(client)
    await client.post("/api/profiles/save", json={
        "name": "switch-test",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["claude-opus-4-6", "claude-sonnet-4-6"],
        "provider": "anthropic",
    }, headers=headers)

    resp = await client.post("/api/profiles/switch", json={"name": "switch-test"}, headers=headers)
    assert resp.status_code == 200
    config = resp.json()["config"]
    assert config.get("models") == ["claude-opus-4-6", "claude-sonnet-4-6"]


@pytest.mark.asyncio
async def test_start_bench_expands_multi_model(client):
    """多模型 Profile 启动 bench 应为每个模型创建独立 task"""
    headers = await auth_headers(client)

    # 创建多模型 profile
    await client.post("/api/profiles/save", json={
        "name": "bench-multi",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["model-a", "model-b"],
        "provider": "openai",
    }, headers=headers)

    resp = await client.post("/api/bench/start", json={
        "concurrency_levels": [1],
        "max_tokens": 16,
        "duration": 1,
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert len(data["task_ids"]) == 2  # 应创建 2 个 task

    # 停止所有任务
    await client.post("/api/bench/stop", headers=headers)


@pytest.mark.asyncio
async def test_start_bench_single_model_still_works(client):
    """单模型 Profile 启动 bench 应只创建 1 个 task（向后兼容）"""
    headers = await auth_headers(client)

    await client.post("/api/profiles/save", json={
        "name": "bench-single",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["model-a"],
        "provider": "openai",
    }, headers=headers)

    resp = await client.post("/api/bench/start", json={
        "concurrency_levels": [1],
        "max_tokens": 16,
        "duration": 1,
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert "task_id" in data  # 单模型保持原有返回格式
    assert "task_ids" not in data

    await client.post("/api/bench/stop", headers=headers)


@pytest.mark.asyncio
async def test_scheduled_task_expands_multi_model(client):
    """定时任务对多模型 Profile 应为每个模型创建子任务"""
    from app.db import create_scheduled_task
    from app.scheduler import _run_scheduled_task
    from unittest.mock import patch, AsyncMock

    headers = await auth_headers(client)

    # 创建多模型 profile
    await client.post("/api/profiles/save", json={
        "name": "sched-multi",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["model-a", "model-b", "model-c"],
        "provider": "openai",
    }, headers=headers)

    # 创建定时任务
    task_id = await create_scheduled_task(
        user_id=1,
        name="test-schedule",
        profile_ids=["sched-multi"],
        configs_json={},
        schedule_type="interval",
        schedule_value="1h",
    )

    # mock _run_benchmark_task 避免实际发送请求
    with patch("app.server._run_benchmark_task", new_callable=AsyncMock) as mock_run:
        await _run_scheduled_task(task_id)

    # 验证 _run_benchmark_task 被调用了 3 次（每个模型一次）
    assert mock_run.call_count == 3

    # 验证每次调用的 config 中 model 不同
    models_called = [call.args[0]["model"] for call in mock_run.call_args_list]
    assert sorted(models_called) == ["model-a", "model-b", "model-c"]


@pytest.mark.asyncio
async def test_multi_model_bench_uses_profile_models(client):
    """start-multi-model 未传 models 时应回退到 Profile 的 models"""
    headers = await auth_headers(client)

    await client.post("/api/profiles/save", json={
        "name": "fallback-test",
        "base_url": "https://api.example.com",
        "api_key": "sk-test",
        "models": ["model-x", "model-y"],
        "provider": "openai",
    }, headers=headers)

    # 不传 models，应该使用 profile 的 models
    resp = await client.post("/api/bench/start-multi-model", json={
        "provider": "openai",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["task_ids"]) == 2

    # 停止
    await client.post("/api/bench/stop", headers=headers)
