#!/usr/bin/env python3
"""一次性迁移：把旧的「1 小时」告警窗口统一改为「30 分钟」。

背景见 issue #98。默认窗口由 小时/1 改为 分钟/30 后，存量任务里显式写着旧窗口的需要刷一遍：
  - mode='count' value=12  （5 分钟一拨 × 12 = 1 小时的写法）
  - mode='time'  value=1   （老默认 1 小时）
统一改成 mode='minute' value=30。其余字段（fail_* / recover_*）保持不变。
空 alert_rules 走新默认自动变 30 分钟，无需处理。

幂等：再次运行不会有可迁移项。alert_rules 是纯 TEXT JSON，UPDATE 走参数绑定，
sqlite / Postgres 通用。
"""

import asyncio
import json

import app.config  # noqa: F401  —— 触发 DB 配置加载
from sqlalchemy import text

from app.db import engine

# 视为「旧 1 小时窗口」的写法 → 一律改为 minute/30
_OLD_ONE_HOUR = {("count", 12), ("time", 1)}
_NEW = {"mode": "minute", "value": 30}


def _migrate_rules(raw: str):
    """返回迁移后的 JSON 字符串；无需迁移则返回 None。"""
    if not raw:
        return None
    try:
        rules = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(rules, dict):
        return None
    key = (rules.get("mode"), rules.get("value"))
    if key not in _OLD_ONE_HOUR:
        return None
    rules = {**rules, **_NEW}
    return json.dumps(rules, ensure_ascii=False)


async def main():
    print("alert window migration: 旧 1 小时窗口 → 30 分钟")
    changed = 0
    async with engine.begin() as conn:
        cur = await conn.execute(
            text("SELECT id, name, alert_rules FROM scheduled_tasks"))
        rows = cur.fetchall()
        for task_id, name, raw in rows:
            new_raw = _migrate_rules(raw)
            if new_raw is None:
                continue
            await conn.execute(
                text("UPDATE scheduled_tasks SET alert_rules=:r WHERE id=:id"),
                {"r": new_raw, "id": task_id})
            changed += 1
            print(f"  #{task_id} {name!r}: {raw} → {new_raw}")
    print(f"done. 共迁移 {changed} 个任务。")


if __name__ == "__main__":
    asyncio.run(main())
