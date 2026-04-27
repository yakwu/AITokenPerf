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
