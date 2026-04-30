import json
import pytest
from unittest.mock import AsyncMock, MagicMock


def _sse(event_type, **kwargs):
    return f"data: {json.dumps({'type': event_type, **kwargs})}\n\n".encode()


class TestToolUseProbe:
    @pytest.mark.asyncio
    async def test_passes_with_correct_result(self):
        from app.diagnostics.tool_use import run_tool_use_probes
        call_count = 0

        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status = 200
            if call_count == 1:
                async def iter1():
                    yield _sse("message_start", message={"usage": {"input_tokens": 50}})
                    yield _sse("content_block_start", content_block={"type": "tool_use", "id": "tu_1", "name": "calc_sum", "input": {}})
                    yield _sse("content_block_delta", delta={"type": "input_json_delta", "partial_json": '{"a":7,"b":13}'})
                    yield _sse("content_block_stop")
                    yield _sse("message_delta", usage={"output_tokens": 10}, delta={"stop_reason": "tool_use"})
                    yield _sse("message_stop")
                mock_resp.content = iter1()
            else:
                async def iter2():
                    yield _sse("message_start", message={"usage": {"input_tokens": 80}})
                    yield _sse("content_block_delta", delta={"type": "text_delta", "text": "计算结果是 20"})
                    yield _sse("message_delta", usage={"output_tokens": 10}, delta={"stop_reason": "end_turn"})
                    yield _sse("message_stop")
                mock_resp.content = iter2()
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)
            return mock_resp

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=mock_post)
        config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
        result = await run_tool_use_probes(config, mock_session, "t", 30)
        assert result.status == "passed"

    @pytest.mark.asyncio
    async def test_fails_when_no_tool_call(self):
        from app.diagnostics.tool_use import run_tool_use_probes

        mock_resp = MagicMock()
        mock_resp.status = 200

        async def iter_content():
            yield _sse("message_start", message={"usage": {"input_tokens": 50}})
            yield _sse("content_block_delta", delta={"type": "text_delta", "text": "我不想调用工具"})
            yield _sse("message_delta", usage={"output_tokens": 10}, delta={"stop_reason": "end_turn"})
            yield _sse("message_stop")

        mock_resp.content = iter_content()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
        result = await run_tool_use_probes(config, mock_session, "t", 30)
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        from app.diagnostics.tool_use import run_tool_use_probes
        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_resp.text = AsyncMock(return_value="Forbidden")

        async def iter_content():
            if False:
                yield

        mock_resp.content = iter_content()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
        result = await run_tool_use_probes(config, mock_session, "t", 30)
        assert result.status == "failed"
