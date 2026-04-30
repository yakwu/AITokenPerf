# Cache Diagnostics (缓存命中率检测) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add prompt cache hit rate detection and response cache risk identification for Claude API endpoints, providing users with actionable cache diagnostics in the history view.

**Architecture:** A new `channel_diagnostics` table stores structured diagnostic reports. The `app/channel_diagnostics.py` module runs 4 cache probes (cold/warm/breaker/identical) against the target API, analyzes usage fields and latency patterns, and produces a structured report. The Anthropic protocol adapter is extended to capture `cache_read_input_tokens` and `cache_creation_input_tokens` from usage events. A new API endpoint orchestrates the probes, and the frontend displays results in the history detail panel.

**Tech Stack:** Python/FastAPI (backend), aiohttp (probe requests), Vue 3 (frontend), SQLite/PostgreSQL (storage)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `app/db.py` | Modify | Add `channel_diagnostics` table schema + CRUD functions |
| `app/channel_diagnostics.py` | Create | Probe definitions, runner, scoring, report generation |
| `app/protocols/anthropic.py` | Modify | Capture `cache_read_input_tokens`, `cache_creation_input_tokens` from usage |
| `app/client.py` | Modify | Extend `RequestMetrics` with cache token fields |
| `app/server.py` | Modify | Add `POST /api/channel-diagnostics` and `GET /api/channel-diagnostics/{id}` endpoints |
| `frontend/src/api/index.js` | Modify | Add diagnostic API client functions |
| `frontend/src/utils/resultDetail.js` | Modify | Render cache diagnostic summary in history detail |
| `tests/test_channel_diagnostics.py` | Create | Unit tests for probes, scoring, and API |

---

### Task 1: Extend RequestMetrics and Anthropic adapter to capture cache usage fields

**Files:**
- Modify: `app/client.py:15-29`
- Modify: `app/protocols/anthropic.py:75-88`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cache_metrics.py
"""测试 Anthropic 适配器是否正确捕获缓存 usage 字段"""

import json
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.client import RequestMetrics


def test_request_metrics_has_cache_fields():
    """RequestMetrics 应包含缓存相关字段"""
    m = RequestMetrics(request_id=1)
    assert hasattr(m, 'cache_read_tokens')
    assert hasattr(m, 'cache_creation_tokens')
    assert m.cache_read_tokens == 0
    assert m.cache_creation_tokens == 0


