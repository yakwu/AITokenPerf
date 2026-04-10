#!/usr/bin/env python3
"""Claude API 压测工具 - Web 后端 (FastAPI 版)"""

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import aiohttp as aiohttp_lib
from fastapi import FastAPI, Depends, Query, Path as FPath, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.client import send_streaming_request
from app.stats import aggregate_metrics, build_report_dict
from app.logger import log_access, log_security

log = logging.getLogger("server")
from app.db import init_db, close_db, get_profiles, get_active_profile, upsert_profile
from app.db import switch_active_profile, delete_profile as db_delete_profile
from app.db import save_result as db_save_result, get_results as db_get_results
from app.db import get_results_aggregated as db_get_results_aggregated
from app.db import get_result_by_filename, delete_result as db_delete_result
from app.db import get_settings, save_settings
from app.db import create_user, get_user_by_email, get_user_by_id, update_user_password, count_users
from app.db import list_users, update_user_display_name, update_user_role, delete_user as db_delete_user
from app.auth import get_current_user, require_admin, hash_password, verify_password, create_jwt_token, decode_jwt_token
from app.auth import _is_public_path

BASE_DIR = Path(__file__).parent.parent
STATIC_DIR = BASE_DIR / "static"

CONNECTION_KEYS = ("base_url", "api_key", "model", "api_version", "provider", "protocol")
BENCHMARK_KEYS = ("mode", "concurrency_levels", "duration", "max_tokens",
                   "timeout", "connector_limit", "system_prompt", "user_prompt")


@dataclass
class BenchTask:
    """单个基准测试任务的状态"""
    task_id: str = ""
    owner_id: Optional[int] = None
    profile_name: str = ""
    model_name: str = ""
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
    event_waiters: list = field(default_factory=list)  # asyncio.Event for SSE


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

SCAN_PATTERNS = [
    "/wp-admin", "/wp-login", "/.env", "/.git", "/.git/config",
    "/actuator", "/phpmyadmin", "/.well-known/security.txt",
    "/xmlrpc.php", "/wp-content", "/wp-includes",
]

_ip_ban: dict[str, float] = {}
_rate_store: dict[str, list[float]] = {}

RATE_LIMITS = {
    "/api/bench/start": (5, 60),
    "/api/bench/stop": (5, 60),
    "/api/bench/status": (120, 60),
    "/api/bench/stream": (10, 60),
    "/api/auth/login": (5, 60),
    "/api/auth/register": (3, 3600),
}
RATE_LIMIT_DEFAULT = (60, 60)

from app.config import CORS_ORIGINS


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


# ---- Helpers ----

async def _publish(task: BenchTask, event_type: str, data: dict):
    task.event_seq += 1
    task.events.append({
        "seq": task.event_seq,
        "type": event_type,
        "data": data,
    })
    # 限制事件列表长度，防止内存无限增长
    if len(task.events) > 500:
        task.events = task.events[-300:]
    for waiter in task.event_waiters:
        waiter.set()


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


def _mask_api_key(key: str) -> str:
    if len(key) > 4:
        return f"...{key[-4:]}"
    return "****"


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

                # 费用计算
                from app.pricing import pricing_service
                pricing = pricing_service.get_pricing(config.get("model", ""))

                result = aggregate_metrics(metrics, level, mode, bench_duration, pricing=pricing)
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
                    log.warning("failed to save result to DB: %s", db_err)

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
        import traceback
        log_security("bench_error", error=str(e))
        log.error("bench error: %s", e, exc_info=True)
        await _publish(task, "bench:error", {"error": "Benchmark execution failed, check server logs for details"})
    finally:
        task.status = "idle"
        task.asyncio_task = None


# ---- App + Lifespan ----

_scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    from app.migrate import migrate
    await migrate()

    # 初始化模型价格服务
    from app.pricing import pricing_service
    await pricing_service.start()

    from app.scheduler import TaskScheduler
    _scheduler = TaskScheduler()
    await _scheduler.start()
    yield
    if _scheduler:
        await _scheduler.stop()
    await close_db()

app = FastAPI(title="AITokenPerf", lifespan=lifespan, docs_url=None, redoc_url=None)

# CORS
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in CORS_ORIGINS.split(",")],
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
else:
    # 开发模式：允许 localhost 任意端口跨域
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://localhost:\d+",
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        allow_credentials=True,
    )


# ---- Security Middleware ----

def _get_real_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri.strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    ip = _get_real_ip(request)
    path = request.url.path
    start = time.monotonic()

    # 1. 检查封禁
    if _check_ban(ip):
        log_security("ip_banned_request", ip=ip, path=path)
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    # 2. 检查恶意扫描路径
    for pattern in SCAN_PATTERNS:
        if path.startswith(pattern):
            _ban_ip(ip)
            log_security("scan_detected", ip=ip, path=path)
            return JSONResponse({"error": "Forbidden"}, status_code=403)

    # 3. 限流（仅 API 路径）
    if path.startswith("/api/") and not _is_public_path(path) and not _check_rate_limit(ip, path):
        log_security("rate_limited", ip=ip, path=path)
        return JSONResponse({"error": "Too Many Requests"}, status_code=429)

    # 4. 处理请求
    try:
        response = await call_next(request)
    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        log_access(request.method, path, 500, ip, duration_ms)
        raise

    duration_ms = (time.monotonic() - start) * 1000

    # 5. 安全响应头
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # 6. 记录访问日志
    log_access(request.method, path, response.status_code, ip, duration_ms)

    return response


