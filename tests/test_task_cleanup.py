"""测试 BenchTaskManager.cleanup_idle —— 防止已完成任务/run 在内存中无界堆积。

回归 issue #24：cleanup_idle 此前从未被调用，且不清理 _runs，导致常驻数月后 OOM。
"""

import pytest

from app.server import BenchTaskManager


def _make_finished_task(mgr: BenchTaskManager, task_id: str, run_id: str,
                        finished_at: float):
    """构造一个已完成（idle + 无 asyncio_task + 带 finished_at）的任务。"""
    task = mgr.create_task(task_id, owner_id=1, run_id=run_id, group_id=run_id)
    task.status = "idle"
    task.asyncio_task = None
    task.finished_at = finished_at
    return task


def test_cleanup_removes_finished_task_and_orphan_run():
    """已完成的任务及其孤儿 run 应被清理。"""
    mgr = BenchTaskManager()
    mgr.create_run("run-1", owner_id=1)
    _make_finished_task(mgr, "task-1", "run-1", finished_at=100.0)

    # grace=0、now 远大于 finished_at → 应清理
    mgr.cleanup_idle(grace_seconds=0.0, now=1000.0)

    assert mgr.get_task("task-1") is None, "已完成任务应被移除"
    assert mgr.get_run("run-1") is None, "孤儿 run 应被移除"


def test_cleanup_respects_grace_period():
    """grace 窗口内刚完成的任务不应被误删（可能仍被 SSE 查看）。"""
    mgr = BenchTaskManager()
    mgr.create_run("run-1", owner_id=1)
    _make_finished_task(mgr, "task-1", "run-1", finished_at=1000.0)

    # now 距 finished_at 仅 10s，grace=1800s → 不应清理
    mgr.cleanup_idle(grace_seconds=1800.0, now=1010.0)

    assert mgr.get_task("task-1") is not None, "grace 内的任务不应被删"
    assert mgr.get_run("run-1") is not None, "其 run 也应保留"

    # 超过 grace 后应被清理
    mgr.cleanup_idle(grace_seconds=1800.0, now=1000.0 + 1801.0)
    assert mgr.get_task("task-1") is None
    assert mgr.get_run("run-1") is None


def test_cleanup_keeps_running_task_and_run():
    """运行中的任务（有 asyncio_task / 非 idle）及其 run 必须保留。"""
    mgr = BenchTaskManager()
    mgr.create_run("run-1", owner_id=1)
    task = mgr.create_task("task-1", owner_id=1, run_id="run-1", group_id="run-1")
    task.status = "running"  # 运行中

    mgr.cleanup_idle(grace_seconds=0.0, now=10_000.0)

    assert mgr.get_task("task-1") is not None, "运行中的任务不能删"
    assert mgr.get_run("run-1") is not None, "有活跃任务的 run 不能删"


def test_cleanup_keeps_never_started_task():
    """从未运行（finished_at==0）的 idle 任务不删，避免误删刚创建待启动的任务。"""
    mgr = BenchTaskManager()
    mgr.create_run("run-1", owner_id=1)
    task = mgr.create_task("task-1", owner_id=1, run_id="run-1", group_id="run-1")
    task.status = "idle"
    task.asyncio_task = None
    # finished_at 保持默认 0.0

    mgr.cleanup_idle(grace_seconds=0.0, now=10_000.0)

    assert mgr.get_task("task-1") is not None, "未完成（finished_at==0）的任务不应被删"


def test_cleanup_mixed_only_removes_eligible():
    """混合场景：只清理符合条件的，保留其余。"""
    mgr = BenchTaskManager()
    mgr.create_run("run-done", owner_id=1)
    mgr.create_run("run-live", owner_id=1)
    _make_finished_task(mgr, "t-done", "run-done", finished_at=100.0)
    live = mgr.create_task("t-live", owner_id=1, run_id="run-live", group_id="run-live")
    live.status = "running"

    mgr.cleanup_idle(grace_seconds=0.0, now=5000.0)

    assert mgr.get_task("t-done") is None
    assert mgr.get_run("run-done") is None
    assert mgr.get_task("t-live") is not None
    assert mgr.get_run("run-live") is not None
