#!/usr/bin/env python3
"""定时任务调度器 — 全局单循环 + next_run_at 绝对时间调度"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from app.db import (
    get_all_active_scheduled_tasks,
    get_scheduled_task,
    update_scheduled_task,
    get_profiles,
    get_settings,
)
from app.logger import log_bench, log_error

log = logging.getLogger("scheduler")
log.setLevel(logging.INFO)
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[scheduler] %(message)s"))
    log.addHandler(_handler)


class TaskScheduler:
    def __init__(self):
        self._running = False
        self._main_loop: asyncio.Task | None = None
        self._executing: set[int] = set()

    # ── 公开接口 ──────────────────────────────────────────

    async def start(self):
        """服务启动时，为所有 active 任务补齐 next_run_at，启动全局循环"""
        self._running = True
        tasks = await get_all_active_scheduled_tasks()
        now = datetime.now(timezone.utc)
        for t in tasks:
            if not t.get("next_run_at"):
                await update_scheduled_task(t["id"], next_run_at=now)
        self._main_loop = asyncio.create_task(self._run())
        log.info("调度器已启动，加载 %d 个活跃任务", len(tasks))

    async def stop(self):
        """服务停止时，取消全局循环"""
        self._running = False
        if self._main_loop:
            self._main_loop.cancel()
            try:
                await self._main_loop
            except asyncio.CancelledError:
                pass
            self._main_loop = None

    def start_loop(self, task_id: int):
        """启动或重置某个任务的调度（设置 next_run_at=now 触发立即执行）"""
        asyncio.create_task(self._trigger(task_id))

    def cancel_loop(self, task_id: int):
        """暂停/删除某个任务：从执行集合移除（循环会因 DB status 变化自动跳过）"""
        self._executing.discard(task_id)

    async def run_now(self, task_id: int):
        """立即执行一次（run-now 端点调用）"""
        if task_id in self._executing:
            log.warning("定时任务 #%d 正在执行中，跳过 run-now", task_id)
            return
        self._executing.add(task_id)
        asyncio.create_task(self._execute_and_schedule(task_id, skip_reschedule=True))

    def has_loop(self, task_id: int) -> bool:
        # 全局循环模式下，只要任务是 active 就算"有循环"
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
        while self._running:
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                return
            if not self._running:
                return
            try:
                tasks = await get_all_active_scheduled_tasks()
                now = datetime.now(timezone.utc)
                for t in tasks:
                    tid = t["id"]
                    if tid in self._executing:
                        continue
                    next_run = t.get("next_run_at")
                    if next_run:
                        # 处理时区：PG 返回带时区的，SQLite 不带
                        if isinstance(next_run, str):
                            try:
                                next_run = datetime.fromisoformat(next_run)
                            except ValueError:
                                continue
                        if next_run.tzinfo is None:
                            next_run = next_run.replace(tzinfo=timezone.utc)
                        if next_run > now:
                            continue
                    # 到期了，触发执行
                    self._executing.add(tid)
                    asyncio.create_task(self._execute_and_schedule(tid))
            except Exception as e:
                log.error("调度循环异常: %s", e)

    async def _execute_and_schedule(self, task_id: int, skip_reschedule: bool = False):
        """执行任务，完成后计算下一次执行时间"""
        try:
            await _run_scheduled_task(task_id)
        except Exception as e:
            log.error("定时任务 #%d 执行异常: %s", task_id, e)
            log_error("scheduler:task_error", error=str(e), task_id=task_id)
        finally:
            self._executing.discard(task_id)
            if not skip_reschedule:
                await self._reschedule(task_id)

    async def _reschedule(self, task_id: int):
        """执行完毕后，基于上一次 next_run_at + interval 推算下次，保持固定节奏"""
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
                    # 固定节奏：上次计划时间 + interval，直到超过 now
                    next_at = prev_next + timedelta(seconds=sv)
                    while next_at <= now:
                        next_at += timedelta(seconds=sv)
                else:
                    # 首次执行，从 now 开始
                    next_at = now + timedelta(seconds=sv)
                await update_scheduled_task(
                    task_id,
                    next_run_at=next_at,
                    last_run_at=now,
                    run_count=(task_row.get("run_count") or 0) + 1,
                )
                delay = (next_at - now).total_seconds()
                log.info("定时任务 #%d 执行完成，下次执行: %.0f 秒后", task_id, delay)
        except Exception as e:
            log.error("定时任务 #%d 更新调度失败: %s", task_id, e)


# ── 模块级工具函数 ───────────────────────────────────────

async def _run_scheduled_task(task_id: int):
    """执行一个定时任务：为每个 profile 并行跑 benchmark"""
    from app.server import manager, _run_benchmark_task, BenchTaskManager, CONNECTION_KEYS, _apply_env_overrides

    task_row = await get_scheduled_task(task_id)
    if not task_row or task_row.get("status") != "active":
        return

    user_id = task_row["user_id"]
    profile_ids = task_row.get("profile_ids", [])
    configs_json = task_row.get("configs", {})

    profiles = await get_profiles(user_id)
    profile_map = {p["name"]: p for p in profiles}
    benchmark = await get_settings(user_id)

    log.info("执行定时任务 #%d '%s'，%d 个 profile", task_id, task_row["name"], len(profile_ids))
    log_bench("scheduler:start", task_id=task_id, name=task_row["name"],
              profiles=profile_ids, user_id=user_id)

    if manager.get_user_task_count(user_id) >= BenchTaskManager.MAX_PER_USER:
        log.warning("用户 %d 并发已达上限，跳过定时任务 #%d", user_id, task_id)
        log_error("scheduler:skipped", error="用户并发已达上限",
                  task_id=task_id, user_id=user_id)
        return

    group_id = f"sched_{uuid.uuid4().hex[:12]}"
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

        for key, val in configs_json.items():
            if val is not None:
                config[key] = val

        cl = config.get("concurrency_levels", [100])
        if isinstance(cl, (list, tuple)):
            config["concurrency_levels"] = [int(v) for v in cl]
        elif isinstance(cl, (int, str)):
            config["concurrency_levels"] = [int(cl)]

        tid = uuid.uuid4().hex[:12]
        bt = manager.create_task(tid, user_id, profile_name=pname, group_id=group_id)
        bt.scheduled_task_id = task_id
        bt.status = "running"
        bt.stop_event = asyncio.Event()
        bt.start_time = time.monotonic()
        bt.asyncio_task = asyncio.create_task(_run_benchmark_task(config, user_id, bt))
        bench_tasks.append(bt)

    if not bench_tasks:
        log.warning("定时任务 #%d: 没有有效的 profile，跳过执行", task_id)
        log_error("scheduler:no_profiles", error="没有有效的 profile",
                  task_id=task_id, profile_ids=profile_ids)
        return

    total_saved = 0
    for bt in bench_tasks:
        if bt.asyncio_task:
            try:
                await bt.asyncio_task
                total_saved += len(bt.result_filenames)
            except Exception as e:
                log.error("定时子任务异常: %s", e)
                log_error("scheduler:task_error", error=str(e),
                          task_id=task_id, task_tid=bt.task_id)

    log.info("定时任务 #%d 本次保存 %d 条结果", task_id, total_saved)
    log_bench("scheduler:complete", task_id=task_id, results_saved=total_saved)
