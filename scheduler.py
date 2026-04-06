#!/usr/bin/env python3
"""定时任务调度器 — 从 DB 加载 active 任务，到时自动执行"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta

from db import (
    get_all_active_scheduled_tasks,
    get_scheduled_task,
    update_scheduled_task,
    get_profiles,
    get_settings,
)
from logger import log_bench, log_error

log = logging.getLogger("scheduler")
# 同时输出到 app.log
log.setLevel(logging.INFO)
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[scheduler] %(message)s"))
    log.addHandler(_handler)


class TaskScheduler:
    def __init__(self):
        self._timers: dict[int, asyncio.Task] = {}  # scheduled_task_id → sleep+execute task
        self._running = False

    async def start(self):
        """启动调度器，加载所有 active 任务"""
        self._running = True
        tasks = await get_all_active_scheduled_tasks()
        for t in tasks:
            self._schedule(t)
        log.info("调度器已启动，加载 %d 个活跃任务", len(tasks))

    async def stop(self):
        """停止调度器，取消所有待执行的 timer"""
        self._running = False
        for timer in self._timers.values():
            timer.cancel()
        self._timers.clear()
        log.info("调度器已停止")

    def _schedule(self, task_row: dict):
        """为一个 scheduled_task 安排下次执行"""
        task_id = task_row["id"]
        # 取消已有 timer
        if task_id in self._timers:
            self._timers[task_id].cancel()

        delay = self._calc_delay(task_row)
        if delay <= 0:
            delay = 1

        self._timers[task_id] = asyncio.create_task(self._wait_and_execute(task_id, delay))

    def _calc_delay(self, task_row: dict) -> float:
        """计算距离下次执行的秒数"""
        schedule_type = task_row.get("schedule_type", "interval")
        schedule_value = int(task_row.get("schedule_value", "300"))

        if schedule_type == "interval":
            last_run = task_row.get("last_run_at")
            if last_run:
                try:
                    last_dt = datetime.fromisoformat(last_run)
                    next_dt = last_dt + timedelta(seconds=schedule_value)
                    delay = (next_dt - datetime.utcnow()).total_seconds()
                    return delay
                except (ValueError, TypeError):
                    pass
            # 从未运行或时间解析失败，立即执行
            return 5
        return schedule_value

    async def _wait_and_execute(self, task_id: int, delay: float):
        """等待 delay 秒后执行任务"""
        try:
            await asyncio.sleep(delay)
            if not self._running:
                return
            await self._execute(task_id)
        except asyncio.CancelledError:
            return
        except Exception as e:
            log.error("定时任务 %d 执行异常: %s", task_id, e)
        finally:
            # 无论成功失败都重新调度
            if self._running:
                task_row = await get_scheduled_task(task_id)
                if task_row and task_row.get("status") == "active":
                    self._schedule(task_row)

    async def _execute(self, task_id: int):
        """执行一个 scheduled_task：为每个 profile 创建 BenchTask 并行跑"""
        # 延迟导入避免循环依赖
        from server import manager, _run_benchmark_task
        import uuid

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

        # 检查并发限制
        from server import BenchTaskManager
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
            from server import CONNECTION_KEYS, _apply_env_overrides
            for k in CONNECTION_KEYS:
                if profile.get(k):
                    config[k] = profile[k]
            _apply_env_overrides(config)

            # 应用定时任务保存的 config 覆盖
            for key, val in configs_json.items():
                if val is not None:
                    config[key] = val

            # 确保 concurrency_levels 是整数列表
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

        # 等待所有 bench task 完成
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

        # 更新 run_count 和 last_run_at
        now_str = datetime.utcnow().isoformat()
        new_run_count = (task_row.get("run_count") or 0) + 1
        await update_scheduled_task(
            task_id,
            last_run_at=now_str,
            run_count=new_run_count,
        )
        log.info("定时任务 #%d 执行完成，累计 %d 次，本次保存 %d 条结果",
                 task_id, new_run_count, total_saved)
        log_bench("scheduler:complete", task_id=task_id,
                  run_count=new_run_count, results_saved=total_saved)
