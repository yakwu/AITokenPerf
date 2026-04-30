"""测试缓存探针"""
import pytest
from unittest.mock import AsyncMock, patch
from app.diagnostics.models import CategoryResult


class TestCacheProbes:
    @pytest.mark.asyncio
    async def test_cache_probes_returns_category_result(self):
        from app.diagnostics.cache_probes import run_cache_probes
        mock_result = AsyncMock()
        mock_result.status = "supported"
        mock_result.confidence = 0.9
        mock_result.run_tag = "abc"
        mock_result.probes = []
        mock_result.report = {"prompt_cache": {"hit_rate": 1.0, "status": "supported"}, "response_cache": {}, "proxy_cache": {}}
        with patch("app.diagnostics.cache_probes.run_cache_diagnostics", return_value=mock_result):
            config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
            result = await run_cache_probes(config, None, "t", 30)
            assert isinstance(result, CategoryResult)
            assert result.category == "cache"
            assert result.status == "passed"

    @pytest.mark.asyncio
    async def test_cache_probes_handles_error(self):
        from app.diagnostics.cache_probes import run_cache_probes
        with patch("app.diagnostics.cache_probes.run_cache_diagnostics", side_effect=Exception("fail")):
            config = {"base_url": "x", "api_key": "k", "model": "m", "protocol": "anthropic"}
            result = await run_cache_probes(config, None, "t", 30)
            assert result.status == "error"
