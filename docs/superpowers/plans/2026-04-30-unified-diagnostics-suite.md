# Unified Diagnostics Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the channel diagnostics system from a cache-only probe into a modular quality suite with 6 test categories (connectivity, streaming, context, tool_use, structured, cache), selectable categories in the API, and a category-based UI.

**Architecture:** Create a new `app/diagnostics/` package with a shared runner, models, and per-category probe modules. The existing `app/channel_diagnostics.py` is preserved as a backward-compatible wrapper. The API endpoint gains a `categories` parameter. The frontend DiagnosticCard renders results by category.

**Tech Stack:** Python asyncio, aiohttp, FastAPI, Vue 3, existing test patterns (pytest + unittest.mock)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `app/diagnostics/__init__.py` | Re-export `run_diagnostics` |
| Create | `app/diagnostics/models.py` | `ProbeResult`, `CategoryResult`, `DiagnosticReport` dataclasses |
| Create | `app/diagnostics/runner.py` | Unified probe dispatcher, shared HTTP session, timeout handling |
| Create | `app/diagnostics/cache_probes.py` | Migrate 7 cache probes from `channel_diagnostics.py` |
| Create | `app/diagnostics/connectivity.py` | Case01: single non-stream request |
| Create | `app/diagnostics/streaming.py` | Case02: stream long output |
| Create | `app/diagnostics/context.py` | Case03: multi-round context |
| Create | `app/diagnostics/tool_use.py` | Case04: function calling |
| Create | `app/diagnostics/structured.py` | Case05: structured JSON output |
| Modify | `app/channel_diagnostics.py` | Add deprecation wrapper importing from new package |
| Modify | `app/server.py:961-1049` | Update `/api/channel-diagnostics` to accept `categories` |
| Modify | `frontend/src/components/SiteTestTab.vue:150-188` | Add category selector checkboxes |
| Modify | `frontend/src/components/DiagnosticCard.vue` | Render category-based results |
| Modify | `frontend/src/utils/diagnosticUtils.js` | Add new probe labels and category helpers |
| Create | `tests/test_diagnostics_runner.py` | Test runner dispatch and category filtering |
| Create | `tests/test_diagnostics_connectivity.py` | Test connectivity probe |
| Create | `tests/test_diagnostics_streaming.py` | Test streaming probe |
| Create | `tests/test_diagnostics_context.py` | Test context probe |
| Create | `tests/test_diagnostics_tool_use.py` | Test tool_use probe |
| Create | `tests/test_diagnostics_structured.py` | Test structured probe |

---

## Task 1: Create diagnostics package with shared models and runner

**Files:**
- Create: `app/diagnostics/__init__.py`
- Create: `app/diagnostics/models.py`
- Create: `app/diagnostics/runner.py`

- [ ] **Step 1: Create `app/diagnostics/models.py`**

```python
"""统一诊断数据模型"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProbeResult:
    """单个探针的结果"""
    name: str = ""
    display_name: str = ""
    status: str = "pending"  # pending | passed | failed | error | timeout | inconclusive
    latency_ms: float = 0
    ttft_ms: Optional[float] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    detail: str = ""
    error: Optional[str] = None
    response_preview: str = ""
    raw_usage: dict = field(default_factory=dict)
    request_preview: str = ""
    sent_chars: int = 0
    expected_system_tokens: int = 0
    expected_user_tokens: int = 0
    expected_total_tokens: int = 0
    # cache probes 专用
    identical_request: bool = False


@dataclass
class CategoryResult:
    """一个测试类别的结果"""
    category: str = ""
    display_name: str = ""
    status: str = "pending"  # passed | warning | failed | error
    probes: list = field(default_factory=list)  # list[ProbeResult]
    summary: dict = field(default_factory=dict)


@dataclass
class DiagnosticReport:
    """完整诊断报告"""
    categories: list = field(default_factory=list)  # list[CategoryResult]
    overall_status: str = "pending"
    overall_risk: str = "unknown"
    confidence: float = 0.0
    model: str = ""
    run_tag: str = ""
```

- [ ] **Step 2: Create `app/diagnostics/runner.py`**

```python
"""统一探针调度器"""

import asyncio
import logging
import uuid
from typing import Callable, Awaitable, Optional

import aiohttp

from app.diagnostics.models import ProbeResult, CategoryResult, DiagnosticReport

log = logging.getLogger("diagnostics")

# 类别注册表：category_id -> runner function
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
    """运行统一诊断

    Args:
        config: 包含 base_url, api_key, model, protocol, provider 等
        categories: 要运行的类别列表，None 表示全部
        timeout_seconds: 每个探针的超时时间
    """
    from app.diagnostics import connectivity, streaming, context, tool_use, structured, cache_probes  # noqa: F401

    run_tag = uuid.uuid4().hex[:8]
    model = config.get("model", "")

    if categories is None or not categories:
        categories = list(_CATEGORY_REGISTRY.keys())

    report = DiagnosticReport(model=model, run_tag=run_tag)

    connector = aiohttp.TCPConnector(limit=5)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for cat_id in categories:
            if cat_id not in _CATEGORY_REGISTRY:
                log.warning("Unknown category: %s", cat_id)
                continue
            runner = _CATEGORY_REGISTRY[cat_id]
            tasks.append(runner(config, session, run_tag, timeout_seconds))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for cat_id, result in zip(categories, results):
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

    # 计算综合状态
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

    # 置信度：取所有类别的平均
    confidences = []
    for cat in report.categories:
        conf = cat.summary.get("confidence")
        if conf is not None:
            confidences.append(conf)
    report.confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.5

    return report
```

- [ ] **Step 3: Create `app/diagnostics/__init__.py`**

```python
"""统一渠道诊断包"""

from app.diagnostics.models import ProbeResult, CategoryResult, DiagnosticReport
from app.diagnostics.runner import run_diagnostics, get_available_categories

__all__ = ["ProbeResult", "CategoryResult", "DiagnosticReport", "run_diagnostics", "get_available_categories"]
```