@pytest.mark.asyncio
async def test_anthropic_adapter_captures_cache_usage():
    """Anthropic 适配器应从 message_start 事件中提取缓存 token 字段"""
    from app.protocols.anthropic import AnthropicAdapter

    adapter = AnthropicAdapter()
    metrics = RequestMetrics(request_id=1)

    # 模拟 SSE 流：message_start 包含 cache usage
    message_start_data = json.dumps({
        "type": "message_start",
        "message": {
            "usage": {
                "input_tokens": 5000,
                "cache_read_input_tokens": 4000,
                "cache_creation_input_tokens": 1000,
            }
        }
    })
    message_stop_data = json.dumps({"type": "message_stop"})

    # 构造模拟响应
    body = f"data: {message_start_data}\n\ndata: {message_stop_data}\n\n"

    class FakeContent:
        def __init__(self, data):
            self._data = data.encode()
        def __aiter__(self):
            return self._async_iter()
        async def _async_iter(self):
            yield self._data

    class FakeResponse:
        content = FakeContent(body)

    resp = FakeResponse()
    await adapter.parse_sse_stream(resp, metrics)

    assert metrics.input_tokens == 5000
    assert metrics.cache_read_tokens == 4000
    assert metrics.cache_creation_tokens == 1000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_cache_metrics.py -v`
Expected: FAIL — `RequestMetrics` 没有 `cache_read_tokens` 属性

- [ ] **Step 3: Add cache fields to RequestMetrics**

在 `app/client.py` 的 `RequestMetrics` dataclass 中，在 `input_tokens` 后添加：

```python
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
```

- [ ] **Step 4: Update Anthropic adapter to capture cache usage**

在 `app/protocols/anthropic.py` 的 `message_start` 处理分支中，`input_tokens` 赋值之后添加：

```python
                        if "cache_read_input_tokens" in usage:
                            metrics.cache_read_tokens = usage["cache_read_input_tokens"]
                        if "cache_creation_input_tokens" in usage:
                            metrics.cache_creation_tokens = usage["cache_creation_input_tokens"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_cache_metrics.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/client.py app/protocols/anthropic.py tests/test_cache_metrics.py
git commit -m "feat: capture cache usage fields from Anthropic API responses"
```

---

### Task 2: Add channel_diagnostics table and DB CRUD functions

**Files:**
- Modify: `app/db.py` (schema + CRUD functions)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_channel_diagnostics_db.py
"""测试 channel_diagnostics 表的 CRUD 操作"""

import json
import pytest
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_save_and_get_channel_diagnostic(client):
    """保存诊断记录并能读取"""
    from app.db import save_channel_diagnostic, get_channel_diagnostic

    diag_id = await save_channel_diagnostic(
        user_id=1,
        profile_name="test-profile",
        model="claude-opus-4-6",
        status="passed",
        overall_risk="low",
        confidence=0.85,
        report_json={
            "schema_version": 1,
            "dimensions": {
                "cache": {
                    "status": "passed",
                    "prompt_cache": {"status": "supported", "hit_rate": 0.83}
                }
            }
        },
    )
    assert diag_id > 0

    result = await get_channel_diagnostic(diag_id, user_id=1)
    assert result is not None
    assert result["profile_name"] == "test-profile"
    assert result["model"] == "claude-opus-4-6"
    assert result["status"] == "passed"
    assert result["overall_risk"] == "low"
    assert result["confidence"] == 0.85
    assert result["report_json"]["schema_version"] == 1


@pytest.mark.asyncio
async def test_get_channel_diagnostic_wrong_user(client):
    """不同用户不能读取别人的诊断记录"""
    from app.db import save_channel_diagnostic, get_channel_diagnostic

    diag_id = await save_channel_diagnostic(
        user_id=1,
        profile_name="test-profile",
        model="claude-opus-4-6",
        status="passed",
        overall_risk="low",
        confidence=0.85,
        report_json={"schema_version": 1},
    )

    result = await get_channel_diagnostic(diag_id, user_id=999)
    assert result is None


@pytest.mark.asyncio
async def test_list_channel_diagnostics(client):
    """按用户列出诊断记录"""
    from app.db import save_channel_diagnostic, list_channel_diagnostics

    for i in range(3):
        await save_channel_diagnostic(
            user_id=1,
            profile_name=f"profile-{i}",
            model="claude-opus-4-6",
            status="passed",
            overall_risk="low",
            confidence=0.8,
            report_json={"schema_version": 1},
        )

    results = await list_channel_diagnostics(user_id=1, limit=10)
    assert len(results) == 3
    assert results[0]["profile_name"] == "profile-2"  # 最新在前
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_channel_diagnostics_db.py -v`
Expected: FAIL — `save_channel_diagnostic` 不存在

- [ ] **Step 3: Add channel_diagnostics table to both schemas**

在 `app/db.py` 的 `_SQLITE_SCHEMA` 末尾（`scheduled_tasks` 表之后）添加：

```sql
CREATE TABLE IF NOT EXISTS channel_diagnostics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_name  TEXT NOT NULL DEFAULT '',
    model         TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'not_run',
    overall_risk  TEXT NOT NULL DEFAULT 'unknown',
    confidence    REAL NOT NULL DEFAULT 0.0,
    report_json   TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
```

在 `_PG_SCHEMA` 末尾添加：

```sql
CREATE TABLE IF NOT EXISTS channel_diagnostics (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_name  TEXT NOT NULL DEFAULT '',
    model         TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'not_run',
    overall_risk  TEXT NOT NULL DEFAULT 'unknown',
    confidence    REAL NOT NULL DEFAULT 0.0,
    report_json   TEXT NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- [ ] **Step 4: Add CRUD functions at the end of app/db.py**

在 `app/db.py` 末尾 `close_db()` 函数之后添加：

```python
# ---- Channel Diagnostics CRUD ----

async def save_channel_diagnostic(
    user_id: int,
    profile_name: str,
    model: str,
    status: str,
    overall_risk: str,
    confidence: float,
    report_json: dict,
) -> int:
    """保存诊断记录，返回 ID"""
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                INSERT INTO channel_diagnostics (user_id, profile_name, model, status, overall_risk, confidence, report_json)
                VALUES (:user_id, :profile_name, :model, :status, :overall_risk, :confidence, :report_json)
            """),
            {
                "user_id": user_id,
                "profile_name": profile_name,
                "model": model,
                "status": status,
                "overall_risk": overall_risk,
                "confidence": confidence,
                "report_json": json.dumps(report_json),
            },
        )
        if _is_sqlite:
            return result.lastrowid
        else:
            row = await conn.execute(
                text("SELECT currval(pg_get_serial_sequence('channel_diagnostics', 'id'))")
            )
            return (await row.fetchone())[0]


async def get_channel_diagnostic(diag_id: int, user_id: int) -> dict | None:
    """按 ID 获取诊断记录（校验用户归属）"""
    async with engine.begin() as conn:
        row = await conn.execute(
            text("SELECT * FROM channel_diagnostics WHERE id = :id AND user_id = :uid"),
            {"id": diag_id, "uid": user_id},
        )
        r = await row.fetchone()
        if not r:
            return None
        return _row_to_dict(r)


async def list_channel_diagnostics(user_id: int, limit: int = 20, offset: int = 0) -> list[dict]:
    """按用户列出诊断记录，最新在前"""
    async with engine.begin() as conn:
        rows = await conn.execute(
            text("""
                SELECT * FROM channel_diagnostics
                WHERE user_id = :uid
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"uid": user_id, "limit": limit, "offset": offset},
        )
        return [_row_to_dict(r) for r in await rows.fetchall()]


