#!/usr/bin/env python3
"""Claude API SSE 流式压测工具 - 统计与报表模块"""

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np

from app.client import RequestMetrics


@dataclass
class BenchmarkResult:
    """单次压测结果"""
    concurrency: int
    mode: str
    total_requests: int
    success_count: int
    failed_count: int
    error_counts: dict  # error_type -> count
    error_details: list  # [{request_id, status_code, error}, ...]

    ttft_values: list  # seconds
    tpot_values: list  # seconds
    e2e_values: list   # seconds
    output_tokens_list: list
    input_tokens_list: list

    duration: float  # 整个测试耗时
    cost_input: float = 0.0    # 输入 token 费用 (USD)
    cost_output: float = 0.0   # 输出 token 费用 (USD)

    @property
    def total_cost(self) -> float:
        return self.cost_input + self.cost_output

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.success_count / self.total_requests * 100

    @property
    def avg_tokens_per_request(self) -> float:
        if not self.output_tokens_list:
            return 0.0
        return sum(self.output_tokens_list) / len(self.output_tokens_list)

    @property
    def total_output_tokens(self) -> int:
        return sum(self.output_tokens_list)

    @property
    def total_input_tokens(self) -> int:
        return sum(self.input_tokens_list)

    @property
    def throughput(self) -> float:
        """请求吞吐量 (req/s)"""
        if self.duration == 0:
            return 0.0
        return self.success_count / self.duration

    @property
    def token_throughput(self) -> float:
        """Token 吞吐量 (tokens/s)"""
        if self.duration == 0:
            return 0.0
        return self.total_output_tokens / self.duration


def _token_percentiles(values: list) -> Optional[dict]:
    """计算 token 数的百分位分布，返回不含 label 的字典"""
    p = compute_percentiles(values, "")
    if p:
        del p["label"]
    return p


def compute_percentiles(values: list, label: str) -> Optional[dict]:
    """计算百分位数"""
    if not values:
        return None
    arr = np.array(values)
    return {
        "label": label,
        "P50": float(np.percentile(arr, 50)),
        "P95": float(np.percentile(arr, 95)),
        "P99": float(np.percentile(arr, 99)),
        "P99.5": float(np.percentile(arr, 99.5)),
        "Max": float(np.max(arr)),
        "Min": float(np.min(arr)),
        "Avg": float(np.mean(arr)),
    }


def aggregate_metrics(
    metrics_list: list[RequestMetrics],
    concurrency: int,
    mode: str,
    duration: float,
    pricing: Optional[dict] = None,
) -> BenchmarkResult:
    """汇总所有请求的指标"""
    success_count = sum(1 for m in metrics_list if m.success)
    failed_count = len(metrics_list) - success_count

    error_counts = {}
    error_details = []
    for m in metrics_list:
        if m.error:
            key = m.error.split(":")[0] if ":" in m.error else m.error
            error_counts[key] = error_counts.get(key, 0) + 1
            detail = {
                "request_id": m.request_id,
                "status_code": m.status_code,
                "error": m.error,
                "duration": round(m.e2e, 2) if m.e2e else None,
                "tokens_received": len(m.token_timestamps),
                "phase": m.phase or "",
                "url": m.url or "",
            }
            error_details.append(detail)

    ttft_values = [m.ttft for m in metrics_list if m.ttft is not None and m.success]
    tpot_values = [m.tpot for m in metrics_list if m.tpot is not None and m.success]
    e2e_values = [m.e2e for m in metrics_list if m.e2e is not None and m.success]
    output_tokens = [m.output_tokens for m in metrics_list if m.success]
    input_tokens = [m.input_tokens for m in metrics_list if m.success]

    # 费用计算
    cost_input = 0.0
    cost_output = 0.0
    if pricing:
        total_in = sum(input_tokens)
        total_out = sum(output_tokens)
        cost_input = total_in * pricing.get("input_cost_per_token", 0.0)
        cost_output = total_out * pricing.get("output_cost_per_token", 0.0)

    return BenchmarkResult(
        concurrency=concurrency,
        mode=mode,
        total_requests=len(metrics_list),
        success_count=success_count,
        failed_count=failed_count,
        error_counts=error_counts,
        error_details=error_details,
        ttft_values=ttft_values,
        tpot_values=tpot_values,
        e2e_values=e2e_values,
        output_tokens_list=output_tokens,
        input_tokens_list=input_tokens,
        duration=duration,
        cost_input=cost_input,
        cost_output=cost_output,
    )