- [ ] **Step 4: Run import test**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -c "from app.diagnostics import run_diagnostics, get_available_categories; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add app/diagnostics/
git commit -m "feat: 创建统一诊断包 models + runner 框架"
```

---

## Task 2: Migrate cache probes to new package

**Files:**
- Create: `app/diagnostics/cache_probes.py`

- [ ] **Step 1: Create `app/diagnostics/cache_probes.py`**

从 `app/channel_diagnostics.py` 迁移缓存探针逻辑。保留所有常量（`_LONG_PREFIX`, `_BREAKER_PREFIX`, `_WARM_QUESTIONS`）和核心函数（`_run_single_probe`, `_extract_cache_tokens`, `build_cache_report`, `compute_overall_status`），但改为注册到新 runner。

关键变化：
- 新增 `@register_category("cache")` 装饰器
- runner 函数签名: `async def run(config, session, run_tag, timeout) -> CategoryResult`
- 复用 `channel_diagnostics.py` 中的 `_run_single_probe`（通过 import）
- ProbeResult 字段映射：旧 `ProbeResult` -> 新 `ProbeResult`（字段名对齐）

```python
"""缓存诊断探针 — 从 channel_diagnostics.py 迁移"""

import asyncio
import logging

import aiohttp

from app.diagnostics.models import ProbeResult, CategoryResult
from app.diagnostics.runner import register_category
from app.channel_diagnostics import (
    run_cache_diagnostics,
    WARM_SAMPLE_COUNT,
)

log = logging.getLogger("diagnostics.cache")


@register_category("cache")
async def run_cache_probes(
    config: dict, session: aiohttp.ClientSession, run_tag: str, timeout: int
) -> CategoryResult:
    """运行缓存诊断（复用现有逻辑）"""
    try:
        result = await run_cache_diagnostics(config, timeout_seconds=timeout)
    except Exception as e:
        return CategoryResult(
            category="cache",
            display_name="Prompt Cache",
            status="error",
            summary={"error": str(e)},
        )

    # 转换 ProbeResult 格式
    probes = []
    for p in result.probes:
        probes.append(ProbeResult(
            name=p.name,
            display_name=_cache_probe_label(p.name),
            status=p.status,
            latency_ms=p.latency_ms,
            input_tokens=p.input_tokens,
            output_tokens=p.output_tokens,
            cache_read_tokens=p.cache_read_tokens,
            cache_creation_tokens=p.cache_creation_tokens,
            identical_request=p.identical_request,
            error=p.error,
            response_preview=p.response_preview,
            raw_usage=p.raw_usage,
            request_preview=p.request_preview,
            sent_chars=p.sent_chars,
            expected_system_tokens=p.expected_system_tokens,
            expected_user_tokens=p.expected_user_tokens,
            expected_total_tokens=p.expected_total_tokens,
        ))

    cat_status = result.status
    if cat_status in ("supported", "partial"):
        cat_status = "passed"
    elif cat_status in ("no_usage_fields", "no_cache"):
        cat_status = "warning"

    return CategoryResult(
        category="cache",
        display_name="Prompt Cache",
        status=cat_status,
        probes=probes,
        summary={
            "hit_rate": result.report.get("prompt_cache", {}).get("hit_rate", 0),
            "confidence": result.confidence,
            "prompt_cache_status": result.report.get("prompt_cache", {}).get("status", "inconclusive"),
            "response_cache": result.report.get("response_cache", {}),
            "proxy_cache": result.report.get("proxy_cache", {}),
            "prompt_cache": result.report.get("prompt_cache", {}),
        },
    )


def _cache_probe_label(name: str) -> str:
    labels = {
        "cold_prefix": "首次请求",
        "warm_prefix": "再次请求",
        "breaker_prefix": "不同内容",
        "repeat_identical": "重发首次",
    }
    return labels.get(name, name)
```

- [ ] **Step 2: Run import test**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -c "from app.diagnostics.cache_probes import run_cache_probes; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add app/diagnostics/cache_probes.py
git commit -m "feat: 迁移缓存探针到统一诊断包"
```

---

## Task 3: Add connectivity probe (case01)

**Files:**
- Create: `app/diagnostics/connectivity.py`
- Create: `tests/test_diagnostics_connectivity.py`

- [ ] **Step 1: Write the failing test**

```python
"""测试连通性探针"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.diagnostics.models import ProbeResult, CategoryResult


class TestConnectivityProbe:
    """连通性探针测试"""

    @pytest.mark.asyncio
    async def test_connectivity_passes_on_valid_response(self):
        """正常响应应返回 passed"""
        from app.diagnostics.connectivity import run_connectivity_probes

        mock_response = MagicMock()
        mock_response.status = 200

        async def mock_iter():
            yield _make_sse_event("message_start", usage={"input_tokens": 10})
            yield _make_sse_event("content_block_delta", delta={"type": "text_delta", "text": "hello"})
            yield _make_sse_event("message_delta", usage={"output_tokens": 5}, delta={"stop_reason": "end_turn"})
            yield _make_sse_event("message_stop")

        mock_response.content = mock_iter()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_response)

        config = {
            "base_url": "https://api.anthropic.com",
            "api_key": "test-key",
            "model": "claude-sonnet-4-20250514",
            "protocol": "anthropic",
        }

        result = await run_connectivity_probes(config, mock_session, "test123", 30)
        assert isinstance(result, CategoryResult)
        assert result.category == "connectivity"
        assert result.status == "passed"
        assert len(result.probes) == 1
        assert result.probes[0].status == "passed"

    @pytest.mark.asyncio
    async def test_connectivity_fails_on_http_error(self):
        """HTTP 错误应返回 failed"""
        from app.diagnostics.connectivity import run_connectivity_probes

        mock_response = MagicMock()
        mock_response.status = 401
        mock_response.text = AsyncMock(return_value="Unauthorized")

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        config = {
            "base_url": "https://api.anthropic.com",
            "api_key": "bad-key",
            "model": "claude-sonnet-4-20250514",
            "protocol": "anthropic",
        }

        result = await run_connectivity_probes(config, mock_session, "test123", 30)
        assert result.status == "failed"


def _make_sse_event(event_type: str, **kwargs) -> bytes:
    data = json.dumps({"type": event_type, **kwargs})
    return f"data: {data}\n\n".encode()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_diagnostics_connectivity.py -v
```

- [ ] **Step 3: Implement connectivity probe**

