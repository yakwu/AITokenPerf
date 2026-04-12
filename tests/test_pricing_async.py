"""TDD 测试：价格服务异步启动 + 镜像备选"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

import pytest


# ==========================================
# 第一部分: start() 不阻塞启动
# ==========================================

@pytest.mark.asyncio
async def test_start_returns_immediately_with_stale_cache(tmp_path):
    """有本地缓存时，start() 应立即返回，不 await refresh"""
    from app import pricing as pricing_module

    cache_file = tmp_path / "pricing_cache.json"
    cache_data = {
        "models": {"test-model": {"input_cost_per_token": 0.01, "output_cost_per_token": 0.03}},
        "last_refresh": time.time() - 200000,  # 远超 24h，已过期
    }
    cache_file.write_text(json.dumps(cache_data))

    svc = pricing_module.PricingService()

    with patch.object(pricing_module, '_CACHE_PATH', cache_file):
        # 模拟 refresh 需要很长时间
        async def slow_refresh():
            await asyncio.sleep(30)  # 如果 start await 了这个，测试会超时

        svc.refresh = slow_refresh

        # start 应在 1 秒内返回
        await asyncio.wait_for(svc.start(), timeout=2.0)

        # 缓存应已加载
        assert svc._loaded is True
        assert "test-model" in svc._cache


@pytest.mark.asyncio
async def test_start_schedules_background_refresh(tmp_path):
    """缓存过期时，start() 应用 create_task 调度后台刷新"""
    from app import pricing as pricing_module

    cache_file = tmp_path / "pricing_cache.json"
    cache_data = {
        "models": {"m": {"input_cost_per_token": 0.01, "output_cost_per_token": 0.03}},
        "last_refresh": time.time() - 200000,
    }
    cache_file.write_text(json.dumps(cache_data))

    svc = pricing_module.PricingService()
    refresh_called = False

    async def mock_refresh():
        nonlocal refresh_called
        refresh_called = True

    svc.refresh = mock_refresh

    with patch.object(pricing_module, '_CACHE_PATH', cache_file):
        await svc.start()

    # 让后台 task 执行
    await asyncio.sleep(0.1)
    assert refresh_called, "start() 应在后台调度 refresh"


@pytest.mark.asyncio
async def test_start_without_cache_does_not_block():
    """无本地缓存时，start() 也不应阻塞"""
    from app import pricing as pricing_module

    svc = pricing_module.PricingService()
    fake_path = Path("/nonexistent/pricing_cache.json")

    async def slow_refresh():
        await asyncio.sleep(30)

    svc.refresh = slow_refresh

    with patch.object(pricing_module, '_CACHE_PATH', fake_path):
        await asyncio.wait_for(svc.start(), timeout=2.0)

    # 没有缓存，_loaded 为 False，但不阻塞
    assert svc._loaded is False


# ==========================================
# 第二部分: refresh() 镜像备选
# ==========================================

@pytest.mark.asyncio
async def test_refresh_tries_mirror_first():
    """refresh() 应先尝试 CDN 镜像"""
    from app.pricing import PricingService, JSDELIVR_URL

    svc = PricingService()

    urls_tried = []

    class FakeResponse:
        status = 200
        async def text(self):
            return json.dumps({"test-model": {"input_cost_per_token": 0.01, "output_cost_per_token": 0.02, "litellm_provider": "test"}})

    class FakeSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            pass

        def get(self, url, **kw):
            urls_tried.append(url)
            return _FakeCtx(FakeResponse())

    class _FakeCtx:
        def __init__(self, resp):
            self.resp = resp
        async def __aenter__(self):
            return self.resp
        async def __aexit__(self, *a):
            pass

    with patch("aiohttp.ClientSession", return_value=FakeSession()):
        with patch.object(svc, '_save_cache'):
            await svc.refresh()

    assert len(urls_tried) >= 1
    assert JSDELIVR_URL in urls_tried[0], f"应先尝试 jsdelivr 镜像，实际: {urls_tried[0]}"


@pytest.mark.asyncio
async def test_refresh_falls_back_to_github():
    """CDN 镜像失败时，应回退到 GitHub raw"""
    from app.pricing import PricingService, JSDELIVR_URL, LITELLM_PRICING_URL

    svc = PricingService()

    urls_tried = []
    call_count = 0

    class FakeResponse:
        def __init__(self, status):
            self.status = status
        async def text(self):
            return json.dumps({"fallback-model": {"input_cost_per_token": 0.01, "output_cost_per_token": 0.02, "litellm_provider": "test"}})

    class _FakeCtx:
        def __init__(self, resp):
            self.resp = resp
        async def __aenter__(self):
            return self.resp
        async def __aexit__(self, *a):
            pass

    class FakeSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            pass

        def get(self, url, **kw):
            nonlocal call_count
            urls_tried.append(url)
            call_count += 1
            if call_count == 1:
                return _FakeCtx(FakeResponse(500))  # 镜像失败
            return _FakeCtx(FakeResponse(200))  # GitHub 成功

    with patch("aiohttp.ClientSession", return_value=FakeSession()):
        with patch.object(svc, '_save_cache'):
            await svc.refresh()

    assert len(urls_tried) == 2, f"应尝试 2 个 URL，实际: {urls_tried}"
    assert "jsdelivr" in urls_tried[0]
    assert "raw.githubusercontent.com" in urls_tried[1]
    assert "fallback-model" in svc._cache
