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
from stats import aggregate_metrics, build_report_dict
from logger import log_access, log_security
from db import init_db, close_db, get_profiles, get_active_profile, upsert_profile
from db import switch_active_profile, delete_profile as db_delete_profile
from db import save_result as db_save_result, get_results as db_get_results
from db import get_results_aggregated as db_get_results_aggregated
from db import get_result_by_filename, delete_result as db_delete_result
from db import get_settings, save_settings
from db import create_user, get_user_by_email, get_user_by_id, update_user_password, count_users
from db import list_users, update_user_display_name, delete_user as db_delete_user
from auth import auth_middleware, hash_password, verify_password, create_jwt_token

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
RESULTS_DIR = BASE_DIR / "data" / "results"
STATIC_DIR = BASE_DIR / "static"

CONNECTION_KEYS = ("base_url", "api_key", "model", "api_version")
BENCHMARK_KEYS = ("mode", "concurrency_levels", "duration", "max_tokens",
                   "timeout", "connector_limit", "system_prompt", "user_prompt")


@dataclass
class BenchTask:
    """单个基准测试任务的状态"""
    task_id: str = ""
    owner_id: Optional[int] = None
    profile_name: str = ""
    group_id: str = ""
    scheduled_task_id: int = 0
    status: str = "idle"  # idle | running | stopping | error
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
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
    asyncio_task: Optional[asyncio.Task] = None
    result_filenames: list = field(default_factory=list)


class BenchTaskManager:
    MAX_PER_USER = 5
    MAX_GLOBAL = 20

    def __init__(self):
        self._tasks: dict[str, BenchTask] = {}
        self._group_tasks: dict[str, list[str]] = {}

    def create_task(self, task_id: str, owner_id: int, profile_name: str = "", group_id: str = "") -> BenchTask:
        task = BenchTask(task_id=task_id, owner_id=owner_id, profile_name=profile_name, group_id=group_id)
        self._tasks[task_id] = task
        if group_id:
            self._group_tasks.setdefault(group_id, []).append(task_id)
        return task

    def get_task(self, task_id: str) -> Optional[BenchTask]:
        return self._tasks.get(task_id)

    def get_user_running_task(self, user_id: int) -> Optional[BenchTask]:
        """返回用户最近一个运行中的任务（向后兼容）"""
        for task in self._tasks.values():
            if task.owner_id == user_id and task.status == "running":
                return task
        return None

    def get_user_task_count(self, user_id: int) -> int:
        return sum(1 for t in self._tasks.values() if t.owner_id == user_id and t.status == "running")

    def get_running_count(self) -> int:
        return sum(1 for t in self._tasks.values() if t.status == "running")

    def get_group_tasks(self, group_id: str) -> list[BenchTask]:
        task_ids = self._group_tasks.get(group_id, [])
        return [self._tasks[tid] for tid in task_ids if tid in self._tasks]

    def remove_task(self, task_id: str):
        task = self._tasks.pop(task_id, None)
        if task and task.group_id:
            group = self._group_tasks.get(task.group_id)
            if group and task_id in group:
                group.remove(task_id)
            if not group:
                self._group_tasks.pop(task.group_id, None)

    def cleanup_idle(self):
        """清理已完成的任务，释放内存"""
        to_remove = [tid for tid, t in self._tasks.items() if t.status == "idle" and t.asyncio_task is None]
        for tid in to_remove:
            self.remove_task(tid)


manager = BenchTaskManager()


# ---- Security ----

# 恶意扫描路径特征
SCAN_PATTERNS = [
    "/wp-admin", "/wp-login", "/.env", "/.git", "/.git/config",
    "/actuator", "/phpmyadmin", "/.well-known/security.txt",
    "/xmlrpc.php", "/wp-content", "/wp-includes",
]

# IP 封禁表 {ip: ban_until_timestamp}
_ip_ban: dict[str, float] = {}

# 限流表 {ip: [timestamp, ...]}
_rate_store: dict[str, list[float]] = {}

# 限流规则 (max_requests, window_seconds)
RATE_LIMITS = {
    "/api/bench/start": (5, 60),
    "/api/bench/stop": (5, 60),
    "/api/bench/status": (120, 60),
}
RATE_LIMIT_DEFAULT = (60, 60)  # 其他 API

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "")


def _check_ban(ip: str) -> bool:
    until = _ip_ban.get(ip)
    if until is None:
        return False
    if time.time() < until:
        return True
    del _ip_ban[ip]
    return False