def _row_to_dict(row) -> dict:
    """将数据库行转为字典，自动解析 JSON 字段"""
    d = dict(row._mapping)
    if "report_json" in d and isinstance(d["report_json"], str):
        try:
            d["report_json"] = json.loads(d["report_json"])
        except (json.JSONDecodeError, TypeError):
            pass
    return d
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_channel_diagnostics_db.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/db.py tests/test_channel_diagnostics_db.py
git commit -m "feat: add channel_diagnostics table and DB CRUD functions"
```

---

### Task 3: Create cache diagnostics probe runner

**Files:**
- Create: `app/channel_diagnostics.py`
- Test: `tests/test_channel_diagnostics.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_channel_diagnostics.py
"""测试缓存诊断核心逻辑"""

import json
import time
import pytest

from app.channel_diagnostics import (
    CacheDiagnosticResult,
    ProbeResult,
    build_cache_report,
    classify_cache_type,
    estimate_cache_hit_rate_from_latency,
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
    cold = ProbeResult(name="cold", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=5000)
    warm = ProbeResult(name="warm", status="passed", input_tokens=5000,
                       cache_read_tokens=4500, cache_creation_tokens=500)

    result = build_cache_report([cold, warm])
    assert result["prompt_cache"]["status"] == "supported"
    assert result["prompt_cache"]["hit_rate"] == pytest.approx(0.9, abs=0.01)
    assert result["prompt_cache"]["evidence"] == "usage_fields"


def test_estimate_hit_rate_from_latency():
    """usage 无字段时用延迟估算，置信度降低"""
    cold = ProbeResult(name="cold", status="passed", input_tokens=5000,
                       latency_ms=2000, cache_read_tokens=0)
    warm = ProbeResult(name="warm", status="passed", input_tokens=5000,
                       latency_ms=800, cache_read_tokens=0)

    result = build_cache_report([cold, warm])
    assert result["prompt_cache"]["status"] == "estimated"
    assert result["prompt_cache"]["confidence"] < 0.7  # 延迟估算置信度低


def test_response_cache_detected():
    """repeat_identical 秒回应检测到 response cache"""
    cold = ProbeResult(name="cold", status="passed", input_tokens=5000, latency_ms=1500)
    identical = ProbeResult(name="repeat_identical", status="passed",
                           input_tokens=5000, latency_ms=80, identical_request=True)

    result = build_cache_report([cold, identical])
    assert result["response_cache"]["status"] == "suspected"
    assert "identical_request_sub_100ms" in result["response_cache"]["evidence"]


def test_response_cache_not_detected_normal_latency():
    """repeat_identical 正常延迟不触发 response cache"""
    cold = ProbeResult(name="cold", status="passed", input_tokens=5000, latency_ms=1500)
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_channel_diagnostics.py -v`
Expected: FAIL — `app/channel_diagnostics` module 不存在

- [ ] **Step 3: Create app/channel_diagnostics.py**

```python
#!/usr/bin/env python3
"""渠道诊断核心模块 — 缓存命中率检测"""

import json
import logging
import time
import uuid
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


# --- Probe prompt 构建 ---

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
    """冷前缀：长前缀 + 问题"""
    return f"{_LONG_PREFIX}\n\nNow, please answer the following question concisely:\n{question}"


def _build_warm_prefix_prompt(question: str) -> str:
    """暖前缀：相同长前缀 + 不同尾部问题"""
    return f"{_LONG_PREFIX}\n\nNow, please answer the following question concisely:\n{question}"


def _build_breaker_prefix_prompt(question: str) -> str:
    """断路器：修改长前缀的前几个字符，使缓存失效"""
    broken_prefix = "You are a junior developer working on a simple todo list application." + _LONG_PREFIX[50:]
    return f"{broken_prefix}\n\nNow, please answer the following question concisely:\n{question}"


# --- 单个 probe 执行 ---

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

    # 使用低温度确保稳定输出
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

            # 解析 SSE 流
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
                            if not result.response_preview:
                                result.response_preview = delta["text"][:1000]
                            else:
                                result.response_preview += delta["text"][:1000 - len(result.response_preview)]

                    elif event_type == "message_delta":
                        usage = event.get("usage", {})
                        result.output_tokens = usage.get("output_tokens", 0)

                    elif event_type == "message_stop":
                        result.status = "passed"

            result.latency_ms = (time.monotonic() - start) * 1000

            if result.status == "pending":
                result.status = "passed"  # 流正常结束但没有 message_stop

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


# --- 缓存类型判定 ---

def classify_cache_type(probe: ProbeResult) -> str:
    """根据 probe 结果判断缓存类型"""
    if probe.identical_request and probe.latency_ms < 100 and probe.cache_read_tokens == 0:
        return "response_cache"
    if probe.cache_read_tokens > 0:
        return "prompt_cache"
    return "unknown_cache"


# --- 报告生成 ---

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

    # --- Prompt Cache 分析 ---
    if warm and warm.status == "passed" and cold and cold.status == "passed":
        # 方式1：usage 字段直接计算
        if warm.input_tokens > 0 and (warm.cache_read_tokens > 0 or warm.cache_creation_tokens > 0):
            hit_rate = warm.cache_read_tokens / warm.input_tokens if warm.input_tokens > 0 else 0
            # breaker 也用 usage 验证
            breaker_confirms = True
            if breaker and breaker.status == "passed" and breaker.input_tokens > 0:
                breaker_hit = breaker.cache_read_tokens / breaker.input_tokens
                # breaker prefix 应该命中率低
                if breaker_hit > 0.5:
                    breaker_confirms = False

            cost_saving = hit_rate * 0.9  # prompt cache 读取成本约为正常输入的 10%
            report["prompt_cache"] = {
                "status": "supported" if breaker_confirms else "warning",
                "hit_rate": round(hit_rate, 4),
                "estimated_cost_saving": round(cost_saving, 4),
                "evidence": "usage_fields",
                "confidence": 0.9 if breaker_confirms else 0.5,
            }

        # 方式2：延迟估算
        elif warm.latency_ms > 0 and cold.latency_ms > 0:
            speedup = 1 - (warm.latency_ms / cold.latency_ms)
            if speedup > 0:
                hit_rate = min(speedup * 1.2, 1.0)  # 估算系数
                report["prompt_cache"] = {
                    "status": "estimated",
                    "hit_rate": round(hit_rate, 4),
                    "estimated_cost_saving": round(hit_rate * 0.9, 4),
                    "evidence": "latency_estimation",
                    "confidence": 0.4,  # 延迟估算置信度低
                }

    # --- Response Cache 分析 ---
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
                "evidence": [f"identical_request_sub_300ms"],
            }

    return report


