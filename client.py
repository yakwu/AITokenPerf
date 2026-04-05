#!/usr/bin/env python3
"""Claude API SSE 流式压测工具 - 指标采集模块"""

import asyncio
import contextlib
import time
import json
from dataclasses import dataclass, field
from typing import Optional

import aiohttp


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
    """发送单个 SSE 流式请求并采集指标"""

    metrics = RequestMetrics(request_id=request_id)
    url = f"{config['base_url'].rstrip('/')}/v1/messages"

    headers = {
        "Content-Type": "application/json",
        "x-api-key": config["api_key"],
        "anthropic-version": config.get("api_version", "2023-06-01"),
    }

    payload = {
        "model": config["model"],
        "max_tokens": config.get("max_tokens", 512),
        "stream": True,
        "system": config.get("system_prompt", "You are a helpful assistant."),
        "messages": [
            {"role": "user", "content": config.get("user_prompt", "Hello")}
        ],
    }

    sem_ctx = semaphore if semaphore else contextlib.AsyncExitStack()

    async with sem_ctx:
        metrics.start_time = time.monotonic()
        try:
            timeout = aiohttp.ClientTimeout(total=config.get("timeout", 120))
            async with session.post(
                url, json=payload, headers=headers, timeout=timeout
            ) as resp:
                metrics.status_code = resp.status

                if resp.status != 200:
                    body = await resp.text()
                    metrics.error = f"HTTP {resp.status}: {body[:200]}"
                    metrics.end_time = time.monotonic()
                    return metrics

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

                        if line.startswith("data: "):
                            data_str = line[6:]

                            if data_str.strip() == "[DONE]":
                                continue

                            try:
                                event = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            event_type = event.get("type", "")

                            if event_type == "content_block_delta":
                                now = time.monotonic()
                                delta = event.get("delta", {})
                                if delta.get("type") == "text_delta" and delta.get("text"):
                                    if not metrics.first_token_time:
                                        metrics.first_token_time = now
                                    metrics.token_timestamps.append(now)

                            elif event_type == "message_delta":
                                usage = event.get("usage", {})
                                if "output_tokens" in usage:
                                    metrics.output_tokens = usage["output_tokens"]

                            elif event_type == "message_start":
                                msg = event.get("message", {})
                                usage = msg.get("usage", {})
                                if "input_tokens" in usage:
                                    metrics.input_tokens = usage["input_tokens"]

                            elif event_type == "message_stop":
                                metrics.end_time = time.monotonic()
                                metrics.success = True

                # 如果没收到 message_stop 但流结束了
                if not metrics.end_time:
                    metrics.end_time = time.monotonic()
                    if not metrics.error:
                        metrics.error = "Stream ended without message_stop"

        except asyncio.TimeoutError:
            metrics.end_time = time.monotonic()
            metrics.error = "Request timed out"
        except aiohttp.ClientError as e:
            metrics.end_time = time.monotonic()
            metrics.error = f"Connection error: {str(e)}"
        except Exception as e:
            metrics.end_time = time.monotonic()
            metrics.error = f"Unexpected error: {str(e)}"

    return metrics
