"""测试缓存诊断核心逻辑"""

import json
import time
import pytest

from app.channel_diagnostics import (
    CacheDiagnosticResult,
    ProbeResult,
    build_cache_report,
    _is_cache_hit,
    WARM_SAMPLE_COUNT,
    APPEND_SAMPLE_COUNT,
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


def test_is_cache_hit_with_usage():
    """cache_read_tokens > 0 视为命中"""
    p = ProbeResult(name="test", cache_read_tokens=4000)
    assert _is_cache_hit(p) is True


def test_is_cache_hit_without_usage():
    """cache_read_tokens = 0 视为未命中"""
    p = ProbeResult(name="test", cache_read_tokens=0)
    assert _is_cache_hit(p) is False


def test_hit_rate_all_hit():
    """全部命中时命中率 = 1.0"""
    probes = [
        ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                   cache_read_tokens=0, cache_creation_tokens=5000),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=4000),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=4200),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=3800),
    ]
    report = build_cache_report(probes)
    assert report["prompt_cache"]["hit_rate"] == 1.0
    assert report["prompt_cache"]["status"] == "supported"


def test_hit_rate_partial():
    """部分命中时命中率正确"""
    probes = [
        ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                   cache_read_tokens=0, cache_creation_tokens=5000, latency_ms=2000),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=4000),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=0),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=3500),
    ]
    report = build_cache_report(probes)
    assert report["prompt_cache"]["hit_rate"] == pytest.approx(2 / 3, abs=0.01)


def test_hit_rate_none():
    """全部未命中时命中率 = 0"""
    probes = [
        ProbeResult(name="cold_prefix", status="passed", input_tokens=5000, cache_read_tokens=0, latency_ms=2000),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=0),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=0),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=0),
    ]
    report = build_cache_report(probes)
    assert report["prompt_cache"]["hit_rate"] == 0


def test_append_consistent():
    """warm 和 append 都命中 → append_consistent = True"""
    probes = [
        ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                   cache_read_tokens=0, cache_creation_tokens=5000),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=4000),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=3800),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=4200),
        ProbeResult(name="warm_append", status="passed", input_tokens=5100, cache_read_tokens=3900),
        ProbeResult(name="warm_append", status="passed", input_tokens=5100, cache_read_tokens=4000),
    ]
    report = build_cache_report(probes)
    assert report["prompt_cache"]["append_consistent"] is True


def test_append_inconsistent():
    """warm 命中但 append 不命中 → append_consistent = False, status = warning"""
    probes = [
        ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                   cache_read_tokens=0, cache_creation_tokens=5000),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=4000),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=3800),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000, cache_read_tokens=4200),
        ProbeResult(name="warm_append", status="passed", input_tokens=5100, cache_read_tokens=0),
        ProbeResult(name="warm_append", status="passed", input_tokens=5100, cache_read_tokens=0),
    ]
    report = build_cache_report(probes)
    assert report["prompt_cache"]["append_consistent"] is False
    assert report["prompt_cache"]["status"] == "warning"


def test_response_cache_detected():
    """repeat_identical 秒回应检测到 response cache"""
    probes = [
        ProbeResult(name="cold_prefix", status="passed", input_tokens=5000, latency_ms=1500),
        ProbeResult(name="repeat_identical", status="passed",
                   input_tokens=5000, latency_ms=80, identical_request=True),
    ]
    report = build_cache_report(probes)
    assert report["response_cache"]["status"] == "suspected"
    assert "identical_request_sub_80ms" in report["response_cache"]["evidence"]


def test_response_cache_not_detected_normal_latency():
    """repeat_identical 正常延迟不触发 response cache"""
    probes = [
        ProbeResult(name="cold_prefix", status="passed", input_tokens=5000, latency_ms=1500),
        ProbeResult(name="repeat_identical", status="passed",
                   input_tokens=5000, latency_ms=1200, identical_request=True),
    ]
    report = build_cache_report(probes)
    assert report["response_cache"]["status"] == "not_detected"


def test_build_cache_report_full_structure():
    """完整报告结构正确 — 3 warm + 2 append + breaker + identical"""
    probes = [
        ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                   cache_read_tokens=0, cache_creation_tokens=5000, latency_ms=2000),
        # warm x3
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                   cache_read_tokens=4000, cache_creation_tokens=0, latency_ms=800),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                   cache_read_tokens=3800, cache_creation_tokens=0, latency_ms=850),
        ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                   cache_read_tokens=4200, cache_creation_tokens=0, latency_ms=750),
        # append x2
        ProbeResult(name="warm_append", status="passed", input_tokens=5100,
                   cache_read_tokens=3900, cache_creation_tokens=0, latency_ms=900),
        ProbeResult(name="warm_append", status="passed", input_tokens=5100,
                   cache_read_tokens=4000, cache_creation_tokens=0, latency_ms=880),
        # breaker
        ProbeResult(name="breaker_prefix", status="passed", input_tokens=5200,
                   cache_read_tokens=0, cache_creation_tokens=5200, latency_ms=2100),
        # identical
        ProbeResult(name="repeat_identical", status="passed", input_tokens=5000,
                   cache_read_tokens=0, latency_ms=1500, identical_request=True),
    ]
    report = build_cache_report(probes)

    assert "prompt_cache" in report
    assert "response_cache" in report
    assert report["prompt_cache"]["status"] == "supported"
    assert report["prompt_cache"]["hit_rate"] == 1.0  # 全部 5 个 warm+append 都命中
    assert report["prompt_cache"]["sample_count"] == 5
    assert report["prompt_cache"]["append_consistent"] is True
    assert len(report["prompt_cache"]["warm_samples"]) == 3
    assert len(report["prompt_cache"]["append_samples"]) == 2
    assert "estimated_cost_saving" in report["prompt_cache"]


def test_probe_sample_count_constants():
    """采样次数常量正确"""
    assert WARM_SAMPLE_COUNT == 3
    assert APPEND_SAMPLE_COUNT == 2
