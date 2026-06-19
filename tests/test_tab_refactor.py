#!/usr/bin/env python3
"""路由架构不变量测试 — 守住 IA 重构（#58/#76/#81）后的既定结构，防旧架构复活。

注：原本配套 tab/ProfileView 旧架构的断言（ProfileView.vue 存在、/config→ProfileView、
VALID_TABS、ProfileView CRUD）已随该架构删除而过时，于 #85 一并清理。
"""

import re
from pathlib import Path

FRONTEND = Path(__file__).parent.parent / "frontend" / "src"


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