def compute_overall_status(report: dict) -> tuple[str, str, float]:
    """根据缓存报告计算总体状态、风险等级和置信度

    Returns: (status, overall_risk, confidence)
    """
    prompt_status = report.get("prompt_cache", {}).get("status", "inconclusive")
    response_status = report.get("response_cache", {}).get("status", "not_detected")
    prompt_confidence = report.get("prompt_cache", {}).get("confidence", 0)

    # Response cache 是风险信号
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


# --- 主入口：运行缓存诊断 ---

async def run_cache_diagnostics(
    config: dict,
    timeout_seconds: int = 60,
) -> CacheDiagnosticResult:
    """运行完整的缓存诊断流程

    Args:
        config: 包含 base_url, api_key, model, protocol 等字段
        timeout_seconds: 单个 probe 超时时间

    Returns:
        CacheDiagnosticResult 包含所有 probe 结果和综合报告
    """
    result = CacheDiagnosticResult()

    connector = aiohttp.TCPConnector(limit=1)
    async with aiohttp.ClientSession(connector=connector) as session:
        # 1. cold_prefix：建立缓存
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

        # 2. warm_prefix：相同前缀不同问题，应命中缓存
        warm_probe = await _run_single_probe(
            session, config,
            prompt=_build_warm_prefix_prompt("What is 2+2? Answer in one word."),
            probe_name="warm_prefix",
            timeout_seconds=timeout_seconds,
        )
        result.probes.append(warm_probe)

        # 3. breaker_prefix：修改前缀，缓存应失效
        breaker_probe = await _run_single_probe(
            session, config,
            prompt=_build_breaker_prefix_prompt("What is the capital of France? Answer in one word."),
            probe_name="breaker_prefix",
            timeout_seconds=timeout_seconds,
        )
        result.probes.append(breaker_probe)

        # 4. repeat_identical：完全相同请求，检测 response cache
        identical_probe = await _run_single_probe(
            session, config,
            prompt=_build_cold_prefix_prompt("What is the capital of France? Answer in one word."),
            probe_name="repeat_identical",
            timeout_seconds=timeout_seconds,
        )
        identical_probe.identical_request = True
        result.probes.append(identical_probe)

    # 构建报告
    result.report = build_cache_report(result.probes)
    status, risk, confidence = compute_overall_status(result.report)
    result.status = status
    result.overall_risk = risk
    result.confidence = confidence

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_channel_diagnostics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/channel_diagnostics.py tests/test_channel_diagnostics.py
git commit -m "feat: add cache diagnostics probe runner and report builder"
```

---

### Task 4: Add API endpoints for channel diagnostics

**Files:**
- Modify: `app/server.py` (add endpoints + imports)
- Modify: `app/db.py` (add export for new functions)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_channel_diagnostics_api.py
"""测试渠道诊断 API 端点"""

import json
import pytest
from unittest.mock import AsyncMock, patch
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_channel_diagnostics_requires_auth(client):
    """未认证请求应返回 401"""
    resp = await client.post("/api/channel-diagnostics", json={
        "profile_name": "test",
        "model": "claude-opus-4-6",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_channel_diagnostics_requires_profile_name(client):
    """缺少 profile_name 应返回 400"""
    headers = await auth_headers(client)
    resp = await client.post("/api/channel-diagnostics", json={
        "model": "claude-opus-4-6",
    }, headers=headers)
    assert resp.status_code == 400
    assert "profile_name" in resp.json()["error"]


@pytest.mark.asyncio
async def test_channel_diagnostics_profile_not_found(client):
    """不存在的 profile 应返回 404"""
    headers = await auth_headers(client)
    resp = await client.post("/api/channel-diagnostics", json={
        "profile_name": "nonexistent",
        "model": "claude-opus-4-6",
    }, headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_channel_diagnostics_success(client):
    """成功运行诊断"""
    headers = await auth_headers(client)

    # 先创建 profile
    await client.post("/api/profiles/save", json={
        "name": "diag-test",
        "base_url": "https://api.anthropic.com",
        "api_key": "sk-test-key",
        "api_key_action": "replace",
        "models": ["claude-opus-4-6"],
        "provider": "anthropic",
    }, headers=headers)

    # Mock 诊断运行器
    from app.channel_diagnostics import CacheDiagnosticResult, ProbeResult

    mock_result = CacheDiagnosticResult(
        status="passed",
        overall_risk="low",
        confidence=0.85,
        probes=[
            ProbeResult(name="cold_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=0, cache_creation_tokens=5000, latency_ms=2000),
            ProbeResult(name="warm_prefix", status="passed", input_tokens=5000,
                       cache_read_tokens=4000, cache_creation_tokens=0, latency_ms=800),
        ],
        report={
            "prompt_cache": {"status": "supported", "hit_rate": 0.8, "evidence": "usage_fields"},
            "response_cache": {"status": "not_detected"},
        },
    )

    with patch("app.server.run_cache_diagnostics", new_callable=AsyncMock, return_value=mock_result):
        resp = await client.post("/api/channel-diagnostics", json={
            "profile_name": "diag-test",
            "model": "claude-opus-4-6",
        }, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert "diagnostic_id" in data
    assert data["status"] == "passed"
    assert data["overall_risk"] == "low"
    assert data["cache_hit_rate"] == 0.8


@pytest.mark.asyncio
async def test_get_channel_diagnostic(client):
    """获取诊断详情"""
    headers = await auth_headers(client)

    # 创建 profile
    await client.post("/api/profiles/save", json={
        "name": "diag-test2",
        "base_url": "https://api.anthropic.com",
        "api_key": "sk-test-key",
        "api_key_action": "replace",
        "models": ["claude-opus-4-6"],
        "provider": "anthropic",
    }, headers=headers)

    from app.channel_diagnostics import CacheDiagnosticResult, ProbeResult

    mock_result = CacheDiagnosticResult(
        status="passed", overall_risk="low", confidence=0.85,
        probes=[], report={"prompt_cache": {"status": "supported", "hit_rate": 0.8}},
    )

    with patch("app.server.run_cache_diagnostics", new_callable=AsyncMock, return_value=mock_result):
        resp = await client.post("/api/channel-diagnostics", json={
            "profile_name": "diag-test2",
            "model": "claude-opus-4-6",
        }, headers=headers)

    diag_id = resp.json()["diagnostic_id"]

    resp = await client.get(f"/api/channel-diagnostics/{diag_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == diag_id
    assert data["model"] == "claude-opus-4-6"
    assert data["report_json"]["prompt_cache"]["hit_rate"] == 0.8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_channel_diagnostics_api.py -v`
