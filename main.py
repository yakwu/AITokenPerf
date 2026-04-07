#!/usr/bin/env python3
"""
AITokenPerf — API SSE 流式压测工具 (Web 模式)

用法:
  python3 main.py                    # 默认 8080 端口
  python3 main.py --port 9000        # 指定端口
"""

import argparse
import asyncio
import os
import time

import aiohttp

from app.client import send_streaming_request


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
                await on_complete(count, 0, m)

            if _stop_event.is_set():
                break

    workers = [asyncio.create_task(worker()) for _ in range(concurrency * 2)]

    start = time.monotonic()
    while time.monotonic() - start < duration:
        await asyncio.sleep(5)
        if _stop_event.is_set():
            break

    _stop_event.set()

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


def main():
    parser = argparse.ArgumentParser(description="AITokenPerf — API 压测工具 (Web 模式)")
    parser.add_argument("--port", type=int, default=8080, help="Web 服务端口 (默认 8080)")
    parser.add_argument("--host", type=str, default=os.environ.get("HOST", "127.0.0.1"), help="绑定地址 (默认 127.0.0.1)")
    parser.add_argument("--workers", type=int, default=1, help="Worker 进程数 (默认 1)")
    args = parser.parse_args()

    import uvicorn
    uvicorn.run("app.server:app", host=args.host, port=args.port,
                log_level="info", workers=args.workers)


if __name__ == "__main__":
    main()
