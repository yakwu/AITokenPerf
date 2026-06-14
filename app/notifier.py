#!/usr/bin/env python3
"""告警通知模块：状态机判定 + 飞书卡片 + webhook 发送（SSRF 限飞书域名）。"""

import json
import logging
from typing import Optional, Tuple
from urllib.parse import urlparse, quote

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


def aggregate_active_alerts(tasks: list) -> list:
    """把多个任务的 alert_state 聚合为"当前正在告警"的格子列表，按 (站点,模型) 合并。
    入参 tasks: get_scheduled_tasks() 返回的 dict 列表（含 alert_state/name/id/profile_ids）。
    前置条件：每个 task 应含 id 字段（来自 get_scheduled_tasks 的主键，必非空）。
    出参: [{"profile","model","streak","task_count","tasks":[{"id","name"}]}, ...]，
    按 (profile, model) 排序，便于前端稳定渲染。"""
    merged: dict = {}
    for t in tasks:
        states = _load_alert_states(t.get("alert_state"))
        for profile, models in states.items():
            if not isinstance(models, dict):
                continue
            for model, cellval in models.items():
                state, streak = _cell_state(cellval)
                if state != ALERT_ALERTING:
                    continue
                key = (profile, model)
                entry = merged.setdefault(key, {
                    "profile": profile, "model": model,
                    "streak": 0, "task_count": 0, "tasks": [],
                })
                entry["streak"] = max(entry["streak"], streak)
                entry["tasks"].append({"id": t.get("id"), "name": t.get("name", "")})
    out = []
    for (profile, model), entry in sorted(merged.items()):
        entry["task_count"] = len(entry["tasks"])
        out.append(entry)
    return out


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
                      cells: list, threshold: int, ts: str,
                      base_url: str = "") -> dict:
    """构造飞书自定义机器人 interactive 卡片。kind ∈ {'alert','recover'}。
    cells: [(profile, model, rate), ...] —— 本轮新翻转的格子。
    base_url: 公开访问基址（如 https://app.aitokenperf.com），空则不加跳转按钮。"""
    n = len(cells)
    cell = f" · {cells[0][0]}/{cells[0][1]}" if cells else ""  # 首个异常的站点/模型，手机一眼定位
    label = f" · {task_name}" if task_name else ""
    if kind == "recover":
        template = color = "green"
        title = f"✅ 已恢复{cell}{label}（{n} 个）"
        summary = f"以下 {n} 个格子已恢复（成功率 ≥ 阈值 {threshold}%）"
    else:
        template = color = "red"
        title = f"🔴 拨测告警{cell}{label}（{n} 个异常）"
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
    if base_url and cells:
        base_url = base_url.rstrip("/")
        site = quote(str(cells[0][0]), safe="")
        elements.append({"tag": "action", "actions": [{
            "tag": "button",
            "text": {"tag": "plain_text", "content": "进站点查看 →"},
            "type": "primary",
            "url": f"{base_url}/sites/{site}",
        }]})
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
