"""测试 Anthropic 适配器是否正确捕获缓存 usage 字段"""

import json
import pytest

from app.client import RequestMetrics


def test_request_metrics_has_cache_fields():
    """RequestMetrics 应包含缓存相关字段"""
    m = RequestMetrics(request_id=1)
    assert hasattr(m, 'cache_read_tokens')
    assert hasattr(m, 'cache_creation_tokens')
    assert m.cache_read_tokens == 0
    assert m.cache_creation_tokens == 0


@pytest.mark.asyncio
async def test_anthropic_adapter_captures_cache_usage():
    """Anthropic 适配器应从 message_start 事件中提取缓存 token 字段"""
    from app.protocols.anthropic import AnthropicAdapter

    adapter = AnthropicAdapter()
    metrics = RequestMetrics(request_id=1)

    # 模拟 SSE 流：message_start 包含 cache usage
    message_start_data = json.dumps({
        "type": "message_start",
        "message": {
            "usage": {
                "input_tokens": 5000,
                "cache_read_input_tokens": 4000,
                "cache_creation_input_tokens": 1000,
            }
        }
    })
    message_stop_data = json.dumps({"type": "message_stop"})

    body = f"data: {message_start_data}\n\ndata: {message_stop_data}\n\n"

    class FakeContent:
        def __init__(self, data):
            self._data = data.encode()
        def __aiter__(self):
            return self._async_iter()
        async def _async_iter(self):
            yield self._data

    class FakeResponse:
        content = FakeContent(body)

    resp = FakeResponse()
    await adapter.parse_sse_stream(resp, metrics)

    assert metrics.input_tokens == 5000
    assert metrics.cache_read_tokens == 4000
    assert metrics.cache_creation_tokens == 1000


# --- 缓存控制 nonce 测试 ---

def test_anthropic_default_breaks_cache():
    """默认模式：system prompt 追加随机 nonce，破坏前缀缓存"""
    from app.protocols.anthropic import AnthropicAdapter
    adapter = AnthropicAdapter()
    config = {
        "model": "claude-sonnet-4-20250514",
        "system_prompt": "You are a helpful assistant.",
        "user_prompt": "Hello",
        "api_key": "test-key",
        "base_url": "https://api.anthropic.com",
    }
    payload = adapter.build_payload(config)
    system_text = payload["system"][0]["text"]
    assert "[nonce:" in system_text
    # nonce 在开头，确保破坏前缀缓存
    assert system_text.startswith("[nonce:")
    assert "You are a helpful assistant." in system_text


def test_anthropic_cache_test_preserves_prompt():
    """cache_test=True：system prompt 不变，允许缓存生效"""
    from app.protocols.anthropic import AnthropicAdapter
    adapter = AnthropicAdapter()
    config = {
        "model": "claude-sonnet-4-20250514",
        "system_prompt": "You are a helpful assistant.",
        "user_prompt": "Hello",
        "api_key": "test-key",
        "base_url": "https://api.anthropic.com",
        "cache_test": True,
    }
    payload = adapter.build_payload(config)
    system_text = payload["system"][0]["text"]
    assert system_text == "You are a helpful assistant."
    assert "[nonce:" not in system_text


def test_anthropic_each_request_has_unique_nonce():
    """默认模式下每次请求 nonce 不同"""
    from app.protocols.anthropic import AnthropicAdapter
    adapter = AnthropicAdapter()
    config = {
        "model": "claude-sonnet-4-20250514",
        "system_prompt": "You are a helpful assistant.",
        "user_prompt": "Hello",
        "api_key": "test-key",
        "base_url": "https://api.anthropic.com",
    }
    nonces = set()
    for _ in range(5):
        payload = adapter.build_payload(config)
        system_text = payload["system"][0]["text"]
        # 提取 nonce 值
        nonce = system_text.split("[nonce:")[1].rstrip("]")
        nonces.add(nonce)
    assert len(nonces) == 5  # 5 个不同的 nonce


def test_openai_chat_default_breaks_cache():
    """OpenAI Chat 适配器默认破坏缓存"""
    from app.protocols.openai_chat import OpenAIChatAdapter
    adapter = OpenAIChatAdapter()
    config = {
        "model": "gpt-4",
        "system_prompt": "You are helpful.",
        "user_prompt": "Hello",
        "api_key": "test-key",
        "base_url": "https://api.openai.com",
    }
    payload = adapter.build_payload(config)
    system_msg = payload["messages"][0]["content"]
    assert "[nonce:" in system_msg


def test_openai_chat_cache_test_preserves_prompt():
    """OpenAI Chat 适配器 cache_test=True 不修改 prompt"""
    from app.protocols.openai_chat import OpenAIChatAdapter
    adapter = OpenAIChatAdapter()
    config = {
        "model": "gpt-4",
        "system_prompt": "You are helpful.",
        "user_prompt": "Hello",
        "api_key": "test-key",
        "base_url": "https://api.openai.com",
        "cache_test": True,
    }
    payload = adapter.build_payload(config)
    system_msg = payload["messages"][0]["content"]
    assert system_msg == "You are helpful."


def test_openai_responses_default_breaks_cache():
    """OpenAI Responses 适配器默认破坏缓存"""
    from app.protocols.openai_responses import OpenAIResponsesAdapter
    adapter = OpenAIResponsesAdapter()
    config = {
        "model": "gpt-5",
        "system_prompt": "You are helpful.",
        "user_prompt": "Hello",
        "api_key": "test-key",
        "base_url": "https://api.openai.com",
    }
    payload = adapter.build_payload(config)
    assert "[nonce:" in payload["instructions"]


def test_openai_responses_cache_test_preserves_prompt():
    """OpenAI Responses 适配器 cache_test=True 不修改 prompt"""
    from app.protocols.openai_responses import OpenAIResponsesAdapter
    adapter = OpenAIResponsesAdapter()
    config = {
        "model": "gpt-5",
        "system_prompt": "You are helpful.",
        "user_prompt": "Hello",
        "api_key": "test-key",
        "base_url": "https://api.openai.com",
        "cache_test": True,
    }
    payload = adapter.build_payload(config)
    assert payload["instructions"] == "You are helpful."
