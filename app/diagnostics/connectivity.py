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
async def run_connectivity_probes(config: dict, session: aiohttp.ClientSession, run_tag: str, timeout: int) -> CategoryResult:
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
    probe = ProbeResult(name="single_non_stream", display_name="单轮非流式")
    start = time.monotonic()
    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            probe.latency_ms = (time.monotonic() - start) * 1000
            if resp.status != 200:
                body = await resp.text()
                probe.status = "failed"
                probe.error = f"HTTP {resp.status}: {body[:200]}"
                return CategoryResult(category="connectivity", display_name="连通性", status="failed", probes=[probe])
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
                    etype = event.get("type", "")
                    if etype == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            output_text += delta.get("text", "")
                    elif etype == "message_start":
                        probe.input_tokens = event.get("message", {}).get("usage", {}).get("input_tokens", 0)
                    elif etype == "message_delta":
                        probe.output_tokens = event.get("usage", {}).get("output_tokens", 0)
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
    return CategoryResult(category="connectivity", display_name="连通性", status="passed" if probe.status == "passed" else "failed", probes=[probe])