# ---- Auth Routes ----

@app.post("/api/auth/register")
async def auth_register(request: Request):
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    display_name = (body.get("display_name") or "").strip()

    if not email or "@" not in email:
        return JSONResponse({"error": "请输入有效的邮箱地址"}, status_code=400)
    if len(password) < 6:
        return JSONResponse({"error": "密码至少 6 位"}, status_code=400)

    existing = await get_user_by_email(email)
    if existing:
        return JSONResponse({"error": "该邮箱已注册"}, status_code=409)

    user_count = await count_users()
    role = "user"
    user_id = await create_user(email, hash_password(password), display_name, role)

    token = create_jwt_token(user_id, email, role)
    return {
        "token": token,
        "user": {"id": user_id, "email": email, "role": role, "display_name": display_name},
    }


@app.post("/api/auth/login")
async def auth_login(request: Request):
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    if not email or not password:
        return JSONResponse({"error": "请输入邮箱和密码"}, status_code=400)

    user = await get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        return JSONResponse({"error": "邮箱或密码错误"}, status_code=401)

    token = create_jwt_token(user["id"], user["email"], user["role"])
    return {
        "token": token,
        "user": {"id": user["id"], "email": user["email"], "role": user["role"],
                 "display_name": user["display_name"],
                 "must_change_password": bool(user.get("must_change_password"))},
    }


@app.post("/api/auth/logout")
async def auth_logout():
    return {"status": "ok"}