```python
"""连通性探针 — 单轮非流式请求"""

import json
import logging
import time

import aiohttp

from app.diagnostics.models import ProbeResult, CategoryResult
from app.diagnostics.runner import register_category
from app.protocols import detect_protocol, get_adapter

log = logging.getLogger("diagnostics.connectivity")


@register_category("connectivity")
async def run_connectivity_probes(
    config: dict, session: aiohttp.ClientSession, run_tag: str, timeout: int
) -> CategoryResult:
    """连通性测试：发一次非流式请求，验证能正常返回"""
    protocol = config.get("protocol") or detect_protocol(config.get("model", ""), config.get("provider", ""))
    adapter = get_adapter(protocol)

    probe_config = dict(config)
    probe_config["system_prompt"] = "You are a helpful assistant."
    probe_config["user_prompt"] = f"[run:{run_tag}] 请用简短中文回复：这是连通性测试。"
    probe_config["max_tokens"] = 100
    probe_config["timeout"] = timeout
    probe_config["cache_test"] = False

    url = adapter.build_url(probe_config)
    headers = adapter.build_headers(probe_config)
    payload = adapter.build_payload(probe_config)

    probe = ProbeResult(
        name="single_non_stream",
        display_name="单轮非流式",
    )
    start = time.monotonic()

    try:
        async with session.post(url, json=payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            probe.latency_ms = (time.monotonic() - start) * 1000

            if resp.status != 200:
                body = await resp.text()
                probe.status = "failed"
                probe.error = f"HTTP {resp.status}: {body[:200]}"
                return CategoryResult(
                    category="connectivity", display_name="连通性",
                    status="failed", probes=[probe],
                )

            buffer = ""
            output_text = ""
            async for chunk in resp.content:
                text = chunk.decode("utf-8", errors="replace")
                buffer += text
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        continue
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            output_text += delta.get("text", "")
                    elif event.get("type") == "message_start":
                        usage = event.get("message", {}).get("usage", {})
                        probe.input_tokens = usage.get("input_tokens", 0)
                    elif event.get("type") == "message_delta":
                        usage = event.get("usage", {})
                        probe.output_tokens = usage.get("output_tokens", 0)

            if output_text.strip():
                probe.status = "passed"
                probe.detail = f"输出 {len(output_text)} 字符"
            else:
                probe.status = "failed"
                probe.detail = "空输出"

    except Exception as e:
        probe.latency_ms = (time.monotonic() - start) * 1000
        probe.status = "error"
        probe.error = str(e)

    cat_status = "passed" if probe.status == "passed" else "failed"
    return CategoryResult(
        category="connectivity",
        display_name="连通性",
        status=cat_status,
        probes=[probe],
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_diagnostics_connectivity.py -v
```

- [ ] **Step 5: Commit**

```bash
git add app/diagnostics/connectivity.py tests/test_diagnostics_connectivity.py
git commit -m "feat: 添加连通性探针 (connectivity)"
```

---

## Task 4: Add streaming probe (case02)

**Files:**
- Create: `app/diagnostics/streaming.py`
- Create: `tests/test_diagnostics_streaming.py`

- [ ] **Step 1: Write the failing test**

```python
"""测试流式传输探针"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.diagnostics.models import CategoryResult


class TestStreamingProbe:
    @pytest.mark.asyncio
    async def test_streaming_passes_with_long_output(self):
        """输出 > 500 字符应 passed"""
        from app.diagnostics.streaming import run_streaming_probes

        long_text = "x" * 600
        mock_response = MagicMock()
        mock_response.status = 200

        async def mock_iter():
            yield _sse("message_start", usage={"input_tokens": 10})
            yield _sse("content_block_delta", delta={"type": "text_delta", "text": long_text})
            yield _sse("message_delta", usage={"output_tokens": 50}, delta={"stop_reason": "end_turn"})
            yield _sse("message_stop")

        mock_response.content = mock_iter()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_response)

        config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
        result = await run_streaming_probes(config, mock_session, "t", 30)
        assert result.status == "passed"
        assert result.probes[0].ttft_ms is not None

    @pytest.mark.asyncio
    async def test_streaming_fails_with_short_output(self):
        """输出 <= 500 字符应 failed"""
        from app.diagnostics.streaming import run_streaming_probes

        mock_response = MagicMock()
        mock_response.status = 200

        async def mock_iter():
            yield _sse("message_start", usage={"input_tokens": 10})
            yield _sse("content_block_delta", delta={"type": "text_delta", "text": "short"})
            yield _sse("message_delta", usage={"output_tokens": 1}, delta={"stop_reason": "end_turn"})
            yield _sse("message_stop")

        mock_response.content = mock_iter()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_response)

        config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
        result = await run_streaming_probes(config, mock_session, "t", 30)
        assert result.status == "failed"


def _sse(event_type: str, **kwargs) -> bytes:
    return f"data: {json.dumps({'type': event_type, **kwargs})}\n\n".encode()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_diagnostics_streaming.py -v
```

- [ ] **Step 3: Implement streaming probe**

