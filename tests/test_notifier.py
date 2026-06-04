import pytest

from app import notifier
from app.notifier import build_feishu_card, evaluate_alert, is_allowed_webhook


def test_alert_fires_on_ok_to_abnormal():
    assert evaluate_alert("ok", 72.0, 90) == ("alerting", "alert")


def test_no_repeat_while_abnormal():
    assert evaluate_alert("alerting", 50.0, 90) == ("alerting", None)


def test_recover_on_abnormal_to_ok():
    assert evaluate_alert("alerting", 95.0, 90) == ("ok", "recover")


def test_no_action_while_ok():
    assert evaluate_alert("ok", 99.0, 90) == ("ok", None)


def test_threshold_boundary_is_normal():
    assert evaluate_alert("ok", 90.0, 90) == ("ok", None)


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
    card = build_feishu_card("alert", "主力渠道", "OpenAI-A", 72.0, 90, "2026-06-04 10:30")
    assert card["msg_type"] == "interactive"
    assert card["card"]["config"]["wide_screen_mode"] is True
    assert card["card"]["header"]["template"] == "red"
    assert "告警" in card["card"]["header"]["title"]["content"]
    flat = str(card)
    assert "72.0%" in flat and "90%" in flat and "主力渠道" in flat


def test_recover_card_green_header():
    card = build_feishu_card("recover", "主力渠道", "OpenAI-A", 95.0, 90, "2026-06-04 10:30")
    assert card["card"]["header"]["template"] == "green"
    assert "恢复" in card["card"]["header"]["title"]["content"]


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