Expected: FAIL — `/api/channel-diagnostics` 端点不存在

- [ ] **Step 3: Add import and endpoints to server.py**

在 `app/server.py` 的 import 区域（约第 26-36 行），在现有 db imports 之后添加：

```python
from app.db import save_channel_diagnostic, get_channel_diagnostic, list_channel_diagnostics
from app.channel_diagnostics import run_cache_diagnostics
```

在 `app/server.py` 的 `@app.delete("/api/results/{filename}")` 函数之后、`# ---- Run Center Routes ----` 之前添加：

```python
# ---- Channel Diagnostics Routes ----

@app.post("/api/channel-diagnostics")
async def create_channel_diagnostic(request: Request, user: dict = Depends(get_current_user)):
    """运行渠道诊断"""
    body = await request.json() if (await request.body()) else {}
    profile_name = (body.get("profile_name") or "").strip()
    if not profile_name:
        return JSONResponse({"error": "profile_name is required"}, status_code=400)

    model = (body.get("model") or "").strip()

    # 获取用户 profile
    profile = await _get_user_profile_by_name(user["user_id"], profile_name)
    if not profile:
        return JSONResponse({"error": "Profile not found"}, status_code=404)

    if not model:
        model = profile.get("model", "")

    # 构建诊断配置
    diag_config = {
        "base_url": profile.get("base_url", ""),
        "api_key": profile.get("api_key", ""),
        "model": model,
        "protocol": profile.get("protocol", ""),
        "api_version": profile.get("api_version", "2023-06-01"),
        "custom_endpoint": profile.get("custom_endpoint", False),
    }

    try:
        result = await run_cache_diagnostics(diag_config)
    except Exception as e:
        log.exception("Channel diagnostics failed")
        return JSONResponse({"error": f"Diagnostics failed: {str(e)}"}, status_code=500)

    # 保存诊断记录
    report_dict = {
        "schema_version": 1,
        "profile_name": profile_name,
        "model": model,
        "dimensions": {
            "cache": result.report,
        },
        "probes": [
            {
                "name": p.name,
                "status": p.status,
                "latency_ms": p.latency_ms,
                "usage": {
                    "input_tokens": p.input_tokens,
                    "cache_read_input_tokens": p.cache_read_tokens,
                    "cache_creation_input_tokens": p.cache_creation_tokens,
                },
            }
            for p in result.probes
        ],
    }

    diag_id = await save_channel_diagnostic(
        user_id=user["user_id"],
        profile_name=profile_name,
        model=model,
        status=result.status,
        overall_risk=result.overall_risk,
        confidence=result.confidence,
        report_json=report_dict,
    )

    cache_hit_rate = result.report.get("prompt_cache", {}).get("hit_rate", 0)

    return {
        "diagnostic_id": diag_id,
        "status": result.status,
        "overall_risk": result.overall_risk,
        "confidence": result.confidence,
        "cache_hit_rate": cache_hit_rate,
        "summary": {
            "cache": result.report.get("prompt_cache", {}).get("status", "inconclusive"),
        },
    }


@app.get("/api/channel-diagnostics/{diag_id}")
async def get_channel_diagnostic_handler(diag_id: int, user: dict = Depends(get_current_user)):
    """获取诊断详情"""
    result = await get_channel_diagnostic(diag_id, user["user_id"])
    if not result:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return result


@app.get("/api/channel-diagnostics")
async def list_channel_diagnostics_handler(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    """列出诊断记录"""
    results = await list_channel_diagnostics(user["user_id"], limit=limit, offset=offset)
    return {"items": results, "total": len(results)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_channel_diagnostics_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/server.py tests/test_channel_diagnostics_api.py
git commit -m "feat: add channel diagnostics API endpoints"
```

