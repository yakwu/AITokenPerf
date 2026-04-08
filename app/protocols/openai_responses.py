#!/usr/bin/env python3
"""OpenAI Responses 协议适配器 — /v1/responses

适用于 gpt-5.4, gpt-5, o3, o3-pro 等新模型。
SSE 事件格式与 chat/completions 完全不同。
"""

import json
import time

import aiohttp

from app.client import RequestMetrics
from app.protocols.base import ProtocolAdapter


class OpenAIResponsesAdapter(ProtocolAdapter):

    def build_url(self, config: dict) -> str:
        return f"{config['base_url'].rstrip('/')}/v1/responses"

    def build_headers(self, config: dict) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}",
        }

    def build_payload(self, config: dict) -> dict:
        payload = {
            "model": config["model"],
            "input": config.get("user_prompt", "Hello"),
            "max_output_tokens": config.get("max_tokens", 512),
            "stream": True,
        }
        system_prompt = config.get("system_prompt")
        if system_prompt:
            payload["instructions"] = system_prompt
        return payload

    async def parse_sse_stream(
        self, resp: aiohttp.ClientResponse, metrics: RequestMetrics
    ) -> None:
        """解析 /v1/responses 的 SSE 流。

        关键事件类型:
        - response.output_text.delta: 文本增量
        - response.completed: 完成，含 usage
        - response.output_text.done: 文本输出完成
        - response.failed: 失败
        """
        buffer = ""
        async for chunk in resp.content:
            text = chunk.decode("utf-8", errors="replace")
            buffer += text

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()

                if not line or line.startswith(":"):
                    continue

                # Responses API 用 event: + data: 格式
                if line.startswith("event: "):
                    # event 行，下一行应该是 data
                    continue

                if line.startswith("data: "):
                    data_str = line[6:]

                    if data_str.strip() == "[DONE]":
                        metrics.end_time = time.monotonic()
                        metrics.success = True
                        continue

                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")

                    if event_type == "response.output_text.delta":
                        now = time.monotonic()
                        delta_text = event.get("delta", "")
                        if delta_text:
                            if not metrics.first_token_time:
                                metrics.first_token_time = now
                            metrics.token_timestamps.append(now)

                    elif event_type == "response.completed":
                        now = time.monotonic()
                        metrics.end_time = now
                        # 提取 usage
                        response_obj = event.get("response", {})
                        usage = response_obj.get("usage", {})
                        if "input_tokens" in usage:
                            metrics.input_tokens = usage["input_tokens"]
                        if "output_tokens" in usage:
                            metrics.output_tokens = usage["output_tokens"]
                        # 检查是否失败
                        status = response_obj.get("status", "")
                        if status == "failed":
                            error_obj = response_obj.get("error", {})
                            metrics.error = f"Response failed: {error_obj.get('message', 'unknown')}"
                            metrics.success = False
                        else:
                            metrics.success = True

                    elif event_type == "response.output_text.done":
                        # 文本输出完成，但不一定有 usage，等 response.completed
                        pass

                    elif event_type == "response.failed":
                        metrics.end_time = time.monotonic()
                        error_msg = event.get("error", {})
                        if isinstance(error_msg, dict):
                            metrics.error = f"Response failed: {error_msg.get('message', 'unknown')}"
                        else:
                            metrics.error = f"Response failed: {error_msg}"
                        metrics.success = False

        # 如果没收到 completed 但流结束了
        if not metrics.end_time:
            metrics.end_time = time.monotonic()
            if not metrics.error:
                metrics.error = "Stream ended without response.completed"
