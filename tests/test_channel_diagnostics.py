"""测试缓存诊断核心逻辑"""

import json
import time
import pytest

from app.channel_diagnostics import (
    CacheDiagnosticResult,
    ProbeResult,
    build_cache_report,
    classify_cache_type,
)


def test_probe_result_defaults():
    """ProbeResult 默认值正确"""
    p = ProbeResult(name="test_probe")
    assert p.status == "pending"
    assert p.latency_ms == 0
    assert p.input_tokens == 0
    assert p.cache_read_tokens == 0
    assert p.cache_creation_tokens == 0
    assert p.error is None


def test_classify_cache_type_with_usage_fields():
    """有 usage 字段时应返回 prompt_cache"""
    probe = ProbeResult(
        name="warm_prefix",
        status="passed",
        input_tokens=5000,
        cache_read_tokens=4000,
    )
    assert classify_cache_type(probe) == "prompt_cache"


def test_classify_cache_type_response_cache():
    """完全相同请求秒回应判断为 response_cache"""
    probe = ProbeResult(
        name="repeat_identical",
        status="passed",
        latency_ms=50,
        input_tokens=5000,
        cache_read_tokens=0,
        identical_request=True,
    )
    assert classify_cache_type(probe) == "response_cache"


def test_classify_cache_type_unknown():
    """无信号时应返回 unknown_cache"""
    probe = ProbeResult(
        name="cold_prefix",
        status="passed",
        input_tokens=5000,
        cache_read_tokens=0,
        latency_ms=1000,
    )
    assert classify_cache_type(probe) == "unknown_cache"


def test_estimate_hit_rate_from_usage():
    """usage 有 cache_read 时直接计算命中率"""
    cold = ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=5000)
    warm = ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=4500, cache_creation_tokens=500)

    result = build_cache_report([cold, warm])
    assert result["prompt_cache"]["status"] == "supported"
    assert result["prompt_cache"]["hit_rate"] == pytest.approx(0.9, abs=0.01)
    assert result["prompt_cache"]["evidence"] == "usage_fields"


def test_estimate_hit_rate_from_latency():
    """usage 无字段时用延迟估算，置信度降低"""
    cold = ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                       latency_ms=2000, cache_read_tokens=0)
    warm = ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       latency_ms=800, cache_read_tokens=0)

    result = build_cache_report([cold, warm])
    assert result["prompt_cache"]["status"] == "estimated"
    assert result["prompt_cache"]["confidence"] < 0.7


def test_response_cache_detected():
    """repeat_identical 秒回应检测到 response cache"""
    cold = ProbeResult(name="cold_prefix", status="passed", input_tokens=5000, latency_ms=1500)
    identical = ProbeResult(name="repeat_identical", status="passed",
                           input_tokens=5000, latency_ms=80, identical_request=True)

    result = build_cache_report([cold, identical])
    assert result["response_cache"]["status"] == "suspected"
    assert "identical_request_sub_80ms" in result["response_cache"]["evidence"]


def test_response_cache_not_detected_normal_latency():
    """repeat_identical 正常延迟不触发 response cache"""
    cold = ProbeResult(name="cold_prefix", status="passed", input_tokens=5000, latency_ms=1500)
    identical = ProbeResult(name="repeat_identical", status="passed",
                           input_tokens=5000, latency_ms=1200, identical_request=True)

    result = build_cache_report([cold, identical])
    assert result["response_cache"]["status"] == "not_detected"


def test_build_cache_report_full_structure():
    """完整报告结构正确"""
    probes = [
        ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                   cache_read_tokens=0, cache_creation_tokens=5000, latency_ms=2000),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                   cache_read_tokens=4000, cache_creation_tokens=0, latency_ms=800),
        ProbeResult(name="breaker_prefix", status="passed", input_tokens=5200,
                   cache_read_tokens=0, cache_creation_tokens=5200, latency_ms=2100),
        ProbeResult(name="repeat_identical", status="passed", input_tokens=5000,
                   cache_read_tokens=0, latency_ms=1500, identical_request=True),
    ]
    report = build_cache_report(probes)

    assert "prompt_cache" in report
    assert "response_cache" in report
    assert report["prompt_cache"]["status"] == "supported"
    assert report["prompt_cache"]["hit_rate"] == pytest.approx(0.8, abs=0.01)
    assert "estimated_cost_saving" in report["prompt_cache"]
