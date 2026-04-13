#!/usr/bin/env python3
"""Anthropic Claude 协议适配器 — /v1/messages"""

import json
import time

import aiohttp

from app.client import RequestMetrics
from app.protocols.base import ProtocolAdapter


class AnthropicAdapter(ProtocolAdapter):

    def build_url(self, config: dict) -> str:
        if config.get("custom_endpoint"):
            return config["base_url"].rstrip("/")
        return f"{config['base_url'].rstrip('/')}/v1/messages"

    def build_headers(self, config: dict) -> dict:
        return {
            "Content-Type": "application/json",
            "x-api-key": config["api_key"],
            "anthropic-version": config.get("api_version", "2023-06-01"),
        }

    def build_payload(self, config: dict) -> dict:
        return {
            "model": config["model"],
            "max_tokens": config.get("max_tokens", 512),
            "stream": True,
            "system": config.get("system_prompt", "You are a helpful assistant."),
            "messages": [
                {"role": "user", "content": config.get("user_prompt", "Hello")}
            ],
        }

    async def parse_sse_stream(
        self, resp: aiohttp.ClientResponse, metrics: RequestMetrics
    ) -> None:
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
