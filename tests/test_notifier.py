import json

import pytest

from app import notifier
from app.notifier import (
    build_feishu_card, evaluate_window, is_allowed_webhook,
    DEFAULT_ALERT_RULES, _load_rules,
)

R = DEFAULT_ALERT_RULES   # 默认 fail_consecutive=2, fail_in_window=3, recover_consecutive=2


# ---- evaluate_window：滑动窗口失败计数判定 ----

def test_cold_start_under_min_samples_no_action():
    # 样本不足（<2）：保留旧态，不动作
    assert evaluate_window([True], "ok", R) == ("ok", None, 1)
    assert evaluate_window([], "ok", R) == ("ok", None, 0)


def test_consecutive_two_fails_alert():
    assert evaluate_window([True, True], "ok", R) == ("alerting", "alert", 2)


def test_intermittent_three_in_window_alert():
    # 坏好坏好坏：不连续但累计 3 → 告警
    assert evaluate_window([True, False, True, False, True], "ok", R) == ("alerting", "alert", 3)


def test_two_non_consecutive_not_alert():
    # 累计 2 个且不连续：容忍，不告警
    assert evaluate_window([True, False, True, False], "ok", R) == ("ok", None, 2)


def test_keeps_alerting_no_repeat():
    assert evaluate_window([True, True], "alerting", R) == ("alerting", None, 2)


def test_recover_needs_two_consecutive_good():
    assert evaluate_window([True, True, False, False], "alerting", R) == ("ok", "recover", 2)


def test_recover_one_good_not_enough():
    assert evaluate_window([True, True, False], "alerting", R) == ("alerting", None, 2)


def test_all_good_no_action():
    assert evaluate_window([False, False], "ok", R) == ("ok", None, 0)


def test_custom_rules():
    rules = {"fail_consecutive": 3, "fail_in_window": 99, "recover_consecutive": 1}
    assert evaluate_window([True, True], "ok", rules) == ("ok", None, 2)
    assert evaluate_window([True, True, True], "ok", rules) == ("alerting", "alert", 3)
    # recover_consecutive=1：一次好即恢复
    assert evaluate_window([True, True, False], "alerting", rules) == ("ok", "recover", 2)


# ---- _load_rules ----

def test_load_rules_default_on_empty():
    assert _load_rules("") == DEFAULT_ALERT_RULES
    assert _load_rules(None) == DEFAULT_ALERT_RULES


def test_load_rules_merges_partial():
    r = _load_rules('{"mode": "count", "value": 20}')
    assert r["mode"] == "count" and r["value"] == 20
    assert r["fail_consecutive"] == 2 and r["fail_in_window"] == 3   # 缺省补全


def test_load_rules_garbage_falls_back():
    assert _load_rules("not json") == DEFAULT_ALERT_RULES
    assert _load_rules("[1,2]") == DEFAULT_ALERT_RULES


def test_load_rules_accepts_dict():
    r = _load_rules({"value": 6})
    assert r["value"] == 6 and r["mode"] == "minute"   # 默认窗口为 分钟/30


def test_default_window_is_30_minutes():
    assert DEFAULT_ALERT_RULES["mode"] == "minute"
    assert DEFAULT_ALERT_RULES["value"] == 30


# ---- _cell_state（解析不变，n 语义=窗口失败数）----

def test_cell_state_legacy_string():
    from app.notifier import _cell_state
    assert _cell_state("ok") == ("ok", 0)
    assert _cell_state("alerting") == ("alerting", 0)


def test_cell_state_new_dict():
    from app.notifier import _cell_state
    assert _cell_state({"s": "ok", "n": 1}) == ("ok", 1)
    assert _cell_state({"s": "alerting", "n": 3}) == ("alerting", 3)


def test_cell_state_missing_or_garbage():
    from app.notifier import _cell_state
    assert _cell_state(None) == ("ok", 0)
    assert _cell_state({}) == ("ok", 0)
    assert _cell_state("weird") == ("ok", 0)
    assert _cell_state({"s": "weird", "n": "x"}) == ("ok", 0)


# ---- SSRF 白名单 ----

def test_feishu_https_allowed():
    assert is_allowed_webhook("https://open.feishu.cn/open-apis/bot/v2/hook/xxx") is True


def test_larksuite_allowed():
    assert is_allowed_webhook("https://open.larksuite.com/open-apis/bot/v2/hook/xxx") is True


def test_http_rejected():
    assert is_allowed_webhook("http://open.feishu.cn/x") is False


def test_localhost_rejected():
    assert is_allowed_webhook("https://localhost/x") is False


def test_internal_ip_rejected():
    assert is_allowed_webhook("https://169.254.169.254/latest/meta-data") is False


def test_other_domain_rejected():
    assert is_allowed_webhook("https://evil.com/x") is False


