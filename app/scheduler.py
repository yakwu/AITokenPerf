#!/usr/bin/env python3
"""定时任务调度器 — 每个任务一个独立 asyncio 循环协程"""

import asyncio
import logging
import time
import uuid
from datetime import datetime

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
        # task_id → asyncio.Task，管理所有循环的生命周期
        self._loops: dict[int, asyncio.Task] = {}

    # ── 公开接口 ──────────────────────────────────────────

    async def start(self):
        """服务启动时，为所有 active 任务启动循环"""
        self._running = True
        tasks = await get_all_active_scheduled_tasks()
        for t in tasks:
            self.start_loop(t["id"])
        log.info("调度器已启动，加载 %d 个活跃任务", len(tasks))

    async def stop(self):
        """服务停止时，取消所有循环"""
        self._running = False
        for task in self._loops.values():
            task.cancel()
        self._loops.clear()

    def start_loop(self, task_id: int):
        """启动或重启某个任务的调度循环"""
        self.cancel_loop(task_id)
        self._loops[task_id] = asyncio.create_task(self._loop(task_id))

    def cancel_loop(self, task_id: int):
        """取消某个任务的调度循环（暂停/删除/重启前调用）"""
        old = self._loops.pop(task_id, None)
        if old:
            old.cancel()

    def has_loop(self, task_id: int) -> bool:
        return task_id in self._loops

    # ── 调度循环 ──────────────────────────────────────────

    async def _loop(self, task_id: int):
        """睡 → 执行 → 睡 → 执行 … 直到被 cancel 或任务不再是 active"""
        while self._running:
            task_row = await get_scheduled_task(task_id)
            if not task_row or task_row.get("status") != "active":
                return

            delay = _calc_delay(task_row)
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return

            if not self._running:
                return

            # sleep 后再确认一次（期间可能被暂停/删除/重启）
            task_row = await get_scheduled_task(task_id)
            if not task_row or task_row.get("status") != "active":
                return

            await self._execute(task_id)

    # ── 执行 ──────────────────────────────────────────────

    async def _execute(self, task_id: int):
        """执行定时任务（外部 run-now 也会调用）"""
        await _run_scheduled_task(task_id)


# ── 模块级工具函数 ───────────────────────────────────────

def _calc_delay(task_row: dict) -> float:
    """根据 last_run_at 和 interval 算出距下次执行的秒数"""
    schedule_value = int(task_row.get("schedule_value", "300"))
    last_run = task_row.get("last_run_at")
    if last_run:
        try:
            last_dt = last_run if isinstance(last_run, datetime) else datetime.fromisoformat(last_run)
            # 统一为 naive datetime 做减法（PG timestamptz 带时区，SQLite 不带）
            now = datetime.utcnow()
            if last_dt.tzinfo is not None:
                from datetime import timezone
                now = now.replace(tzinfo=timezone.utc)
            elapsed = (now - last_dt).total_seconds()
            remaining = schedule_value - elapsed
            if remaining > 0:
                return remaining
        except (ValueError, TypeError):
            pass
    return 5  # 首次运行或时间解析失败，5 秒后执行


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

    try:
        new_run_count = (task_row.get("run_count") or 0) + 1
        await update_scheduled_task(task_id, last_run_at=datetime.utcnow(), run_count=new_run_count)
        log.info("定时任务 #%d 执行完成，累计 %d 次，本次保存 %d 条结果",
                 task_id, new_run_count, total_saved)
        log_bench("scheduler:complete", task_id=task_id,
                  run_count=new_run_count, results_saved=total_saved)
    except Exception as e:
        log.error("定时任务 #%d 更新 run_count 失败: %s", task_id, e)
