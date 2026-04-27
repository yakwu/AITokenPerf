#!/usr/bin/env python3
"""渠道诊断核心模块 — 缓存命中率检测"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

from app.protocols import get_adapter

log = logging.getLogger("channel_diagnostics")


@dataclass
class ProbeResult:
    """单个 probe 的结果"""
    name: str = ""
    status: str = "pending"  # pending | passed | error | timeout | inconclusive
    latency_ms: float = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    identical_request: bool = False
    error: Optional[str] = None
    response_preview: str = ""  # 前 1000 字符


@dataclass
class CacheDiagnosticResult:
    """缓存诊断整体结果"""
    status: str = "not_run"
    overall_risk: str = "unknown"
    confidence: float = 0.0
    probes: list[ProbeResult] = field(default_factory=list)
    report: dict = field(default_factory=dict)


# 长前缀：约 2000+ tokens，用于建立缓存候选
_LONG_PREFIX = """You are an expert software engineer with deep knowledge of distributed systems, databases, and API design. You have been working on a large-scale microservices architecture that handles millions of requests per day. The system uses a combination of PostgreSQL for persistent storage, Redis for caching, and Kafka for event streaming.

Your current task involves optimizing the data pipeline that processes user analytics events. The pipeline currently has the following stages:
1. Event ingestion via HTTP API (Node.js)
2. Event validation and enrichment (Python)
3. Event routing to appropriate Kafka topics
4. Consumer groups processing events for different analytics dimensions
5. Aggregation and storage in ClickHouse for OLAP queries
6. Real-time dashboard updates via WebSocket

The system currently handles approximately 50,000 events per second during peak hours, with a P99 latency of 200ms for the ingestion pipeline. Your goal is to reduce this to under 100ms while maintaining data consistency and reliability.

Some specific areas you've identified for optimization:
- The validation step is doing synchronous database lookups for user enrichment
- The Kafka producer is using default configuration without batching
- The ClickHouse inserts are happening one row at a time instead of using batch inserts
- The WebSocket updates are being sent individually instead of being batched

You also need to consider the operational aspects:
- Monitoring and alerting for the pipeline health
- Graceful degradation when downstream services are unavailable
- Data backfill capabilities for historical data corrections
- Schema evolution strategy for the event format

The team is using Python 3.12 with asyncio for the event processing, and they've recently migrated from Celery to a custom task queue built on top of Redis Streams. The codebase follows a clean architecture pattern with clear separation between domain logic and infrastructure concerns."""


def _build_cold_prefix_prompt(question: str) -> str:
    return f"{_LONG_PREFIX}\n\nNow, please answer the following question concisely:\n{question}"


def _build_warm_prefix_prompt(question: str) -> str:
    return f"{_LONG_PREFIX}\n\nNow, please answer the following question concisely:\n{question}"


def _build_breaker_prefix_prompt(question: str) -> str:
    broken_prefix = "You are a junior developer working on a simple todo list application." + _LONG_PREFIX[50:]
    return f"{broken_prefix}\n\nNow, please answer the following question concisely:\n{question}"


async def _run_single_probe(
    session: aiohttp.ClientSession,
    config: dict,
    prompt: str,
    probe_name: str,
    timeout_seconds: int = 60,
) -> ProbeResult:
    """执行单个 probe 请求"""
    adapter = get_adapter(config.get("protocol", "anthropic"))

    probe_config = dict(config)
    probe_config["user_prompt"] = prompt
    probe_config["max_tokens"] = 100
    probe_config["timeout"] = timeout_seconds

    url = adapter.build_url(probe_config)
    headers = adapter.build_headers(probe_config)
    payload = adapter.build_payload(probe_config)
    payload["temperature"] = 0.0

    result = ProbeResult(name=probe_name)
    start = time.monotonic()

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with session.post(url, json=payload, headers=headers, timeout=timeout) as resp:
            if resp.status != 200:
                body = await resp.text()
                result.status = "error"
                result.error = f"HTTP {resp.status}: {body[:200]}"
                result.latency_ms = (time.monotonic() - start) * 1000
                return result

            buffer = ""
            async for chunk in resp.content:
                text = chunk.decode("utf-8", errors="replace")
                buffer += text

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data: "):
                        continue

                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        continue

                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")

                    if event_type == "message_start":
                        msg = event.get("message", {})
                        usage = msg.get("usage", {})
                        result.input_tokens = usage.get("input_tokens", 0)
                        result.cache_read_tokens = usage.get("cache_read_input_tokens", 0)
                        result.cache_creation_tokens = usage.get("cache_creation_input_tokens", 0)

                    elif event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            if len(result.response_preview) < 1000:
                                result.response_preview += delta["text"]

                    elif event_type == "message_delta":
                        usage = event.get("usage", {})
                        result.output_tokens = usage.get("output_tokens", 0)

                    elif event_type == "message_stop":
                        result.status = "passed"

            result.latency_ms = (time.monotonic() - start) * 1000

            if result.status == "pending":
                result.status = "passed"

    except asyncio.TimeoutError:
        result.latency_ms = (time.monotonic() - start) * 1000
        result.status = "timeout"
        result.error = f"Probe timed out after {timeout_seconds}s"
    except aiohttp.ClientError as e:
        result.latency_ms = (time.monotonic() - start) * 1000
        result.status = "error"
        result.error = f"Connection error: {str(e)}"
    except Exception as e:
        result.latency_ms = (time.monotonic() - start) * 1000
        result.status = "error"
        result.error = f"Unexpected error: {str(e)}"

    return result


