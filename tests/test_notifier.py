import pytest

from app import notifier
from app.notifier import build_feishu_card, evaluate_alert, is_allowed_webhook


def test_first_abnormal_no_alert_increments_streak():
    # 第一次低于阈值：不告警，仅累积 streak
    assert evaluate_alert("ok", 0, 72.0, 90) == ("ok", 1, None)


def test_second_consecutive_abnormal_fires():
    # 连续第二次低于阈值：翻红告警
    assert evaluate_alert("ok", 1, 72.0, 90) == ("alerting", 2, "alert")


def test_no_repeat_while_abnormal():
    # 已告警继续异常：保持，不重复发
    assert evaluate_alert("alerting", 2, 50.0, 90) == ("alerting", 2, None)


def test_recover_on_abnormal_to_ok():
    # 告警中一次回到阈值即报恢复，并清零
    assert evaluate_alert("alerting", 2, 95.0, 90) == ("ok", 0, "recover")


def test_single_normal_resets_streak():
    # 累积中(streak=1)遇到一次正常：清零，不告警
    assert evaluate_alert("ok", 1, 99.0, 90) == ("ok", 0, None)


def test_no_action_while_ok():
    assert evaluate_alert("ok", 0, 99.0, 90) == ("ok", 0, None)


def test_threshold_boundary_is_normal():
    # 等于阈值不算异常，且清零
    assert evaluate_alert("ok", 1, 90.0, 90) == ("ok", 0, None)


def test_custom_fail_needed_three():
    # fail_needed=3：第 2 次仍不发，第 3 次才发
    assert evaluate_alert("ok", 1, 50.0, 90, fail_needed=3) == ("ok", 2, None)
    assert evaluate_alert("ok", 2, 50.0, 90, fail_needed=3) == ("alerting", 3, "alert")


def test_cell_state_legacy_string():
    from app.notifier import _cell_state
    assert _cell_state("ok") == ("ok", 0)
    assert _cell_state("alerting") == ("alerting", 0)


def test_cell_state_new_dict():
    from app.notifier import _cell_state
    assert _cell_state({"s": "ok", "n": 1}) == ("ok", 1)
    assert _cell_state({"s": "alerting", "n": 2}) == ("alerting", 2)


def test_cell_state_missing_or_garbage():
    from app.notifier import _cell_state
    assert _cell_state(None) == ("ok", 0)
    assert _cell_state({}) == ("ok", 0)
    assert _cell_state("weird") == ("ok", 0)
    assert _cell_state({"s": "weird", "n": "x"}) == ("ok", 0)


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


def test_alert_card_red_header():
    card = build_feishu_card("alert", "主力渠道",
                             [("OpenAI-A", "gpt-4o", 72.0), ("OpenAI-B", "claude", 65.0)],
                             90, "2026-06-09 10:30")
    assert card["msg_type"] == "interactive"
    assert card["card"]["config"]["wide_screen_mode"] is True
    assert card["card"]["header"]["template"] == "red"
    title = card["card"]["header"]["title"]["content"]
    assert "告警" in title and "主力渠道" in title and "2 个异常" in title
    assert "OpenAI-A/gpt-4o" in title          # 首个异常的站点×模型进标题
    flat = str(card)
    assert "OpenAI-A" in flat and "gpt-4o" in flat and "72.0%" in flat
    assert "OpenAI-B" in flat and "claude" in flat and "65.0%" in flat
    assert "低于阈值 90%" in flat            # 汇总行带阈值


def test_recover_card_green_header():
    card = build_feishu_card("recover", "主力渠道",
                             [("OpenAI-A", "gpt-4o", 95.0)], 90, "2026-06-09 10:30")
    assert card["card"]["header"]["template"] == "green"
    title = card["card"]["header"]["title"]["content"]
    assert "恢复" in title and "主力渠道" in title and "1 个" in title
    assert "OpenAI-A/gpt-4o" in title
    flat = str(card)
    assert "OpenAI-A" in flat and "gpt-4o" in flat and "95.0%" in flat


def test_card_title_handles_empty_task_name():
    card = build_feishu_card("alert", "", [("S", "m", 50.0)], 90, "t")
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
