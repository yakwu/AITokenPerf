from app.notifier import evaluate_alert


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