---

### Task 5: Add frontend API client for diagnostics

**Files:**
- Modify: `frontend/src/api/index.js`

- [ ] **Step 1: Add API functions**

在 `frontend/src/api/index.js` 的 `// Sites` 部分（`getSiteTrend` 函数）之后添加：

```javascript
// Channel Diagnostics
export const createChannelDiagnostic = (data) =>
  api('/api/channel-diagnostics', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

export const getChannelDiagnostic = (id) =>
  api(`/api/channel-diagnostics/${id}`);

export const listChannelDiagnostics = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return api('/api/channel-diagnostics' + (qs ? '?' + qs : ''));
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/index.js
git commit -m "feat: add channel diagnostics API client functions"
```

---

### Task 6: Add cache diagnostic display in history detail

**Files:**
- Modify: `frontend/src/utils/resultDetail.js`

- [ ] **Step 1: Add cache diagnostic rendering to resultDetail.js**

在 `frontend/src/utils/resultDetail.js` 的 `renderResultDetail` 函数中，在最后返回 `html` 之前（约在函数末尾），添加缓存诊断展示。

先在文件顶部 import 区域添加缓存图标函数（如果还没有的话），然后在 `renderResultDetail` 函数的 `let html = ...` 模板中，在 metrics-grid 之后添加：

