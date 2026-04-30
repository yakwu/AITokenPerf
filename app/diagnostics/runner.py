"""统一探针调度器"""

import asyncio
import logging
import uuid
from typing import Callable, Awaitable, Optional

import aiohttp

from app.diagnostics.models import ProbeResult, CategoryResult, DiagnosticReport

log = logging.getLogger("diagnostics")

CategoryRunner = Callable[[dict, aiohttp.ClientSession, str, int], Awaitable[CategoryResult]]

_CATEGORY_REGISTRY: dict[str, CategoryRunner] = {}


def register_category(category_id: str):
    """装饰器：注册一个探针类别"""
    def decorator(fn: CategoryRunner):
        _CATEGORY_REGISTRY[category_id] = fn
        return fn
    return decorator


def get_available_categories() -> list[str]:
    return list(_CATEGORY_REGISTRY.keys())


async def run_diagnostics(
    config: dict,
    categories: Optional[list[str]] = None,
    timeout_seconds: int = 60,
) -> DiagnosticReport:
    """运行统一诊断"""
    # Import all probe modules to trigger registration
    from app.diagnostics import connectivity, streaming, context, tool_use, structured, cache_probes  # noqa: F401

    run_tag = uuid.uuid4().hex[:8]
    model = config.get("model", "")

    if categories is None or not categories:
        categories = list(_CATEGORY_REGISTRY.keys())

    report = DiagnosticReport(model=model, run_tag=run_tag)

    connector = aiohttp.TCPConnector(limit=5)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        cat_ids = []
        for cat_id in categories:
            if cat_id not in _CATEGORY_REGISTRY:
                log.warning("Unknown category: %s", cat_id)
                continue
            runner = _CATEGORY_REGISTRY[cat_id]
            tasks.append(runner(config, session, run_tag, timeout_seconds))
            cat_ids.append(cat_id)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for cat_id, result in zip(cat_ids, results):
            if isinstance(result, Exception):
                cat = CategoryResult(
                    category=cat_id,
                    display_name=cat_id,
                    status="error",
                    summary={"error": str(result)},
                )
            else:
                cat = result
            report.categories.append(cat)

    # Compute overall status
    statuses = [c.status for c in report.categories if c.status != "pending"]
    if not statuses:
        report.overall_status = "error"
    elif all(s == "passed" for s in statuses):
        report.overall_status = "passed"
        report.overall_risk = "low"
    elif any(s == "error" for s in statuses):
        report.overall_status = "error"
        report.overall_risk = "high"
    elif any(s == "failed" for s in statuses):
        report.overall_status = "failed"
        report.overall_risk = "medium"
    elif any(s == "warning" for s in statuses):
        report.overall_status = "warning"
        report.overall_risk = "medium"
    else:
        report.overall_status = "passed"
        report.overall_risk = "low"

    confidences = []
    for cat in report.categories:
        conf = cat.summary.get("confidence")
        if conf is not None:
            confidences.append(conf)
    report.confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.5

    return report
