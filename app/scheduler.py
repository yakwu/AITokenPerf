#!/usr/bin/env python3
"""定时任务调度器 — 全局单循环 + next_run_at 绝对时间调度 + DB 分布式锁"""

import asyncio
import json
import logging
import random
import time
import uuid
from datetime import datetime, timedelta, timezone

from app.db import (
    get_all_active_scheduled_tasks,
    get_due_scheduled_tasks,
    get_scheduled_task,
    update_scheduled_task,
    get_profiles,
    get_settings,
    get_user_by_id,
    claim_scheduled_task,
    release_scheduled_task,
    release_and_reschedule_scheduled_task,
)
from app.logger import log_bench, log_error, current_run_id, RunIdFormatter

log = logging.getLogger("scheduler")
log.setLevel(logging.INFO)
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(RunIdFormatter("%(asctime)s [%(run_id)s] [scheduler] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    log.addHandler(_handler)


class TaskScheduler:
    def __init__(self):
        self._running = False
        self._main_loop: asyncio.Task | None = None
        self._child_tasks: set[asyncio.Task] = set()

    # ── 公开接口 ──────────────────────────────────────────

    async def start(self):
        """服务启动时，为所有 active 任务补齐 next_run_at，释放过期锁，启动全局循环"""
        self._running = True
        tasks = await get_all_active_scheduled_tasks()
        now = datetime.now(timezone.utc)
        for t in tasks:
            if not t.get("next_run_at"):
                await update_scheduled_task(t["id"], next_run_at=now)
            # 启动时释放可能残留的锁（进程异常退出的情况）
            if t.get("locked_until"):
                await release_scheduled_task(t["id"])
        self._main_loop = asyncio.create_task(self._run())
        log.info("调度器已启动，加载 %d 个活跃任务", len(tasks))

    async def stop(self):
        """服务停止时，取消全局循环和所有子任务"""
        self._running = False
        if self._main_loop:
            self._main_loop.cancel()
            try:
                await self._main_loop
            except asyncio.CancelledError:
                pass
            self._main_loop = None
        # 取消所有正在执行的子任务
        for task in list(self._child_tasks):
            task.cancel()
        if self._child_tasks:
            await asyncio.gather(*self._child_tasks, return_exceptions=True)
            self._child_tasks.clear()

    def start_loop(self, task_id: int):
        """启动或重置某个任务的调度（设置 next_run_at=now 触发立即执行）"""
        asyncio.create_task(self._trigger(task_id))

    async def cancel_loop(self, task_id: int):
        """暂停/删除某个任务：释放 DB 锁"""
        await release_scheduled_task(task_id)

    async def run_now(self, task_id: int):
        """立即执行一次（run-now 端点调用）"""
        if not await claim_scheduled_task(task_id):
            log.warning("定时任务 #%d 正在执行中，跳过 run-now", task_id)
            return
        asyncio.create_task(self._execute_and_schedule(task_id, skip_reschedule=True))

    def has_loop(self, task_id: int) -> bool:
        # 全局循环模式下，只要调度器在运行就算"有循环"
        return self._running

    # ── 内部方法 ──────────────────────────────────────────

    async def _trigger(self, task_id: int):
        """将任务的 next_run_at 设为 now，触发下一轮调度"""
        task_row = await get_scheduled_task(task_id)
        if not task_row or task_row.get("status") != "active":
            return
        await update_scheduled_task(task_id, next_run_at=datetime.now(timezone.utc))

    async def _run(self):
        """全局调度循环：每 5 秒扫一次 DB，触发到期任务"""
        from app.server import BenchTaskManager
        while self._running:
            try:
                # 加随机 jitter 错开多实例查询峰值
                await asyncio.sleep(5 + random.uniform(0, 1))
            except asyncio.CancelledError:
                return
            if not self._running:
                return
            try:
                now = datetime.now(timezone.utc)
                tasks = await get_due_scheduled_tasks(now)
                for t in tasks:
                    tid = t["id"]
                    # 到期了，尝试用 DB 锁抢占（多 worker 安全 + DB 级并发限制）
                    if not await claim_scheduled_task(
                        tid,
                        max_global=BenchTaskManager.MAX_GLOBAL,
                        max_per_user=BenchTaskManager.MAX_PER_USER,
                    ):
                        continue
                    task = asyncio.create_task(self._execute_and_schedule(tid))
                    self._child_tasks.add(task)
                    task.add_done_callback(self._child_tasks.discard)
            except Exception as e:
                log.error("调度循环异常: %s", e)

    async def _execute_and_schedule(self, task_id: int, skip_reschedule: bool = False):
        """执行任务（带超时保护），完成后计算下一次执行时间"""
        from app.config import SCHEDULER_TASK_TIMEOUT
        cancelled = False
        try:
            await asyncio.wait_for(
                _run_scheduled_task(task_id),
                timeout=SCHEDULER_TASK_TIMEOUT,
            )
        except asyncio.TimeoutError:
            log.error("定时任务 #%d 执行超时（%ds），强制终止", task_id, SCHEDULER_TASK_TIMEOUT)
            log_error("scheduler:timeout", error=f"超时 {SCHEDULER_TASK_TIMEOUT}s", task_id=task_id)
        except asyncio.CancelledError:
            cancelled = True
        except Exception as e:
            log.error("定时任务 #%d 执行异常: %s", task_id, e)
            log_error("scheduler:task_error", error=str(e), task_id=task_id)
        finally:
            if not skip_reschedule and not cancelled:
                await self._release_and_reschedule(task_id)
            else:
                await release_scheduled_task(task_id)
            if cancelled:
                raise asyncio.CancelledError()

    async def _release_and_reschedule(self, task_id: int):
        """原子释放锁并重新调度 — 防止 release→reschedule 窗口期的竞态"""
        try:
            task_row = await get_scheduled_task(task_id)
            if task_row and task_row.get("status") == "active":
                sv = int(task_row.get("schedule_value", "300"))
                now = datetime.now(timezone.utc)
                prev_next = task_row.get("next_run_at")
                if isinstance(prev_next, str):
                    try:
                        prev_next = datetime.fromisoformat(prev_next)
                    except ValueError:
                        prev_next = None
                if prev_next and prev_next.tzinfo:
                    elapsed = (now - prev_next).total_seconds()
                    intervals_elapsed = int(elapsed // sv) + 1
                    next_at = prev_next + timedelta(seconds=sv * intervals_elapsed)
                    # 防连续触发：确保下次执行至少在 now 之后
                    if next_at <= now:
                        next_at = now + timedelta(seconds=sv)
                else:
                    next_at = now + timedelta(seconds=sv)
                new_count = (task_row.get("run_count") or 0) + 1
                await release_and_reschedule_scheduled_task(task_id, next_at, now, new_count)
                delay = (next_at - now).total_seconds()
                log.info("定时任务 #%d 执行完成，下次执行: %.0f 秒后", task_id, delay)
            else:
                await release_scheduled_task(task_id)
        except Exception as e:
            log.error("定时任务 #%d 原子调度失败: %s", task_id, e)
            await release_scheduled_task(task_id)



# ── 模块级工具函数 ───────────────────────────────────────

async def _run_scheduled_task(task_id: int):
    """执行一个定时任务：为每个 profile 并行跑 benchmark"""
    from app.server import manager, _run_benchmark_task, BenchTaskManager, CONNECTION_KEYS, _apply_env_overrides

    run_id = f"sched_{uuid.uuid4().hex[:8]}"
    current_run_id.set(run_id)

    task_row = await get_scheduled_task(task_id)
    if not task_row or task_row.get("status") != "active":
        return

    user_id = task_row["user_id"]

    # 检查用户状态 — 防止已删除/禁用用户的任务继续执行
    user = await get_user_by_id(user_id)
    if not user:
        log.warning("定时任务 #%d: 用户 %d 已删除，暂停任务", task_id, user_id)
        await update_scheduled_task(task_id, status="paused")
        return

    # 全局并发限制
    if manager.get_running_count() >= BenchTaskManager.MAX_GLOBAL:
        log.warning("全局并发已达上限（%d），跳过定时任务 #%d", BenchTaskManager.MAX_GLOBAL, task_id)
        log_error("scheduler:skipped", error="全局并发已达上限",
                  task_id=task_id, user_id=user_id)
        return

    # 用户并发限制
    if manager.get_user_task_count(user_id) >= BenchTaskManager.MAX_PER_USER:
        log.warning("用户 %d 并发已达上限，跳过定时任务 #%d", user_id, task_id)
        log_error("scheduler:skipped", error="用户并发已达上限",
                  task_id=task_id, user_id=user_id)
        return

    # 轻量检查通过后，才做较重的 DB 查询
    profile_ids = task_row.get("profile_ids", [])
    configs_json = task_row.get("configs", {})

    profiles = await get_profiles(user_id)
    profile_map = {p["name"]: p for p in profiles}
    benchmark = await get_settings(user_id)

    log.info("执行定时任务 #%d '%s'，%d 个 profile", task_id, task_row["name"], len(profile_ids))
    log_bench("scheduler:start", task_id=task_id, name=task_row["name"],
              profiles=profile_ids, user_id=user_id)

    group_id = run_id
    bench_tasks = []

    for pname in profile_ids:
        profile = profile_map.get(pname)
        if not profile:
            log.warning("定时任务 #%d: profile '%s' 不存在", task_id, pname)
            log_error("scheduler:profile_missing", error=f"Profile '{pname}' not found",
                      task_id=task_id, profile=pname)
            continue

        config = dict(benchmark) if benchmark else {}
        for k in CONNECTION_KEYS:
            if profile.get(k):
                config[k] = profile[k]
        _apply_env_overrides(config)

        # 获取模型列表（优先用定时任务中选的模型子集）
        models = configs_json.get("models") or []
        if not models:
            raw_model = configs_json.get("model") or ""
            models = [raw_model] if raw_model else []
        if not models:
            models = profile.get("models", [])
        if not models:
            raw_model = config.get("model", "")
            models = [raw_model] if raw_model else []

        for key, val in configs_json.items():
            if val is not None:
                config[key] = val

        cl = config.get("concurrency_levels", [100])
        try:
            if isinstance(cl, str):
                cl = json.loads(cl)
            if isinstance(cl, (list, tuple)):
                config["concurrency_levels"] = [int(v) for v in cl]
            elif isinstance(cl, (int, float)):
                config["concurrency_levels"] = [int(cl)]
            else:
                config["concurrency_levels"] = [100]
        except (ValueError, TypeError, json.JSONDecodeError):
            config["concurrency_levels"] = [100]

        # 为每个模型创建独立 task
        for model_name in models:
            model_config = dict(config)
            model_config["model"] = model_name
            model_config["profile_name"] = pname

            # 检查必要配置
            missing = [k for k in ("base_url", "api_key", "model") if not model_config.get(k)]
            if missing:
                log.warning("定时任务 #%d: profile '%s' model '%s' 缺少配置 %s，跳过",
                           task_id, pname, model_name, missing)
                log_error("scheduler:config_missing", error=f"缺少配置: {', '.join(missing)}",
                          task_id=task_id, profile=pname, model=model_name, missing=missing)
                continue

            from app.protocols import detect_protocol
            model_config["protocol"] = detect_protocol(model_name, model_config.get("provider", ""))

            tid = uuid.uuid4().hex[:12]
            bt = manager.create_task(tid, user_id, profile_name=pname, group_id=group_id)
            bt.scheduled_task_id = task_id
            bt.model_name = model_name
            bt.status = "running"
            bt.stop_event = asyncio.Event()
            bt.start_time = time.monotonic()
            bt.asyncio_task = asyncio.create_task(_run_benchmark_task(model_config, user_id, bt))
            bench_tasks.append(bt)

    if not bench_tasks:
        log.warning("定时任务 #%d: 没有有效的 profile，跳过执行", task_id)
        log_error("scheduler:no_profiles", error="没有有效的 profile",
                  task_id=task_id, profile_ids=profile_ids)
        return

    async def _wait_one(bt):
        if bt.asyncio_task:
            try:
                await bt.asyncio_task
                return len(bt.result_filenames)
            except Exception as e:
                log.error("定时子任务异常: %s", e)
                log_error("scheduler:task_error", error=str(e),
                          task_id=task_id, task_tid=bt.task_id)
        return 0

    results = await asyncio.gather(*[_wait_one(bt) for bt in bench_tasks], return_exceptions=True)
    total_saved = sum(r for r in results if isinstance(r, int))

    log.info("定时任务 #%d 本次保存 %d 条结果", task_id, total_saved)
    log_bench("scheduler:complete", task_id=task_id, results_saved=total_saved)