```javascript
  // --- 渠道诊断摘要 ---
  const diag = c.channel_diagnostic || r.channel_diagnostic_summary_json;
  if (diag && diag.status) {
    const diagStatusMap = {
      passed: { color: 'var(--success)', label: '缓存正常' },
      warning: { color: 'var(--warning)', label: '需关注' },
      critical: { color: 'var(--danger)', label: '高风险' },
      inconclusive: { color: 'var(--text-tertiary)', label: '无法判断' },
      error: { color: 'var(--danger)', label: '诊断失败' },
    };
    const diagInfo = diagStatusMap[diag.status] || diagStatusMap.inconclusive;
    html += `
    <div style="margin-top:16px;padding:12px 16px;background:var(--bg);border-radius:8px;border-left:3px solid ${diagInfo.color}">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
        <span style="font-weight:600;font-size:13px">渠道诊断</span>
        <span style="background:${diagInfo.color};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">${diagInfo.label}</span>
      </div>
      <div style="display:flex;gap:16px;font-size:12px;color:var(--text-secondary)">`;
    if (diag.cache_hit_rate != null) {
      html += `<span>缓存命中率: <strong>${(diag.cache_hit_rate * 100).toFixed(1)}%</strong></span>`;
    }
    if (diag.overall_risk) {
      html += `<span>风险等级: <strong>${escHtml(diag.overall_risk)}</strong></span>`;
    }
    if (diag.confidence != null) {
      html += `<span>置信度: <strong>${(diag.confidence * 100).toFixed(0)}%</strong></span>`;
    }
    html += `
      </div>
    </div>`;
  }
```