```python
"""流式传输探针 — 流式长输出"""

import json
import logging
import time

import aiohttp

from app.diagnostics.models import ProbeResult, CategoryResult
from app.diagnostics.runner import register_category
from app.protocols import detect_protocol, get_adapter

log = logging.getLogger("diagnostics.streaming")

MIN_OUTPUT_LENGTH = 500


@register_category("streaming")
async def run_streaming_probes(
    config: dict, session: aiohttp.ClientSession, run_tag: str, timeout: int
) -> CategoryResult:
    """流式传输测试：发一次流式请求，要求输出 > 500 字符"""
    protocol = config.get("protocol") or detect_protocol(config.get("model", ""), config.get("provider", ""))
    adapter = get_adapter(protocol)

    probe_config = dict(config)
    probe_config["system_prompt"] = "You are a helpful assistant."
    probe_config["user_prompt"] = (
        f"[run:{run_tag}] 请输出一段超过500个字符的中文内容，主题是"软件测试可观测性实践"，"
        "请连续输出，不要分点，不要用代码块。"
    )
    probe_config["max_tokens"] = 4096
    probe_config["timeout"] = timeout
    probe_config["cache_test"] = False

    url = adapter.build_url(probe_config)
    headers = adapter.build_headers(probe_config)
    payload = adapter.build_payload(probe_config)

    probe = ProbeResult(name="stream_long_output", display_name="流式长输出")
    start = time.monotonic()
    first_text_at = None
    output_text = ""

    try:
        async with session.post(url, json=payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=timeout), stream=True) as resp:
            if resp.status != 200:
                body = await resp.text()
                probe.status = "error"
                probe.error = f"HTTP {resp.status}: {body[:200]}"
                probe.latency_ms = (time.monotonic() - start) * 1000
                return CategoryResult(category="streaming", display_name="流式传输", status="failed", probes=[probe])

            buffer = ""
            async for chunk in resp.content:
                text = chunk.decode("utf-8", errors="replace")
                buffer += text
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        continue
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    etype = event.get("type", "")
                    if etype == "message_start":
                        usage = event.get("message", {}).get("usage", {})
                        probe.input_tokens = usage.get("input_tokens", 0)
                    elif etype == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            output_text += delta["text"]
                            if first_text_at is None:
                                first_text_at = time.monotonic()
                    elif etype == "message_delta":
                        usage = event.get("usage", {})
                        probe.output_tokens = usage.get("output_tokens", 0)

            probe.latency_ms = (time.monotonic() - start) * 1000
            if first_text_at:
                probe.ttft_ms = (first_text_at - start) * 1000

            if len(output_text) > MIN_OUTPUT_LENGTH:
                probe.status = "passed"
                probe.detail = f"len={len(output_text)}"
            else:
                probe.status = "failed"
                probe.detail = f"len={len(output_text)} <= {MIN_OUTPUT_LENGTH}"

    except Exception as e:
        probe.latency_ms = (time.monotonic() - start) * 1000
        probe.status = "error"
        probe.error = str(e)

    return CategoryResult(
        category="streaming", display_name="流式传输",
        status="passed" if probe.status == "passed" else "failed",
        probes=[probe],
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_diagnostics_streaming.py -v
```

- [ ] **Step 5: Commit**

```bash
git add app/diagnostics/streaming.py tests/test_diagnostics_streaming.py
git commit -m "feat: 添加流式传输探针 (streaming)"
```

---

## Task 5: Add context probe (case03)

**Files:**
- Create: `app/diagnostics/context.py`
- Create: `tests/test_diagnostics_context.py`

- [ ] **Step 1: Write the failing test**

```python
"""测试多轮上下文探针"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.diagnostics.models import CategoryResult


class TestContextProbe:
    @pytest.mark.asyncio
    async def test_context_passes_all_rounds(self):
        """6 轮每轮 > 200 字符应 passed"""
        from app.diagnostics.context import run_context_probes

        call_count = 0

        def make_response():
            nonlocal call_count
            call_count += 1
            text = "x" * 250
            mock_resp = MagicMock()
            mock_resp.status = 200

            async def iter_content():
                yield _sse("message_start", usage={"input_tokens": 100})
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
    async def test_context_fails_on_short_round(self):
        """某轮输出 <= 200 应 failed"""
        from app.diagnostics.context import run_context_probes

        call_count = 0

        def make_response():
            nonlocal call_count
            call_count += 1
            text = "x" * 250 if call_count != 3 else "short"
            mock_resp = MagicMock()
            mock_resp.status = 200

            async def iter_content():
                yield _sse("message_start", usage={"input_tokens": 100})
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


def _sse(event_type: str, **kwargs) -> bytes:
    return f"data: {json.dumps({'type': event_type, **kwargs})}\n\n".encode()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_diagnostics_context.py -v
```

- [ ] **Step 3: Implement context probe**

```python
"""多轮上下文探针 — 6 轮流式对话"""

import json
import logging
import time
from typing import List

import aiohttp

from app.diagnostics.models import ProbeResult, CategoryResult
from app.diagnostics.runner import register_category
from app.protocols import detect_protocol, get_adapter

log = logging.getLogger("diagnostics.context")

TOTAL_ROUNDS = 6
CONTEXT_WINDOW = 10  # 保留前 5 轮 (10 条 messages)
MIN_ROUND_LENGTH = 200


@register_category("context")
async def run_context_probes(
    config: dict, session: aiohttp.ClientSession, run_tag: str, timeout: int
) -> CategoryResult:
    """多轮上下文测试：6 轮流式对话，每轮要求 > 200 字符"""
    protocol = config.get("protocol") or detect_protocol(config.get("model", ""), config.get("provider", ""))
    adapter = get_adapter(protocol)

    history: List[dict] = []
    probes: List[ProbeResult] = []

    for idx in range(1, TOTAL_ROUNDS + 1):
        prompt = (
            f"[run:{run_tag}] 这是第{idx}轮，请围绕"稳定性测试策略"连续写一段超过200字符的中文正文，"
            "不要分点，不要标题。"
        )

        probe_config = dict(config)
        probe_config["system_prompt"] = "You are a helpful assistant."
        probe_config["user_prompt"] = prompt
        probe_config["max_tokens"] = 4096
        probe_config["timeout"] = timeout
        probe_config["cache_test"] = False

        # 构建含历史的消息
        url = adapter.build_url(probe_config)
        headers = adapter.build_headers(probe_config)
        payload = adapter.build_payload(probe_config)

        # 注入历史消息
        context = history[-CONTEXT_WINDOW:]
        payload["messages"] = context + [{"role": "user", "content": prompt}]

        probe = ProbeResult(name=f"round_{idx}", display_name=f"第{idx}轮对话")
        start = time.monotonic()
        output_text = ""

        try:
            async with session.post(url, json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=timeout), stream=True) as resp:
                if resp.status != 200:
                    probe.status = "error"
                    probe.error = f"HTTP {resp.status}"
                    probe.latency_ms = (time.monotonic() - start) * 1000
                    probes.append(probe)
                    break

                buffer = ""
                async for chunk in resp.content:
                    text = chunk.decode("utf-8", errors="replace")
                    buffer += text
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            continue
                        try:
                            event = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        etype = event.get("type", "")
                        if etype == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                output_text += delta.get("text", "")
                        elif etype == "message_start":
                            usage = event.get("message", {}).get("usage", {})
                            probe.input_tokens = usage.get("input_tokens", 0)
                        elif etype == "message_delta":
                            usage = event.get("usage", {})
                            probe.output_tokens = usage.get("output_tokens", 0)

                probe.latency_ms = (time.monotonic() - start) * 1000

                if len(output_text) > MIN_ROUND_LENGTH:
                    probe.status = "passed"
                    probe.detail = f"len={len(output_text)}"
                else:
                    probe.status = "failed"
                    probe.detail = f"len={len(output_text)} <= {MIN_ROUND_LENGTH}"

        except Exception as e:
            probe.latency_ms = (time.monotonic() - start) * 1000
            probe.status = "error"
            probe.error = str(e)

        probes.append(probe)

        # 更新历史
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": output_text})

        if probe.status != "passed":
            break

    all_passed = all(p.status == "passed" for p in probes)
    round_lens = [len(p.detail.split("len=")[1].split(" ")[0]) if "len=" in p.detail else 0 for p in probes]

    return CategoryResult(
        category="context",
        display_name="多轮上下文",
        status="passed" if all_passed else "failed",
        probes=probes,
        summary={"rounds_completed": len(probes), "all_passed": all_passed},
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_diagnostics_context.py -v
```

