#!/usr/bin/env python3
"""渠道诊断核心模块 — 缓存命中率检测

Probe 策略：
- cold_prefix: 首次请求，建立缓存（应 miss）
- warm_prefix x3: 相同前缀不同问题，应命中缓存
- warm_append x2: system prompt 尾部追加内容，前缀仍应命中
- breaker_prefix: 修改前缀开头，应 miss
- repeat_identical: 完全相同请求，检测 response cache
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

from app.protocols import get_adapter, detect_protocol

log = logging.getLogger("channel_diagnostics")

# 采样次数
WARM_SAMPLE_COUNT = 3
APPEND_SAMPLE_COUNT = 2

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

# 追加到 system prompt 尾部的内容（不影响前缀缓存）
_APPEND_TEXT = """

Additional context: You should always respond in a concise, direct manner. Focus on the most important points and avoid unnecessary elaboration. When providing technical recommendations, prioritize practical solutions over theoretical perfection."""

# warm_prefix 采样问题列表
_WARM_QUESTIONS = [
    "What is 2+2? Answer in one word.",
    "What color is the sky? Answer in one word.",
    "What is the boiling point of water in Celsius? Answer with just the number.",
]

# warm_append 采样问题列表
_APPEND_QUESTIONS = [
    "What is the largest planet in our solar system? Answer in one word.",
    "What programming language is known for its coffee logo? Answer in one word.",
]


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


# --- Prompt 构建 ---

def _build_prefix_prompt(system_prompt: str, question: str) -> dict:
    """构建 probe 的 system + user prompt 配置"""
    return {
        "system_prompt": system_prompt,
        "user_prompt": question,
    }


def cold_prefix_prompts(question: str) -> dict:
    return _build_prefix_prompt(_LONG_PREFIX, question)


def warm_prefix_prompts(question: str) -> dict:
    return _build_prefix_prompt(_LONG_PREFIX, question)


def warm_append_prompts(question: str) -> dict:
    return _build_prefix_prompt(_LONG_PREFIX + _APPEND_TEXT, question)


def breaker_prefix_prompts(question: str) -> dict:
    broken = "You are a junior developer working on a simple todo list application." + _LONG_PREFIX[50:]
    return _build_prefix_prompt(broken, question)


# --- 单个 probe 执行 ---

async def _run_single_probe(
    session: aiohttp.ClientSession,
    config: dict,
    system_prompt: str,
    user_prompt: str,
    probe_name: str,
    timeout_seconds: int = 60,
) -> ProbeResult:
    """执行单个 probe 请求"""
    protocol = config.get("protocol") or detect_protocol(config.get("model", ""), config.get("provider", ""))
    adapter = get_adapter(protocol)

    probe_config = dict(config)
    probe_config["system_prompt"] = system_prompt
    probe_config["user_prompt"] = user_prompt
    probe_config["max_tokens"] = 100
    probe_config["timeout"] = timeout_seconds
    probe_config["cache_test"] = True  # 诊断探针需要测试真实缓存，不追加 nonce

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


# --- 缓存命中判定 ---

def _is_cache_hit(probe: ProbeResult) -> bool:
    """判断单个 probe 是否命中了 prompt cache"""
    # 方式1：usage 字段明确显示 cache_read > 0
    if probe.cache_read_tokens > 0:
        return True
    # 方式2：无 usage 字段时，用延迟判断（warm 请求比 cold 快 30%+）
    # 这个需要外部传入 cold 延迟做基准，这里只用 usage 判断
    return False


def _compute_hit_rate(probes: list[ProbeResult]) -> tuple[float, str]:
    """计算一组 probe 的缓存命中率

    Returns: (hit_rate, evidence_type)
    """
    valid = [p for p in probes if p.status == "passed"]
    if not valid:
        return 0.0, "none"

    # 优先用 usage 字段
    has_usage = any(p.cache_read_tokens > 0 or p.cache_creation_tokens > 0 for p in valid)
    if has_usage:
        hits = sum(1 for p in valid if _is_cache_hit(p))
        return hits / len(valid), "usage_fields"

    # 无 usage 字段时，返回 0（延迟估算需要 cold 基准，在外层处理）
    return 0.0, "no_usage_fields"


def _compute_avg_latency(probes: list[ProbeResult]) -> float:
    """计算平均延迟"""
    valid = [p for p in probes if p.status == "passed"]
    if not valid:
        return 0
    return sum(p.latency_ms for p in valid) / len(valid)


# --- 报告生成 ---

def build_cache_report(probes: list[ProbeResult]) -> dict:
    """根据所有 probe 结果构建缓存诊断报告"""

    cold = [p for p in probes if p.name == "cold_prefix"]
    warm = [p for p in probes if p.name == "warm_prefix"]
    append = [p for p in probes if p.name == "warm_append"]
    breaker = [p for p in probes if p.name == "breaker_prefix"]
    identical = [p for p in probes if p.name == "repeat_identical"]

    report = {
        "prompt_cache": {
            "status": "inconclusive",
            "hit_rate": 0,
            "sample_count": len(warm) + len(append),
            "evidence": "none",
            "confidence": 0,
            "warm_samples": [],
            "append_samples": [],
            "append_consistent": None,
        },
        "response_cache": {"status": "not_detected", "confidence": 0, "evidence": []},
    }

    cold_latency = _compute_avg_latency(cold) if cold else 0

    # --- Warm prefix 命中率 ---
    if warm and cold:
        warm_hit_rate, warm_evidence = _compute_hit_rate(warm)
        warm_avg_latency = _compute_avg_latency(warm)

        # 每个样本的详情
        warm_sample_details = []
        for p in warm:
            warm_sample_details.append({
                "status": p.status,
                "cache_read_tokens": p.cache_read_tokens,
                "input_tokens": p.input_tokens,
                "latency_ms": round(p.latency_ms, 1),
                "hit": _is_cache_hit(p),
            })

        # 无 usage 字段时不做延迟猜（延迟差异不可靠），保持 hit_rate=0

        report["prompt_cache"]["warm_samples"] = warm_sample_details

    else:
        warm_hit_rate, warm_evidence = 0, "no_samples"
        warm_avg_latency = 0

    # --- Append 命中率（前缀缓存验证）---
    append_hit_rate = 0
    if append and cold:
        append_hit_rate, _ = _compute_hit_rate(append)
        append_sample_details = []
        for p in append:
            append_sample_details.append({
                "status": p.status,
                "cache_read_tokens": p.cache_read_tokens,
                "input_tokens": p.input_tokens,
                "latency_ms": round(p.latency_ms, 1),
                "hit": _is_cache_hit(p),
            })
        report["prompt_cache"]["append_samples"] = append_sample_details

        # append 一致性：warm 命中但 append 不命中，可能是渠道切换、缓存过期、或非真实前缀缓存
        if warm_hit_rate > 0.5 and append_hit_rate < 0.3:
            report["prompt_cache"]["append_consistent"] = False
        elif warm_hit_rate > 0.5 and append_hit_rate > 0.3:
            report["prompt_cache"]["append_consistent"] = True

    # --- 综合 prompt cache 结果 ---
    total_samples = len(warm) + len(append)
    if total_samples > 0:
        total_valid_warm = len([p for p in warm if p.status == "passed"])
        total_valid_append = len([p for p in append if p.status == "passed"])
        total_valid = total_valid_warm + total_valid_append

        if total_valid > 0:
            # 综合命中率 = 总命中数 / 总请求数
            warm_hits = sum(1 for p in warm if p.status == "passed" and _is_cache_hit(p))
            append_hits = sum(1 for p in append if p.status == "passed" and _is_cache_hit(p))
            combined_hit_rate = (warm_hits + append_hits) / total_valid

            # Breaker 验证
            breaker_confirms = True
            if breaker:
                breaker_hit_rate, _ = _compute_hit_rate(breaker)
                if breaker_hit_rate > 0.5:
                    breaker_confirms = False

            # Append 一致性检查
            append_ok = report["prompt_cache"]["append_consistent"]
            if append_ok is False:
                # warm 命中但 append 不命中 → 可能是渠道切换、缓存过期、或非真实前缀缓存
                status = "warning"
                confidence = 0.4
            elif breaker_confirms and combined_hit_rate > 0.5:
                status = "supported"
                confidence = 0.9
            elif breaker_confirms and combined_hit_rate > 0:
                status = "partial"
                confidence = 0.7
            elif warm_evidence == "no_usage_fields":
                # API 不返回 cache usage 字段，无法判断
                status = "no_usage_fields"
                confidence = 0.2
            else:
                status = "inconclusive"
                confidence = 0.3

            cost_saving = combined_hit_rate * 0.9
            report["prompt_cache"].update({
                "status": status,
                "hit_rate": round(combined_hit_rate, 4),
                "estimated_cost_saving": round(cost_saving, 4),
                "evidence": warm_evidence,
                "confidence": confidence,
            })

    # --- Response Cache ---
    if identical:
        identical_probe = identical[0]
        if identical_probe.status == "passed" and identical_probe.identical_request:
            if identical_probe.latency_ms < 100:
                report["response_cache"] = {
                    "status": "suspected",
                    "confidence": 0.7 + max(0, (100 - identical_probe.latency_ms) / 100) * 0.25,
                    "evidence": [f"identical_request_sub_{int(identical_probe.latency_ms)}ms"],
                }
            elif identical_probe.latency_ms < 300:
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
    append_consistent = report.get("prompt_cache", {}).get("append_consistent")

    # append 不一致是风险信号
    if append_consistent is False:
        return "warning", "medium", 0.5

    if response_status == "suspected":
        return "warning", "medium", 0.7

    if prompt_status == "supported":
        return "passed", "low", prompt_confidence
    elif prompt_status == "partial":
        return "passed", "low", prompt_confidence
    elif prompt_status == "no_usage_fields":
        return "no_usage_fields", "unknown", 0.2
    elif prompt_status == "warning":
        return "warning", "medium", prompt_confidence
    else:
        return "inconclusive", "unknown", 0.3


# --- 主入口 ---

async def run_cache_diagnostics(
    config: dict,
    timeout_seconds: int = 60,
) -> CacheDiagnosticResult:
    """运行完整的缓存诊断流程

    流程：
    1. cold_prefix — 建立缓存基准
    2. warm_prefix x3 — 多次采样缓存命中
    3. warm_append x2 — system prompt 追加内容，验证前缀缓存
    4. breaker_prefix — 修改前缀，验证缓存失效
    5. repeat_identical — 完全相同请求，检测 response cache
    """
    result = CacheDiagnosticResult()

    connector = aiohttp.TCPConnector(limit=1)
    async with aiohttp.ClientSession(connector=connector) as session:

        # 1. cold_prefix
        prompts = cold_prefix_prompts("What is the capital of France? Answer in one word.")
        cold_probe = await _run_single_probe(
            session, config,
            system_prompt=prompts["system_prompt"],
            user_prompt=prompts["user_prompt"],
            probe_name="cold_prefix",
            timeout_seconds=timeout_seconds,
        )
        result.probes.append(cold_probe)

        if cold_probe.status == "error":
            result.status = "error"
            result.report = {"error": cold_probe.error}
            return result

        # 2. warm_prefix x3
        for i, question in enumerate(_WARM_QUESTIONS[:WARM_SAMPLE_COUNT]):
            prompts = warm_prefix_prompts(question)
            probe = await _run_single_probe(
                session, config,
                system_prompt=prompts["system_prompt"],
                user_prompt=prompts["user_prompt"],
                probe_name="warm_prefix",
                timeout_seconds=timeout_seconds,
            )
            result.probes.append(probe)

        # 3. warm_append x2
        for i, question in enumerate(_APPEND_QUESTIONS[:APPEND_SAMPLE_COUNT]):
            prompts = warm_append_prompts(question)
            probe = await _run_single_probe(
                session, config,
                system_prompt=prompts["system_prompt"],
                user_prompt=prompts["user_prompt"],
                probe_name="warm_append",
                timeout_seconds=timeout_seconds,
            )
            result.probes.append(probe)

        # 4. breaker_prefix
        prompts = breaker_prefix_prompts("What is the capital of France? Answer in one word.")
        breaker_probe = await _run_single_probe(
            session, config,
            system_prompt=prompts["system_prompt"],
            user_prompt=prompts["user_prompt"],
            probe_name="breaker_prefix",
            timeout_seconds=timeout_seconds,
        )
        result.probes.append(breaker_probe)

        # 5. repeat_identical
        prompts = cold_prefix_prompts("What is the capital of France? Answer in one word.")
        identical_probe = await _run_single_probe(
            session, config,
            system_prompt=prompts["system_prompt"],
            user_prompt=prompts["user_prompt"],
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
