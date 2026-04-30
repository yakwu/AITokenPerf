"""测试统一诊断调度器"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.diagnostics.models import DiagnosticReport, CategoryResult
from app.diagnostics.runner import run_diagnostics, get_available_categories, _CATEGORY_REGISTRY


def _mock_session_context():
    """返回一个可 async with 的 mock session 的 patch 对象"""
    mock_session = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return patch("aiohttp.ClientSession", return_value=mock_cm), patch("aiohttp.TCPConnector")


class TestCategoryRegistry:
    def test_all_six_categories_registered(self):
        """6 个类别都应注册"""
        from app.diagnostics import connectivity, streaming, context, tool_use, structured, cache_probes  # noqa: F401
        cats = get_available_categories()
        assert "connectivity" in cats
        assert "streaming" in cats
        assert "context" in cats
        assert "tool_use" in cats
        assert "structured" in cats
        assert "cache" in cats
        assert len(cats) == 6


class TestRunDiagnostics:
    @pytest.mark.asyncio
    async def test_run_specific_categories(self):
        """指定类别只运行那些类别"""
        config = {
            "base_url": "https://api.anthropic.com",
            "api_key": "test-key",
            "model": "test-model",
            "protocol": "anthropic",
        }
        mock_result = CategoryResult(category="connectivity", display_name="连通性", status="passed")
        mock_runner = AsyncMock(return_value=mock_result)

        cs_patch, tc_patch = _mock_session_context()
        with patch.dict(_CATEGORY_REGISTRY, {"connectivity": mock_runner}), cs_patch, tc_patch:
            report = await run_diagnostics(config, categories=["connectivity"], timeout_seconds=5)
            assert isinstance(report, DiagnosticReport)
            assert len(report.categories) == 1
            assert report.categories[0].category == "connectivity"
            mock_runner.assert_called_once()

    @pytest.mark.asyncio
    async def test_overall_status_all_passed(self):
        """所有类别 passed → overall passed, risk low"""
        config = {"base_url": "x", "api_key": "k", "model": "m", "protocol": "anthropic"}
        mock_result = CategoryResult(category="connectivity", status="passed", summary={"confidence": 0.9})
        mock_runner = AsyncMock(return_value=mock_result)

        cs_patch, tc_patch = _mock_session_context()
        with patch.dict(_CATEGORY_REGISTRY, {"connectivity": mock_runner}), cs_patch, tc_patch:
            report = await run_diagnostics(config, categories=["connectivity"], timeout_seconds=5)
            assert report.overall_status == "passed"
            assert report.overall_risk == "low"
            assert report.confidence == 0.9

    @pytest.mark.asyncio
    async def test_overall_status_mixed(self):
        """passed + warning → overall warning"""
        config = {"base_url": "x", "api_key": "k", "model": "m", "protocol": "anthropic"}
        mock_pass = CategoryResult(category="connectivity", status="passed", summary={"confidence": 0.9})
        mock_warn = CategoryResult(category="cache", status="warning", summary={"confidence": 0.5})

        cs_patch, tc_patch = _mock_session_context()
        with patch.dict(_CATEGORY_REGISTRY, {
            "connectivity": AsyncMock(return_value=mock_pass),
            "cache": AsyncMock(return_value=mock_warn),
        }), cs_patch, tc_patch:
            report = await run_diagnostics(config, categories=["connectivity", "cache"], timeout_seconds=5)
            assert report.overall_status == "warning"
            assert report.overall_risk == "medium"

    @pytest.mark.asyncio
    async def test_overall_status_error(self):
        """任何类别 error → overall error, risk high"""
        config = {"base_url": "x", "api_key": "k", "model": "m", "protocol": "anthropic"}
        mock_err = CategoryResult(category="connectivity", status="error", summary={})
        mock_runner = AsyncMock(return_value=mock_err)

        cs_patch, tc_patch = _mock_session_context()
        with patch.dict(_CATEGORY_REGISTRY, {"connectivity": mock_runner}), cs_patch, tc_patch:
            report = await run_diagnostics(config, categories=["connectivity"], timeout_seconds=5)
            assert report.overall_status == "error"
            assert report.overall_risk == "high"

    @pytest.mark.asyncio
    async def test_handles_runner_exception(self):
        """runner 抛异常时应捕获并标记为 error"""
        config = {"base_url": "x", "api_key": "k", "model": "m", "protocol": "anthropic"}
        mock_runner = AsyncMock(side_effect=RuntimeError("boom"))

        cs_patch, tc_patch = _mock_session_context()
        with patch.dict(_CATEGORY_REGISTRY, {"connectivity": mock_runner}), cs_patch, tc_patch:
            report = await run_diagnostics(config, categories=["connectivity"], timeout_seconds=5)
            assert report.categories[0].status == "error"
            assert "boom" in report.categories[0].summary["error"]

    @pytest.mark.asyncio
    async def test_unknown_category_skipped(self):
        """未知类别应被跳过"""
        config = {"base_url": "x", "api_key": "k", "model": "m", "protocol": "anthropic"}

        cs_patch, tc_patch = _mock_session_context()
        with cs_patch, tc_patch:
            report = await run_diagnostics(config, categories=["nonexistent"], timeout_seconds=5)
            assert len(report.categories) == 0