def _ban_ip(ip: str, duration: int = 86400):
    _ip_ban[ip] = time.time() + duration


def _check_rate_limit(ip: str, path: str) -> bool:
    max_req, window = RATE_LIMIT_DEFAULT
    for pattern, limits in RATE_LIMITS.items():
        if path.startswith(pattern):
            max_req, window = limits
            break

    now = time.time()
    key = f"{ip}:{path}"
    hits = _rate_store.get(key, [])
    hits = [t for t in hits if now - t < window]
    if len(hits) >= max_req:
        return False
    hits.append(now)
    _rate_store[key] = hits
    return True


@web.middleware
async def security_middleware(request: web.Request, handler):
    ip = request.remote or "unknown"
    path = request.path
    start = time.monotonic()

    # 1. 检查封禁
    if _check_ban(ip):
        log_security("ip_banned_request", ip=ip, path=path)
        return web.json_response({"error": "Forbidden"}, status=403)

    # 2. 检查恶意扫描路径
    for pattern in SCAN_PATTERNS:
        if path.startswith(pattern):
            _ban_ip(ip)
            log_security("scan_detected", ip=ip, path=path)
            return web.json_response({"error": "Forbidden"}, status=403)

    # 3. CORS 预检
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
        _set_cors_headers(resp, request)
        return resp

    # 4. 限流（仅 API 路径）
    if path.startswith("/api/") and not _check_rate_limit(ip, path):
        log_security("rate_limited", ip=ip, path=path)
        return web.json_response({"error": "Too Many Requests"}, status=429)

    # 5. 处理请求
    try:
        resp = await handler(request)
    except web.HTTPException:
        raise
    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        log_access(request.method, path, 500, ip, duration_ms)
        raise

    duration_ms = (time.monotonic() - start) * 1000

    # 6. 安全响应头
    if path.startswith("/api/"):
        _set_cors_headers(resp, request)
    resp.headers.pop("Server", None)

    # 7. 记录访问日志
    log_access(request.method, path, resp.status, ip, duration_ms)

    return resp


def _set_cors_headers(resp: web.Response, request: web.Request):
    origin = request.headers.get("Origin", "")
    if CORS_ORIGINS:
        allowed = [o.strip() for o in CORS_ORIGINS.split(",")]
        if origin in allowed:
            resp.headers["Access-Control-Allow-Origin"] = origin
    else:
        resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"


# ---- Helpers ----

