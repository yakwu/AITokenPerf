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
async def run_streaming_probes(config: dict, session: aiohttp.ClientSession, run_tag: str, timeout: int) -> CategoryResult:
    protocol = config.get("protocol") or detect_protocol(config.get("model", ""), config.get("provider", ""))
    adapter = get_adapter(protocol)
    probe_config = dict(config)
    probe_config["system_prompt"] = "You are a helpful assistant."
    probe_config["user_prompt"] = f'[run:{run_tag}] 请输出一段超过500个字符的中文内容，主题是“软件测试可观测性实践”，请连续输出，不要分点，不要用代码块。'
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
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout), stream=True) as resp:
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
                        probe.input_tokens = event.get("message", {}).get("usage", {}).get("input_tokens", 0)
                    elif etype == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            output_text += delta["text"]
                            if first_text_at is None:
                                first_text_at = time.monotonic()
                    elif etype == "message_delta":
                        probe.output_tokens = event.get("usage", {}).get("output_tokens", 0)
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
    return CategoryResult(category="streaming", display_name="流式传输", status="passed" if probe.status == "passed" else "failed", probes=[probe])