- [ ] **Step 5: Commit**

```bash
git add app/diagnostics/context.py tests/test_diagnostics_context.py
git commit -m "feat: 添加多轮上下文探针 (context)"
```

---

## Task 6: Add tool_use probe (case04)

**Files:**
- Create: `app/diagnostics/tool_use.py`
- Create: `tests/test_diagnostics_tool_use.py`

- [ ] **Step 1: Write the failing test**

```python
"""测试工具调用探针"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.diagnostics.models import CategoryResult


class TestToolUseProbe:
    @pytest.mark.asyncio
    async def test_tool_use_passes_with_correct_result(self):
        """正确的 function call + 结果应 passed"""
        from app.diagnostics.tool_use import run_tool_use_probes

        call_count = 0

        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status = 200

            if call_count == 1:
                # 第一轮：返回 tool_use
                async def iter1():
                    yield _sse("message_start", usage={"input_tokens": 50})
                    yield _sse("content_block_start", content_block={"type": "tool_use", "id": "tu_1", "name": "calc_sum", "input": {}})
                    yield _sse("content_block_delta", delta={"type": "input_json_delta", "partial_json": '{"a":7,"b":13}'})
                    yield _sse("content_block_stop")
                    yield _sse("message_delta", usage={"output_tokens": 10}, delta={"stop_reason": "tool_use"})
                    yield _sse("message_stop")
                mock_resp.content = iter1()
            else:
                # 第二轮：返回文本结果
                async def iter2():
                    yield _sse("message_start", usage={"input_tokens": 80})
                    yield _sse("content_block_delta", delta={"type": "text_delta", "text": "计算结果是 20"})
                    yield _sse("message_delta", usage={"output_tokens": 10}, delta={"stop_reason": "end_turn"})
                    yield _sse("message_stop")
                mock_resp.content = iter2()

            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)
            return mock_resp

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=mock_post)

        config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
        result = await run_tool_use_probes(config, mock_session, "t", 30)
        assert result.status == "passed"


def _sse(event_type: str, **kwargs) -> bytes:
    return f"data: {json.dumps({'type': event_type, **kwargs})}\n\n".encode()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_diagnostics_tool_use.py -v
```

- [ ] **Step 3: Implement tool_use probe**

```python
"""工具调用探针 — function calling 多轮"""

import json
import logging
import time
from typing import Any, Dict

import aiohttp

from app.diagnostics.models import ProbeResult, CategoryResult
from app.diagnostics.runner import register_category
from app.protocols import detect_protocol, get_adapter

log = logging.getLogger("diagnostics.tool_use")

TOOLS = [
    {
        "name": "calc_sum",
        "description": "Calculate sum of a and b",
        "input_schema": {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
    },
]


def _execute_tool(name: str, tool_input: Dict[str, Any]) -> str:
    if name == "calc_sum":
        return str(int(tool_input.get("a", 0)) + int(tool_input.get("b", 0)))
    return "unsupported"


@register_category("tool_use")
async def run_tool_use_probes(
    config: dict, session: aiohttp.ClientSession, run_tag: str, timeout: int
) -> CategoryResult:
    """工具调用测试：发送 function call 请求，验证 tool_use 返回和结果正确性"""
    protocol = config.get("protocol") or detect_protocol(config.get("model", ""), config.get("provider", ""))
    adapter = get_adapter(protocol)

    # 第一轮：请求调用 calc_sum
    probe1 = ProbeResult(name="tool_call_round1", display_name="工具调用-请求")
    probe2 = ProbeResult(name="tool_call_round2", display_name="工具调用-结果")
    start1 = time.monotonic()

    round1_config = dict(config)
    round1_config["system_prompt"] = "You are a helpful assistant."
    round1_config["user_prompt"] = f"[run:{run_tag}] 请调用calc_sum，参数a=7,b=13。计算后告诉我最终结果。"
    round1_config["max_tokens"] = 1024
    round1_config["timeout"] = timeout
    round1_config["cache_test"] = False

    url = adapter.build_url(round1_config)
    headers = adapter.build_headers(round1_config)
    payload1 = adapter.build_payload(round1_config)
    payload1["tools"] = TOOLS

    tool_block = None
    content_blocks = []
    round1_content = []

    try:
        async with session.post(url, json=payload1, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            probe1.latency_ms = (time.monotonic() - start1) * 1000
            if resp.status != 200:
                body = await resp.text()
                probe1.status = "error"
                probe1.error = f"HTTP {resp.status}: {body[:200]}"
                return CategoryResult(category="tool_use", display_name="工具调用", status="failed", probes=[probe1])

            buffer = ""
            async for chunk in resp.content:
                text = chunk.decode("utf-8", errors="replace")
                buffer += text
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        continue
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    etype = event.get("type", "")
                    if etype == "content_block_start":
                        block = event.get("content_block", {})
                        if block.get("type") == "tool_use":
                            tool_block = block
                            content_blocks.append(block)
                    elif etype == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "input_json_delta" and tool_block:
                            tool_block.setdefault("input", "")
                            tool_block["input"] += delta.get("partial_json", "")
                    elif etype == "message_delta":
                        usage = event.get("usage", {})
                        probe1.output_tokens = usage.get("output_tokens", 0)

            if tool_block:
                try:
                    tool_block["input"] = json.loads(tool_block["input"])
                except (json.JSONDecodeError, TypeError):
                    pass
                probe1.status = "passed"
                probe1.detail = f"tool={tool_block.get('name')}"
            else:
                probe1.status = "failed"
                probe1.detail = "no tool_use block"

    except Exception as e:
        probe1.latency_ms = (time.monotonic() - start1) * 1000
        probe1.status = "error"
        probe1.error = str(e)
        return CategoryResult(category="tool_use", display_name="工具调用", status="failed", probes=[probe1])

    if probe1.status != "passed":
        return CategoryResult(category="tool_use", display_name="工具调用", status="failed", probes=[probe1])

    # 第二轮：发送 tool_result
    tool_name = tool_block.get("name", "")
    tool_input = tool_block.get("input", {})
    tool_use_id = tool_block.get("id", "")
    tool_result = _execute_tool(tool_name, tool_input if isinstance(tool_input, dict) else {})

    start2 = time.monotonic()
    round2_config = dict(config)
    round2_config["system_prompt"] = "You are a helpful assistant."
    round2_config["user_prompt"] = f"[run:{run_tag}] 请调用calc_sum，参数a=7,b=13。计算后告诉我最终结果。"
    round2_config["max_tokens"] = 1024
    round2_config["timeout"] = timeout
    round2_config["cache_test"] = False

    payload2 = adapter.build_payload(round2_config)
    payload2["tools"] = TOOLS
    payload2["messages"] = [
        {"role": "user", "content": round2_config["user_prompt"]},
        {"role": "assistant", "content": content_blocks},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": tool_result}]},
    ]

    try:
        async with session.post(url, json=payload2, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            probe2.latency_ms = (time.monotonic() - start2) * 1000
            if resp.status != 200:
                probe2.status = "error"
                probe2.error = f"HTTP {resp.status}"
            else:
                output_text = ""
                buffer = ""
                async for chunk in resp.content:
                    text = chunk.decode("utf-8", errors="replace")
                    buffer += text
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            continue
                        try:
                            event = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                output_text += delta.get("text", "")

                if "20" in output_text:
                    probe2.status = "passed"
                    probe2.detail = f"结果包含 20"
                else:
                    probe2.status = "failed"
                    probe2.detail = f"结果不含 20: {output_text[:100]}"

    except Exception as e:
        probe2.latency_ms = (time.monotonic() - start2) * 1000
        probe2.status = "error"
        probe2.error = str(e)

    all_passed = probe1.status == "passed" and probe2.status == "passed"
    return CategoryResult(
        category="tool_use",
        display_name="工具调用",
        status="passed" if all_passed else "failed",
        probes=[probe1, probe2],
        summary={"tool_name": tool_name, "tool_result": tool_result},
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_diagnostics_tool_use.py -v
```

