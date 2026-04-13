"""TDD 测试：custom_endpoint 完整 URL 模式"""

import pytest
from tests.conftest import auth_headers

from app.protocols.openai_chat import OpenAIChatAdapter
from app.protocols.anthropic import AnthropicAdapter
from app.protocols.openai_responses import OpenAIResponsesAdapter


# ── 适配器 build_url 测试 ──


class TestOpenAIChatAdapterCustomEndpoint:
    """OpenAI Chat 适配器在 custom_endpoint 开启/关闭时的 URL 构建"""

    def test_default_appends_path(self):
        """默认模式：拼接 /v1/chat/completions"""
        adapter = OpenAIChatAdapter()
        url = adapter.build_url({"base_url": "https://api.openai.com"})
        assert url == "https://api.openai.com/v1/chat/completions"

    def test_custom_endpoint_uses_full_url(self):
        """custom_endpoint=1: 直接使用 base_url，不追加路径"""
        adapter = OpenAIChatAdapter()
        url = adapter.build_url({
            "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            "custom_endpoint": 1,
        })
        assert url == "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    def test_custom_endpoint_strips_trailing_slash(self):
        """custom_endpoint=1 且末尾有斜杠时应去掉"""
        adapter = OpenAIChatAdapter()
        url = adapter.build_url({
            "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions/",
            "custom_endpoint": 1,
        })
        assert url == "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    def test_custom_endpoint_zero_still_appends(self):
        """custom_endpoint=0 时行为与默认一致"""
        adapter = OpenAIChatAdapter()
        url = adapter.build_url({
            "base_url": "https://api.deepseek.com",
            "custom_endpoint": 0,
        })
        assert url == "https://api.deepseek.com/v1/chat/completions"


class TestAnthropicAdapterCustomEndpoint:
    """Anthropic 适配器在 custom_endpoint 开启/关闭时的 URL 构建"""

    def test_default_appends_path(self):
        adapter = AnthropicAdapter()
        url = adapter.build_url({"base_url": "https://api.anthropic.com"})
        assert url == "https://api.anthropic.com/v1/messages"

    def test_custom_endpoint_uses_full_url(self):
        adapter = AnthropicAdapter()
        url = adapter.build_url({
            "base_url": "https://my-proxy.com/anthropic/v1/messages",
            "custom_endpoint": 1,
        })
        assert url == "https://my-proxy.com/anthropic/v1/messages"


class TestOpenAIResponsesAdapterCustomEndpoint:
    """OpenAI Responses 适配器在 custom_endpoint 开启/关闭时的 URL 构建"""

    def test_default_appends_path(self):
        adapter = OpenAIResponsesAdapter()
        url = adapter.build_url({"base_url": "https://api.openai.com"})
        assert url == "https://api.openai.com/v1/responses"

    def test_custom_endpoint_uses_full_url(self):
        adapter = OpenAIResponsesAdapter()
        url = adapter.build_url({
            "base_url": "https://my-proxy.com/openai/v1/responses",
            "custom_endpoint": 1,
        })
        assert url == "https://my-proxy.com/openai/v1/responses"


# ── Profile API 测试 ──


@pytest.mark.asyncio
async def test_save_profile_with_custom_endpoint(client):
    """保存 profile 时传入 custom_endpoint=True，读取时返回 True"""
    headers = await auth_headers(client)

    resp = await client.post("/api/profiles/save", json={
        "name": "zhipu-test",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "api_key": "sk-test",
        "models": ["glm-5.1"],
        "custom_endpoint": True,
    }, headers=headers)
    assert resp.status_code == 200

    resp = await client.get("/api/profiles", headers=headers)
    profiles = resp.json()["profiles"]
    p = next(x for x in profiles if x["name"] == "zhipu-test")
    assert p["custom_endpoint"] is True


@pytest.mark.asyncio
async def test_save_profile_default_custom_endpoint_false(client):
    """不传 custom_endpoint 时，默认为 False"""
    headers = await auth_headers(client)

    resp = await client.post("/api/profiles/save", json={
        "name": "openai-test",
        "base_url": "https://api.openai.com",
        "api_key": "sk-test",
        "models": ["gpt-4o"],
    }, headers=headers)
    assert resp.status_code == 200

    resp = await client.get("/api/profiles", headers=headers)
    profiles = resp.json()["profiles"]
    p = next(x for x in profiles if x["name"] == "openai-test")
    assert p["custom_endpoint"] is False


@pytest.mark.asyncio
async def test_custom_endpoint_propagates_to_bench_config(client):
    """custom_endpoint 字段应能传递到 benchmark config 中"""
    headers = await auth_headers(client)

    # 创建带 custom_endpoint 的 profile
    resp = await client.post("/api/profiles/save", json={
        "name": "zhipu-bench",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "api_key": "sk-test",
        "models": ["glm-5.1"],
        "custom_endpoint": True,
    }, headers=headers)
    assert resp.status_code == 200

    # 激活这个 profile
    resp = await client.post("/api/profiles/switch", json={
        "name": "zhipu-bench",
    }, headers=headers)
    assert resp.status_code == 200
    config = resp.json().get("config", {})
    assert config.get("custom_endpoint") is True