def test_empty_rejected():
    assert is_allowed_webhook("") is False


# ---- 飞书卡片（cells 为 (profile, model, fail_count, total)）----

def test_alert_card_red_header():
    card = build_feishu_card("alert", "主力渠道",
                             [("OpenAI-A", "gpt-4o", 3, 12), ("OpenAI-B", "claude", 5, 12)],
                             90, "2026-06-09 10:30")
    assert card["msg_type"] == "interactive"
    assert card["card"]["config"]["wide_screen_mode"] is True
    assert card["card"]["header"]["template"] == "red"
    title = card["card"]["header"]["title"]["content"]
    assert "告警" in title and "主力渠道" in title and "2 个异常" in title
    assert "OpenAI-A/gpt-4o" in title          # 首个异常的站点×模型进标题
    flat = str(card)
    assert "OpenAI-A" in flat and "gpt-4o" in flat and "3/12" in flat
    assert "OpenAI-B" in flat and "claude" in flat and "5/12" in flat
    assert "< 90%" in flat                      # 汇总行带单轮健康线


def test_recover_card_green_header():
    card = build_feishu_card("recover", "主力渠道",
                             [("OpenAI-A", "gpt-4o", 0, 12)], 90, "2026-06-09 10:30")
    assert card["card"]["header"]["template"] == "green"
    title = card["card"]["header"]["title"]["content"]
    assert "恢复" in title and "主力渠道" in title and "1 个" in title
    assert "OpenAI-A/gpt-4o" in title
    flat = str(card)
    assert "OpenAI-A" in flat and "gpt-4o" in flat


def test_card_title_handles_empty_task_name():
    card = build_feishu_card("alert", "", [("S", "m", 2, 5)], 90, "t")
    title = card["card"]["header"]["title"]["content"]
    assert title.startswith("🔴 拨测告警 · S/m")   # 站点×模型进标题
    assert "1 个异常" in title
    assert " ·  · " not in title                   # 空任务名不留悬空分隔符


@pytest.mark.asyncio
async def test_send_webhook_rejects_ssrf():
    assert await notifier.send_webhook("https://evil.com/x", {"a": 1}) is False


@pytest.mark.asyncio
async def test_send_webhook_success(monkeypatch):
    class FakeResp:
        status = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
    class FakeSession:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def post(self, *a, **k): return FakeResp()
    monkeypatch.setattr(notifier.aiohttp, "ClientSession", FakeSession)
    assert await notifier.send_webhook("https://open.feishu.cn/open-apis/bot/v2/hook/x", {"a": 1}) is True


@pytest.mark.asyncio
async def test_send_webhook_non_2xx_returns_false(monkeypatch):
    class FakeResp:
        status = 500
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
    class FakeSession:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def post(self, *a, **k): return FakeResp()
    monkeypatch.setattr(notifier.aiohttp, "ClientSession", FakeSession)
    assert await notifier.send_webhook("https://open.feishu.cn/x", {"a": 1}) is False


def test_load_alert_states_valid_json():
    from app.notifier import _load_alert_states
    assert _load_alert_states('{"SiteA": {"gpt-4o": "alerting"}}') == {"SiteA": {"gpt-4o": "alerting"}}


def test_load_alert_states_legacy_scalar():
    from app.notifier import _load_alert_states
    assert _load_alert_states("ok") == {}
    assert _load_alert_states("alerting") == {}


def test_load_alert_states_empty_or_none():
    from app.notifier import _load_alert_states
    assert _load_alert_states("") == {}
    assert _load_alert_states(None) == {}


def test_load_alert_states_non_dict_json():
    from app.notifier import _load_alert_states
    assert _load_alert_states('"ok"') == {}
    assert _load_alert_states("123") == {}
    assert _load_alert_states("[1, 2]") == {}


def test_feishu_card_includes_link_when_base_url_given():
    card = build_feishu_card("alert", "任务A", [("siteX", "gpt-4", 3, 12)],
                             90, "2026-06-14 10:00:00", base_url="https://app.aitokenperf.com")
    blob = json.dumps(card, ensure_ascii=False)
    assert "https://app.aitokenperf.com/sites/siteX" in blob


def test_feishu_card_no_link_when_base_url_absent():
    card = build_feishu_card("alert", "任务A", [("siteX", "gpt-4", 3, 12)],
                             90, "2026-06-14 10:00:00")
    blob = json.dumps(card, ensure_ascii=False)
    assert "/sites/" not in blob


def test_feishu_card_link_encodes_special_chars():
    card = build_feishu_card("alert", "", [("site/A?x=1", "m", 1, 12)],
                             90, "2026-06-14 00:00:00", base_url="https://h.example.com")
    blob = json.dumps(card, ensure_ascii=False)
    assert "site%2FA%3Fx%3D1" in blob
