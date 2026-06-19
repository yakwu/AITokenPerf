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

# 滑动窗口告警默认规则：
#   mode='time' → 最近 value 小时；'minute' → 最近 value 分钟；'count' → 每格取最近 value 轮
#   fail_consecutive   末尾连续坏轮 ≥ 此值 → 告警（抓硬故障）
#   fail_in_window     窗口内累计坏轮 ≥ 此值 → 告警（抓间歇抖动，容忍偶发）
#   recover_consecutive 告警中末尾连续好轮 ≥ 此值 且 窗口内坏轮 < fail_in_window → 恢复
#     （对称迟滞：触发看窗口整体健康度，恢复也要等窗口退烧，避免单次抖动反复横跳）
# 默认 30 分钟窗口：与拨测间隔解耦，改频率不影响窗口时长。
DEFAULT_ALERT_RULES = {
    "mode": "minute", "value": 30,
    "fail_consecutive": 2, "fail_in_window": 3, "recover_consecutive": 2,
}
_MIN_SAMPLES = 2   # 窗口内有效轮数不足则视为冷启动，不评估


def _load_rules(raw) -> dict:
    """读取 alert_rules（JSON 串）并与默认规则合并。空/非法一律回退默认。"""
    rules = dict(DEFAULT_ALERT_RULES)
    if not raw:
        return rules
    try:
        v = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return rules
    if isinstance(v, dict):
        for k in DEFAULT_ALERT_RULES:
            if v.get(k) is not None:
                rules[k] = v[k]
    return rules


def evaluate_window(rounds: list, prev_state: str,
                    rules: dict) -> Tuple[str, Optional[str], int]:
    """基于「坏轮序列」做滑动窗口判定。
    rounds: 旧→新 的 bool 序列（True=该轮成功率低于单轮健康线，即坏轮）。
    返回 (新状态, 动作, 窗口内坏轮数)。动作 ∈ {None, 'alert', 'recover'}。
    样本不足（< _MIN_SAMPLES）视为冷启动：保留旧态、不动作。"""
    fail_count = sum(1 for b in rounds if b)
    if len(rounds) < _MIN_SAMPLES:
        return prev_state, None, fail_count

    fc = int(rules.get("fail_consecutive", 2) or 2)
    fw = int(rules.get("fail_in_window", 3) or 3)
    rc = int(rules.get("recover_consecutive", 2) or 2)

    consec_fail = 0
    for b in reversed(rounds):
        if b:
            consec_fail += 1
        else:
            break
    consec_good = 0
    for b in reversed(rounds):
        if not b:
            consec_good += 1
        else:
            break

    if prev_state == ALERT_ALERTING:
        # 对称迟滞：连续好轮够 且 窗口已退烧（累计坏轮 < fw）才恢复，
        # 否则保持告警——避免老失败还压在窗口里时被单次抖动反复弹回。
        if consec_good >= rc and fail_count < fw:
            return ALERT_OK, "recover", fail_count          # 连续好 + 窗口退烧 → 恢复
        return ALERT_ALERTING, None, fail_count             # 保持告警，不重复发
    if consec_fail >= fc or fail_count >= fw:
        return ALERT_ALERTING, "alert", fail_count          # 连续坏 或 累计坏 → 告警
    return ALERT_OK, None, fail_count


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
    """解析单格状态，返回 (状态, 窗口内坏轮数)。
    n 字段在滑动窗口模型下表示「窗口内坏轮数」（仅供展示，判定每次从 results 实时重算）。
    兼容旧的裸字符串（"ok"/"alerting"）与 {"s": 状态, "n": 计数}。"""
    if isinstance(value, dict):
        state = value.get("s", ALERT_OK)
        try:
            fail_count = int(value.get("n", 0) or 0)
        except (TypeError, ValueError):
            fail_count = 0
        return (state if state in (ALERT_OK, ALERT_ALERTING) else ALERT_OK), fail_count
    if isinstance(value, str) and value in (ALERT_OK, ALERT_ALERTING):
        return value, 0
    return ALERT_OK, 0


