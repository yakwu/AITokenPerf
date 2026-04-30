"""工具调用探针 — function calling 多轮"""
import json
import logging
import time
from typing import Any, Dict
import aiohttp
from app.diagnostics.models import ProbeResult, CategoryResult
from app.diagnostics.runner import register_category
from app.protocols import detect_protocol, get_adapter

log = logging.getLogger("diagnostics.tool_use")
TOOLS = [{"name": "calc_sum", "description": "Calculate sum of a and b", "input_schema": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"]}}]


def _execute_tool(name: str, tool_input: Dict[str, Any]) -> str:
    if name == "calc_sum":
        return str(int(tool_input.get("a", 0)) + int(tool_input.get("b", 0)))
    return "unsupported"


@register_category("tool_use")
async def run_tool_use_probes(config: dict, session: aiohttp.ClientSession, run_tag: str, timeout: int) -> CategoryResult:
    protocol = config.get("protocol") or detect_protocol(config.get("model", ""), config.get("provider", ""))
    adapter = get_adapter(protocol)
    probe1 = ProbeResult(name="tool_call_round1", display_name="工具调用-请求")
    probe2 = ProbeResult(name="tool_call_round2", display_name="工具调用-结果")
    start1 = time.monotonic()

    round1_config = dict(config)
    round1_config["system_prompt"] = "You are a helpful assistant."
    round1_config["user_prompt"] = f"[run:{run_tag}] 请调用calc_sum，参数a=7,b=13。计算后告诉我最终结果。"
    round1_config["max_tokens"] = 1024
    round1_config["timeout"] = timeout
    round1_config["cache_test"] = False
    url = adapter.build_url(round1_config)
    headers = adapter.build_headers(round1_config)
    payload1 = adapter.build_payload(round1_config)
    payload1["tools"] = TOOLS

    tool_block = None
    content_blocks = []

    try:
        async with session.post(url, json=payload1, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            probe1.latency_ms = (time.monotonic() - start1) * 1000
            if resp.status != 200:
                body = await resp.text()
                probe1.status = "error"
                probe1.error = f"HTTP {resp.status}: {body[:200]}"
                return CategoryResult(category="tool_use", display_name="工具调用", status="failed", probes=[probe1])
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
                    if etype == "content_block_start":
                        block = event.get("content_block", {})
                        if block.get("type") == "tool_use":
                            tool_block = block
                            content_blocks.append(block)
                    elif etype == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "input_json_delta" and tool_block:
                            tool_block.setdefault("input_str", "")
                            tool_block["input_str"] += delta.get("partial_json", "")
                    elif etype == "message_delta":
                        probe1.output_tokens = event.get("usage", {}).get("output_tokens", 0)
            if tool_block:
                try:
                    tool_block["input"] = json.loads(tool_block.get("input_str", "{}"))
                except (json.JSONDecodeError, TypeError):
                    tool_block["input"] = {}
                tool_block.pop("input_str", None)
                probe1.status = "passed"
                probe1.detail = f"tool={tool_block.get('name')}"
            else:
                probe1.status = "failed"
                probe1.detail = "no tool_use block"
    except Exception as e:
        probe1.latency_ms = (time.monotonic() - start1) * 1000
        probe1.status = "error"
        probe1.error = str(e)
        return CategoryResult(category="tool_use", display_name="工具调用", status="failed", probes=[probe1])

    if probe1.status != "passed":
        return CategoryResult(category="tool_use", display_name="工具调用", status="failed", probes=[probe1])

    # Round 2: send tool_result
    tool_name = tool_block.get("name", "")
    tool_input = tool_block.get("input", {})
    tool_use_id = tool_block.get("id", "")
    tool_result = _execute_tool(tool_name, tool_input if isinstance(tool_input, dict) else {})

    start2 = time.monotonic()
    round2_config = dict(config)
    round2_config["system_prompt"] = "You are a helpful assistant."
    round2_config["user_prompt"] = f"[run:{run_tag}] 请调用calc_sum，参数a=7,b=13。计算后告诉我最终结果。"
    round2_config["max_tokens"] = 1024
    round2_config["timeout"] = timeout
    round2_config["cache_test"] = False
    payload2 = adapter.build_payload(round2_config)
    payload2["tools"] = TOOLS
    payload2["messages"] = [
        {"role": "user", "content": round2_config["user_prompt"]},
        {"role": "assistant", "content": content_blocks},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": tool_result}]},
    ]
    try:
        async with session.post(url, json=payload2, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            probe2.latency_ms = (time.monotonic() - start2) * 1000
            if resp.status != 200:
                probe2.status = "error"
                probe2.error = f"HTTP {resp.status}"
            else:
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
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                output_text += delta.get("text", "")
                if "20" in output_text:
                    probe2.status = "passed"
                    probe2.detail = "结果包含 20"
                else:
                    probe2.status = "failed"
                    probe2.detail = f"结果不含 20: {output_text[:100]}"
    except Exception as e:
        probe2.latency_ms = (time.monotonic() - start2) * 1000
        probe2.status = "error"
        probe2.error = str(e)

    all_passed = probe1.status == "passed" and probe2.status == "passed"
    return CategoryResult(category="tool_use", display_name="工具调用", status="passed" if all_passed else "failed", probes=[probe1, probe2], summary={"tool_name": tool_name, "tool_result": tool_result})