注意：这段代码应该插入到 `metrics-grid` 的 `<div>` 结束之后，但在整个 html 模板结束之前。具体位置是在 `</div>` (metrics-grid 结束) 之后。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/utils/resultDetail.js
git commit -m "feat: display cache diagnostic summary in history detail view"
```

---

### Task 7: Add diagnostic icon in history table model column

**Files:**
- Modify: `frontend/src/views/HistoryView.vue` (model column + data loading)

- [ ] **Step 1: Add diagnostic summary to results data**

在 `frontend/src/views/HistoryView.vue` 的 `<script setup>` 区域，结果数据加载逻辑中，需要将诊断摘要附加到结果记录上。在现有的 `results` 数据中，`config` 对象可以携带 `channel_diagnostic_summary_json`。

在模型列的模板中（约第 107 行），将当前的：
```html
<td style="max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="r.config?.model || ''">{{ r.config?.model || '-' }}</td>
```

替换为：
```html
<td style="max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="r.config?.model || ''">
  {{ r.config?.model || '-' }}
  <span v-if="r.channel_diagnostic_status" class="diag-icon" :class="'diag-' + r.channel_diagnostic_status" :title="diagTooltip(r)" style="display:inline-block;width:8px;height:8px;border-radius:50%;margin-left:4px;vertical-align:middle"></span>
</td>
```

在 `<script setup>` 区域添加 `diagTooltip` 函数：
```javascript
function diagTooltip(r) {
  const statusMap = {
    passed: '缓存正常',
    warning: '需关注',
    critical: '高风险',
    inconclusive: '无法判断',
    error: '诊断失败',
  };
  const s = statusMap[r.channel_diagnostic_status] || '未知';
  const rate = r.channel_diagnostic_cache_hit_rate;
  const parts = [`诊断: ${s}`];
  if (rate != null) parts.push(`缓存命中率: ${(rate * 100).toFixed(1)}%`);
  return parts.join(' | ');
}
```

在 `<style>` 区域添加图标颜色：
```css
.diag-icon.diag-passed { background: var(--success); }
.diag-icon.diag-warning { background: var(--warning); }
.diag-icon.diag-critical { background: var(--danger); }
.diag-icon.diag-inconclusive { background: var(--text-tertiary); }
.diag-icon.diag-error { background: var(--danger); }
```

注意：`channel_diagnostic_status` 和 `channel_diagnostic_cache_hit_rate` 需要从后端 `/api/results` 接口返回。这需要在 `app/db.py` 的 `get_results_aggregated` 中，将关联的诊断信息一并查询。如果 results 表增加了 `channel_diagnostic_id` 字段，可以通过 JOIN 或单独查询来实现。在 MVP 阶段，可以先在 `config_json` 中嵌入诊断摘要来简化实现。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/HistoryView.vue
git commit -m "feat: show cache diagnostic icon next to model name in history"
```

---

### Task 8: Run full test suite and fix any issues

- [ ] **Step 1: Run all tests**

Run: `cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/ -v --timeout=30`
Expected: All existing + new tests pass

- [ ] **Step 2: Fix any test failures**

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: fix test issues from cache diagnostics integration"
```
