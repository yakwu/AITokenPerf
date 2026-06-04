#!/usr/bin/env python3
"""告警通知模块：状态机判定 + 飞书卡片 + webhook 发送（SSRF 限飞书域名）。"""

import logging
from typing import Optional, Tuple
from urllib.parse import urlparse

import aiohttp

log = logging.getLogger("notifier")

ALERT_OK = "ok"
ALERT_ALERTING = "alerting"
FEISHU_ALLOWED_HOSTS = {"open.feishu.cn", "open.larksuite.com"}


def evaluate_alert(prev_state: str, success_rate: float, threshold: int) -> Tuple[str, Optional[str]]:
    """返回 (新状态, 动作)。动作 ∈ {None, 'alert', 'recover'}。仅状态翻转时给动作。"""
    abnormal = success_rate < threshold
    if abnormal and prev_state != ALERT_ALERTING:
        return ALERT_ALERTING, "alert"
    if not abnormal and prev_state == ALERT_ALERTING:
        return ALERT_OK, "recover"
    return prev_state, None
