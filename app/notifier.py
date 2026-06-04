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


def _safe_host(url: str) -> str:
    """日志脱敏：只取 host，绝不打印含 secret 的完整 URL。"""
    try:
        return urlparse(url).hostname or "?"
    except Exception:
        return "?"


def is_allowed_webhook(url: str) -> bool:
    """SSRF 防护：仅允许 https 的飞书域名。其余一律拒绝。"""
    if not url:
        return False
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme != "https":
        return False
    return p.hostname in FEISHU_ALLOWED_HOSTS


def build_feishu_card(kind: str, task_name: str, profile: str,
                      rate: float, threshold: int, ts: str) -> dict:
    """构造飞书自定义机器人 interactive 卡片。kind ∈ {'alert','recover'}。"""
    if kind == "recover":
        template, title, color = "green", "✅ 已恢复", "green"
    else:
        template, title, color = "red", "🔴 拨测告警", "red"
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"template": template,
                       "title": {"tag": "plain_text", "content": title}},
            "elements": [
                {"tag": "div", "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**任务**\n{task_name}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**站点**\n{profile}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**成功率**\n<font color='{color}'>{rate:.1f}%</font>"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**阈值**\n{threshold}%"}},
                ]},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "lark_md", "content": f"⏰ {ts} · AITokenPerf"}]},
            ],
        },
    }


async def send_webhook(url: str, payload: dict, timeout: float = 10.0) -> bool:
    """best-effort 发送 webhook。先 SSRF 校验；失败只 log（不含完整 URL）、返回 False、不抛。"""
    if not is_allowed_webhook(url):
        log.warning("拒绝非法 webhook 目标 host=%s", _safe_host(url))
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status // 100 == 2:
                    return True
                log.warning("webhook 推送失败 host=%s status=%s", _safe_host(url), resp.status)
                return False
    except Exception as e:
        log.warning("webhook 推送异常 host=%s err=%s", _safe_host(url), type(e).__name__)
        return False