- [ ] **Step 5: Commit**

```bash
git add app/diagnostics/tool_use.py tests/test_diagnostics_tool_use.py
git commit -m "feat: 添加工具调用探针 (tool_use)"
```

---

## Task 7: Add structured output probe (case05)

**Files:**
- Create: `app/diagnostics/structured.py`
- Create: `tests/test_diagnostics_structured.py`

- [ ] **Step 1: Write the failing test**

```python
"""测试结构化输出探针"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.diagnostics.models import CategoryResult


class TestStructuredProbe:
    @pytest.mark.asyncio
    async def test_structured_passes_with_valid_json(self):
        """正确的 JSON 输出应 passed"""
        from app.diagnostics.structured import run_structured_probes

        mock_resp = MagicMock()
        mock_resp.status = 200
        json_output = json.dumps({"name": "alice", "score": 95, "passed": True})

        async def iter_content():
            yield _sse("message_start", usage={"input_tokens": 20})
            yield _sse("content_block_delta", delta={"type": "text_delta", "text": json_output})
            yield _sse("message_delta", usage={"output_tokens": 15}, delta={"stop_reason": "end_turn"})
            yield _sse("message_stop")

        mock_resp.content = iter_content()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
        result = await run_structured_probes(config, mock_session, "t", 30)
        assert result.status == "passed"

    @pytest.mark.asyncio
    async def test_structured_fails_with_wrong_json(self):
        """字段值不对应 failed"""
        from app.diagnostics.structured import run_structured_probes

        mock_resp = MagicMock()
        mock_resp.status = 200
        json_output = json.dumps({"name": "bob", "score": 50, "passed": False})

        async def iter_content():
            yield _sse("message_start", usage={"input_tokens": 20})
            yield _sse("content_block_delta", delta={"type": "text_delta", "text": json_output})
            yield _sse("message_delta", usage={"output_tokens": 15}, delta={"stop_reason": "end_turn"})
            yield _sse("message_stop")

        mock_resp.content = iter_content()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        config = {"base_url": "https://api.anthropic.com", "api_key": "k", "model": "m", "protocol": "anthropic"}
        result = await run_structured_probes(config, mock_session, "t", 30)
        assert result.status == "failed"


def _sse(event_type: str, **kwargs) -> bytes:
    return f"data: {json.dumps({'type': event_type, **kwargs})}\n\n".encode()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_diagnostics_structured.py -v
```

- [ ] **Step 3: Implement structured probe**

