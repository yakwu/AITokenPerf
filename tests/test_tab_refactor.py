#!/usr/bin/env python3
"""Tab 重构验证测试 — 确保路由、Tab 栏、文件结构正确"""

import re
from pathlib import Path

FRONTEND = Path(__file__).parent.parent / "frontend" / "src"


def test_profile_view_exists():
    """ProfileView.vue 应该存在"""
    assert (FRONTEND / "views" / "ProfileView.vue").exists(), \
        "ProfileView.vue 不存在 — 需要从 BenchmarkView 提取 Profile 管理逻辑"


def test_test_view_exists():
    """TestView.vue 应该存在"""
    assert (FRONTEND / "views" / "TestView.vue").exists(), \
        "TestView.vue 不存在 — 需要新建统一测试入口"


def test_router_has_bench_route():
    """router.js 应该有 /bench 路由指向 TestView.vue"""
    router = (FRONTEND / "router.js").read_text()
    assert re.search(r"['\"]\/bench['\"]", router), \
        "router.js 中没有 /bench 路由"
    assert "TestView" in router, \
        "/bench 路由应该指向 TestView.vue"


def test_router_has_config_route():
    """router.js 应该有 /config 路由指向 ProfileView.vue"""
    router = (FRONTEND / "router.js").read_text()
    assert re.search(r"['\"]\/config['\"]", router), \
        "router.js 中没有 /config 路由"
    assert "ProfileView" in router, \
        "/config 路由应该指向 ProfileView.vue"


def test_router_no_benchmark_route():
    """router.js 不应该再有 /benchmark 路由（已替换为 /bench）"""
    router = (FRONTEND / "router.js").read_text()
    assert not re.search(r"['\"]\/benchmark['\"].*BenchmarkView", router), \
        "router.js 中仍有 /benchmark → BenchmarkView 路由，应该已替换"


def test_router_no_schedules_route():
    """router.js 不应该再有 /schedules 路由（定时任务已合并到 /bench）"""
    router = (FRONTEND / "router.js").read_text()
    # /schedules 路由不应该出现在 routes 中
    # 注意：SchedulesView 可能仍被 TestView 导入，但路由本身不应存在
    lines = router.split('\n')
    for line in lines:
        assert not re.search(r"['\"]\/schedules['\"]", line), \
            "router.js 中仍有 /schedules 路由，定时任务已合并到 /bench"


def test_app_vue_tab_bar():
    """App.vue Tab 栏应该有: 总览 / 测试 / 历史记录 / 配置"""
    app = (FRONTEND / "App.vue").read_text()

    # 应该有这些 tab
    assert "/bench" in app, "App.vue 应该有 /bench 链接（测试 tab）"
    assert "/config" in app, "App.vue 应该有 /config 链接（配置 tab）"
    assert "测试</router-link>" in app or "测试<" in app, \
        "App.vue 应该有「测试」tab"
    assert "配置</router-link>" in app or "配置<" in app, \
        "App.vue 应该有「配置」tab"

    # 不应该有旧的 tab
    assert not re.search(r"/benchmark.*新建测试", app), \
        "App.vue 不应该再有「新建测试」tab"
    assert not re.search(r'/schedules.*定时任务', app), \
        "App.vue 不应该再有「定时任务」tab（已合并到测试）"


def test_app_vue_bench_active_class():
    """App.vue /bench tab 应该用 startsWith 判断 active"""
    app = (FRONTEND / "App.vue").read_text()
    assert "startsWith('/bench')" in app, \
        "/bench tab 的 active 判断应该用 startsWith('/bench') 以支持子路径"


def test_store_valid_tabs():
    """stores/app.js VALID_TABS 应该更新"""
    store = (FRONTEND / "stores" / "app.js").read_text()
    assert "'bench'" in store or '"bench"' in store, \
        "VALID_TABS 应该包含 'bench'"
    assert "'config'" in store or '"config"' in store, \
        "VALID_TABS 应该包含 'config'"


def test_test_view_has_sub_tabs():
    """TestView.vue 应该有单次测试和定时任务的子 Tab 切换"""
    test_view = (FRONTEND / "views" / "TestView.vue").read_text()
    assert "单次测试" in test_view, "TestView 应该有「单次测试」子 tab"
    assert "定时任务" in test_view, "TestView 应该有「定时任务」子 tab"
    assert "subMode" in test_view or "sub-mode" in test_view or "subTab" in test_view, \
        "TestView 应该有子模式切换逻辑"


def test_profile_view_has_crud():
    """ProfileView.vue 应该包含 Profile CRUD 功能"""
    pv = (FRONTEND / "views" / "ProfileView.vue").read_text()
    assert "saveProfile" in pv, "ProfileView 应该有 saveProfile 函数"
    assert "delete" in pv.lower(), "ProfileView 应该有删除功能"
    assert "switchProfile" in pv or "selectProfile" in pv, \
        "ProfileView 应该有切换 Profile 功能"
    assert "base_url" in pv, "ProfileView 应该有 base_url 字段"
    assert "api_key" in pv, "ProfileView 应该有 api_key 字段"


def test_test_view_imports_schedule_apis():
    """TestView 应该导入定时任务相关的 API"""
    tv = (FRONTEND / "views" / "TestView.vue").read_text()
    assert "getSchedules" in tv, "TestView 应该导入 getSchedules"
    assert "createScheduleApi" in tv, "TestView 应该导入 createScheduleApi"


def test_check_running_status_skips_sse_for_scheduled_task():
    """checkRunningStatus 应根据 scheduled_task_id 决定是否启动 SSE"""
    vue_file = Path(__file__).parent.parent / "frontend" / "src" / "views" / "TestView.vue"
    content = vue_file.read_text()
    # 应该有条件判断：只有非定时任务才启动 SSE
    assert "data.scheduled_task_id" in content, \
        "checkRunningStatus should check scheduled_task_id before starting SSE"
    assert "startSSE" in content


def test_bench_complete_has_guard_before_switch():
    """bench:complete 处理应在 switchTab 前有守卫条件"""
    vue_file = Path(__file__).parent.parent / "frontend" / "src" / "views" / "TestView.vue"
    content = vue_file.read_text()
    match = re.search(r"case 'bench:complete':(.+?)(?:break|case)", content, re.DOTALL)
    assert match, "bench:complete case not found"
    case_body = match.group(1)
    assert "liveResults" in case_body or "running" in case_body, \
        "bench:complete should guard switchTab with a condition"


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