def format_time(seconds: float) -> str:
    """格式化时间"""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    return f"{seconds:.2f}s"


def print_report(result: BenchmarkResult, config: dict = None):
    """打印压测报告"""
    print("\n" + "=" * 70)
    if config:
        print(f"  Base URL: {config.get('base_url')} | Model: {config.get('model')}")
    print(f"  Concurrency: {result.concurrency} | Mode: {result.mode}")
    print("=" * 70)

    print(f"\n  Total: {result.total_requests} | "
          f"Success: {result.success_count} ({result.success_rate:.1f}%) | "
          f"Failed: {result.failed_count}")
    print(f"  Duration: {format_time(result.duration)} | "
          f"Throughput: {result.throughput:.1f} req/s | "
          f"Token Rate: {result.token_throughput:.0f} tokens/s")

    if result.error_counts:
        print(f"\n  Errors:")
        for err, count in sorted(result.error_counts.items(), key=lambda x: -x[1]):
            print(f"    {err}: {count}")

    # 百分位表格
    stats = [
        compute_percentiles(result.ttft_values, "TTFT"),
        compute_percentiles(result.tpot_values, "TPOT"),
        compute_percentiles(result.e2e_values, "E2E"),
    ]
    stats = [s for s in stats if s is not None]

    if stats:
        print(f"\n  {'':8s} {'P50':>8s} {'P95':>8s} {'P99':>8s} {'P99.5':>8s} {'Max':>8s} {'Avg':>8s}")
        print(f"  {'-'*56}")
        for s in stats:
            print(f"  {s['label']:8s} "
                  f"{format_time(s['P50']):>8s} "
                  f"{format_time(s['P95']):>8s} "
                  f"{format_time(s['P99']):>8s} "
                  f"{format_time(s['P99.5']):>8s} "
                  f"{format_time(s['Max']):>8s} "
                  f"{format_time(s['Avg']):>8s}")

    print(f"\n  Avg Output Tokens/Request: {result.avg_tokens_per_request:.1f}")
    print(f"  Total Tokens: input={result.total_input_tokens}, output={result.total_output_tokens}")
    print("=" * 70)


def build_report_dict(result: BenchmarkResult, config: dict) -> dict:
    """构建报告字典（不写文件）"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    test_id = uuid.uuid4().hex[:8]
    report = {
        "test_id": test_id,
        "timestamp": timestamp,
        "config": {
            "profile_name": config.get("profile_name", ""),
            "model": config.get("model"),
            "base_url": config.get("base_url"),
            "api_version": config.get("api_version"),
            "max_tokens": config.get("max_tokens"),
            "concurrency": result.concurrency,
            "mode": result.mode,
            "duration": config.get("duration"),
            "timeout": config.get("timeout"),
            "system_prompt": config.get("system_prompt"),
            "user_prompt": config.get("user_prompt"),
        },
        "summary": {
            "total_requests": result.total_requests,
            "success_count": result.success_count,
            "failed_count": result.failed_count,
            "success_rate": result.success_rate,
            "duration_seconds": result.duration,
            "throughput_rps": result.throughput,
            "token_throughput_tps": result.token_throughput,
            "avg_output_tokens": result.avg_tokens_per_request,
            "total_input_tokens": result.total_input_tokens,
            "total_output_tokens": result.total_output_tokens,
            "cost_input_usd": round(result.cost_input, 8),
            "cost_output_usd": round(result.cost_output, 8),
            "cost_total_usd": round(result.total_cost, 8),
            "input_tokens": _token_percentiles(result.input_tokens_list),
            "output_tokens": _token_percentiles(result.output_tokens_list),
        },
        "percentiles": {},
        "errors": result.error_counts,
        "error_details": result.error_details,
    }

    for name, values in [("TTFT", result.ttft_values), ("TPOT", result.tpot_values), ("E2E", result.e2e_values)]:
        p = compute_percentiles(values, name)
        if p:
            del p["label"]
            report["percentiles"][name] = p

    return report
