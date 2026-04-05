#!/usr/bin/env python3
"""Claude API 压测工具 - Web 后端"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from aiohttp import web

import aiohttp as aiohttp_lib

from client import send_streaming_request
from stats import aggregate_metrics, build_report_dict, save_report

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
RESULTS_DIR = BASE_DIR / "results"
STATIC_DIR = BASE_DIR / "static"

CONNECTION_KEYS = ("base_url", "api_key", "model", "api_version")
BENCHMARK_KEYS = ("mode", "concurrency_levels", "duration", "max_tokens",
                   "timeout", "connector_limit", "system_prompt", "user_prompt")


@dataclass
class BenchState:
    status: str = "idle"  # idle | running | stopping
    current_task: Optional[asyncio.Task] = None
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    task_id: str = ""
    events: list = field(default_factory=list)
    event_seq: int = 0
    current_concurrency: int = 0
    current_level: int = 0
    total_levels: int = 0
    done_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    total_count: int = 0
    start_time: float = 0.0


state = BenchState()


# ---- Helpers ----

async def _publish(event_type: str, data: dict):
    state.event_seq += 1
    state.events.append({
        "seq": state.event_seq,
        "type": event_type,
        "data": data,
    })


def _apply_env_overrides(config: dict) -> dict:
    """环境变量覆盖配置（优先级：环境变量 > config.yaml）"""
    env_map = {
        "API_KEY": "api_key",
        "BASE_URL": "base_url",
        "MODEL": "model",
        "API_VERSION": "api_version",
    }
    for env_key, config_key in env_map.items():
        val = os.environ.get(env_key)
        if val:
            config[config_key] = val
    return config


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}
    return _apply_env_overrides(config)


def _resolve_config(config: dict) -> dict:
    """将 profiles + benchmark 结构合并为扁平运行时配置"""
    resolved = {}
    # 1. benchmark 参数
    benchmark = config.get("benchmark", {})
    for k in BENCHMARK_KEYS:
        if k in benchmark:
            resolved[k] = benchmark[k]
    # 2. output_dir
    resolved["output_dir"] = config.get("output_dir", "./results")
    # 3. 兼容旧格式：如果顶层有 benchmark 参数（没有 benchmark 区块），从顶层读
    if not benchmark:
        for k in BENCHMARK_KEYS:
            if k in config:
                resolved[k] = config[k]
    # 4. active profile 连接信息
    profiles = config.get("profiles", [])
    active_name = config.get("active_profile", "")
    active = next((p for p in profiles if p.get("name") == active_name), None)
    if active:
        for k in CONNECTION_KEYS:
            if active.get(k):
                resolved[k] = active[k]
    if active_name:
        resolved["profile_name"] = active_name
    # 5. 兼容旧格式：顶层连接字段
    for k in CONNECTION_KEYS:
        if k not in resolved and k in config:
            resolved[k] = config[k]
    # 6. 环境变量最终覆盖
    _apply_env_overrides(resolved)
    return resolved


def _write_config(config: dict):
    """将完整配置写回 config.yaml"""
    config.pop("api_key_display", None)
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


# ---- Config routes ----

async def get_config(request):
    config = _load_config()
    resolved = _resolve_config(config)
    # 脱敏展示
    if "api_key" in resolved:
        key = resolved["api_key"]
        resolved["api_key_display"] = f"...{key[-4:]}" if len(key) > 4 else "****"
    return web.json_response(resolved)


async def update_config(request):
    """前端提交扁平配置，拆分写入 benchmark 区块 + 更新 active profile"""
    data = await request.json()
    data.pop("api_key_display", None)

    raw = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            raw = yaml.safe_load(f) or {}

    # api_key 脱敏占位 → 保留原值
    if not data.get("api_key") or data["api_key"].startswith("..."):
        # 从当前 active profile 取
        profiles = raw.get("profiles", [])
        active_name = raw.get("active_profile", "")
        active = next((p for p in profiles if p.get("name") == active_name), None)
        data["api_key"] = active.get("api_key", "") if active else ""

    # 写入 benchmark 区块
    benchmark = {}
    for k in BENCHMARK_KEYS:
        if k in data:
            benchmark[k] = data[k]
    raw["benchmark"] = benchmark
    raw["output_dir"] = data.get("output_dir", raw.get("output_dir", "./results"))

    # 更新 active profile 的连接信息
    profiles = raw.get("profiles", [])
    active_name = raw.get("active_profile", "")
    idx = next((i for i, p in enumerate(profiles) if p.get("name") == active_name), -1)
    if idx >= 0:
        for k in CONNECTION_KEYS:
            if k in data:
                profiles[idx][k] = data[k]

    _write_config(raw)
    return web.json_response({"status": "ok"})


# ---- Profiles routes ----

async def get_profiles(request):
    config = _load_config()
    return web.json_response({
        "profiles": config.get("profiles", []),
        "active_profile": config.get("active_profile", ""),
    })


async def save_profile(request):
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        return web.json_response({"error": "Profile name is required"}, status=400)

    profile = {"name": name}
    for k in CONNECTION_KEYS:
        profile[k] = data.get(k, "")

    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}

    profiles = raw.get("profiles", [])
    idx = next((i for i, p in enumerate(profiles) if p.get("name") == name), -1)
    if idx >= 0:
        profiles[idx] = profile
    else:
        profiles.append(profile)

    raw["profiles"] = profiles
    raw["active_profile"] = name
    _write_config(raw)
    return web.json_response({"status": "ok"})


async def switch_profile(request):
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        return web.json_response({"error": "Profile name is required"}, status=400)

    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}

    profiles = raw.get("profiles", [])
    target = next((p for p in profiles if p.get("name") == name), None)
    if not target:
        return web.json_response({"error": "Profile not found"}, status=404)

    raw["active_profile"] = name
    _write_config(raw)

    # 返回合并后的配置
    resolved = _resolve_config(raw)
    return web.json_response({"status": "ok", "config": resolved})


async def delete_profile(request):
    name = request.match_info["name"]
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}

    profiles = raw.get("profiles", [])
    raw["profiles"] = [p for p in profiles if p.get("name") != name]
    if raw.get("active_profile") == name:
        raw["active_profile"] = ""
    _write_config(raw)
    return web.json_response({"status": "deleted"})


# ---- Results routes ----

async def list_results(request):
    RESULTS_DIR.mkdir(exist_ok=True)
    results = []
    for f in RESULTS_DIR.glob("bench_*.json"):
        try:
            with open(f) as fh:
                data = json.load(fh)
                data["_filename"] = f.name
                results.append(data)
        except (json.JSONDecodeError, IOError):
            continue
    results.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return web.json_response(results)


async def get_result(request):
    filename = request.match_info["filename"]
    filepath = RESULTS_DIR / filename
    if not filepath.exists():
        return web.json_response({"error": "Not found"}, status=404)
    with open(filepath) as f:
        return web.json_response(json.load(f))


async def delete_result(request):
    filename = request.match_info["filename"]
    filepath = RESULTS_DIR / filename
    if filepath.exists():
        filepath.unlink()
    return web.json_response({"status": "deleted"})


# ---- Benchmark routes ----

async def start_bench(request):
    if state.status == "running":
        return web.json_response({"error": "Benchmark already running"}, status=409)

    body = await request.json() if request.content_length else {}

    config = _load_config()
    config = _resolve_config(config)
    # 允许前端覆盖部分配置
    for key in BENCHMARK_KEYS + CONNECTION_KEYS + ("requests_per_level",):
        if key in body and body[key] is not None:
            config[key] = body[key]

    import uuid
    state.task_id = uuid.uuid4().hex[:12]
    state.events = []
    state.event_seq = 0
    state.status = "running"
    state.stop_event = asyncio.Event()
    state.start_time = time.monotonic()
    state.current_task = asyncio.create_task(_run_benchmark_task(config))

    return web.json_response({"status": "started", "task_id": state.task_id})


async def stop_bench(request):
    if state.status != "running":
        return web.json_response({"error": "No benchmark running"}, status=400)
    state.status = "stopping"
    state.stop_event.set()
    return web.json_response({"status": "stopping"})


async def bench_status(request):
    since = int(request.query.get("since", 0))
    new_events = [e for e in state.events if e["seq"] > since]
    elapsed = round(time.monotonic() - state.start_time, 1) if state.start_time else 0

    return web.json_response({
        "task_id": state.task_id,
        "status": state.status,
        "concurrency": state.current_concurrency,
        "level": state.current_level,
        "total_levels": state.total_levels,
        "done": state.done_count,
        "total": state.total_count,
        "success": state.success_count,
        "failed": state.failed_count,
        "elapsed": elapsed,
        "events": new_events,
    })


# ---- Core benchmark task ----

async def _run_benchmark_task(config: dict):
    from main import run_burst, run_sustained

    try:
        mode = config.get("mode", "burst")
        concurrency_levels = config.get("concurrency_levels", [100])
        if isinstance(concurrency_levels, int):
            concurrency_levels = [concurrency_levels]
        output_dir = config.get("output_dir", "./results")

        state.total_levels = len(concurrency_levels)
        saved_reports = []

        connector = aiohttp_lib.TCPConnector(
            limit=config.get("connector_limit", 1200),
            force_close=False,
            enable_cleanup_closed=True,
        )

        async with aiohttp_lib.ClientSession(connector=connector) as session:
            for idx, level in enumerate(concurrency_levels):
                if state.stop_event.is_set():
                    break

                state.current_level = idx + 1
                state.current_concurrency = level
                state.done_count = 0
                state.success_count = 0
                state.failed_count = 0
                state.total_count = level if mode == "burst" else 0

                await _publish("bench:start", {
                    "concurrency": level,
                    "mode": mode,
                    "current_level": idx + 1,
                    "total_levels": len(concurrency_levels),
                })

                bench_start = time.monotonic()
                throttle_last = 0

                async def on_progress(done, total, m):
                    nonlocal throttle_last
                    state.done_count = done
                    state.total_count = total
                    if m.success:
                        state.success_count += 1
                    else:
                        state.failed_count += 1

                    now = time.monotonic()
                    if now - throttle_last >= 0.1 or done == total:
                        throttle_last = now
                        await _publish("bench:progress", {
                            "done": done, "total": total,
                            "success": state.success_count,
                            "failed": state.failed_count,
                            "concurrency": level,
                            "elapsed": round(now - bench_start, 1),
                        })

                if mode == "burst":
                    metrics = await run_burst(session, config, level, on_complete=on_progress)
                else:
                    duration = config.get("duration", 120)
                    metrics = await run_sustained(
                        session, config, level, duration,
                        on_complete=on_progress, stop_event=state.stop_event,
                    )

                bench_duration = time.monotonic() - bench_start
                result = aggregate_metrics(metrics, level, mode, bench_duration)
                report_dict = build_report_dict(result, config)
                filepath = save_report(result, output_dir, config)
                saved_reports.append(os.path.basename(filepath))

                await _publish("bench:level_complete", {
                    "concurrency": level,
                    "result": report_dict,
                    "filename": os.path.basename(filepath),
                })

                if level != concurrency_levels[-1] and not state.stop_event.is_set():
                    await asyncio.sleep(5)

        if state.stop_event.is_set():
            await _publish("bench:stopped", {"message": "Benchmark stopped by user"})
        else:
            await _publish("bench:complete", {
                "message": "Benchmark complete",
                "reports": saved_reports,
            })

    except Exception as e:
        await _publish("bench:error", {"error": str(e)})
    finally:
        state.status = "idle"
        state.current_task = None


# ---- Static files ----

async def index_handler(request):
    return web.FileResponse(STATIC_DIR / "index.html")


async def favicon_handler(request):
    return web.FileResponse(STATIC_DIR / "favicon.ico")


# ---- App ----

def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index_handler)
    app.router.add_get("/favicon.ico", favicon_handler)
    app.router.add_static("/css/", STATIC_DIR / "css")
    app.router.add_static("/js/", STATIC_DIR / "js")
    app.router.add_get("/api/config", get_config)
    app.router.add_put("/api/config", update_config)
    app.router.add_get("/api/profiles", get_profiles)
    app.router.add_post("/api/profiles/save", save_profile)
    app.router.add_post("/api/profiles/switch", switch_profile)
    app.router.add_delete("/api/profiles/{name}", delete_profile)
    app.router.add_get("/api/results", list_results)
    app.router.add_get("/api/results/{filename}", get_result)
    app.router.add_delete("/api/results/{filename}", delete_result)
    app.router.add_post("/api/bench/start", start_bench)
    app.router.add_post("/api/bench/stop", stop_bench)
    app.router.add_get("/api/bench/status", bench_status)
    return app


async def start_server(config: dict, port: int = 8080):
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    print(f"\n  AITokenPerf Web UI: http://localhost:{port}")
    print(f"  Press Ctrl+C to stop.\n")
    await site.start()
    await asyncio.Event().wait()