@app.get("/api/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    user_data = await get_user_by_id(user["user_id"])
    if not user_data:
        return JSONResponse({"error": "User not found"}, status_code=404)
    return {
        "id": user_data["id"], "email": user_data["email"],
        "role": user_data["role"], "display_name": user_data["display_name"],
        "must_change_password": bool(user_data.get("must_change_password")),
    }


@app.put("/api/auth/password")
async def auth_change_password(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    old_password = body.get("old_password", "")
    new_password = body.get("new_password", "")

    if len(new_password) < 6:
        return JSONResponse({"error": "新密码至少 6 位"}, status_code=400)

    user_data = await get_user_by_id(user["user_id"])
    if not user_data or not verify_password(old_password, user_data["password_hash"]):
        return JSONResponse({"error": "原密码错误"}, status_code=401)

    await update_user_password(user["user_id"], hash_password(new_password))
    return {"status": "ok"}


@app.put("/api/auth/profile")
async def auth_update_profile(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    display_name = (body.get("display_name") or "").strip()
    await update_user_display_name(user["user_id"], display_name)
    user_data = await get_user_by_id(user["user_id"])
    return {
        "id": user_data["id"], "email": user_data["email"],
        "role": user_data["role"], "display_name": user_data["display_name"],
    }


# 前端兼容路由
@app.put("/api/user/profile")
async def user_update_profile(request: Request, user: dict = Depends(get_current_user)):
    return await auth_update_profile(request, user)


@app.put("/api/user/password")
async def user_change_password(request: Request, user: dict = Depends(get_current_user)):
    return await auth_change_password(request, user)


# ---- Admin Routes ----

@app.get("/api/admin/users")
async def admin_list_users(user: dict = Depends(require_admin)):
    users = await list_users()
    return {"users": users}


@app.put("/api/admin/users/{user_id}/role")
async def admin_update_user_role(user_id: int, body: dict, user: dict = Depends(require_admin)):
    role = body.get("role", "")
    if role not in ("admin", "user"):
        return JSONResponse({"error": "role must be 'admin' or 'user'"}, status_code=400)
    if user_id == user["user_id"]:
        return JSONResponse({"error": "不能修改自己的角色"}, status_code=400)
    await update_user_role(user_id, role)
    return {"ok": True}


@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: int, user: dict = Depends(require_admin)):
    if user_id == user["user_id"]:
        return JSONResponse({"error": "不能删除自己"}, status_code=400)
    await db_delete_user(user_id)
    return {"status": "deleted"}


# ---- Config Routes ----

@app.get("/api/config")
async def get_config(user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    benchmark = await get_settings(user_id)
    active = await get_active_profile(user_id)

    resolved = dict(benchmark) if benchmark else {}
    resolved["output_dir"] = "./data/results"

    if active:
        for k in CONNECTION_KEYS:
            if active.get(k):
                resolved[k] = active[k]
        resolved["profile_name"] = active["name"]
        resolved["models"] = active.get("models", [])
        if "api_key" in resolved:
            resolved["api_key_display"] = _mask_api_key(resolved["api_key"])
            del resolved["api_key"]

    return resolved


@app.put("/api/config")
async def update_config(request: Request, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    data = await request.json()
    data.pop("api_key_display", None)

    if not data.get("api_key") or data["api_key"].startswith("..."):
        active = await get_active_profile(user_id)
        data["api_key"] = active.get("api_key", "") if active else ""

    benchmark = {}
    for k in BENCHMARK_KEYS:
        if k in data:
            benchmark[k] = data[k]
    output_dir = data.get("output_dir", "./data/results")
    await save_settings(user_id, benchmark, output_dir)

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

    return {"status": "ok"}


# ---- Profiles Routes ----

@app.get("/api/profiles")
async def get_profiles_handler(user: dict = Depends(get_current_user)):
    profiles = await get_profiles(user["user_id"])
    active = await get_active_profile(user["user_id"])
    active_name = active["name"] if active else ""
    for p in profiles:
        if "api_key" in p:
            p["api_key_display"] = _mask_api_key(p["api_key"])
            del p["api_key"]
    return {"profiles": profiles, "active_profile": active_name}


@app.post("/api/profiles")
async def create_profile(request: Request, user: dict = Depends(get_current_user)):
    """前端 createProfile 调用"""
    return await save_profile(request, user)


@app.post("/api/profiles/save")
async def save_profile(request: Request, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "Profile name is required"}, status_code=400)

    api_key = data.get("api_key", "")
    if api_key.startswith("..."):
        active = await get_active_profile(user_id)
        api_key = active.get("api_key", "") if active else ""

    models = data.get("models")
    model = data.get("model", "")
    await upsert_profile(
        user_id, name,
        base_url=data.get("base_url", ""),
        api_key=api_key,
        api_version=data.get("api_version", "2023-06-01"),
        models=models,
        model=model,
        provider=data.get("provider", ""),
        protocol=data.get("protocol", ""),
        set_active=True,
    )
    return {"status": "ok"}


@app.post("/api/profiles/switch")
async def switch_profile(request: Request, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "Profile name is required"}, status_code=400)

    ok = await switch_active_profile(user_id, name)
    if not ok:
        return JSONResponse({"error": "Profile not found"}, status_code=404)

    active = await get_active_profile(user_id)
    benchmark = await get_settings(user_id)
    resolved = dict(benchmark) if benchmark else {}
    if active:
        for k in CONNECTION_KEYS:
            if active.get(k):
                resolved[k] = active[k]
        resolved["profile_name"] = active["name"]
        resolved["models"] = active.get("models", [])
        if "api_key" in resolved:
            resolved["api_key_display"] = _mask_api_key(resolved["api_key"])
            del resolved["api_key"]
    return {"status": "ok", "config": resolved}


@app.put("/api/profiles/{name}")
async def update_profile(name: str, request: Request, user: dict = Depends(get_current_user)):
    """前端 updateProfile 调用"""
    user_id = user["user_id"]
    data = await request.json()

    api_key = data.get("api_key", "")
    if api_key.startswith("..."):
        active = await get_active_profile(user_id)
        api_key = active.get("api_key", "") if active else ""

    models = data.get("models")
    model = data.get("model", "")
    await upsert_profile(
        user_id, name,
        base_url=data.get("base_url", ""),
        api_key=api_key,
        api_version=data.get("api_version", "2023-06-01"),
        models=models,
        model=model,
        provider=data.get("provider", ""),
        protocol=data.get("protocol", ""),
        set_active=data.get("set_active", False),
    )
    return {"status": "ok"}


@app.delete("/api/profiles/{name}")
async def delete_profile_handler(name: str, user: dict = Depends(get_current_user)):
    await db_delete_profile(user["user_id"], name)
    return {"status": "deleted"}


# ---- Results Routes ----

@app.get("/api/results")
async def list_results(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    hours: int | None = Query(None),
    user: dict = Depends(get_current_user),
):
    result = await db_get_results_aggregated(user["user_id"], limit=limit, offset=offset, hours=hours)
    return {"total": result["total"], "items": result["items"]}


@app.get("/api/results/compare")
async def compare_results(filenames: str = Query(...), user: dict = Depends(get_current_user)):
    """前端对比功能：接收逗号分隔的 filenames"""
    names = [n.strip() for n in filenames.split(",") if n.strip()]
    results = []
    for name in names:
        r = await get_result_by_filename(user["user_id"], name)
        if r:
            results.append(r)
    return {"results": results}


@app.get("/api/results/{filename}")
async def get_result(filename: str, user: dict = Depends(get_current_user)):
    result = await get_result_by_filename(user["user_id"], filename)
    if not result:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return result


@app.delete("/api/results/{filename}")
async def delete_result_handler(filename: str, user: dict = Depends(get_current_user)):
    await db_delete_result(user["user_id"], filename)
    return {"status": "deleted"}


# ---- Benchmark Routes ----

@app.post("/api/bench/start")
async def start_bench(request: Request, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]

    existing = manager.get_user_running_task(user_id)
    if existing:
        return JSONResponse({"error": "Benchmark already running"}, status_code=409)

    body = await request.json() if (await request.body()) else {}

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
        return JSONResponse({"error": "; ".join(errors)}, status_code=400)

    benchmark = await get_settings(user_id)
    active = await get_active_profile(user_id)
    config = dict(benchmark) if benchmark else {}
    if active:
        for k in CONNECTION_KEYS:
            if active.get(k):
                config[k] = active[k]
    _apply_env_overrides(config)

    for key in BENCHMARK_KEYS + CONNECTION_KEYS + ("requests_per_level",):
        if key in body and body[key] is not None:
            if key == "api_key" and isinstance(body[key], str) and body[key].startswith("..."):
                continue
            config[key] = body[key]

    # 获取模型列表
    models = []
    if active and active.get("models"):
        models = active["models"]
    elif config.get("model"):
        models = [config["model"]]
    else:
        return JSONResponse({"error": "No model configured"}, status_code=400)

    profile_name = active["name"] if active else ""

    if len(models) == 1:
        # 单模型：保持原有行为，返回单个 task_id
        config["model"] = models[0]
        task_id = uuid.uuid4().hex[:12]
        task = manager.create_task(task_id, user_id, profile_name=profile_name)
        task.status = "running"
        task.stop_event = asyncio.Event()
        task.start_time = time.monotonic()
        task.asyncio_task = asyncio.create_task(_run_benchmark_task(config, user_id, task))
        return {"status": "started", "task_id": task_id}
    else:
        # 多模型：为每个模型创建独立 task
        # 并发限制检查
        current_running = manager.get_running_count()
        if current_running + len(models) > BenchTaskManager.MAX_GLOBAL:
            return JSONResponse({"error": f"全局并发任务数已达上限 ({BenchTaskManager.MAX_GLOBAL})"}, status_code=429)
        user_running = manager.get_user_task_count(user_id)
        if user_running + len(models) > BenchTaskManager.MAX_PER_USER:
            return JSONResponse({"error": f"用户并发任务数已达上限 ({BenchTaskManager.MAX_PER_USER})"}, status_code=429)

        group_id = f"multi_{uuid.uuid4().hex[:12]}"
        task_ids = []
        from app.protocols import detect_protocol
        for model_name in models:
            model_config = dict(config)
            model_config["model"] = model_name
            model_config["protocol"] = detect_protocol(model_name, config.get("provider", ""))

            task_id = uuid.uuid4().hex[:12]
            task = manager.create_task(task_id, user_id, profile_name=profile_name, group_id=group_id)
            task.model_name = model_name
            task.status = "running"
            task.stop_event = asyncio.Event()
            task.start_time = time.monotonic()
            task.asyncio_task = asyncio.create_task(_run_benchmark_task(model_config, user_id, task))
            task_ids.append(task_id)

        return {"status": "started", "group_id": group_id, "task_ids": task_ids}


@app.post("/api/bench/stop")
async def stop_bench(
    task_id: str = Query(""),
    user: dict = Depends(get_current_user),
):
    if task_id:
        task = manager.get_task(task_id)
        if not task or task.status != "running":
            return JSONResponse({"error": "No benchmark running"}, status_code=400)
        if task.owner_id != user["user_id"]:
            return JSONResponse({"error": "Not your benchmark"}, status_code=403)
        task.status = "stopping"
        task.stop_event.set()
        return {"status": "stopping"}
    else:
        # 不指定 task_id：停止用户所有运行中的任务
        stopped = []
        for t in manager._tasks.values():
            if t.owner_id == user["user_id"] and t.status == "running":
                t.status = "stopping"
                t.stop_event.set()
                stopped.append(t.task_id)
        if not stopped:
            return JSONResponse({"error": "No benchmark running"}, status_code=400)
        return {"status": "stopping", "task_ids": stopped}


@app.get("/api/bench/status")
async def bench_status(
    task_id: str = Query(""),
    since: int = Query(0),
    user: dict = Depends(get_current_user),
):
    if task_id:
        task = manager.get_task(task_id)
    else:
        task = manager.get_user_running_task(user["user_id"])

    if not task:
        return {
            "task_id": "", "status": "idle",
            "scheduled_task_id": 0,
            "concurrency": 0, "level": 0, "total_levels": 0,
            "done": 0, "total": 0, "success": 0, "failed": 0,
            "elapsed": 0, "events": [],
        }

    new_events = [e for e in task.events if e["seq"] > since]
    elapsed = round(time.monotonic() - task.start_time, 1) if task.start_time else 0

    return {
        "task_id": task.task_id,
        "status": task.status,
        "scheduled_task_id": task.scheduled_task_id or 0,
        "concurrency": task.current_concurrency,
        "level": task.current_level,
        "total_levels": task.total_levels,
        "done": task.done_count,
        "total": task.total_count,
        "success": task.success_count,
        "failed": task.failed_count,
        "elapsed": elapsed,
        "events": new_events,
    }


@app.post("/api/bench/start-multi")
async def start_multi_bench(request: Request, user: dict = Depends(get_current_user)):
    """多服务器并行测试"""
    user_id = user["user_id"]
    body = await request.json()

    tasks_spec = body.get("tasks", [])
    if not tasks_spec or len(tasks_spec) > 10:
        return JSONResponse({"error": "tasks 数量需在 1-10 之间"}, status_code=400)

    current_running = manager.get_running_count()
    if current_running + len(tasks_spec) > BenchTaskManager.MAX_GLOBAL:
        return JSONResponse({"error": f"全局并发任务数已达上限 ({BenchTaskManager.MAX_GLOBAL})"}, status_code=429)
    user_running = manager.get_user_task_count(user_id)
    if user_running + len(tasks_spec) > BenchTaskManager.MAX_PER_USER:
        return JSONResponse({"error": f"用户并发任务数已达上限 ({BenchTaskManager.MAX_PER_USER})"}, status_code=429)

    profiles = await get_profiles(user_id)
    profile_map = {p["name"]: p for p in profiles}
    benchmark = await get_settings(user_id)

    group_id = f"grp_{uuid.uuid4().hex[:12]}"
    task_ids = []

    for spec in tasks_spec:
        profile_name = spec.get("profile_name", "")
        profile = profile_map.get(profile_name)
        if not profile:
            return JSONResponse({"error": f"Profile '{profile_name}' 不存在"}, status_code=400)

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

    return {"status": "started", "group_id": group_id, "task_ids": task_ids}


@app.post("/api/bench/start-multi-model")
async def start_multi_model_bench(request: Request, user: dict = Depends(get_current_user)):
    """多模型并行测试 — 单 profile，多个模型"""
    user_id = user["user_id"]
    body = await request.json()

    models = body.get("models", [])

    # 获取 active profile 作为基础配置
    active = await get_active_profile(user_id)
    if not active:
        return JSONResponse({"error": "没有活跃的配置，请先创建一个 profile"}, status_code=400)

    # 前端未传 models 时回退到 Profile 的 models
    if not models:
        models = active.get("models", [])

    if not models:
        return JSONResponse({"error": "未指定测试模型，请在请求中传入 models 或在 Profile 中配置 models"}, status_code=400)
    if len(models) > 10:
        return JSONResponse({"error": "models 数量不能超过 10 个"}, status_code=400)

    benchmark = await get_settings(user_id)
    provider = body.get("provider", active.get("provider", ""))

    current_running = manager.get_running_count()
    if current_running + len(models) > BenchTaskManager.MAX_GLOBAL:
        return JSONResponse({"error": f"全局并发任务数已达上限 ({BenchTaskManager.MAX_GLOBAL})"}, status_code=429)
    user_running = manager.get_user_task_count(user_id)
    if user_running + len(models) > BenchTaskManager.MAX_PER_USER:
        return JSONResponse({"error": f"用户并发任务数已达上限 ({BenchTaskManager.MAX_PER_USER})"}, status_code=429)

    group_id = f"multi_{uuid.uuid4().hex[:12]}"
    task_ids = []

    for model_name in models:
        config = dict(benchmark) if benchmark else {}
        for k in CONNECTION_KEYS:
            if active.get(k):
                config[k] = active[k]
        _apply_env_overrides(config)

        # 用当前模型覆盖
        config["model"] = model_name
        config["provider"] = provider

        # 自动检测协议
        from app.protocols import detect_protocol
        config["protocol"] = detect_protocol(model_name, provider)

        # 应用 body 中的 benchmark 参数覆盖
        overrides = {k: v for k, v in body.items() if k not in ("models", "provider")}
        for key in BENCHMARK_KEYS + ("requests_per_level",):
            if key in overrides and overrides[key] is not None:
                config[key] = overrides[key]

        task_id = uuid.uuid4().hex[:12]
        profile_name = active.get("name", "")
        task = manager.create_task(task_id, user_id, profile_name=profile_name, group_id=group_id)
        task.model_name = model_name
        task.status = "running"
        task.stop_event = asyncio.Event()
        task.start_time = time.monotonic()
        task.asyncio_task = asyncio.create_task(_run_benchmark_task(config, user_id, task))
        task_ids.append(task_id)

    return {"status": "started", "group_id": group_id, "task_ids": task_ids}


@app.get("/api/bench/status-multi/{group_id}")
async def status_multi_by_path(group_id: str, user: dict = Depends(get_current_user)):
    """多服务器测试状态聚合 — 路径参数版（前端调用）"""
    return await _status_multi_impl(group_id)


@app.get("/api/bench/status-multi")
async def status_multi_by_query(
    group_id: str = Query(""),
    user: dict = Depends(get_current_user),
):
    """多服务器测试状态聚合 — 查询参数版（向后兼容）"""
    if not group_id:
        return JSONResponse({"error": "group_id is required"}, status_code=400)
    return await _status_multi_impl(group_id)


async def _status_multi_impl(group_id: str):
    tasks = manager.get_group_tasks(group_id)
    if not tasks:
        return JSONResponse({"error": "Group not found"}, status_code=404)

    task_statuses = []
    for task in tasks:
        elapsed = round(time.monotonic() - task.start_time, 1) if task.start_time else 0
        task_statuses.append({
            "task_id": task.task_id,
            "profile_name": task.profile_name,
            "model_name": task.model_name,
            "status": task.status,
            "done": task.done_count,
            "total": task.total_count,
            "success": task.success_count,
            "failed": task.failed_count,
            "elapsed": elapsed,
            "result_filenames": task.result_filenames,
        })

    all_done = all(t["status"] != "running" for t in task_statuses)
    return {
        "group_id": group_id,
        "status": "completed" if all_done else "running",
        "tasks": task_statuses,
    }


@app.post("/api/bench/dry-run")
async def dry_run(request: Request, user: dict = Depends(get_current_user)):
    """单次请求验证连通性"""
    from main import run_dry

    user_id = user["user_id"]
    body = await request.json() if (await request.body()) else {}

    benchmark = await get_settings(user_id)
    active = await get_active_profile(user_id)
    config = dict(benchmark) if benchmark else {}
    if active:
        for k in CONNECTION_KEYS:
            if active.get(k):
                config[k] = active[k]
    _apply_env_overrides(config)

    for key in BENCHMARK_KEYS + CONNECTION_KEYS:
        if key in body and body[key] is not None:
            if key == "api_key" and isinstance(body[key], str) and body[key].startswith("..."):
                continue
            config[key] = body[key]

    connector = aiohttp_lib.TCPConnector(limit=10)
    async with aiohttp_lib.ClientSession(connector=connector) as session:
        ok = await run_dry(session, config)

    if ok:
        return {"status": "ok"}
    else:
        return JSONResponse({"error": "Dry run failed"}, status_code=400)


# ---- Schedule Routes ----

# run-now 冷却时间（秒），同一任务在此时间内不能重复触发
_RUN_NOW_COOLDOWN = 30

# configs_json 允许覆盖的字段白名单
_SCHEDULE_CONFIG_WHITELIST = {
    "model", "max_tokens", "temperature", "top_p", "stream",
    "concurrency_levels", "num_requests", "request_timeout",
    "api_base", "api_key", "custom_api_base",
}

@app.get("/api/schedules")
async def list_schedules(user: dict = Depends(get_current_user)):
    from app.db import get_scheduled_tasks, get_latest_result_ids_by_user
    tasks = await get_scheduled_tasks(user["user_id"])
    latest = await get_latest_result_ids_by_user(user["user_id"])
    for t in tasks:
        t["latest_result_id"] = latest.get(t["id"])
    return {"schedules": tasks}


@app.post("/api/schedules")
async def create_schedule(request: Request, user: dict = Depends(get_current_user)):
    from app.db import create_scheduled_task, get_scheduled_task, count_user_scheduled_tasks
    user_id = user["user_id"]
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return JSONResponse({"error": "名称不能为空"}, status_code=400)
    profile_ids = body.get("profile_ids", [])
    if not profile_ids:
        return JSONResponse({"error": "请至少选择一个 Profile"}, status_code=400)

    # 定时任务数量限制
    MAX_SCHEDULES_PER_USER = 10
    count = await count_user_scheduled_tasks(user_id)
    if count >= MAX_SCHEDULES_PER_USER:
        return JSONResponse({"error": f"定时任务数量已达上限（{MAX_SCHEDULES_PER_USER}个）"}, status_code=400)

    configs_json = body.get("configs_json", {})
    # 白名单过滤，防止覆盖内部关键字段
    if isinstance(configs_json, dict):
        configs_json = {k: v for k, v in configs_json.items() if k in _SCHEDULE_CONFIG_WHITELIST}
    else:
        configs_json = {}
    schedule_type = body.get("schedule_type", "interval")
    schedule_value = str(body.get("schedule_value", "300"))

    # 最小间隔限制
    try:
        sv_int = int(schedule_value)
    except (ValueError, TypeError):
        return JSONResponse({"error": "schedule_value 必须是正整数"}, status_code=400)
    if sv_int < 60:
        return JSONResponse({"error": "定时任务间隔不能小于 60 秒"}, status_code=400)

    sid = await create_scheduled_task(
        user_id, name, profile_ids, configs_json, schedule_type, schedule_value,
    )
    if _scheduler:
        _scheduler.start_loop(sid)
    return {"id": sid, "status": "created"}


@app.put("/api/schedules/{task_id}")
async def update_schedule(task_id: int, request: Request, user: dict = Depends(get_current_user)):
    from app.db import update_scheduled_task, get_scheduled_task
    user_id = user["user_id"]
    task_row = await get_scheduled_task(task_id)
    if not task_row or task_row["user_id"] != user_id:
        return JSONResponse({"error": "Not found"}, status_code=404)
    body = await request.json()
    allowed = {"name", "profile_ids", "configs_json", "schedule_type", "schedule_value", "status"}
    fields = {k: v for k, v in body.items() if k in allowed}

    # configs_json 白名单过滤
    if "configs_json" in fields and isinstance(fields["configs_json"], dict):
        fields["configs_json"] = {k: v for k, v in fields["configs_json"].items() if k in _SCHEDULE_CONFIG_WHITELIST}

    # 最小间隔限制
    if "schedule_value" in fields:
        try:
            sv_int = int(fields["schedule_value"])
        except (ValueError, TypeError):
            return JSONResponse({"error": "schedule_value 必须是正整数"}, status_code=400)
        if sv_int < 60:
            return JSONResponse({"error": "定时任务间隔不能小于 60 秒"}, status_code=400)

    if fields:
        await update_scheduled_task(task_id, **fields)
    if _scheduler:
        final_status = fields.get("status", task_row.get("status"))
        if final_status == "active":
            _scheduler.start_loop(task_id)
        else:
            await _scheduler.cancel_loop(task_id)
    return {"status": "updated"}


@app.delete("/api/schedules/{task_id}")
async def delete_schedule(task_id: int, user: dict = Depends(get_current_user)):
    from app.db import delete_scheduled_task, get_scheduled_task
    user_id = user["user_id"]
    task_row = await get_scheduled_task(task_id)
    if not task_row or task_row["user_id"] != user_id:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if _scheduler:
        await _scheduler.cancel_loop(task_id)
    await delete_scheduled_task(task_id)
    return {"status": "deleted"}


@app.post("/api/schedules/{task_id}/pause")
async def pause_schedule(task_id: int, user: dict = Depends(get_current_user)):
    from app.db import update_scheduled_task, get_scheduled_task
    user_id = user["user_id"]
    task_row = await get_scheduled_task(task_id)
    if not task_row or task_row["user_id"] != user_id:
        return JSONResponse({"error": "Not found"}, status_code=404)
    await update_scheduled_task(task_id, status="paused")
    if _scheduler:
        await _scheduler.cancel_loop(task_id)
    return {"status": "paused"}


@app.post("/api/schedules/{task_id}/resume")
async def resume_schedule(task_id: int, user: dict = Depends(get_current_user)):
    from app.db import update_scheduled_task, get_scheduled_task
    user_id = user["user_id"]
    task_row = await get_scheduled_task(task_id)
    if not task_row or task_row["user_id"] != user_id:
        return JSONResponse({"error": "Not found"}, status_code=404)
    await update_scheduled_task(task_id, status="active")
    if _scheduler:
        _scheduler.start_loop(task_id)
    return {"status": "resumed"}


@app.post("/api/schedules/{task_id}/run-now")
async def run_schedule_now(task_id: int, user: dict = Depends(get_current_user)):
    from app.db import get_scheduled_task
    user_id = user["user_id"]
    task_row = await get_scheduled_task(task_id)
    if not task_row or task_row["user_id"] != user_id:
        return JSONResponse({"error": "Not found"}, status_code=404)
    # DB 级冷却检查（跨实例安全）
    if task_row.get("last_run_at"):
        from datetime import datetime, timezone
        last_run = task_row["last_run_at"]
        if isinstance(last_run, str):
            try:
                last_run = datetime.fromisoformat(last_run)
            except ValueError:
                last_run = None
        if last_run:
            elapsed = (datetime.now(timezone.utc) - last_run.replace(tzinfo=timezone.utc)).total_seconds()
            if elapsed < _RUN_NOW_COOLDOWN:
                remaining = int(_RUN_NOW_COOLDOWN - elapsed)
                return JSONResponse({"error": f"请等待 {remaining} 秒后再试"}, status_code=429)
    if _scheduler:
        await _scheduler.run_now(task_id)
    return {"status": "triggered"}


@app.get("/api/schedules/{task_id}/results")
async def get_schedule_results(task_id: int, limit: int = 100, offset: int = 0, hours: int | None = None,
                               user: dict = Depends(get_current_user)):
    from app.db import get_results_by_scheduled_task, get_scheduled_task
    user_id = user["user_id"]
    task_row = await get_scheduled_task(task_id)
    if not task_row or task_row["user_id"] != user_id:
        return JSONResponse({"error": "Not found"}, status_code=404)
    data = await get_results_by_scheduled_task(user_id, task_id, limit=limit, offset=offset, hours=hours)
    clean = []
    for r in data["results"]:
        clean.append({
            "test_id": r.get("test_id", ""),
            "filename": r.get("filename", ""),
            "timestamp": r.get("timestamp", ""),
            "config": r.get("config", {}),
            "summary": r.get("summary", {}),
            "percentiles": r.get("percentiles", {}),
            "errors": r.get("errors", {}),
            "error_details": r.get("error_details", []),
            "scheduled_task_id": r.get("scheduled_task_id", 0),
            "schedule_name": r.get("schedule_name", ""),
        })
    return {"results": clean, "total": data["total"]}


@app.get("/api/schedules/{task_id}/trend")
async def get_schedule_trend(task_id: int, hours: int | None = None, user: dict = Depends(get_current_user)):
    from app.db import get_schedule_results_trend, get_scheduled_task
    user_id = user["user_id"]
    task_row = await get_scheduled_task(task_id)
    if not task_row or task_row["user_id"] != user_id:
        return JSONResponse({"error": "Not found"}, status_code=404)
    trend = await get_schedule_results_trend(user_id, task_id, hours=hours)
    return {"trend": trend}


# ---- Models Route (frontend) ----

@app.post("/api/models")
async def list_models(request: Request, user: dict = Depends(get_current_user)):
    """根据 base_url 获取可用模型列表"""
    body = await request.json() if (await request.body()) else {}
    base_url = body.get("base_url", "")
    api_key = body.get("api_key", "")

    if not base_url:
        active = await get_active_profile(user["user_id"])
        if active:
            base_url = active.get("base_url", "")
            api_key = active.get("api_key", "")

    if not base_url:
        return JSONResponse({"error": "base_url is required"}, status_code=400)

    # 调用 /v1/models 接口
    models_url = base_url.rstrip("/") + "/v1/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        connector = aiohttp_lib.TCPConnector(limit=5)
        async with aiohttp_lib.ClientSession(connector=connector) as session:
            async with session.get(models_url, headers=headers, timeout=aiohttp_lib.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = []
                    for m in data.get("data", []):
                        models.append({"id": m.get("id", ""), "name": m.get("id", "")})
                    return {"models": models}
                else:
                    return JSONResponse({"error": f"Upstream returned {resp.status}"}, status_code=resp.status)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


# ---- Pricing ----

@app.get("/api/pricing/models")
async def pricing_models(
    provider: str = Query(""),
    enabled_only: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    """按 provider 返回 LiteLLM 价格库中的模型列表"""
    from app.pricing import pricing_service
    models = pricing_service.get_models_by_provider(provider, enabled_only=enabled_only)
    return {"models": models, "total": len(models)}


@app.get("/api/pricing/models-config")
async def get_models_config(user: dict = Depends(get_current_user)):
    """返回用户启用的模型列表"""
    from app.pricing import pricing_service
    return {"enabled_models": pricing_service.get_enabled_models()}


@app.put("/api/pricing/models-config")
async def put_models_config(body: dict, user: dict = Depends(require_admin)):
    """管理员保存全局启用的模型列表"""
    from app.pricing import pricing_service
    models = body.get("enabled_models", [])
    if not isinstance(models, list):
        return JSONResponse({"error": "enabled_models must be a list"}, status_code=400)
    pricing_service.save_enabled_models(models)
    return {"ok": True, "count": len(models)}


@app.post("/api/pricing/refresh")
async def pricing_refresh(user: dict = Depends(require_admin)):
    """管理员手动刷新价格数据"""
    from app.pricing import pricing_service
    await pricing_service.refresh()
    return {"ok": True, "total_models": len(pricing_service._cache)}


# ---- SSE Stream ----

@app.get("/api/bench/stream")
async def bench_stream(request: Request, token: str = Query("")):
    """SSE 长连接 — 实时推送测试事件"""
    if not token:
        return JSONResponse({"error": "Missing token"}, status_code=401)
    payload = decode_jwt_token(token)
    if payload is None:
        return JSONResponse({"error": "Invalid token"}, status_code=401)
    user_id = int(payload["sub"])

    task = manager.get_user_running_task(user_id)
    if not task:
        # 没有运行中的任务，发送 idle 后关闭
        def idle_stream():
            yield f"event: bench:idle\ndata: {json.dumps({'status': 'idle'})}\n\n"
        return StreamingResponse(idle_stream(), media_type="text/event-stream")

    waiter = asyncio.Event()
    task.event_waiters.append(waiter)
    last_seq = 0

    async def event_generator():
        nonlocal last_seq
        try:
            # 发送存量事件
            for evt in task.events:
                last_seq = evt["seq"]
                yield f"id: {evt['seq']}\nevent: {evt['type']}\ndata: {json.dumps(evt['data'])}\n\n"

            # 等待新事件
            while True:
                # 检查连接是否断开
                if await request.is_disconnected():
                    break
                # 30s 超时 = keepalive
                try:
                    await asyncio.wait_for(waiter.wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                waiter.clear()
                # 发送新事件
                new_events = [e for e in task.events if e["seq"] > last_seq]
                for evt in new_events:
                    last_seq = evt["seq"]
                    yield f"id: {evt['seq']}\nevent: {evt['type']}\ndata: {json.dumps(evt['data'])}\n\n"
                # 如果任务已完成或出错，结束流
                if task.status == "idle" and new_events:
                    break
        finally:
            if waiter in task.event_waiters:
                task.event_waiters.remove(waiter)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---- Static Files ----

@app.get("/favicon.ico")
async def favicon_handler():
    favicon_path = STATIC_DIR / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(str(favicon_path))
    return Response(status_code=404)

# Mount static directories if they exist
if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")
if (STATIC_DIR / "vendor").exists():
    app.mount("/vendor", StaticFiles(directory=str(STATIC_DIR / "vendor")), name="vendor")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """SPA 兜底 — 返回 index.html"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return Response(status_code=404)
