"""测试缓存诊断核心逻辑 — Claude prompt caching 诊断

Spec 要求的 7 个测试用例：
1. Anthropic payload 包含 cache_control
2. 长前缀 >= 2500 词
3. cold creation + warm read + breaker creation → supported
4. warm read + breaker read → warning
5. 无 usage → no_usage_fields
6. repeat_identical 不影响 prompt cache hit rate
7. 非 Anthropic 协议返回错误
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from app.channel_diagnostics import (
    CacheDiagnosticResult,
    ProbeResult,
    build_cache_report,
    compute_overall_status,
    _is_cache_hit,
    _extract_cache_tokens,
    _LONG_PREFIX,
    _BREAKER_PREFIX,
    WARM_SAMPLE_COUNT,
    cold_prefix_prompts,
    breaker_prefix_prompts,
)
from app.protocols.anthropic import AnthropicAdapter


# --- Spec 测试用例 1: payload 包含 cache_control ---

class TestCacheControlInPayload:
    """Anthropic 诊断 payload 的 system block 包含 cache_control: {"type": "ephemeral"}"""

    def test_cache_control_added_when_enabled(self):
        """cache_control=True 时 system block 包含 cache_control 字段"""
        adapter = AnthropicAdapter()
        config = {
            "model": "claude-sonnet-4-20250514",
            "system_prompt": "test system prompt",
            "user_prompt": "hello",
            "cache_test": True,
            "cache_control": True,
        }
        payload = adapter.build_payload(config)
        system_block = payload["system"][0]
        assert "cache_control" in system_block
        assert system_block["cache_control"] == {"type": "ephemeral"}
        assert system_block["type"] == "text"

    def test_cache_control_not_added_when_disabled(self):
        """cache_control=False 时 system block 不包含 cache_control 字段"""
        adapter = AnthropicAdapter()
        config = {
            "model": "claude-sonnet-4-20250514",
            "system_prompt": "test system prompt",
            "user_prompt": "hello",
            "cache_test": True,
            "cache_control": False,
        }
        payload = adapter.build_payload(config)
        system_block = payload["system"][0]
        assert "cache_control" not in system_block

    def test_probe_config_sets_cache_control(self):
        """诊断 probe 的 config 中应设置 cache_control=True"""
        prompts = cold_prefix_prompts("test question")
        config = {
            "model": "claude-sonnet-4-20250514",
            "protocol": "anthropic",
            "api_key": "test-key",
            "base_url": "https://api.anthropic.com",
        }
        # 模拟 _run_single_probe 中的 config 构建
        probe_config = dict(config)
        probe_config["system_prompt"] = prompts["system_prompt"]
        probe_config["user_prompt"] = prompts["user_prompt"]
        probe_config["cache_test"] = True
        probe_config["cache_control"] = True

        adapter = AnthropicAdapter()
        payload = adapter.build_payload(probe_config)
        assert payload["system"][0].get("cache_control") == {"type": "ephemeral"}


# --- Spec 测试用例 2: 长前缀 >= 2500 词 ---

class TestPrefixLength:
    """Claude 诊断长前缀达到长度下限"""

    def test_long_prefix_exceeds_4096_threshold(self):
        """_LONG_PREFIX 用 tiktoken 实测超过 4096 tokens（Opus 4.x 缓存阈值）"""
        from app.channel_diagnostics import _estimate_tokens
        actual_tokens = _estimate_tokens(_LONG_PREFIX)
        assert actual_tokens >= 4096, f"长前缀 tiktoken 实测 {actual_tokens} tokens，需要 >= 4096"

    def test_breaker_prefix_exceeds_4096_threshold(self):
        """_BREAKER_PREFIX 用 tiktoken 实测超过 4096 tokens"""
        from app.channel_diagnostics import _estimate_tokens
        actual_tokens = _estimate_tokens(_BREAKER_PREFIX)
        assert actual_tokens >= 4096, f"breaker 前缀 tiktoken 实测 {actual_tokens} tokens，需要 >= 4096"

    def test_cold_prefix_uses_long_prefix(self):
        """cold_prefix_prompts 使用 _LONG_PREFIX"""
        prompts = cold_prefix_prompts("test")
        assert prompts["system_prompt"] == _LONG_PREFIX

    def test_breaker_prefix_differs_from_original(self):
        """breaker_prefix 的内容与原始完全不同"""
        prompts = breaker_prefix_prompts("test")
        assert prompts["system_prompt"] != _LONG_PREFIX
        # 开头就不同
        assert prompts["system_prompt"][:50] != _LONG_PREFIX[:50]


# --- Spec 测试用例 3: cold creation + warm read + breaker creation → supported ---

class TestSupportedDetection:
    """cold creation + warm read + breaker creation → supported"""

    def test_cold_creation_warm_read_breaker_creation_supported(self):
        """标准支持场景：cold 有 creation，warm 有 read，breaker 有新 creation"""
        probes = [
            ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=4500),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=4000, cache_creation_tokens=0),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=4200, cache_creation_tokens=0),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=3800, cache_creation_tokens=0),
            ProbeResult(name="breaker_prefix", status="passed", input_tokens=5200,
                       cache_read_tokens=0, cache_creation_tokens=5200),
            ProbeResult(name="repeat_identical", status="passed", input_tokens=5000,
                       cache_read_tokens=0, latency_ms=1500, identical_request=True),
        ]
        report = build_cache_report(probes)
        assert report["prompt_cache"]["status"] == "supported"
        assert report["prompt_cache"]["hit_rate"] == 1.0
        assert report["prompt_cache"]["confidence"] >= 0.8

        status, risk, confidence = compute_overall_status(report)
        assert status == "passed"
        assert risk == "low"


# --- Spec 测试用例 4: warm read + breaker read → warning ---

class TestWarningDetection:
    """warm 能命中，但 breaker 也读到缓存 → warning"""

    def test_warm_read_breaker_also_read_warning(self):
        """breaker 读到旧缓存是异常信号"""
        probes = [
            ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=4500),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=4000, cache_creation_tokens=0),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=4200, cache_creation_tokens=0),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=3800, cache_creation_tokens=0),
            # breaker 读到了旧缓存 → 异常
            ProbeResult(name="breaker_prefix", status="passed", input_tokens=5200,
                       cache_read_tokens=3000, cache_creation_tokens=0),
        ]
        report = build_cache_report(probes)
        assert report["prompt_cache"]["status"] == "warning"
        # breaker cache_read 触发 proxy 检测，confidence 被 clamp 到 0.3
        assert report["prompt_cache"]["confidence"] == 0.3

        status, risk, confidence = compute_overall_status(report)
        assert status == "warning"
        assert risk == "medium"


# --- Spec 测试用例 5: 无 usage → no_usage_fields ---

class TestNoUsageFields:
    """请求成功但所有 probe 都没有 cache_creation/read 字段 → no_usage_fields"""

    def test_no_usage_fields_not_unsupported(self):
        """无 usage 字段应判为 no_usage_fields，而不是不支持缓存"""
        probes = [
            ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=0),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=0),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=0),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=0),
            ProbeResult(name="breaker_prefix", status="passed", input_tokens=5200,
                       cache_read_tokens=0, cache_creation_tokens=0),
        ]
        report = build_cache_report(probes)
        assert report["prompt_cache"]["status"] == "no_usage_fields"
        assert report["prompt_cache"]["confidence"] == 0.2
        # 绝对不应是 "supported" 或 "unsupported"
        assert report["prompt_cache"]["status"] != "supported"

        status, risk, confidence = compute_overall_status(report)
        assert status == "no_usage_fields"


class TestNoCache:
    """缓存字段存在但值全为 0 → no_cache（区别于字段完全不存在的 no_usage_fields）"""

    def test_cache_fields_present_but_zero(self):
        """raw_usage 含 cache 字段但值为 0 → no_cache，不是 no_usage_fields"""
        probes = [
            ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=0,
                       raw_usage={"input_tokens": 5000, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=0,
                       raw_usage={"input_tokens": 5000, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=0,
                       raw_usage={"input_tokens": 5000, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=0,
                       raw_usage={"input_tokens": 5000, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}),
            ProbeResult(name="breaker_prefix", status="passed", input_tokens=5200,
                       cache_read_tokens=0, cache_creation_tokens=0,
                       raw_usage={"input_tokens": 5200, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}),
        ]
        report = build_cache_report(probes)
        assert report["prompt_cache"]["status"] == "no_cache"
        assert report["prompt_cache"]["confidence"] == 0.3
        # 必须不是 no_usage_fields
        assert report["prompt_cache"]["status"] != "no_usage_fields"

        status, risk, confidence = compute_overall_status(report)
        assert status == "no_cache"


# --- Spec 测试用例 6: repeat_identical 不影响 prompt cache hit rate ---

class TestRepeatIdenticalIsolation:
    """repeat_identical 秒回只影响 response_cache，不改变 prompt cache hit rate"""

    def test_identical_fast_response_only_affects_response_cache(self):
        """repeat_identical 秒回应只标记 response_cache，不影响 prompt_cache"""
        probes = [
            ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=4500),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=4000, cache_creation_tokens=0),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=4200, cache_creation_tokens=0),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=3800, cache_creation_tokens=0),
            ProbeResult(name="breaker_prefix", status="passed", input_tokens=5200,
                       cache_read_tokens=0, cache_creation_tokens=5200),
            # 秒回应的 repeat_identical
            ProbeResult(name="repeat_identical", status="passed", input_tokens=5000,
                       cache_read_tokens=0, latency_ms=50, identical_request=True),
        ]
        report = build_cache_report(probes)

        # prompt cache 不受 repeat_identical 影响
        assert report["prompt_cache"]["hit_rate"] == 1.0
        assert report["prompt_cache"]["status"] == "supported"

        # response cache 被检测到
        assert report["response_cache"]["status"] == "suspected"
        assert "identical_request_sub_50ms" in report["response_cache"]["evidence"]

    def test_identical_normal_latency_no_response_cache(self):
        """repeat_identical 正常延迟不触发 response cache"""
        probes = [
            ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=4500),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=4000, cache_creation_tokens=0),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=4200, cache_creation_tokens=0),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=3800, cache_creation_tokens=0),
            ProbeResult(name="breaker_prefix", status="passed", input_tokens=5200,
                       cache_read_tokens=0, cache_creation_tokens=5200),
            ProbeResult(name="repeat_identical", status="passed", input_tokens=5000,
                       cache_read_tokens=0, latency_ms=1500, identical_request=True),
        ]
        report = build_cache_report(probes)
        assert report["response_cache"]["status"] == "not_detected"


# --- Spec 测试用例 7: 非 Anthropic 协议返回错误 ---

class TestNonAnthropicGate:
    """非 Anthropic 协议调用渠道诊断返回明确错误"""

    @pytest.mark.asyncio
    async def test_openai_protocol_returns_error(self):
        """OpenAI 协议应返回 error 状态"""
        from app.channel_diagnostics import run_cache_diagnostics
        config = {
            "base_url": "https://api.openai.com",
            "api_key": "test-key",
            "model": "gpt-4",
            "protocol": "openai_chat",
        }
        result = await run_cache_diagnostics(config)
        assert result.status == "error"
        assert "仅支持 Anthropic" in result.report.get("error", "")

    @pytest.mark.asyncio
    async def test_openai_responses_protocol_returns_error(self):
        """OpenAI Responses 协议应返回 error 状态"""
        from app.channel_diagnostics import run_cache_diagnostics
        config = {
            "base_url": "https://api.openai.com",
            "api_key": "test-key",
            "model": "gpt-4",
            "protocol": "openai_responses",
        }
        result = await run_cache_diagnostics(config)
        assert result.status == "error"
        assert "仅支持 Anthropic" in result.report.get("error", "")

    @pytest.mark.asyncio
    async def test_provider_anthropic_without_claude_model_name(self):
        """provider=anthropic + 非 claude 字样模型名仍应通过 gate"""
        from app.channel_diagnostics import run_cache_diagnostics
        from app.protocols import detect_protocol
        # provider=anthropic 但模型名不含 "claude"
        protocol = detect_protocol("sonnet-4", "anthropic")
        assert protocol == "anthropic"
        config = {
            "base_url": "https://api.anthropic.com",
            "api_key": "test-key",
            "model": "sonnet-4",
            "protocol": "",
            "provider": "anthropic",
        }
        cold_result = ProbeResult(name="cold_prefix", status="error", error="synthetic cold failure")
        with patch("app.channel_diagnostics._run_single_probe", new=AsyncMock(return_value=cold_result)) as probe:
            result = await run_cache_diagnostics(config)

        assert probe.await_count == 1
        assert result.status == "error"
        assert result.report.get("error") == "cold_prefix probe failed: error — synthetic cold failure"


# --- Cold probe 失败/超时测试 ---

class TestColdProbeFailure:
    """cold probe 非 passed 应直接返回 error"""

    def test_cold_timeout_results_in_error_report(self):
        """cold probe 超时应产生 error 报告，不是 inconclusive"""
        # 模拟 cold probe 超时
        probes = [
            ProbeResult(name="cold_prefix", status="timeout", error="Probe timed out after 60s"),
        ]
        report = build_cache_report(probes)
        # 由于 cold 超时后不会运行 warm/breaker，报告中 prompt_cache 仍为 inconclusive
        # 但 run_cache_diagnostics 会提前返回 error
        # 这里验证报告结构不会崩溃
        assert "prompt_cache" in report

    @pytest.mark.asyncio
    async def test_cold_timeout_stops_diagnostics(self):
        """cold probe 超时时 run_cache_diagnostics 应返回 error 状态"""
        from app.channel_diagnostics import run_cache_diagnostics
        config = {
            "base_url": "https://api.anthropic.com",
            "api_key": "test-key",
            "model": "claude-sonnet-4-20250514",
            "protocol": "anthropic",
        }
        cold_result = ProbeResult(name="cold_prefix", status="timeout", error="Probe timed out after 2s")
        with patch("app.channel_diagnostics._run_single_probe", new=AsyncMock(return_value=cold_result)) as probe:
            result = await run_cache_diagnostics(config, timeout_seconds=2)

        assert result.status == "error"
        assert result.report.get("error") == "cold_prefix probe failed: timeout — Probe timed out after 2s"
        assert probe.await_count == 1
        # 应该只跑了 cold probe
        assert len(result.probes) == 1
        assert result.probes[0].name == "cold_prefix"


# --- 补充测试 ---

class TestHitRateCalculation:
    """缓存命中率计算"""

    def test_is_cache_hit_with_usage(self):
        """cache_read_tokens > 0 视为命中"""
        p = ProbeResult(name="test", cache_read_tokens=4000)
        assert _is_cache_hit(p) is True

    def test_is_cache_hit_without_usage(self):
        """cache_read_tokens = 0 视为未命中"""
        p = ProbeResult(name="test", cache_read_tokens=0)
        assert _is_cache_hit(p) is False

    def test_warm_all_hit(self):
        """全部 warm 命中 + breaker 通过 → supported"""
        probes = [
            ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=5000),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=4000),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=4200),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=3800),
            ProbeResult(name="breaker_prefix", status="passed", input_tokens=5200,
                       cache_read_tokens=0, cache_creation_tokens=5200),
        ]
        report = build_cache_report(probes)
        assert report["prompt_cache"]["hit_rate"] == 1.0
        assert report["prompt_cache"]["status"] == "supported"

    def test_warm_partial_hit(self):
        """部分 warm 命中时 hit_rate 正确"""
        probes = [
            ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=5000),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=4000),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=0),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=3500),
            ProbeResult(name="breaker_prefix", status="passed", input_tokens=5200,
                       cache_read_tokens=0, cache_creation_tokens=5200),
        ]
        report = build_cache_report(probes)
        assert report["prompt_cache"]["hit_rate"] == pytest.approx(2 / 3, abs=0.01)
        assert report["prompt_cache"]["status"] == "partial"


class TestReportStructure:
    """报告结构完整性"""

    def test_report_has_expected_keys(self):
        """报告包含所有预期的 key"""
        probes = [
            ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=5000),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=4000),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=4200),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=3800),
            ProbeResult(name="breaker_prefix", status="passed", input_tokens=5200,
                       cache_read_tokens=0, cache_creation_tokens=5200),
            ProbeResult(name="repeat_identical", status="passed", input_tokens=5000,
                       cache_read_tokens=0, latency_ms=1500, identical_request=True),
        ]
        report = build_cache_report(probes)
        assert "prompt_cache" in report
        assert "response_cache" in report
        assert "status" in report["prompt_cache"]
        assert "hit_rate" in report["prompt_cache"]
        assert "confidence" in report["prompt_cache"]
        assert "samples" in report["prompt_cache"]
        assert "warm_samples" in report["prompt_cache"]

    def test_sample_count_matches_warm_probes(self):
        """sample_count 等于 warm probe 数量"""
        probes = [
            ProbeResult(name="cold_prefix", status="passed", input_tokens=5000),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=4000),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=4200),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=3800),
        ]
        report = build_cache_report(probes)
        assert report["prompt_cache"]["sample_count"] == 3


# --- _extract_cache_tokens 测试 ---

class TestExtractCacheTokens:
    """兼容多种代理返回格式的 cache token 提取"""

    def test_standard_fields(self):
        """标准 Anthropic 字段"""
        usage = {"input_tokens": 5000, "cache_read_input_tokens": 4000, "cache_creation_input_tokens": 0}
        read, creation = _extract_cache_tokens(usage)
        assert read == 4000
        assert creation == 0

    def test_nested_cache_creation_object(self):
        """嵌套 cache_creation 对象（如 ephemeral_5m_input_tokens）"""
        usage = {
            "input_tokens": 1202,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation": {"ephemeral_5m_input_tokens": 944, "ephemeral_1h_input_tokens": 0},
        }
        read, creation = _extract_cache_tokens(usage)
        assert creation == 944
        assert read == 0

    def test_nested_cache_read_object(self):
        """嵌套 cache_read 对象"""
        usage = {
            "input_tokens": 5000,
            "cache_read_input_tokens": 0,
            "cache_read": {"ephemeral_5m_input_tokens": 3500},
        }
        read, creation = _extract_cache_tokens(usage)
        assert read == 3500
        assert creation == 0

    def test_standard_fields_take_priority(self):
        """标准字段存在时优先使用标准字段"""
        usage = {
            "cache_read_input_tokens": 4000,
            "cache_creation_input_tokens": 500,
            "cache_creation": {"ephemeral_5m_input_tokens": 999},
            "cache_read": {"ephemeral_5m_input_tokens": 888},
        }
        read, creation = _extract_cache_tokens(usage)
        assert read == 4000
        assert creation == 500

    def test_empty_usage(self):
        """空 usage 返回 0"""
        read, creation = _extract_cache_tokens({})
        assert read == 0
        assert creation == 0

    def test_bool_and_non_token_keys_ignored(self):
        """嵌套对象中的 bool、非 *_input_tokens 字段应被忽略"""
        usage = {
            "cache_read": {
                "ephemeral_5m_input_tokens": 0,
                "ttl_seconds": 300,
                "hit": True,
            },
            "cache_creation": {
                "ephemeral_5m_input_tokens": 0,
                "enabled": True,
                "max_size": 1024,
            },
        }
        read, creation = _extract_cache_tokens(usage)
        # ttl_seconds、hit、enabled、max_size 都不是 *_input_tokens，应被忽略
        assert read == 0
        assert creation == 0