```python
"""结构化输出探针 — JSON 输出验证"""

import json
import logging
import time

import aiohttp

from app.diagnostics.models import ProbeResult, CategoryResult
from app.diagnostics.runner import register_category
from app.protocols import detect_protocol, get_adapter

log = logging.getLogger("diagnostics.structured")


@register_category("structured")
async def run_structured_probes(
    config: dict, session: aiohttp.ClientSession, run_tag: str, timeout: int
) -> CategoryResult:
    """结构化输出测试：要求模型输出特定 JSON，验证格式和内容"""
    protocol = config.get("protocol") or detect_protocol(config.get("model", ""), config.get("provider", ""))
    adapter = get_adapter(protocol)

    probe_config = dict(config)
    probe_config["system_prompt"] = "You are a helpful assistant."
    probe_config["user_prompt"] = (
        f"[run:{run_tag}] 请只输出JSON，不要任何额外文本。"
        '格式为{"name":"...","score":数字,"passed":布尔值}，'
        "其中name=alice, score=95, passed=true。"
    )
    probe_config["max_tokens"] = 1024
    probe_config["timeout"] = timeout
    probe_config["cache_test"] = False

    url = adapter.build_url(probe_config)
    headers = adapter.build_headers(probe_config)
    payload = adapter.build_payload(probe_config)

    probe = ProbeResult(name="structured_json", display_name="结构化 JSON")
    start = time.monotonic()
    output_text = ""

    try:
        async with session.post(url, json=payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            probe.latency_ms = (time.monotonic() - start) * 1000
            if resp.status != 200:
                body = await resp.text()
                probe.status = "error"
                probe.error = f"HTTP {resp.status}: {body[:200]}"
                return CategoryResult(category="structured", display_name="结构化输出", status="failed", probes=[probe])

            buffer = ""
            async for chunk in resp.content:
                text = chunk.decode("utf-8", errors="replace")
                buffer += text
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        continue
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    etype = event.get("type", "")
                    if etype == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            output_text += delta.get("text", "")
                    elif etype == "message_start":
                        usage = event.get("message", {}).get("usage", {})
                        probe.input_tokens = usage.get("input_tokens", 0)
                    elif etype == "message_delta":
                        usage = event.get("usage", {})
                        probe.output_tokens = usage.get("output_tokens", 0)

            try:
                obj = json.loads(output_text.strip())
            except Exception:
                probe.status = "failed"
                probe.detail = f"invalid json: {output_text[:100]}"
                return CategoryResult(category="structured", display_name="结构化输出", status="failed", probes=[probe])

            valid = (
                isinstance(obj, dict)
                and obj.get("name") == "alice"
                and obj.get("score") == 95
                and obj.get("passed") is True
            )
            if valid:
                probe.status = "passed"
                probe.detail = "json schema matched"
            else:
                probe.status = "failed"
                probe.detail = f"json mismatch: {obj}"

    except Exception as e:
        probe.latency_ms = (time.monotonic() - start) * 1000
        probe.status = "error"
        probe.error = str(e)

    return CategoryResult(
        category="structured", display_name="结构化输出",
        status="passed" if probe.status == "passed" else "failed",
        probes=[probe],
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_diagnostics_structured.py -v
```

- [ ] **Step 5: Commit**

```bash
git add app/diagnostics/structured.py tests/test_diagnostics_structured.py
git commit -m "feat: 添加结构化输出探针 (structured)"
```

---

## Task 8: Update API endpoint

**Files:**
- Modify: `app/server.py:961-1049`

- [ ] **Step 1: Update the POST endpoint to accept categories and use new runner**

修改 `app/server.py` 中的 `create_channel_diagnostic` 函数：

1. 从请求体读取 `categories` 字段（可选列表）
2. 调用 `run_diagnostics(config, categories=categories)` 替代 `run_cache_diagnostics`
3. 返回格式改为包含 `categories` 数组的统一结构

关键改动：
- import `from app.diagnostics import run_diagnostics, get_available_categories`
- 请求体新增 `categories` 可选字段
- 返回值新增 `categories` 数组，保留 `probes` 和 `summary` 向后兼容

- [ ] **Step 2: Run existing API tests to verify backward compatibility**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_channel_diagnostics_api.py -v
```

- [ ] **Step 3: Commit**

```bash
git add app/server.py
git commit -m "feat: API 端点支持 categories 参数和统一诊断"
```

---

## Task 9: Update frontend — category selector

**Files:**
- Modify: `frontend/src/components/SiteTestTab.vue:150-188`

- [ ] **Step 1: Add category selector to diagnostics tab**

在 `SiteTestTab.vue` 的 `<!-- Diagnostics Tab -->` 部分：

1. 新增 `diagCategories` ref，默认全选 6 个类别
2. 新增类别 checkbox 组 UI
3. 修改 `runDiagnostics()` 传递 `categories` 参数
4. 更新提示文案显示 token 消耗范围

新增 data:
```js
const diagCategories = ref(['connectivity', 'streaming', 'context', 'tool_use', 'structured', 'cache'])
const allDiagCategories = [
  { id: 'connectivity', label: '连通性', desc: '基础连通验证' },
  { id: 'streaming', label: '流式传输', desc: '流式长输出' },
  { id: 'context', label: '多轮上下文', desc: '6轮对话' },
  { id: 'tool_use', label: '工具调用', desc: 'function calling' },
  { id: 'structured', label: '结构化输出', desc: 'JSON 输出' },
  { id: 'cache', label: 'Prompt Cache', desc: '缓存诊断' },
]
```

模板中 checkbox 组:
```html
<div class="diag-category-selector">
  <div class="diag-category-header">
    <span style="font-size:13px;font-weight:600">测试类别</span>
    <div style="display:flex;gap:8px">
      <button class="btn btn-ghost btn-sm" @click="diagCategories = allDiagCategories.map(c => c.id)">全选</button>
      <button class="btn btn-ghost btn-sm" @click="diagCategories = []">全不选</button>
    </div>
  </div>
  <div class="diag-category-grid">
    <label v-for="cat in allDiagCategories" :key="cat.id" class="diag-category-item">
      <input type="checkbox" :value="cat.id" v-model="diagCategories">
      <span class="diag-category-label">{{ cat.label }}</span>
      <span class="diag-category-desc">{{ cat.desc }}</span>
    </label>
  </div>
</div>
```

- [ ] **Step 2: Update runDiagnostics to pass categories**

修改 `runDiagnostics()` 函数，传递 `categories` 参数给 API。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SiteTestTab.vue
git commit -m "feat: 诊断 Tab 新增类别选择器"
```

---

## Task 10: Update frontend — DiagnosticCard for categories

**Files:**
- Modify: `frontend/src/components/DiagnosticCard.vue`
- Modify: `frontend/src/utils/diagnosticUtils.js`

- [ ] **Step 1: Update diagnosticUtils.js**

新增类别和探针标签映射：

