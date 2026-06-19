"""迁移脚本 scripts/migrate_alert_window_30min.py 的匹配逻辑单测。"""

import importlib.util
import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "..",
                     "scripts", "migrate_alert_window_30min.py")
_spec = importlib.util.spec_from_file_location("migrate_alert_window_30min", _PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_migrate = _mod._migrate_rules


def test_count12_migrates_to_minute30():
    d = json.loads(_migrate('{"mode":"count","value":12,"fail_in_window":3}'))
    assert d["mode"] == "minute" and d["value"] == 30
    assert d["fail_in_window"] == 3          # 其余字段保留


def test_time1_migrates_to_minute30():
    d = json.loads(_migrate('{"mode":"time","value":1}'))
    assert d["mode"] == "minute" and d["value"] == 30


def test_leaves_short_windows_and_empty_and_idempotent():
    assert _migrate("") is None                       # 空 → 走新默认，不处理
    assert _migrate('{"mode":"count","value":6}') is None     # 自定义短窗口不动
    assert _migrate('{"mode":"time","value":2}') is None      # 2 小时不动
    assert _migrate('{"mode":"minute","value":30}') is None   # 幂等：已是目标
    assert _migrate("garbage") is None                # 非法 JSON 不动
