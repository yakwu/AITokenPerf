#!/usr/bin/env python3
"""Claude API SSE 流式压测工具 - 指标采集模块"""

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

from app.protocols import detect_protocol, get_adapter


@dataclass
class RequestMetrics:
    """单个请求的指标"""
    request_id: int
    start_time: float = 0.0
    first_token_time: float = 0.0
    end_time: float = 0.0
    token_timestamps: list = field(default_factory=list)
    output_tokens: int = 0
    input_tokens: int = 0
    success: bool = False
    error: Optional[str] = None
    status_code: int = 0
    url: str = ""
    phase: str = ""  # "connecting" | "streaming" — 超时时记录阶段

    @property
    def ttft(self) -> Optional[float]:
        """Time To First Token (秒)"""
        if self.first_token_time and self.start_time:
            return self.first_token_time - self.start_time
        return None

    @property
    def e2e(self) -> Optional[float]:
        """End to End 总耗时 (秒)"""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return None

    @property
    def tpot(self) -> Optional[float]:
        """Time Per Output Token - 平均每 token 输出延迟 (秒)"""
        if len(self.token_timestamps) >= 2:
            intervals = []
            for i in range(1, len(self.token_timestamps)):
                intervals.append(self.token_timestamps[i] - self.token_timestamps[i - 1])
            return sum(intervals) / len(intervals)
        return None


async def send_streaming_request(
    session: aiohttp.ClientSession,
    config: dict,
    request_id: int,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> RequestMetrics:
    """发送单个 SSE 流式请求并采集指标。

    根据 config 中的 protocol（或 model 名自动检测）选择对应的协议适配器。
    """

    metrics = RequestMetrics(request_id=request_id)

    # 确定协议
    protocol = config.get("protocol") or detect_protocol(
        config.get("model", ""), config.get("provider", "")
    )
    adapter = get_adapter(protocol)

    url = adapter.build_url(config)
    metrics.url = url
    headers = adapter.build_headers(config)
    payload = adapter.build_payload(config)

    sem_ctx = semaphore if semaphore else contextlib.AsyncExitStack()

    async with sem_ctx:
        metrics.start_time = time.monotonic()
        metrics.phase = "connecting"
        try:
            timeout = aiohttp.ClientTimeout(total=config.get("timeout", 120))
            async with session.post(
                url, json=payload, headers=headers, timeout=timeout
            ) as resp:
                metrics.status_code = resp.status
                metrics.phase = "streaming"

                if resp.status != 200:
                    body = await resp.text()
                    metrics.error = f"HTTP {resp.status}: {body[:200]}"
                    metrics.end_time = time.monotonic()
                    return metrics

                # 由适配器解析 SSE 流
                await adapter.parse_sse_stream(resp, metrics)

                # 如果没收到结束信号但流结束了
                if not metrics.end_time:
                    metrics.end_time = time.monotonic()
                    if not metrics.error:
                        metrics.error = "Stream ended unexpectedly"

        except asyncio.TimeoutError:
            metrics.end_time = time.monotonic()
            if metrics.phase == "connecting":
                metrics.error = "Connection timed out"
            else:
                tokens = len(metrics.token_timestamps)
                metrics.error = f"Stream timed out (received {tokens} tokens in {metrics.e2e:.1f}s)"
        except aiohttp.ClientError as e:
            metrics.end_time = time.monotonic()
            metrics.error = f"Connection error: {str(e)}"
        except Exception as e:
            metrics.end_time = time.monotonic()
            metrics.error = f"Unexpected error: {str(e)}"

    return metrics
