#!/usr/bin/env python3
"""Tab 重构验证测试 — 确保路由、Tab 栏、文件结构正确"""

import re
from pathlib import Path

FRONTEND = Path(__file__).parent.parent / "frontend" / "src"


def test_profile_view_exists():
    """ProfileView.vue 应该存在"""
    assert (FRONTEND / "views" / "ProfileView.vue").exists(), \
        "ProfileView.vue 不存在 — 需要从 BenchmarkView 提取 Profile 管理逻辑"


def test_router_has_config_route():
    """router.js 应该有 /config 路由指向 ProfileView.vue"""
    router = (FRONTEND / "router.js").read_text()
    assert re.search(r"['\"]\/config['\"]", router), \
        "router.js 中没有 /config 路由"
    assert "ProfileView" in router, \
        "/config 路由应该指向 ProfileView.vue"


def test_router_no_benchmark_route():
    """router.js 不应该再有 /benchmark 路由（已替换为站点中心化架构）"""
    router = (FRONTEND / "router.js").read_text()
    assert not re.search(r"['\"]\/benchmark['\"].*BenchmarkView", router), \
        "router.js 中仍有 /benchmark → BenchmarkView 路由，应该已替换"


def test_router_no_schedules_route():
    """router.js 不应该再有 /schedules 路由（定时任务已合并到站点详情页）"""
    router = (FRONTEND / "router.js").read_text()
    lines = router.split('\n')
    for line in lines:
        assert not re.search(r"['\"]\/schedules['\"]", line), \
            "router.js 中仍有 /schedules 路由，定时任务已合并到站点详情页"


def test_store_valid_tabs():
    """stores/app.js VALID_TABS 应该更新"""
    store = (FRONTEND / "stores" / "app.js").read_text()
    assert "'bench'" in store or '"bench"' in store, \
        "VALID_TABS 应该包含 'bench'"
    assert "'config'" in store or '"config"' in store, \
        "VALID_TABS 应该包含 'config'"


def test_profile_view_has_crud():
    """ProfileView.vue 应该包含 Profile CRUD 功能"""
    pv = (FRONTEND / "views" / "ProfileView.vue").read_text()
    assert "saveProfile" in pv, "ProfileView 应该有 saveProfile 函数"
    assert "delete" in pv.lower(), "ProfileView 应该有删除功能"
    assert "switchProfile" in pv or "selectProfile" in pv, \
        "ProfileView 应该有切换 Profile 功能"
    assert "base_url" in pv, "ProfileView 应该有 base_url 字段"
    assert "api_key" in pv, "ProfileView 应该有 api_key 字段"


def test_no_hard_redirect_on_401():
    """401 处理不应使用 window.location.href 硬刷新"""
    api_file = Path(__file__).parent.parent / "frontend" / "src" / "api" / "index.js"
    content = api_file.read_text()
    match = re.search(r"if\s*\(res\.status\s*===\s*401\)(.+?)(?:return|throw|\n\s*\})", content, re.DOTALL)
    assert match, "401 handler not found"
    handler = match.group(1)
    assert "window.location.href" not in handler, \
        "401 handler should not use window.location.href (hard redirect)"


if __name__ == "__main__":
    import sys
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