```js
export function categoryLabel(catId) {
  const map = {
    connectivity: '连通性',
    streaming: '流式传输',
    context: '多轮上下文',
    tool_use: '工具调用',
    structured: '结构化输出',
    cache: 'Prompt Cache',
  }
  return map[catId] || catId
}

export function categoryIcon(catId) {
  const map = {
    connectivity: '🔗',
    streaming: '📡',
    context: '💬',
    tool_use: '🔧',
    structured: '📋',
    cache: '💾',
  }
  return map[catId] || '•'
}

export function probeDisplayName(name) {
  const map = {
    single_non_stream: '单轮非流式',
    stream_long_output: '流式长输出',
    round_1: '第1轮', round_2: '第2轮', round_3: '第3轮',
    round_4: '第4轮', round_5: '第5轮', round_6: '第6轮',
    tool_call_round1: '工具调用-请求',
    tool_call_round2: '工具调用-结果',
    structured_json: '结构化 JSON',
    cold_prefix: '首次请求',
    warm_prefix: '再次请求',
    breaker_prefix: '不同内容',
    repeat_identical: '重发首次',
  }
  return map[name] || name
}
```

- [ ] **Step 2: Update DiagnosticCard.vue to render categories**

改造 DiagnosticCard，支持两种模式：
1. **新版**：有 `categories` 数组时，按类别折叠展示
2. **兼容**：无 `categories` 时，回退到原有缓存探针渲染

模板结构：
```html
<template v-if="categories && categories.length">
  <!-- 综合评分条 -->
  <div class="diag-overall-bar">
    <span class="diag-overall-badge" :style="'background:' + diagStatusColor(overallStatus)">
      {{ overallStatusLabel }}
    </span>
    <span v-if="confidence != null">置信度: {{ (confidence * 100).toFixed(0) }}%</span>
  </div>
  <!-- 类别列表 -->
  <div v-for="cat in categories" :key="cat.category" class="diag-category-section">
    <div class="diag-category-header" @click="toggleCategory(cat.category)">
      <span class="diag-cat-status" :style="'background:' + diagStatusColor(cat.status)"></span>
      <span class="diag-cat-name">{{ categoryLabel(cat.category) }}</span>
      <span class="diag-cat-arrow">{{ expandedCategories.has(cat.category) ? '▲' : '▼' }}</span>
    </div>
    <div v-if="expandedCategories.has(cat.category)" class="diag-category-body">
      <!-- 每个探针 -->
      <div v-for="probe in cat.probes" :key="probe.name" class="diag-probe-row">
        <span class="diag-probe-name">{{ probeDisplayName(probe.name) }}</span>
        <span class="diag-probe-detail">{{ probe.detail }}</span>
        <span class="diag-probe-latency">{{ probe.latency_ms ? (probe.latency_ms / 1000).toFixed(1) + 's' : '' }}</span>
        <span class="diag-probe-status" :style="'color:' + (probe.status === 'passed' ? 'var(--success)' : 'var(--danger)')">
          {{ probe.status === 'passed' ? '✓' : '✗' }}
        </span>
      </div>
      <!-- cache 类别特殊渲染 -->
      <template v-if="cat.category === 'cache' && cat.summary?.prompt_cache">
        <div class="diag-cache-summary">
          <span>命中率: {{ (cat.summary.hit_rate * 100).toFixed(1) }}%</span>
          <span>状态: {{ cat.summary.prompt_cache_status }}</span>
        </div>
      </template>
    </div>
  </div>
</template>
<template v-else>
  <!-- 原有缓存探针渲染逻辑（保持不变） -->
</template>
```

新增 props:
```js
const props = defineProps({
  // ... existing props
  categories: { type: Array, default: null },
  overallStatus: { type: String, default: '' },
})
```

- [ ] **Step 3: Run frontend dev server and verify**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && bun run dev
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/DiagnosticCard.vue frontend/src/utils/diagnosticUtils.js
git commit -m "feat: DiagnosticCard 支持按类别展示诊断结果"
```

---

## Task 11: Add runner integration tests

**Files:**
- Create: `tests/test_diagnostics_runner.py`

- [ ] **Step 1: Write runner tests**

```python
"""测试统一诊断调度器"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.diagnostics.models import DiagnosticReport, CategoryResult
from app.diagnostics.runner import run_diagnostics, get_available_categories


class TestRunnerCategories:
    def test_all_categories_registered(self):
        """6 个类别都应注册"""
        cats = get_available_categories()
        assert "connectivity" in cats
        assert "streaming" in cats
        assert "context" in cats
        assert "tool_use" in cats
        assert "structured" in cats
        assert "cache" in cats

    @pytest.mark.asyncio
    async def test_run_specific_categories(self):
        """指定类别只运行那些类别"""
        config = {
            "base_url": "https://api.anthropic.com",
            "api_key": "test-key",
            "model": "test-model",
            "protocol": "anthropic",
        }
        with patch("app.diagnostics.connectivity.run_connectivity_probes") as mock_conn:
            mock_conn.return_value = CategoryResult(category="connectivity", display_name="连通性", status="passed")
            report = await run_diagnostics(config, categories=["connectivity"], timeout_seconds=5)
            assert len(report.categories) == 1
            assert report.categories[0].category == "connectivity"
            mock_conn.assert_called_once()

    @pytest.mark.asyncio
    async def test_overall_status_all_passed(self):
        """所有类别 passed → overall passed"""
        config = {"base_url": "x", "api_key": "k", "model": "m", "protocol": "anthropic"}
        with patch("app.diagnostics.connectivity.run_connectivity_probes") as mock_c:
            mock_c.return_value = CategoryResult(category="connectivity", status="passed")
            report = await run_diagnostics(config, categories=["connectivity"], timeout_seconds=5)
            assert report.overall_status == "passed"
            assert report.overall_risk == "low"
```

- [ ] **Step 2: Run tests**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_diagnostics_runner.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_diagnostics_runner.py
git commit -m "test: 添加统一诊断调度器测试"
```

---

## Task 12: Run full test suite and verify

- [ ] **Step 1: Run all tests**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/ -v --tb=short
```

- [ ] **Step 2: Run frontend type check / build**

```bash
cd /Users/yakun/linkingrid/AITokenPerf/frontend && bun run build
```

- [ ] **Step 3: Manual smoke test**

启动 dev server，打开一个站点详情页，切换到「渠道诊断」Tab，验证：
- 类别选择器显示 6 个 checkbox
- 全选/全不选按钮工作
- 点击开始诊断后进度正常
- 结果按类别折叠展示
- 每个探针显示 pass/fail 状态

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: 统一渠道质量诊断套件完成"
```
