#!/usr/bin/env python3
"""
Claude API SSE 流式压测工具

用法:
  python3 main.py                          # 使用 config.yaml
  python3 main.py -c myconfig.yaml         # 指定配置文件
  python3 main.py --concurrency 100        # 只跑 100 并发
  python3 main.py --mode sustained --duration 60  # 持续模式
  python3 main.py --dry-run                # 只发 1 个请求验证连通性
  python3 main.py --web                    # 启动 Web 管理界面
  python3 main.py --web --port 9000        # 指定端口
"""

import argparse
import asyncio
import sys
import time

import aiohttp
import yaml

from client import send_streaming_request
from stats import aggregate_metrics, print_report, save_report


async def run_burst(session: aiohttp.ClientSession, config: dict, concurrency: int, on_complete=None) -> list:
    """Burst 模式：一次性发出 N 个并发请求"""
    total_requests = config.get("requests_per_level") or concurrency
    print(f"\n  [Burst] Launching {total_requests} requests with concurrency={concurrency}...")

    semaphore = asyncio.Semaphore(concurrency)

    async def limited_request(i):
        async with semaphore:
            return await send_streaming_request(session, config, i)

    tasks = [limited_request(i) for i in range(total_requests)]

    results = []
    done = 0
    for coro in asyncio.as_completed(tasks):
        m = await coro
        done += 1
        results.append(m)
        if on_complete:
            await on_complete(done, total_requests, m)
        else:
            status = "OK" if m.success else f"FAIL({m.error})"
            if done % max(1, total_requests // 10) == 0 or done == total_requests:
                print(f"    Progress: {done}/{total_requests} ({status})")

    return results


async def run_sustained(
    session: aiohttp.ClientSession, config: dict, concurrency: int, duration: int,
    on_complete=None, stop_event: asyncio.Event = None
) -> list:
    """Sustained 模式：持续维持 N 个并发请求，跑 duration 秒"""
    print(f"\n  [Sustained] Maintaining {concurrency} concurrent for {duration}s...")

    results = []
    request_counter = 0
    semaphore = asyncio.Semaphore(concurrency)
    _stop_event = stop_event or asyncio.Event()
    lock = asyncio.Lock()

    async def worker():
        nonlocal request_counter
        while not _stop_event.is_set():
            async with lock:
                request_counter += 1
                rid = request_counter

            m = await send_streaming_request(session, config, rid, semaphore)
            async with lock:
                results.append(m)
                count = len(results)

            if on_complete:
                await on_complete(count, 0, m)  # total=0 means unknown in sustained mode
            elif not on_complete:
                pass  # CLI progress handled below

            if _stop_event.is_set():
                break

    # 启动比并发数更多的 worker 以保证持续有请求
    workers = [asyncio.create_task(worker()) for _ in range(concurrency * 2)]

    # 进度报告 (CLI only when no callback)
    start = time.monotonic()
    while time.monotonic() - start < duration:
        await asyncio.sleep(5)
        if _stop_event.is_set():
            break
        elapsed = time.monotonic() - start
        async with lock:
            count = len(results)
            success = sum(1 for r in results if r.success)
        if not on_complete:
            print(f"    [{elapsed:.0f}s] Completed: {count}, Success: {success}")

    _stop_event.set()

    # 等待所有 worker 结束（给个超时）
    done, pending = await asyncio.wait(workers, timeout=config.get("timeout", 120))
    for t in pending:
        t.cancel()

    return results


async def run_dry(session: aiohttp.ClientSession, config: dict):
    """Dry run: 发 1 个请求验证连通性和指标采集"""
    print("\n  [Dry Run] Sending 1 request to verify connectivity...\n")
    m = await send_streaming_request(session, config, 0)

    if m.success:
        print(f"    Status: OK")
        print(f"    TTFT: {m.ttft:.3f}s" if m.ttft else "    TTFT: N/A")
        print(f"    TPOT: {m.tpot:.4f}s" if m.tpot else "    TPOT: N/A")
        print(f"    E2E:  {m.e2e:.3f}s" if m.e2e else "    E2E: N/A")
        print(f"    Output Tokens: {m.output_tokens}")
        print(f"    Input Tokens: {m.input_tokens}")
        print(f"    Token events captured: {len(m.token_timestamps)}")
        print(f"\n    Dry run passed. Ready to benchmark.")
    else:
        print(f"    Status: FAILED")
        print(f"    HTTP Code: {m.status_code}")
        print(f"    Error: {m.error}")
        print(f"\n    Fix the error above before running the benchmark.")
        return False
    return True


async def main():
    parser = argparse.ArgumentParser(description="AITokenPerf - API SSE Streaming Benchmark")
    parser.add_argument("-c", "--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--concurrency", type=int, nargs="+", help="覆盖并发级别，如 --concurrency 100 500")
    parser.add_argument("--mode", choices=["burst", "sustained"], help="覆盖测试模式")
    parser.add_argument("--duration", type=int, help="sustained 模式持续时间(秒)")
    parser.add_argument("--dry-run", action="store_true", help="只发 1 个请求验证")
    parser.add_argument("--output", help="覆盖输出目录")
    parser.add_argument("--web", action="store_true", help="启动 Web 管理界面")
    parser.add_argument("--port", type=int, default=8080, help="Web 服务端口 (默认 8080)")
    args = parser.parse_args()

    # 加载配置（支持环境变量覆盖，config.yaml 非必需）
    import os
    config_path = args.config
    if os.path.exists(config_path):
        with open(config_path) as f:
            raw_config = yaml.safe_load(f) or {}
    else:
        raw_config = {}

    # Web 模式传入原始配置
    if args.web:
        from server import start_server
        await start_server(raw_config, args.port)
        return

    # 合并 profiles + benchmark 为扁平运行配置
    from server import _resolve_config
    config = _resolve_config(raw_config)

    # 命令行参数覆盖
    if args.concurrency:
        config["concurrency_levels"] = args.concurrency
    if args.mode:
        config["mode"] = args.mode
    if args.duration:
        config["duration"] = args.duration
    if args.output:
        config["output_dir"] = args.output

    mode = config.get("mode", "burst")
    output_dir = config.get("output_dir", "./results")
    concurrency_levels = config.get("concurrency_levels", [100])

    # 检查必要配置
    if not config.get("api_key") or config["api_key"].startswith("sk-ant-xxxxx"):
        print("Error: Please set a valid api_key in config.yaml")
        sys.exit(1)

    print(f"\n{'='*70}")
    print(f"  AITokenPerf")
    print(f"  Model: {config.get('model')} | Base URL: {config.get('base_url')}")
    print(f"  Mode: {mode} | Levels: {concurrency_levels}")
    print(f"{'='*70}")

    # 创建连接池
    connector = aiohttp.TCPConnector(
        limit=config.get("connector_limit", 1200),
        force_close=False,
        enable_cleanup_closed=True,
    )

    async with aiohttp.ClientSession(connector=connector) as session:
        # Dry run
        if args.dry_run:
            await run_dry(session, config)
            return

        # 先做一次 dry run 验证
        print("\n  Pre-check: verifying connectivity...")
        if not await run_dry(session, config):
            sys.exit(1)

        # 逐级加压
        all_results = []
        for level in concurrency_levels:
            print(f"\n{'='*70}")
            print(f"  Starting benchmark: concurrency={level}, mode={mode}")
            print(f"{'='*70}")

            bench_start = time.monotonic()

            if mode == "burst":
                metrics = await run_burst(session, config, level)
            else:
                duration = config.get("duration", 120)
                metrics = await run_sustained(session, config, level, duration)

            bench_duration = time.monotonic() - bench_start

            result = aggregate_metrics(metrics, level, mode, bench_duration)
            print_report(result, config)
            save_report(result, output_dir, config)
            all_results.append(result)

            # 级别间间隔 5 秒，让服务端恢复
            if level != concurrency_levels[-1]:
                print("\n  Cooling down 5s before next level...")
                await asyncio.sleep(5)

        # 汇总对比
        if len(all_results) > 1:
            print(f"\n\n{'='*70}")
            print(f"  Summary Comparison")
            print(f"{'='*70}")
            print(f"\n  {'Level':>8s} {'Success%':>10s} {'TTFT-P50':>10s} {'TPOT-P50':>10s} {'E2E-P50':>10s} {'Throughput':>12s}")
            print(f"  {'-'*58}")
            for r in all_results:
                from stats import compute_percentiles, format_time
                ttft_p = compute_percentiles(r.ttft_values, "")
                tpot_p = compute_percentiles(r.tpot_values, "")
                e2e_p = compute_percentiles(r.e2e_values, "")
                print(f"  {r.concurrency:>8d} "
                      f"{r.success_rate:>9.1f}% "
                      f"{format_time(ttft_p['P50']) if ttft_p else 'N/A':>10s} "
                      f"{format_time(tpot_p['P50']) if tpot_p else 'N/A':>10s} "
                      f"{format_time(e2e_p['P50']) if e2e_p else 'N/A':>10s} "
                      f"{r.throughput:>10.1f}/s")
            print()


if __name__ == "__main__":
    asyncio.run(main())
