#!/usr/bin/env python3
"""OpenAI Chat Completions 协议适配器 — /v1/chat/completions

适用于 DeepSeek、Qwen、GLM、gpt-4 等使用传统 chat completions 格式的模型。
"""

import json
import time

import aiohttp

from app.client import RequestMetrics
from app.protocols.base import ProtocolAdapter


class OpenAIChatAdapter(ProtocolAdapter):

    def build_url(self, config: dict) -> str:
        if config.get("custom_endpoint"):
            return config["base_url"].rstrip("/")
        return f"{config['base_url'].rstrip('/')}/v1/chat/completions"

    def build_headers(self, config: dict) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}",
        }

    def build_payload(self, config: dict) -> dict:
        messages = []
        system_prompt = config.get("system_prompt")
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append(
            {"role": "user", "content": config.get("user_prompt", "Hello")}
        )
        return {
            "model": config["model"],
            "max_tokens": config.get("max_tokens", 512),
            "stream": True,
            "messages": messages,
        }

    async def parse_sse_stream(
        self, resp: aiohttp.ClientResponse, metrics: RequestMetrics
    ) -> None:
        """解析 /v1/chat/completions 的 SSE 流。

        格式: data: {"choices":[{"delta":{"content":"..."}}], "usage":{...}}
        最后一个 chunk: data: [DONE]
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

                if line.startswith("data: "):
                    data_str = line[6:]

                    if data_str.strip() == "[DONE]":
                        metrics.end_time = time.monotonic()
                        if not metrics.error:
                            metrics.success = True
                        continue

                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    # 检查错误
                    if "error" in event:
                        metrics.end_time = time.monotonic()
                        err = event["error"]
                        if isinstance(err, dict):
                            metrics.error = err.get("message", str(err))
                        else:
                            metrics.error = str(err)
                        continue

                    choices = event.get("choices", [])
                    if choices:
                        choice = choices[0]
                        delta = choice.get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            now = time.monotonic()
                            if not metrics.first_token_time:
                                metrics.first_token_time = now
                            metrics.token_timestamps.append(now)

                        # 某些 provider 在最后一个 chunk 中附带 usage
                        usage = event.get("usage")
                        if usage:
                            if "prompt_tokens" in usage:
                                metrics.input_tokens = usage["prompt_tokens"]
                            if "completion_tokens" in usage:
                                metrics.output_tokens = usage["completion_tokens"]

                    # 有些 provider 在最后一个 chunk 无 choices 但有 usage
                    usage = event.get("usage")
                    if usage and not choices:
                        if "prompt_tokens" in usage:
                            metrics.input_tokens = usage["prompt_tokens"]
                        if "completion_tokens" in usage:
                            metrics.output_tokens = usage["completion_tokens"]

        # 如果没收到 [DONE] 但流结束了
        if not metrics.end_time:
            metrics.end_time = time.monotonic()
            if not metrics.error:
                # 如果成功接收到了 token，视为成功
                if metrics.token_timestamps:
                    metrics.success = True
                else:
                    metrics.error = "Stream ended without [DONE]"
