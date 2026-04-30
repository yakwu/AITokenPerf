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
CONTEXT_WINDOW = 10
MIN_ROUND_LENGTH = 200


@register_category("context")
async def run_context_probes(config: dict, session: aiohttp.ClientSession, run_tag: str, timeout: int) -> CategoryResult:
    protocol = config.get("protocol") or detect_protocol(config.get("model", ""), config.get("provider", ""))
    adapter = get_adapter(protocol)
    history: List[dict] = []
    probes: List[ProbeResult] = []
    for idx in range(1, TOTAL_ROUNDS + 1):
        prompt = f'[run:{run_tag}] 这是第{idx}轮，请围绕“稳定性测试策略”连续写一段超过200字符的中文正文，不要分点，不要标题。'
        probe_config = dict(config)
        probe_config["system_prompt"] = "You are a helpful assistant."
        probe_config["user_prompt"] = prompt
        probe_config["max_tokens"] = 4096
        probe_config["timeout"] = timeout
        probe_config["cache_test"] = False
        url = adapter.build_url(probe_config)
        headers = adapter.build_headers(probe_config)
        payload = adapter.build_payload(probe_config)
        context = history[-CONTEXT_WINDOW:]
        payload["messages"] = context + [{"role": "user", "content": prompt}]
        probe = ProbeResult(name=f"round_{idx}", display_name=f"第{idx}轮对话")
        start = time.monotonic()
        output_text = ""
        try:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout), stream=True) as resp:
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
                            probe.input_tokens = event.get("message", {}).get("usage", {}).get("input_tokens", 0)
                        elif etype == "message_delta":
                            probe.output_tokens = event.get("usage", {}).get("output_tokens", 0)
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
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": output_text})
        if probe.status != "passed":
            break
    all_passed = all(p.status == "passed" for p in probes)
    return CategoryResult(category="context", display_name="多轮上下文", status="passed" if all_passed else "failed", probes=probes, summary={"rounds_completed": len(probes), "all_passed": all_passed})