def classify_cache_type(probe: ProbeResult) -> str:
    """根据 probe 结果判断缓存类型"""
    if probe.identical_request and probe.latency_ms < 100 and probe.cache_read_tokens == 0:
        return "response_cache"
    if probe.cache_read_tokens > 0:
        return "prompt_cache"
    return "unknown_cache"


def build_cache_report(probes: list[ProbeResult]) -> dict:
    """根据所有 probe 结果构建缓存诊断报告"""

    cold = next((p for p in probes if p.name == "cold_prefix"), None)
    warm = next((p for p in probes if p.name == "warm_prefix"), None)
    breaker = next((p for p in probes if p.name == "breaker_prefix"), None)
    identical = next((p for p in probes if p.name == "repeat_identical"), None)

    report = {
        "prompt_cache": {"status": "inconclusive", "hit_rate": 0, "evidence": "none", "confidence": 0},
        "response_cache": {"status": "not_detected", "confidence": 0, "evidence": []},
    }

    # --- Prompt Cache ---
    if warm and warm.status == "passed" and cold and cold.status == "passed":
        if warm.input_tokens > 0 and (warm.cache_read_tokens > 0 or warm.cache_creation_tokens > 0):
            hit_rate = warm.cache_read_tokens / warm.input_tokens if warm.input_tokens > 0 else 0
            breaker_confirms = True
            if breaker and breaker.status == "passed" and breaker.input_tokens > 0:
                breaker_hit = breaker.cache_read_tokens / breaker.input_tokens
                if breaker_hit > 0.5:
                    breaker_confirms = False

            cost_saving = hit_rate * 0.9
            report["prompt_cache"] = {
                "status": "supported" if breaker_confirms else "warning",
                "hit_rate": round(hit_rate, 4),
                "estimated_cost_saving": round(cost_saving, 4),
                "evidence": "usage_fields",
                "confidence": 0.9 if breaker_confirms else 0.5,
            }

        elif warm.latency_ms > 0 and cold.latency_ms > 0:
            speedup = 1 - (warm.latency_ms / cold.latency_ms)
            if speedup > 0:
                hit_rate = min(speedup * 1.2, 1.0)
                report["prompt_cache"] = {
                    "status": "estimated",
                    "hit_rate": round(hit_rate, 4),
                    "estimated_cost_saving": round(hit_rate * 0.9, 4),
                    "evidence": "latency_estimation",
                    "confidence": 0.4,
                }

    # --- Response Cache ---
    if identical and identical.status == "passed" and identical.identical_request:
        if identical.latency_ms < 100:
            report["response_cache"] = {
                "status": "suspected",
                "confidence": 0.7 + max(0, (100 - identical.latency_ms) / 100) * 0.25,
                "evidence": [f"identical_request_sub_{int(identical.latency_ms)}ms"],
            }
        elif identical.latency_ms < 300:
            report["response_cache"] = {
                "status": "possible",
                "confidence": 0.4,
                "evidence": ["identical_request_sub_300ms"],
            }

    return report


def compute_overall_status(report: dict) -> tuple[str, str, float]:
    """根据缓存报告计算总体状态、风险等级和置信度"""
    prompt_status = report.get("prompt_cache", {}).get("status", "inconclusive")
    response_status = report.get("response_cache", {}).get("status", "not_detected")
    prompt_confidence = report.get("prompt_cache", {}).get("confidence", 0)

    if response_status == "suspected":
        return "warning", "medium", 0.7

    if prompt_status == "supported":
        return "passed", "low", prompt_confidence
    elif prompt_status == "estimated":
        return "passed", "low", prompt_confidence
    elif prompt_status == "warning":
        return "warning", "medium", prompt_confidence
    else:
        return "inconclusive", "unknown", 0.3


async def run_cache_diagnostics(
    config: dict,
    timeout_seconds: int = 60,
) -> CacheDiagnosticResult:
    """运行完整的缓存诊断流程"""
    result = CacheDiagnosticResult()

    connector = aiohttp.TCPConnector(limit=1)
    async with aiohttp.ClientSession(connector=connector) as session:
        # 1. cold_prefix
        cold_probe = await _run_single_probe(
            session, config,
            prompt=_build_cold_prefix_prompt("What is the capital of France? Answer in one word."),
            probe_name="cold_prefix",
            timeout_seconds=timeout_seconds,
        )
        result.probes.append(cold_probe)

        if cold_probe.status == "error":
            result.status = "error"
            result.report = {"error": cold_probe.error}
            return result

        # 2. warm_prefix
        warm_probe = await _run_single_probe(
            session, config,
            prompt=_build_warm_prefix_prompt("What is 2+2? Answer in one word."),
            probe_name="warm_prefix",
            timeout_seconds=timeout_seconds,
        )
        result.probes.append(warm_probe)

        # 3. breaker_prefix
        breaker_probe = await _run_single_probe(
            session, config,
            prompt=_build_breaker_prefix_prompt("What is the capital of France? Answer in one word."),
            probe_name="breaker_prefix",
            timeout_seconds=timeout_seconds,
        )
        result.probes.append(breaker_probe)

        # 4. repeat_identical
        identical_probe = await _run_single_probe(
            session, config,
            prompt=_build_cold_prefix_prompt("What is the capital of France? Answer in one word."),
            probe_name="repeat_identical",
            timeout_seconds=timeout_seconds,
        )
        identical_probe.identical_request = True
        result.probes.append(identical_probe)

    result.report = build_cache_report(result.probes)
    status, risk, confidence = compute_overall_status(result.report)
    result.status = status
    result.overall_risk = risk
    result.confidence = confidence

    return result
