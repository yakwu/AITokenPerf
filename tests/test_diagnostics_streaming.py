import json
import pytest
from unittest.mock import AsyncMock, MagicMock


def _sse(event_type, **kwargs):
    return f"data: {json.dumps({'type': event_type, **kwargs})}\n\n".encode()


class TestStreamingProbe:
    @pytest.mark.asyncio
    async def test_passes_with_long_output(self):
        from app.diagnostics.streaming import run_streaming_probes
        long_text = "x" * 600
        mock_resp = MagicMock()
        mock_resp.status = 200

        async def iter_content():
            yield _sse("message_start", message={"usage": {"input_tokens": 10}})
            yield _sse("content_block_delta", delta={"type": "text_delta", "text": long_text})
            yield _sse("message_delta", usage={"output_tokens": 50}, delta={"stop_reason": "end_turn"})
            yield _sse("message_stop")

        mock_resp.content = iter_content()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
        result = await run_streaming_probes(config, mock_session, "t", 30)
        assert result.status == "passed"
        assert result.probes[0].ttft_ms is not None

    @pytest.mark.asyncio
    async def test_fails_with_short_output(self):
        from app.diagnostics.streaming import run_streaming_probes
        mock_resp = MagicMock()
        mock_resp.status = 200

        async def iter_content():
            yield _sse("message_start", message={"usage": {"input_tokens": 10}})
            yield _sse("content_block_delta", delta={"type": "text_delta", "text": "short"})
            yield _sse("message_delta", usage={"output_tokens": 1}, delta={"stop_reason": "end_turn"})
            yield _sse("message_stop")

        mock_resp.content = iter_content()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
        result = await run_streaming_probes(config, mock_session, "t", 30)
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        from app.diagnostics.streaming import run_streaming_probes
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_resp.text = AsyncMock(return_value="Internal Server Error")

        async def iter_content():
            if False:
                yield

        mock_resp.content = iter_content()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
        result = await run_streaming_probes(config, mock_session, "t", 30)
        assert result.status == "failed"