def aggregate_active_alerts(tasks: list, valid_profiles: set | None = None) -> list:
    """把多个任务的 alert_state 聚合为"当前正在告警"的格子列表，按 (站点,模型) 合并。
    入参 tasks: get_scheduled_tasks() 返回的 dict 列表（含 alert_state/name/id/profile_ids）。
    valid_profiles: 若传入，仅保留仍存在的站点；过滤掉已删除站点遗留的告警格（自愈残留卡）。
                    默认 None = 不过滤。
    前置条件：每个 task 应含 id 字段（来自 get_scheduled_tasks 的主键，必非空）。
    出参: [{"profile","model","fail_count","task_count","tasks":[{"id","name"}]}, ...]，
    按 (profile, model) 排序，便于前端稳定渲染。
    fail_count = 该格当前窗口内的坏轮数（取所属任务中的最大值）。"""
    merged: dict = {}
    for t in tasks:
        states = _load_alert_states(t.get("alert_state"))
        for profile, models in states.items():
            if not isinstance(models, dict):
                continue
            if valid_profiles is not None and profile not in valid_profiles:
                continue
            for model, cellval in models.items():
                state, fail_count = _cell_state(cellval)
                if state != ALERT_ALERTING:
                    continue
                key = (profile, model)
                entry = merged.setdefault(key, {
                    "profile": profile, "model": model,
                    "fail_count": 0, "task_count": 0, "tasks": [],
                })
                entry["fail_count"] = max(entry["fail_count"], fail_count)
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
    cells: [(profile, model, metric, total), ...] —— 本轮新翻转的格子，total=窗口内有效轮数。
           alert  时 metric=窗口内坏轮数；recover 时 metric=末尾连续正常轮数。
    排版：按站点分组，站点名只写一次，组内每个模型占一行，手机上扫读最快。
    threshold: 单轮健康线（单次拨测成功率 < threshold% 记为一次失败）。
    base_url: 公开访问基址（如 https://app.aitokenperf.com），空则不加跳转按钮。"""
    n = len(cells)
    cell = f" · {cells[0][0]}/{cells[0][1]}" if cells else ""  # 首个异常的站点/模型，手机一眼定位
    label = f" · {task_name}" if task_name else ""
    if kind == "recover":
        template = color = "green"
        icon = "✅"
        title = f"✅ 已恢复{cell}{label}（{n} 个）"
        summary = f"以下 {n} 个站点/模型拨测已恢复稳定"
    else:
        template = color = "red"
        icon = "🔴"
        title = f"🔴 拨测告警{cell}{label}（{n} 个异常）"
        summary = (f"以下 {n} 个站点/模型近窗口内拨测失败次数超限"
                   f"（单次成功率 < {threshold}% 记为一次失败）")
    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**任务**：{task_name}"}},
        {"tag": "div", "text": {"tag": "lark_md", "content": summary}},
    ]
    # 按站点分组（保持 cells 原有顺序），站点名一行 + 组内各模型逐行
    grouped: list = []          # [(profile, [(model, metric, total), ...]), ...]
    index: dict = {}
    for profile, model, metric, total in cells:
        if profile not in index:
            index[profile] = len(grouped)
            grouped.append((profile, []))
        grouped[index[profile]][1].append((model, metric, total))
    for profile, rows in grouped:
        lines = [f"**站点 {profile}**"]
        for model, metric, total in rows:
            if kind == "recover":
                stat = f"已连续 <font color='{color}'>{metric}</font> 轮正常"
            else:
                stat = f"失败 <font color='{color}'>{metric}/{total}</font> 轮"
            lines.append(f"{icon} {model} · {stat}")
        elements.append({"tag": "div",
                         "text": {"tag": "lark_md", "content": "\n".join(lines)}})
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
