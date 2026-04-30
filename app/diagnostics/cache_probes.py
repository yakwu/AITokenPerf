"""缓存诊断探针 — 复用 channel_diagnostics.py"""

import logging
import aiohttp
from app.diagnostics.models import ProbeResult, CategoryResult
from app.diagnostics.runner import register_category
from app.channel_diagnostics import run_cache_diagnostics

log = logging.getLogger("diagnostics.cache")


@register_category("cache")
async def run_cache_probes(config: dict, session: aiohttp.ClientSession, run_tag: str, timeout: int) -> CategoryResult:
    try:
        result = await run_cache_diagnostics(config, timeout_seconds=timeout)
    except Exception as e:
        return CategoryResult(category="cache", display_name="Prompt Cache", status="error", summary={"error": str(e)})

    probes = []
    for p in result.probes:
        probes.append(ProbeResult(
            name=p.name, display_name=_label(p.name), status=p.status,
            latency_ms=p.latency_ms, input_tokens=p.input_tokens, output_tokens=p.output_tokens,
            cache_read_tokens=p.cache_read_tokens, cache_creation_tokens=p.cache_creation_tokens,
            identical_request=p.identical_request, error=p.error, response_preview=p.response_preview,
            raw_usage=p.raw_usage, request_preview=p.request_preview, sent_chars=p.sent_chars,
            expected_system_tokens=p.expected_system_tokens, expected_user_tokens=p.expected_user_tokens,
            expected_total_tokens=p.expected_total_tokens,
        ))

    cat_status = result.status
    if cat_status in ("supported", "partial"):
        cat_status = "passed"
    elif cat_status in ("no_usage_fields", "no_cache"):
        cat_status = "warning"

    return CategoryResult(
        category="cache", display_name="Prompt Cache", status=cat_status, probes=probes,
        summary={
            "hit_rate": result.report.get("prompt_cache", {}).get("hit_rate", 0),
            "confidence": result.confidence,
            "prompt_cache_status": result.report.get("prompt_cache", {}).get("status", "inconclusive"),
            "response_cache": result.report.get("response_cache", {}),
            "proxy_cache": result.report.get("proxy_cache", {}),
            "prompt_cache": result.report.get("prompt_cache", {}),
        },
    )


def _label(name: str) -> str:
    return {"cold_prefix": "首次请求", "warm_prefix": "再次请求", "breaker_prefix": "不同内容", "repeat_identical": "重发首次"}.get(name, name)
