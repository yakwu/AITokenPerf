from app.notifier import evaluate_alert, is_allowed_webhook


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