async def _publish(task: BenchTask, event_type: str, data: dict):
    task.event_seq += 1
    task.events.append({
        "seq": task.event_seq,
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
    resolved["output_dir"] = config.get("output_dir", "./data/results")
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
    user_id = request["user_id"]
    # 从 DB 加载用户配置和活跃 profile
    benchmark = await get_settings(user_id)
    active = await get_active_profile(user_id)

    resolved = dict(benchmark) if benchmark else {}
    resolved["output_dir"] = "./data/results"

    if active:
        for k in CONNECTION_KEYS:
            if active.get(k):
                resolved[k] = active[k]
        resolved["profile_name"] = active["name"]
        # 脱敏：返回 display 占位符，不返回完整 api_key
        if "api_key" in resolved:
            key = resolved["api_key"]
            resolved["api_key_display"] = f"...{key[-4:]}" if len(key) > 4 else "****"
            del resolved["api_key"]

    return web.json_response(resolved)


async def update_config(request):
    """前端提交扁平配置，拆分写入 user_settings + 更新 active profile"""
    user_id = request["user_id"]
    data = await request.json()
    data.pop("api_key_display", None)

    # api_key 脱敏占位 → 从活跃 profile 保留原值
    if not data.get("api_key") or data["api_key"].startswith("..."):
        active = await get_active_profile(user_id)
        data["api_key"] = active.get("api_key", "") if active else ""

    # 写入 benchmark 配置
    benchmark = {}
    for k in BENCHMARK_KEYS:
        if k in data:
            benchmark[k] = data[k]
    output_dir = data.get("output_dir", "./data/results")
    await save_settings(user_id, benchmark, output_dir)

    # 更新活跃 profile 的连接信息
    active = await get_active_profile(user_id)
    if active:
        profile_data = {
            "name": active["name"],
            "base_url": data.get("base_url", active["base_url"]),
            "api_key": data.get("api_key", active["api_key"]),
            "api_version": data.get("api_version", active["api_version"]),
            "model": data.get("model", active["model"]),
        }
        await upsert_profile(user_id, set_active=False, **profile_data)

    return web.json_response({"status": "ok"})


# ---- Profiles routes ----

async def get_profiles_handler(request):
    user_id = request["user_id"]
    profiles = await get_profiles(user_id)
    active = await get_active_profile(user_id)
    active_name = active["name"] if active else ""
    # api_key 脱敏
    for p in profiles:
        if "api_key" in p:
            key = p["api_key"]
            p["api_key_display"] = f"...{key[-4:]}" if len(key) > 4 else "****"
            del p["api_key"]
    return web.json_response({
        "profiles": profiles,
        "active_profile": active_name,
    })


async def save_profile(request):
    user_id = request["user_id"]
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        return web.json_response({"error": "Profile name is required"}, status=400)

    api_key = data.get("api_key", "")
    # 脱敏占位符 → 从当前活跃 profile 保留原值
    if api_key.startswith("..."):
        active = await get_active_profile(user_id)
        api_key = active.get("api_key", "") if active else ""

    await upsert_profile(
        user_id, name,
        base_url=data.get("base_url", ""),
        api_key=api_key,
        api_version=data.get("api_version", "2023-06-01"),
        model=data.get("model", ""),
        set_active=True,
    )
    return web.json_response({"status": "ok"})


async def switch_profile(request):
    user_id = request["user_id"]
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        return web.json_response({"error": "Profile name is required"}, status=400)

    ok = await switch_active_profile(user_id, name)
    if not ok:
        return web.json_response({"error": "Profile not found"}, status=404)

    # 返回合并后的配置（api_key 脱敏）
    active = await get_active_profile(user_id)
    benchmark = await get_settings(user_id)
    resolved = dict(benchmark) if benchmark else {}
    if active:
        for k in CONNECTION_KEYS:
            if active.get(k):
                resolved[k] = active[k]
        resolved["profile_name"] = active["name"]
        if "api_key" in resolved:
            key = resolved["api_key"]
            resolved["api_key_display"] = f"...{key[-4:]}" if len(key) > 4 else "****"
            del resolved["api_key"]
    return web.json_response({"status": "ok", "config": resolved})


async def delete_profile_handler(request):
    user_id = request["user_id"]
    name = request.match_info["name"]
    await db_delete_profile(user_id, name)
    return web.json_response({"status": "deleted"})


# ---- Results routes ----

async def list_results(request):
    user_id = request["user_id"]
    limit = int(request.query.get("limit", 50))
    offset = int(request.query.get("offset", 0))
    # 限制范围
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    result = await db_get_results_aggregated(user_id, limit=limit, offset=offset)
    items = result["items"]
    total = result["total"]

    # Fallback: 兼容旧文件系统中的 results（仅在第一页时补充）
    if offset == 0:
        db_filenames = set()
        for item in items:
            db_filenames.add(item.get("_filename") or item.get("filename") or "")
            for child in item.get("children", []):
                db_filenames.add(child.get("_filename") or child.get("filename") or "")
        if RESULTS_DIR.exists():
            for f in sorted(RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                if f.name not in db_filenames:
                    try:
                        data = json.loads(f.read_text())
                        data["_filename"] = f.name
                        items.append(data)
                        total += 1
                    except (json.JSONDecodeError, OSError):
                        pass

    return web.json_response({"total": total, "items": items})


async def get_result(request):
    user_id = request["user_id"]
    filename = request.match_info["filename"]
    result = await get_result_by_filename(user_id, filename)
    if not result:
        # Fallback: 从文件系统读取
        filepath = RESULTS_DIR / filename
        if filepath.exists():
            try:
                result = json.loads(filepath.read_text())
                result["_filename"] = filename
            except (json.JSONDecodeError, OSError):
                pass
    if not result:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response(result)


async def delete_result_handler(request):
    user_id = request["user_id"]
    filename = request.match_info["filename"]
    await db_delete_result(user_id, filename)
    # 同时删除文件（如果存在）
    filepath = RESULTS_DIR / filename
    if filepath.exists():
        filepath.unlink()
    return web.json_response({"status": "deleted"})


# ---- Benchmark routes ----

async def start_bench(request):
    user_id = request["user_id"]

    existing = manager.get_user_running_task(user_id)
    if existing:
        return web.json_response({"error": "Benchmark already running"}, status=409)

    body = await request.json() if request.content_length else {}

    # 输入校验
    errors = []
    levels = body.get("concurrency_levels")
    if levels:
        if not isinstance(levels, list):
            levels = [levels]
        if len(levels) > 20:
            errors.append("concurrency_levels 最多 20 项")
        for v in levels:
            if not isinstance(v, int) or v < 1 or v > 2000:
                errors.append(f"concurrency 值 {v} 超出范围 (1-2000)")
    duration = body.get("duration")
    if duration is not None and (not isinstance(duration, int) or duration < 1 or duration > 3600):
        errors.append("duration 超出范围 (1-3600)")
    max_tokens = body.get("max_tokens")
    if max_tokens is not None and (not isinstance(max_tokens, int) or max_tokens < 1 or max_tokens > 8192):
        errors.append("max_tokens 超出范围 (1-8192)")
    rpl = body.get("requests_per_level")
    if rpl is not None and (not isinstance(rpl, int) or rpl < 1 or rpl > 50000):
        errors.append("requests_per_level 超出范围 (1-50000)")
    if errors:
        return web.json_response({"error": "; ".join(errors)}, status=400)

    # 从 DB 加载用户配置
    benchmark = await get_settings(user_id)
    active = await get_active_profile(user_id)
    config = dict(benchmark) if benchmark else {}
    if active:
        for k in CONNECTION_KEYS:
            if active.get(k):
                config[k] = active[k]
    _apply_env_overrides(config)

    # 允许前端覆盖部分配置（api_key 脱敏占位符忽略）
    for key in BENCHMARK_KEYS + CONNECTION_KEYS + ("requests_per_level",):
        if key in body and body[key] is not None:
            if key == "api_key" and isinstance(body[key], str) and body[key].startswith("..."):
                continue
            config[key] = body[key]

    import uuid
    task_id = uuid.uuid4().hex[:12]
    profile_name = active["name"] if active else ""
    task = manager.create_task(task_id, user_id, profile_name=profile_name)
    task.status = "running"
    task.stop_event = asyncio.Event()
    task.start_time = time.monotonic()
    task.asyncio_task = asyncio.create_task(_run_benchmark_task(config, user_id, task))

    return web.json_response({"status": "started", "task_id": task_id})


async def stop_bench(request):
    user_id = request["user_id"]
    task_id = request.query.get("task_id", "")

    if task_id:
        task = manager.get_task(task_id)
    else:
        task = manager.get_user_running_task(user_id)

    if not task or task.status != "running":
        return web.json_response({"error": "No benchmark running"}, status=400)
    if task.owner_id != user_id:
        return web.json_response({"error": "Not your benchmark"}, status=403)
    task.status = "stopping"
    task.stop_event.set()
    return web.json_response({"status": "stopping"})


async def bench_status(request):
    user_id = request["user_id"]
    task_id = request.query.get("task_id", "")

    if task_id:
        task = manager.get_task(task_id)
    else:
        task = manager.get_user_running_task(user_id)

    if not task:
        return web.json_response({
            "task_id": "", "status": "idle",
            "concurrency": 0, "level": 0, "total_levels": 0,
            "done": 0, "total": 0, "success": 0, "failed": 0,
            "elapsed": 0, "events": [],
        })

    since = int(request.query.get("since", 0))
    new_events = [e for e in task.events if e["seq"] > since]
    elapsed = round(time.monotonic() - task.start_time, 1) if task.start_time else 0

    return web.json_response({
        "task_id": task.task_id,
        "status": task.status,
        "concurrency": task.current_concurrency,
        "level": task.current_level,
        "total_levels": task.total_levels,
        "done": task.done_count,
        "total": task.total_count,
        "success": task.success_count,
        "failed": task.failed_count,
        "elapsed": elapsed,
        "events": new_events,
    })


async def start_multi_bench(request):
    """多服务器并行测试"""
    import uuid
    user_id = request["user_id"]
    body = await request.json()

    tasks_spec = body.get("tasks", [])
    if not tasks_spec or len(tasks_spec) > 10:
        return web.json_response({"error": "tasks 数量需在 1-10 之间"}, status=400)

    # 检查并发限制
    current_running = manager.get_running_count()
    if current_running + len(tasks_spec) > BenchTaskManager.MAX_GLOBAL:
        return web.json_response({"error": f"全局并发任务数已达上限 ({BenchTaskManager.MAX_GLOBAL})"}, status=429)
    user_running = manager.get_user_task_count(user_id)
    if user_running + len(tasks_spec) > BenchTaskManager.MAX_PER_USER:
        return web.json_response({"error": f"用户并发任务数已达上限 ({BenchTaskManager.MAX_PER_USER})"}, status=429)

    # 加载用户所有 profile
    profiles = await get_profiles(user_id)
    profile_map = {p["name"]: p for p in profiles}
    benchmark = await get_settings(user_id)

    group_id = f"grp_{uuid.uuid4().hex[:12]}"
    task_ids = []

    for spec in tasks_spec:
        profile_name = spec.get("profile_name", "")
        profile = profile_map.get(profile_name)
        if not profile:
            return web.json_response({"error": f"Profile '{profile_name}' 不存在"}, status=400)

        # 合并配置：benchmark defaults -> profile connection -> 前端覆盖
        config = dict(benchmark) if benchmark else {}
        for k in CONNECTION_KEYS:
            if profile.get(k):
                config[k] = profile[k]
        _apply_env_overrides(config)

        overrides = spec.get("config", {})
        for key in BENCHMARK_KEYS + CONNECTION_KEYS + ("requests_per_level",):
            if key in overrides and overrides[key] is not None:
                if key == "api_key" and isinstance(overrides[key], str) and overrides[key].startswith("..."):
                    continue
                config[key] = overrides[key]

        task_id = uuid.uuid4().hex[:12]
        task = manager.create_task(task_id, user_id, profile_name=profile_name, group_id=group_id)
        task.status = "running"
        task.stop_event = asyncio.Event()
        task.start_time = time.monotonic()
        task.asyncio_task = asyncio.create_task(_run_benchmark_task(config, user_id, task))
        task_ids.append(task_id)

    return web.json_response({
        "status": "started",
        "group_id": group_id,
        "task_ids": task_ids,
    })


async def status_multi(request):
    """多服务器测试状态聚合"""
    group_id = request.query.get("group_id", "")
    if not group_id:
        return web.json_response({"error": "group_id is required"}, status=400)

    tasks = manager.get_group_tasks(group_id)
    if not tasks:
        return web.json_response({"error": "Group not found"}, status=404)

    task_statuses = []
    for task in tasks:
        elapsed = round(time.monotonic() - task.start_time, 1) if task.start_time else 0
        task_statuses.append({
            "task_id": task.task_id,
            "profile_name": task.profile_name,
            "status": task.status,
            "done": task.done_count,
            "total": task.total_count,
            "success": task.success_count,
            "failed": task.failed_count,
            "elapsed": elapsed,
            "result_filenames": task.result_filenames,
        })

    all_done = all(t["status"] != "running" for t in task_statuses)
    return web.json_response({
        "group_id": group_id,
        "status": "completed" if all_done else "running",
        "tasks": task_statuses,
    })


# ---- Core benchmark task ----

async def _run_benchmark_task(config: dict, owner_id: int, task: BenchTask):
    from main import run_burst, run_sustained

    try:
        mode = config.get("mode", "burst")
        concurrency_levels = config.get("concurrency_levels", [100])
        if isinstance(concurrency_levels, int):
            concurrency_levels = [concurrency_levels]
        output_dir = config.get("output_dir", "./data/results")

        task.total_levels = len(concurrency_levels)

        connector = aiohttp_lib.TCPConnector(
            limit=config.get("connector_limit", 1200),
            force_close=False,
            enable_cleanup_closed=True,
        )

        async with aiohttp_lib.ClientSession(connector=connector) as session:
            for idx, level in enumerate(concurrency_levels):
                if task.stop_event.is_set():
                    break

                task.current_level = idx + 1
                task.current_concurrency = level
                task.done_count = 0
                task.success_count = 0
                task.failed_count = 0
                task.total_count = level if mode == "burst" else 0

                await _publish(task, "bench:start", {
                    "concurrency": level,
                    "mode": mode,
                    "current_level": idx + 1,
                    "total_levels": len(concurrency_levels),
                })

                bench_start = time.monotonic()
                throttle_last = 0

                async def on_progress(done, total, m, _task=task, _level=level, _bench_start=bench_start):
                    nonlocal throttle_last
                    _task.done_count = done
                    _task.total_count = total
                    if m.success:
                        _task.success_count += 1
                    else:
                        _task.failed_count += 1

                    now = time.monotonic()
                    if now - throttle_last >= 0.1 or done == total:
                        throttle_last = now
                        await _publish(_task, "bench:progress", {
                            "done": done, "total": total,
                            "success": _task.success_count,
                            "failed": _task.failed_count,
                            "concurrency": _level,
                            "elapsed": round(now - _bench_start, 1),
                        })

                if mode == "burst":
                    metrics = await run_burst(session, config, level, on_complete=on_progress)
                else:
                    duration = config.get("duration", 120)
                    metrics = await run_sustained(
                        session, config, level, duration,
                        on_complete=on_progress, stop_event=task.stop_event,
                    )

                bench_duration = time.monotonic() - bench_start
                result = aggregate_metrics(metrics, level, mode, bench_duration)
                report_dict = build_report_dict(result, config)
                filename = f"bench_{result.concurrency}c_{result.mode}_{report_dict.get('timestamp', '')}.json"
                task.result_filenames.append(filename)

                # 保存到 DB
                try:
                    await db_save_result(
                        user_id=owner_id,
                        test_id=report_dict.get("test_id", ""),
                        filename=filename,
                        timestamp=report_dict.get("timestamp", ""),
                        config_json=json.dumps(report_dict.get("config", {})),
                        summary_json=json.dumps(report_dict.get("summary", {})),
                        percentiles_json=json.dumps(report_dict.get("percentiles", {})),
                        errors_json=json.dumps(report_dict.get("errors", {})),
                        error_details_json=json.dumps(report_dict.get("error_details", [])),
                        group_id=task.group_id,
                        scheduled_task_id=task.scheduled_task_id,
                    )
                except Exception as db_err:
                    print(f"Warning: failed to save result to DB: {db_err}")

                await _publish(task, "bench:level_complete", {
                    "concurrency": level,
                    "result": report_dict,
                    "filename": filename,
                })

                if level != concurrency_levels[-1] and not task.stop_event.is_set():
                    await asyncio.sleep(5)

        if task.stop_event.is_set():
            await _publish(task, "bench:stopped", {"message": "Benchmark stopped by user"})
        else:
            await _publish(task, "bench:complete", {
                "message": "Benchmark complete",
                "reports": task.result_filenames,
            })

    except Exception as e:
        await _publish(task, "bench:error", {"error": str(e)})
    finally:
        task.status = "idle"
        task.asyncio_task = None


# ---- Auth routes ----

async def auth_register(request):
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    display_name = (body.get("display_name") or "").strip()

    if not email or "@" not in email:
        return web.json_response({"error": "请输入有效的邮箱地址"}, status=400)
    if len(password) < 6:
        return web.json_response({"error": "密码至少 6 位"}, status=400)

    existing = await get_user_by_email(email)
    if existing:
        return web.json_response({"error": "该邮箱已注册"}, status=409)

    # 首个用户自动成为 admin
    user_count = await count_users()
    role = "admin" if user_count == 0 else "user"
    user_id = await create_user(email, hash_password(password), display_name, role)

    token = create_jwt_token(user_id, email, role)
    return web.json_response({
        "token": token,
        "user": {"id": user_id, "email": email, "role": role, "display_name": display_name},
    })


async def auth_login(request):
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    if not email or not password:
        return web.json_response({"error": "请输入邮箱和密码"}, status=400)

    user = await get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        return web.json_response({"error": "邮箱或密码错误"}, status=401)

    token = create_jwt_token(user["id"], user["email"], user["role"])
    return web.json_response({
        "token": token,
        "user": {"id": user["id"], "email": user["email"], "role": user["role"],
                 "display_name": user["display_name"]},
    })


async def auth_me(request):
    user_id = request["user_id"]
    user = await get_user_by_id(user_id)
    if not user:
        return web.json_response({"error": "User not found"}, status=404)
    return web.json_response({
        "id": user["id"], "email": user["email"],
        "role": user["role"], "display_name": user["display_name"],
    })


async def auth_change_password(request):
    user_id = request["user_id"]
    body = await request.json()
    old_password = body.get("old_password", "")
    new_password = body.get("new_password", "")

    if len(new_password) < 6:
        return web.json_response({"error": "新密码至少 6 位"}, status=400)

    user = await get_user_by_id(user_id)
    if not user or not verify_password(old_password, user["password_hash"]):
        return web.json_response({"error": "原密码错误"}, status=401)

    await update_user_password(user_id, hash_password(new_password))
    return web.json_response({"status": "ok"})


async def auth_update_profile(request):
    user_id = request["user_id"]
    body = await request.json()
    display_name = (body.get("display_name") or "").strip()
    await update_user_display_name(user_id, display_name)
    user = await get_user_by_id(user_id)
    return web.json_response({
        "id": user["id"], "email": user["email"],
        "role": user["role"], "display_name": user["display_name"],
    })


# ---- Admin routes ----

async def admin_list_users(request):
    if request.get("user_role") != "admin":
        return web.json_response({"error": "Forbidden"}, status=403)
    users = await list_users()
    return web.json_response({"users": users})


async def admin_delete_user(request):
    if request.get("user_role") != "admin":
        return web.json_response({"error": "Forbidden"}, status=403)
    target_id = int(request.match_info["user_id"])
    current_id = request["user_id"]
    if target_id == current_id:
        return web.json_response({"error": "不能删除自己"}, status=400)
    await db_delete_user(target_id)
    return web.json_response({"status": "deleted"})


# ---- Static files ----

async def index_handler(request):
    return web.FileResponse(STATIC_DIR / "index.html")


async def favicon_handler(request):
    return web.FileResponse(STATIC_DIR / "favicon.ico")


# ---- Schedule API ----

async def list_schedules(request):
    from db import get_scheduled_tasks
    user_id = request["user_id"]
    tasks = await get_scheduled_tasks(user_id)
    return web.json_response({"schedules": tasks})


async def create_schedule(request):
    from db import create_scheduled_task
    user_id = request["user_id"]
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return web.json_response({"error": "名称不能为空"}, status=400)
    profile_ids = body.get("profile_ids", [])
    if not profile_ids:
        return web.json_response({"error": "请至少选择一个 Profile"}, status=400)
    configs_json = body.get("configs_json", {})
    schedule_type = body.get("schedule_type", "interval")
    schedule_value = str(body.get("schedule_value", "300"))
    sid = await create_scheduled_task(
        user_id, name, profile_ids, configs_json, schedule_type, schedule_value,
    )
    # 调度新任务
    from db import get_scheduled_task
    task_row = await get_scheduled_task(sid)
    if task_row and _scheduler:
        _scheduler._schedule(task_row)
    return web.json_response({"id": sid, "status": "created"})


async def update_schedule(request):
    from db import update_scheduled_task, get_scheduled_task
    task_id = int(request.match_info["id"])
    user_id = request["user_id"]
    task_row = await get_scheduled_task(task_id)
    if not task_row or task_row["user_id"] != user_id:
        return web.json_response({"error": "Not found"}, status=404)
    body = await request.json()
    allowed = {"name", "profile_ids", "configs_json", "schedule_type", "schedule_value", "status"}
    fields = {k: v for k, v in body.items() if k in allowed}
    if fields:
        await update_scheduled_task(task_id, **fields)
    # 重新调度
    if _scheduler and fields.get("status", task_row.get("status")) == "active":
        updated = await get_scheduled_task(task_id)
        if updated:
            _scheduler._schedule(updated)
    return web.json_response({"status": "updated"})


async def delete_schedule(request):
    from db import delete_scheduled_task, get_scheduled_task
    task_id = int(request.match_info["id"])
    user_id = request["user_id"]
    task_row = await get_scheduled_task(task_id)
    if not task_row or task_row["user_id"] != user_id:
        return web.json_response({"error": "Not found"}, status=404)
    # 取消 timer
    if _scheduler and task_id in _scheduler._timers:
        _scheduler._timers[task_id].cancel()
        del _scheduler._timers[task_id]
    await delete_scheduled_task(task_id)
    return web.json_response({"status": "deleted"})


async def pause_schedule(request):
    from db import update_scheduled_task, get_scheduled_task
    task_id = int(request.match_info["id"])
    user_id = request["user_id"]
    task_row = await get_scheduled_task(task_id)
    if not task_row or task_row["user_id"] != user_id:
        return web.json_response({"error": "Not found"}, status=404)
    await update_scheduled_task(task_id, status="paused")
    if _scheduler and task_id in _scheduler._timers:
        _scheduler._timers[task_id].cancel()
        del _scheduler._timers[task_id]
    return web.json_response({"status": "paused"})


async def resume_schedule(request):
    from db import update_scheduled_task, get_scheduled_task
    task_id = int(request.match_info["id"])
    user_id = request["user_id"]
    task_row = await get_scheduled_task(task_id)
    if not task_row or task_row["user_id"] != user_id:
        return web.json_response({"error": "Not found"}, status=404)
    await update_scheduled_task(task_id, status="active")
    if _scheduler:
        updated = await get_scheduled_task(task_id)
        if updated:
            _scheduler._schedule(updated)
    return web.json_response({"status": "resumed"})


async def run_schedule_now(request):
    from db import get_scheduled_task
    task_id = int(request.match_info["id"])
    user_id = request["user_id"]
    task_row = await get_scheduled_task(task_id)
    if not task_row or task_row["user_id"] != user_id:
        return web.json_response({"error": "Not found"}, status=404)
    if _scheduler:
        asyncio.create_task(_scheduler._execute(task_id))
    return web.json_response({"status": "triggered"})


async def get_schedule_results(request):
    from db import get_results_by_scheduled_task, get_scheduled_task
    task_id = int(request.match_info["id"])
    user_id = request["user_id"]
    task_row = await get_scheduled_task(task_id)
    if not task_row or task_row["user_id"] != user_id:
        return web.json_response({"error": "Not found"}, status=404)
    results = await get_results_by_scheduled_task(user_id, task_id)
    # 清理 JSON 字段，只返回前端需要的结构
    clean = []
    for r in results:
        clean.append({
            "test_id": r.get("test_id", ""),
            "filename": r.get("_filename", ""),
            "timestamp": r.get("timestamp", ""),
            "config": r.get("config", {}),
            "summary": r.get("summary", {}),
            "percentiles": r.get("percentiles", {}),
            "scheduled_task_id": r.get("scheduled_task_id", 0),
            "schedule_name": r.get("schedule_name", ""),
        })
    return web.json_response({"results": clean})


# ---- App ----

_scheduler = None

def create_app() -> web.Application:
    global _scheduler
    app = web.Application(
        middlewares=[security_middleware, auth_middleware],
        client_max_size=1024 * 1024,  # 1MB
    )

    async def on_startup(app):
        global _scheduler
        from migrate import migrate
        await migrate()
        from scheduler import TaskScheduler
        _scheduler = TaskScheduler()
        await _scheduler.start()

    async def on_cleanup(app):
        global _scheduler
        if _scheduler:
            await _scheduler.stop()
            _scheduler = None
        await close_db()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    app.router.add_get("/", index_handler)
    app.router.add_get("/favicon.ico", favicon_handler)
    app.router.add_static("/css/", STATIC_DIR / "css")
    app.router.add_static("/js/", STATIC_DIR / "js")
    app.router.add_static("/vendor/", STATIC_DIR / "vendor")

    # Auth routes
    app.router.add_post("/api/auth/register", auth_register)
    app.router.add_post("/api/auth/login", auth_login)
    app.router.add_post("/api/auth/logout", lambda r: web.json_response({"status": "ok"}))
    app.router.add_get("/api/auth/me", auth_me)
    app.router.add_put("/api/auth/password", auth_change_password)
    app.router.add_put("/api/auth/profile", auth_update_profile)

    # Admin routes
    app.router.add_get("/api/admin/users", admin_list_users)
    app.router.add_delete("/api/admin/users/{user_id}", admin_delete_user)

    # Config routes
    app.router.add_get("/api/config", get_config)
    app.router.add_put("/api/config", update_config)

    # Profile routes
    app.router.add_get("/api/profiles", get_profiles_handler)
    app.router.add_post("/api/profiles/save", save_profile)
    app.router.add_post("/api/profiles/switch", switch_profile)
    app.router.add_delete("/api/profiles/{name}", delete_profile_handler)

    # Result routes
    app.router.add_get("/api/results", list_results)
    app.router.add_get("/api/results/{filename}", get_result)
    app.router.add_delete("/api/results/{filename}", delete_result_handler)

    # Benchmark routes
    app.router.add_post("/api/bench/start", start_bench)
    app.router.add_post("/api/bench/stop", stop_bench)
    app.router.add_get("/api/bench/status", bench_status)
    app.router.add_post("/api/bench/start-multi", start_multi_bench)
    app.router.add_get("/api/bench/status-multi", status_multi)

    # Schedule routes
    app.router.add_get("/api/schedules", list_schedules)
    app.router.add_post("/api/schedules", create_schedule)
    app.router.add_put("/api/schedules/{id}", update_schedule)
    app.router.add_delete("/api/schedules/{id}", delete_schedule)
    app.router.add_post("/api/schedules/{id}/pause", pause_schedule)
    app.router.add_post("/api/schedules/{id}/resume", resume_schedule)
    app.router.add_post("/api/schedules/{id}/run-now", run_schedule_now)
    app.router.add_get("/api/schedules/{id}/results", get_schedule_results)

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
