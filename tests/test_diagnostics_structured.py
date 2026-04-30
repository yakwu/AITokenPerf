import json
import pytest
from unittest.mock import AsyncMock, MagicMock


def _sse(event_type, **kwargs):
    return f"data: {json.dumps({'type': event_type, **kwargs})}\n\n".encode()


class TestStructuredProbe:
    @pytest.mark.asyncio
    async def test_passes_with_valid_json(self):
        from app.diagnostics.structured import run_structured_probes
        mock_resp = MagicMock()
        mock_resp.status = 200
        json_output = json.dumps({"name": "alice", "score": 95, "passed": True})

        async def iter_content():
            yield _sse("message_start", message={"usage": {"input_tokens": 20}})
            yield _sse("content_block_delta", delta={"type": "text_delta", "text": json_output})
            yield _sse("message_delta", usage={"output_tokens": 15}, delta={"stop_reason": "end_turn"})
            yield _sse("message_stop")

        mock_resp.content = iter_content()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
        result = await run_structured_probes(config, mock_session, "t", 30)
        assert result.status == "passed"

    @pytest.mark.asyncio
    async def test_fails_with_wrong_json(self):
        from app.diagnostics.structured import run_structured_probes
        mock_resp = MagicMock()
        mock_resp.status = 200
        json_output = json.dumps({"name": "bob", "score": 50, "passed": False})

        async def iter_content():
            yield _sse("message_start", message={"usage": {"input_tokens": 20}})
            yield _sse("content_block_delta", delta={"type": "text_delta", "text": json_output})
            yield _sse("message_delta", usage={"output_tokens": 15}, delta={"stop_reason": "end_turn"})
            yield _sse("message_stop")

        mock_resp.content = iter_content()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
        result = await run_structured_probes(config, mock_session, "t", 30)
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_fails_with_invalid_json(self):
        from app.diagnostics.structured import run_structured_probes
        mock_resp = MagicMock()
        mock_resp.status = 200

        async def iter_content():
            yield _sse("message_start", message={"usage": {"input_tokens": 20}})
            yield _sse("content_block_delta", delta={"type": "text_delta", "text": "not json at all"})
            yield _sse("message_delta", usage={"output_tokens": 5}, delta={"stop_reason": "end_turn"})
            yield _sse("message_stop")

        mock_resp.content = iter_content()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
        result = await run_structured_probes(config, mock_session, "t", 30)
        assert result.status == "failed"
