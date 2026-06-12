#!/usr/bin/env python3
"""告警通知模块：状态机判定 + 飞书卡片 + webhook 发送（SSRF 限飞书域名）。"""

import json
import logging
from typing import Optional, Tuple
from urllib.parse import urlparse

import aiohttp

log = logging.getLogger("notifier")

ALERT_OK = "ok"
ALERT_ALERTING = "alerting"
FEISHU_ALLOWED_HOSTS = {"open.feishu.cn", "open.larksuite.com"}


def evaluate_alert(prev_state: str, prev_streak: int, success_rate: float,
                   threshold: int, fail_needed: int = 2) -> Tuple[str, int, Optional[str]]:
    """连续 fail_needed 次低于阈值才告警；恢复 1 次回到阈值即报（防抖）。
    返回 (新状态, 新连续异常计数, 动作)。动作 ∈ {None, 'alert', 'recover'}。"""
    abnormal = success_rate < threshold
    if abnormal:
        if prev_state == ALERT_ALERTING:
            return ALERT_ALERTING, prev_streak, None      # 已在告警，保持不重复发
        streak = prev_streak + 1
        if streak >= fail_needed:
            return ALERT_ALERTING, streak, "alert"        # 连续达标，翻红告警
        return ALERT_OK, streak, None                     # 仍在累积，先不发
    if prev_state == ALERT_ALERTING:
        return ALERT_OK, 0, "recover"                     # 一次回到阈值即恢复
    return ALERT_OK, 0, None                              # 一直正常


def _load_alert_states(raw) -> dict:
    """读取 alert_state：合法 JSON dict 原样返回；裸值/空/非 dict 一律视为空（存量兼容）。"""
    if not raw:
        return {}
    try:
        v = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return v if isinstance(v, dict) else {}


def _cell_state(value) -> Tuple[str, int]:
    """解析单格状态，返回 (状态, 连续异常计数)。
    兼容旧的裸字符串（"ok"/"alerting"）与新的 {"s": 状态, "n": 连续计数}。"""
    if isinstance(value, dict):
        state = value.get("s", ALERT_OK)
        try:
            streak = int(value.get("n", 0) or 0)
        except (TypeError, ValueError):
            streak = 0
        return (state if state in (ALERT_OK, ALERT_ALERTING) else ALERT_OK), streak
    if isinstance(value, str) and value in (ALERT_OK, ALERT_ALERTING):
        return value, 0
    return ALERT_OK, 0


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


def build_feishu_card(kind: str, task_name: str,
                      cells: list, threshold: int, ts: str) -> dict:
    """构造飞书自定义机器人 interactive 卡片。kind ∈ {'alert','recover'}。
    cells: [(profile, model, rate), ...] —— 本轮新翻转的格子。"""
    n = len(cells)
    label = f" · {task_name}" if task_name else ""
    if kind == "recover":
        template = color = "green"
        title = f"✅ 已恢复{label}（{n} 个）"
        summary = f"以下 {n} 个格子已恢复（成功率 ≥ 阈值 {threshold}%）"
    else:
        template = color = "red"
        title = f"🔴 拨测告警{label}（{n} 个异常）"
        summary = f"本轮 {n} 个格子成功率低于阈值 {threshold}%"
    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**任务**：{task_name}"}},
        {"tag": "div", "text": {"tag": "lark_md", "content": summary}},
    ]
    for profile, model, rate in cells:
        elements.append({"tag": "div", "fields": [
            {"is_short": True, "text": {"tag": "lark_md", "content": f"**站点**\n{profile}"}},
            {"is_short": True, "text": {"tag": "lark_md", "content": f"**模型**\n{model}"}},
            {"is_short": True, "text": {"tag": "lark_md",
                "content": f"**成功率**\n<font color='{color}'>{rate:.1f}%</font>"}},
        ]})
    elements.append({"tag": "hr"})
    elements.append({"tag": "note", "elements": [
        {"tag": "lark_md", "content": f"{ts} · AITokenPerf"}]})
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"template": template,
                       "title": {"tag": "plain_text", "content": title}},
            "elements": elements,
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
