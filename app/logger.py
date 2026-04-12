#!/usr/bin/env python3
"""结构化日志模块 — JSONL 格式写入文件或 stdout"""

import contextvars
import json
import logging
import os
import sys
import time
from pathlib import Path

# ── 日志关联 ID ──────────────────────────────────────────
current_run_id: contextvars.ContextVar[str] = contextvars.ContextVar("run_id", default="-")

from app.config import LOG_MODE

LOG_DIR = Path(os.environ.get("LOG_DIR", "data/logs"))
LOG_FILE = LOG_DIR / "app.log"


class RunIdFormatter(logging.Formatter):
    """自动注入 run_id 的日志 formatter"""

    def format(self, record):
        record.run_id = current_run_id.get()
        return super().format(record)


def _write(level: str, event: str, **kwargs):
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "run_id": current_run_id.get(),
        "level": level,
        "event": event,
        **kwargs,
    }
    line = json.dumps(entry, ensure_ascii=False)

    if LOG_MODE == "stdout":
        print(line, file=sys.stdout)
        return

    # 文件模式（默认）
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def log_access(method: str, path: str, status: int, ip: str, duration_ms: float):
    _write("info", "access", method=method, path=path, status=status, ip=ip,
           duration_ms=round(duration_ms, 2))


def log_bench(event: str, **kwargs):
    _write("info", event, **kwargs)


def log_error(event: str, error: str, **kwargs):
    _write("error", event, error=error, **kwargs)


def log_security(event: str, **kwargs):
    _write("warn", event, **kwargs)
