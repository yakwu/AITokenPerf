#!/usr/bin/env python3
"""E2E 测试模式 — 拦截出站 AI API 请求，返回模拟 SSE 响应"""

import asyncio
import time
from app.client import RequestMetrics

MOCK_DELAY = 0.05
MOCK_INPUT_TOKENS = 100
MOCK_OUTPUT_TOKENS = 50
MOCK_TOKEN_CONTENT = "Test "


async def mock_send_streaming_request(
    config: dict,
    request_id: int,
) -> RequestMetrics:
    """模拟 send_streaming_request，返回预设指标，不发出真实 HTTP 请求。"""
    from app.protocols import detect_protocol

    metrics = RequestMetrics(request_id=request_id)
    protocol = config.get("protocol") or detect_protocol(
        config.get("model", ""), config.get("provider", "")
    )

    await asyncio.sleep(MOCK_DELAY)

    metrics.start_time = time.monotonic()
    metrics.first_token_time = time.monotonic()
    metrics.status_code = 200
    metrics.input_tokens = MOCK_INPUT_TOKENS
    metrics.output_tokens = MOCK_OUTPUT_TOKENS
    metrics.success = True

    for i in range(MOCK_OUTPUT_TOKENS):
        metrics.token_timestamps.append(time.monotonic())

    metrics.end_time = time.monotonic()
    metrics.url = f"mock://e2e-test/{protocol}"

    return metrics
