#!/usr/bin/env python3
"""模型价格服务 — 从 LiteLLM 下载价格数据，本地缓存，按模型名查价"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

import aiohttp

LITELLM_PRICING_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
# CDN 镜像（国内可访问），优先级高于 GitHub raw
JSDELIVR_URL = (
    "https://cdn.jsdelivr.net/gh/BerriAI/litellm@main/"
    "model_prices_and_context_window.json"
)
_PRICING_SOURCES = [JSDELIVR_URL, LITELLM_PRICING_URL]
_FETCH_TIMEOUT = 10  # seconds，从 30s 缩短

_CACHE_PATH = Path(__file__).parent.parent / "data" / "pricing_cache.json"

log = logging.getLogger("pricing")
_MODELS_CONFIG_PATH = Path(__file__).parent.parent / "data" / "models_config.json"
_REFRESH_INTERVAL = 86400  # 24 hours

# 用于过滤模型名的关键词 — 每个 provider 对应一组模型名关键词
PROVIDER_MODEL_KEYWORDS = {
    "anthropic": ["claude"],
    "openai": ["gpt-", "o1", "o3", "o4", "chatgpt"],
    "deepseek": ["deepseek"],
    "qwen": ["qwen", "qwq"],
    "google": ["gemini", "gemma", "palm"],
    "mistral": ["mistral", "mixtral", "codestral", "pixtral"],
    "cohere": ["command", "cohere"],
    "bytedance": ["doubao", "bytedance"],
    "zhipu": ["glm", "chatglm", "zhipu"],
    "moonshot": ["moonshot", "kimi"],
}


class PricingService:
    def __init__(self):
        self._cache: dict[str, dict] = {}
        self._last_refresh: float = 0.0
        self._lock = asyncio.Lock()
        self._loaded = False

    async def start(self):
        """启动服务，加载本地缓存后立即返回。
        缓存过期或不存在时，后台异步刷新，不阻塞启动流程。
        """
        if _CACHE_PATH.exists():
            try:
                data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
                self._cache = data.get("models", {})
                self._last_refresh = data.get("last_refresh", 0.0)
                self._loaded = True
                log.info("本地缓存已加载: %d 个模型", len(self._cache))
            except Exception as e:
                log.warning("本地缓存读取失败: %s", e)

        # 缓存过期或不存在 → 后台异步刷新（不阻塞启动）
        if not self._loaded or (time.time() - self._last_refresh) > _REFRESH_INTERVAL:
            try:
                asyncio.create_task(self.refresh())
            except RuntimeError:
                # 没有事件循环（理论上 lifespan 里不会发生），跳过
                log.warning("无事件循环，跳过后台刷新")

    async def refresh(self):
        """从远程下载最新价格数据 — 依次尝试 CDN 镜像、GitHub raw。"""
        async with self._lock:
            raw = await self._fetch_from_sources()
            if raw is None:
                return

            # 解析：只保留有价格信息的模型
            models = {}
            for key, info in raw.items():
                if key == "sample_spec" or not isinstance(info, dict):
                    continue
                input_cost = info.get("input_cost_per_token")
                output_cost = info.get("output_cost_per_token")
                if input_cost is None and output_cost is None:
                    continue
                models[key] = {
                    "input_cost_per_token": input_cost or 0.0,
                    "output_cost_per_token": output_cost or 0.0,
                    "litellm_provider": info.get("litellm_provider", ""),
                    "max_input_tokens": info.get("max_input_tokens"),
                    "max_output_tokens": info.get("max_output_tokens"),
                    "mode": info.get("mode", ""),
                }

            self._cache = models
            self._last_refresh = time.time()
            self._loaded = True

            log.info("已加载 %d 个模型的价格数据", len(models))
            self._save_cache()

    async def _fetch_from_sources(self) -> Optional[dict]:
        """按顺序尝试各个数据源，返回第一个成功的 JSON 数据。"""
        for url in _PRICING_SOURCES:
            try:
                log.info("正在下载模型价格数据: %s", url)
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=_FETCH_TIMEOUT),
                    ) as resp:
                        if resp.status != 200:
                            log.warning("下载失败 %s: HTTP %d", url, resp.status)
                            continue
                        return json.loads(await resp.text())
            except Exception as e:
                log.warning("下载失败 %s: %r", url, e)
                continue
        log.error("所有价格数据源均不可用")
        return None

    def _save_cache(self):
        """将当前 cache 持久化到本地文件。"""
        try:
            _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _CACHE_PATH.write_text(
                json.dumps(
                    {"models": self._cache, "last_refresh": self._last_refresh},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            log.warning("价格缓存保存失败: %s", e)

    def get_pricing(self, model_name: str) -> Optional[dict]:
        """根据模型名获取价格信息。返回 {input_cost_per_token, output_cost_per_token} 或 None"""
        if not model_name or not self._cache:
            return None

        # 1. 精确匹配 (case-insensitive)
        for key, info in self._cache.items():
            if key.lower() == model_name.lower():
                return info

        # 2. 去 provider 前缀匹配 (如 "anthropic/claude-sonnet-4" → "claude-sonnet-4")
        if "/" in model_name:
            short_name = model_name.split("/", 1)[1]
            for key, info in self._cache.items():
                if key.lower() == short_name.lower():
                    return info

        # 3. 前缀匹配: "claude-sonnet-4" → "claude-sonnet-4-20250514" (取最新)
        candidates = []
        search_lower = model_name.lower()
        for key, info in self._cache.items():
            if key.lower().startswith(search_lower):
                candidates.append((key, info))
        if candidates:
            # 按 key 降序排列（日期后缀越大越新）
            candidates.sort(key=lambda x: x[0].lower(), reverse=True)
            return candidates[0][1]

        return None

    def get_models_by_provider(self, provider: str = "", enabled_only: bool = False) -> list[dict]:
        """按 provider 过滤返回模型列表，用于前端下拉框"""
        if not self._cache:
            return []

        enabled = set()
        if enabled_only:
            enabled = set(self.get_enabled_models())

        if not provider or provider == "other":
            items = list(self._cache.items())
        else:
            # 按关键词匹配模型名
            keywords = PROVIDER_MODEL_KEYWORDS.get(provider, [])
            if not keywords:
                items = list(self._cache.items())
            else:
                items = []
                for key, info in self._cache.items():
                    key_lower = key.lower()
                    if any(kw in key_lower for kw in keywords):
                        items.append((key, info))

        if enabled:
            items = [(k, v) for k, v in items if k in enabled]

        return self._format_model_list(items)

    # ---- 模型启用配置 ----

    def get_enabled_models(self) -> list[str]:
        """返回用户启用的模型列表，空列表 = 全部启用"""
        try:
            if _MODELS_CONFIG_PATH.exists():
                data = json.loads(_MODELS_CONFIG_PATH.read_text(encoding="utf-8"))
                return data.get("enabled_models", [])
        except Exception:
            pass
        return []

    def save_enabled_models(self, models: list[str]):
        """保存用户启用的模型列表"""
        _MODELS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _MODELS_CONFIG_PATH.write_text(
            json.dumps(
                {"enabled_models": models, "updated_at": time.time()},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _format_model_list(items: list) -> list[dict]:
        """格式化模型列表，用于 API 返回"""
        result = []
        for key, info in items:
            result.append({
                "id": key,
                "input_cost_per_token": info.get("input_cost_per_token", 0),
                "output_cost_per_token": info.get("output_cost_per_token", 0),
                "provider": info.get("litellm_provider", ""),
                "max_input_tokens": info.get("max_input_tokens"),
                "max_output_tokens": info.get("max_output_tokens"),
                "mode": info.get("mode", ""),
            })
        # 按模型名排序
        result.sort(key=lambda x: x["id"])
        return result


# 模块级单例
pricing_service = PricingService()
