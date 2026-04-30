import json
import pytest
from unittest.mock import AsyncMock, MagicMock


def _sse(event_type, **kwargs):
    return f"data: {json.dumps({'type': event_type, **kwargs})}\n\n".encode()


class TestContextProbe:
    @pytest.mark.asyncio
    async def test_passes_all_rounds(self):
        from app.diagnostics.context import run_context_probes

        def make_response():
            text = "x" * 250
            mock_resp = MagicMock()
            mock_resp.status = 200

            async def iter_content():
                yield _sse("message_start", message={"usage": {"input_tokens": 100}})
                yield _sse("content_block_delta", delta={"type": "text_delta", "text": text})
                yield _sse("message_delta", usage={"output_tokens": 20}, delta={"stop_reason": "end_turn"})
                yield _sse("message_stop")

            mock_resp.content = iter_content()
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)
            return mock_resp

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=lambda *a, **kw: make_response())
        config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
        result = await run_context_probes(config, mock_session, "t", 30)
        assert result.status == "passed"
        assert len(result.probes) == 6

    @pytest.mark.asyncio
    async def test_fails_on_short_round(self):
        from app.diagnostics.context import run_context_probes
        call_count = 0

        def make_response():
            nonlocal call_count
            call_count += 1
            text = "x" * 250 if call_count != 3 else "short"
            mock_resp = MagicMock()
            mock_resp.status = 200

            async def iter_content():
                yield _sse("message_start", message={"usage": {"input_tokens": 100}})
                yield _sse("content_block_delta", delta={"type": "text_delta", "text": text})
                yield _sse("message_delta", usage={"output_tokens": 20}, delta={"stop_reason": "end_turn"})
                yield _sse("message_stop")

            mock_resp.content = iter_content()
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)
            return mock_resp

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=lambda *a, **kw: make_response())
        config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
        result = await run_context_probes(config, mock_session, "t", 30)
        assert result.status == "failed"
