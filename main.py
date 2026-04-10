#!/usr/bin/env python3
"""
AITokenPerf — API SSE 流式压测工具 (Web 模式)

用法:
  python3 main.py                    # 默认 8080 端口
  python3 main.py --port 9000        # 指定端口
"""

import argparse
import asyncio
import logging
import os
import time

import aiohttp

from app.client import send_streaming_request

log = logging.getLogger("bench")


async def run_burst(session: aiohttp.ClientSession, config: dict, concurrency: int, on_complete=None) -> list:
    """Burst 模式：一次性发出 N 个并发请求"""
    total_requests = config.get("requests_per_level") or concurrency
    log.info("[Burst] Launching %d requests with concurrency=%d", total_requests, concurrency)

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
        if not m.success:
            log.warning("[Burst] Request %d/%d FAILED: %s (status=%s)", done, total_requests, m.error, m.status_code)
        if on_complete:
            await on_complete(done, total_requests, m)
        else:
            status = "OK" if m.success else f"FAIL({m.error})"
            if done % max(1, total_requests // 10) == 0 or done == total_requests:
                log.info("[Burst] Progress: %d/%d (%s)", done, total_requests, status)

    log.info("[Burst] Done: %d results, %d succeeded", len(results), sum(1 for r in results if r.success))
    return results


async def run_sustained(
    session: aiohttp.ClientSession, config: dict, concurrency: int, duration: int,
    on_complete=None, stop_event: asyncio.Event = None
) -> list:
    """Sustained 模式：持续维持 N 个并发请求，跑 duration 秒"""
    log.info("[Sustained] Maintaining %d concurrent for %ds", concurrency, duration)

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
    log.info("[Dry Run] Sending 1 request to verify connectivity")
    m = await send_streaming_request(session, config, 0)

    if m.success:
        log.info("[Dry Run] OK — TTFT: %s, TPOT: %s, E2E: %s, tokens: %d in / %d out",
                 f"{m.ttft:.3f}s" if m.ttft else "N/A",
                 f"{m.tpot:.4f}s" if m.tpot else "N/A",
                 f"{m.e2e:.3f}s" if m.e2e else "N/A",
                 m.input_tokens, m.output_tokens)
        return True
    else:
        log.error("[Dry Run] FAILED — HTTP %s, error: %s", m.status_code, m.error)
        return False


def main():
    parser = argparse.ArgumentParser(description="AITokenPerf — API 压测工具 (Web 模式)")
    parser.add_argument("--port", type=int, default=8080, help="Web 服务端口 (默认 8080)")
    parser.add_argument("--host", type=str, default=os.environ.get("HOST", "127.0.0.1"), help="绑定地址 (默认 127.0.0.1)")
    parser.add_argument("--workers", type=int, default=1, help="Worker 进程数 (默认 1)")
    args = parser.parse_args()

    import uvicorn
    log_fmt = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(level=logging.INFO, format=log_fmt, datefmt=date_fmt)

    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": log_fmt,
                "datefmt": date_fmt,
            },
            "access": {
                "format": log_fmt,
                "datefmt": date_fmt,
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        },
    }
    uvicorn.run("app.server:app", host=args.host, port=args.port,
                log_level="info", workers=args.workers, log_config=log_config)


if __name__ == "__main__":
    main()
