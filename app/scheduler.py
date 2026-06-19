#!/usr/bin/env python3
"""定时任务调度器 — 全局单循环 + next_run_at 绝对时间调度 + DB 分布式锁"""

import asyncio
import json
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone

from app.db import (
    get_all_active_scheduled_tasks,
    get_due_scheduled_tasks,
    get_scheduled_task,
    update_scheduled_task,
    get_profiles,
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
        self._retention_loop: asyncio.Task | None = None

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
        self._retention_loop = asyncio.create_task(self._run_retention())
        log.info("调度器已启动，加载 %d 个活跃任务", len(tasks))

    async def stop(self):
        """服务停止时，取消全局循环和所有子任务"""
        self._running = False
        if self._retention_loop:
            self._retention_loop.cancel()
            try:
                await self._retention_loop
            except asyncio.CancelledError:
                pass
            self._retention_loop = None
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

    async def _run_retention(self):
        """数据保留循环：定期删除过期 results，防止表无界膨胀（issue #25）。

        启动后先短暂延迟再首次清理，之后每 interval 一次。先清理后 sleep
        可保证频繁重启（如每次发版）的部署也能真正跑到清理，而不是等满一个周期。
        """
        from app.db import delete_results_older_than
        import app.config as _cfg
        # 启动初次延迟，避开启动期初始化高峰
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            return
        while self._running:
            try:
                days = _cfg.RESULTS_RETENTION_DAYS
                if days > 0:
                    deleted = await delete_results_older_than(days)
                    if deleted:
                        log.info("数据保留：删除 %d 条超过 %d 天的历史结果", deleted, days)
            except Exception as e:
                log.error("数据保留清理异常: %s", e)
            try:
                await asyncio.sleep(_cfg.RESULTS_RETENTION_INTERVAL)
            except asyncio.CancelledError:
                return

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

async def _maybe_send_alert(task_id: int, task_row: dict, run_ids: list):
    """按 (站点,模型) 在滑动窗口内数坏轮，逐格状态翻转，聚合成红/绿卡发送。全程不抛。

    单轮健康线 = alert_threshold（单次成功率 < 此值记为一次失败）；
    告警规则 = alert_rules（连续坏轮 / 窗口内累计坏轮 / 恢复连续好轮）。"""
    from app.db import (
        get_run_success_rate_by_cell, get_task_window_rounds_by_cell, get_notifier,
    )
    from app.notifier import (
        evaluate_window, build_feishu_card, send_webhook,
        _load_alert_states, _cell_state, _load_rules, ALERT_ALERTING,
    )
    from app.config import APP_PUBLIC_URL

    notifier_id = task_row.get("alert_notifier_id") or 0
    if not task_row.get("alert_enabled") or not notifier_id:
        return  # 未开启 或 未选告警器：不发、不报错
    ntf = await get_notifier(notifier_id)
    webhook = (ntf or {}).get("webhook", "").strip()
    if not webhook:
        log.info("定时任务 #%d 告警器缺失或 webhook 空，跳过告警", task_id)
        return

    # 本轮出现的格子集合（只评估这些，避免对已消失的格子误判）
    cells = await get_run_success_rate_by_cell(run_ids)
    if not cells:
        log.info("定时任务 #%d 本轮无有效请求，跳过告警评估", task_id)
        return

    threshold = int(task_row.get("alert_threshold") or 90)
    rules = _load_rules(task_row.get("alert_rules"))
    mode = rules.get("mode", "time")
    value = int(rules.get("value", 1) or 1)
    # 各格窗口内坏轮序列（含本轮，本轮结果已落库）
    windows = await get_task_window_rounds_by_cell(task_id, threshold, mode, value)

    prev = _load_alert_states(task_row.get("alert_state"))
    new_states: dict = {}
    alerts, recovers = [], []
    for (profile, model) in cells:
        rounds = windows.get((profile, model), [])
        p_state, _ = _cell_state(prev.get(profile, {}).get(model))
        n_state, action, fail_count = evaluate_window(rounds, p_state, rules)
        new_states.setdefault(profile, {})[model] = {"s": n_state, "n": fail_count}
        total = len(rounds)
        if action == "alert":
            alerts.append((profile, model, fail_count, total))
        elif action == "recover":
            # 恢复卡展示末尾连续正常轮数（坏轮序列尾部连续 False 的个数）
            consec_good = 0
            for b in reversed(rounds):
                if b:
                    break
                consec_good += 1
            recovers.append((profile, model, consec_good, total))

    # 本轮未出现但仍在告警的旧格子：保留状态，避免临时跳过（如容量不足）丢失告警
    for profile, models in prev.items():
        if not isinstance(models, dict):
            continue
        for model, cellval in models.items():
            if model in new_states.get(profile, {}):
                continue
            st, fc = _cell_state(cellval)
            if st == ALERT_ALERTING:
                latest = windows.get((profile, model))   # 窗口内仍有数据则刷新失败数
                if latest:
                    fc = sum(1 for b in latest if b)
                new_states.setdefault(profile, {})[model] = {"s": st, "n": fc}

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    name = task_row.get("name", "")
    if alerts:
        await send_webhook(webhook, build_feishu_card("alert", name, alerts, threshold, ts, base_url=APP_PUBLIC_URL))
    if recovers:
        await send_webhook(webhook, build_feishu_card("recover", name, recovers, threshold, ts, base_url=APP_PUBLIC_URL))

    if new_states != prev:
        await update_scheduled_task(
            task_id, alert_state=json.dumps(new_states, ensure_ascii=False))


async def _run_scheduled_task(task_id: int):
    """执行一个定时任务：为每个 profile 并行跑 benchmark"""
    from app.config import RUN_MAX_GLOBAL_SLOTS, RUN_MAX_USER_SLOTS
    from app.server import (
        RunCapacityError,
        _normalize_concurrency_levels,
        _start_run_for_profile,
        manager,
    )

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

    # 轻量检查通过后，才做较重的 DB 查询
    profile_ids = task_row.get("profile_ids", [])
    configs_json = task_row.get("configs", {})

    profiles = await get_profiles(user_id)
    profile_map = {p["name"]: p for p in profiles}

    log.info("执行定时任务 #%d '%s'，%d 个 profile", task_id, task_row["name"], len(profile_ids))
    log_bench("scheduler:start", task_id=task_id, name=task_row["name"],
              profiles=profile_ids, user_id=user_id)

    run_plans = []
    total_requested_slots = 0
    levels, _ = _normalize_concurrency_levels(configs_json.get("concurrency_levels"))

    # 先做整组容量预检：容量不足则整个定时任务跳过，不启动部分模型。
    for pname in profile_ids:
        profile = profile_map.get(pname)
        if not profile:
            log.warning("定时任务 #%d: profile '%s' 不存在", task_id, pname)
            log_error("scheduler:profile_missing", error=f"Profile '{pname}' not found",
                      task_id=task_id, profile=pname)
            continue

        models = configs_json.get("models") or []
        if not models:
            raw_model = configs_json.get("model") or ""
            models = [raw_model] if raw_model else []
        if not models:
            models = profile.get("models", [])
        if not models:
            log_warning = f"profile '{pname}' 未绑定模型"
            log.warning("定时任务 #%d: %s，跳过", task_id, log_warning)
            log_error("scheduler:config_missing", error=log_warning, task_id=task_id, profile=pname)
            continue

        body = dict(configs_json)
        body["models"] = models
        body["concurrency_levels"] = levels
        run_plans.append((profile, body))
        total_requested_slots += len(models) * max(levels)

    available_slots = min(
        RUN_MAX_USER_SLOTS - manager.get_running_slots(user_id),
        RUN_MAX_GLOBAL_SLOTS - manager.get_running_slots(),
    )
    if total_requested_slots > available_slots:
        log.warning("定时任务 #%d 容量不足，跳过: requested=%d available=%d",
                    task_id, total_requested_slots, max(0, available_slots))
        log_error("scheduler:skipped_capacity",
                  error="并发容量不足",
                  task_id=task_id,
                  requested_slots=total_requested_slots,
                  available_slots=max(0, available_slots))
        return

    bench_tasks = []
    run_ids = []

    for profile, body in run_plans:
        try:
            result = await _start_run_for_profile(
                user_id=user_id,
                profile=profile,
                body=body,
                source="scheduled",
                scheduled_task_id=task_id,
            )
        except RunCapacityError as e:
            log.warning("定时任务 #%d 容量不足，跳过: requested=%d available=%d",
                        task_id, e.requested_slots, e.available_slots)
            log_error("scheduler:skipped_capacity", error="并发容量不足",
                      task_id=task_id, requested_slots=e.requested_slots,
                      available_slots=e.available_slots)
            return
        if result.get("error"):
            log_error("scheduler:run_create_failed", error=result["error"], task_id=task_id)
            continue
        run_ids.append(result["run_id"])
        bench_tasks.extend(manager.get_run_tasks(result["run_id"]))

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

    # 失败告警评估（best-effort，绝不影响主流程）
    try:
        await _maybe_send_alert(task_id, task_row, run_ids)
    except Exception as e:
        log.error("定时任务 #%d 告警评估失败: %s", task_id, e)
        log_error("scheduler:alert_error", error=str(e), task_id=task_id)
