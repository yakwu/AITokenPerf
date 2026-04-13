# 模型管理整改 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将模型管理从 LiteLLM 全量数据源改为自维护 JSON 配置文件，提取通用 ModelSelector 组件，消除重复代码，修复厂商过滤 bug。

**Architecture:** 新增 `data/builtin_models.json` 作为模型权威数据源（含厂商注册表），LiteLLM 退化为纯价格查询 + 模型库浏览。后端 `pricing.py` 新增内置模型 CRUD 方法，前端提取 `ModelSelector.vue` 通用组件替代三处手写 combobox。模型管理页改为双 Tab（我的模型 + 模型库）。

**Tech Stack:** Python/FastAPI (后端), Vue 3 + Composition API (前端), Vitest (前端测试), pytest + pytest-asyncio (后端测试)

---

## File Structure

### New Files
| Path | Responsibility |
|------|---------------|
| `data/builtin_models.json` | 内置模型 + 厂商注册表的权威数据源（运行时生成，gitignored） |
| `app/builtin_models.py` | 内置模型的读写逻辑，默认模型种子数据 |
| `tests/test_builtin_models.py` | 后端内置模型 CRUD 测试 |
| `tests/test_builtin_models_api.py` | 后端 API 端点集成测试 |
| `frontend/src/components/ModelSelector.vue` | 通用模型选择器组件（tags + 厂商 chips + dropdown） |
| `frontend/src/components/__tests__/ModelSelector.test.js` | ModelSelector 组件测试 |

### Modified Files
| Path | Changes |
|------|---------|
| `app/pricing.py` | 删除 `PROVIDER_MODEL_KEYWORDS`、`get_models_by_provider`、`get_enabled_models`、`save_enabled_models`，新增 `get_library()` 方法 |
| `app/server.py` | 改造 `/api/pricing/models`、`/models-config` 路由，新增 `/api/pricing/library`、`/api/pricing/vendors` |
| `frontend/src/api/index.js` | 新增 `getVendors`、`getLibrary`，改造 `getPricingModels`、`putModelsConfig`、`getModelsConfig` |
| `frontend/src/views/ModelsView.vue` | 双 Tab 重写（我的模型 + 模型库） |
| `frontend/src/views/SitesView.vue` | 去掉 provider combobox，改用 ModelSelector |
| `frontend/src/components/SiteConfigTab.vue` | 去掉 provider combobox，改用 ModelSelector |

---

## Task 1: 内置模型数据层 (`app/builtin_models.py`)

**Files:**
- Create: `app/builtin_models.py`
- Create: `tests/test_builtin_models.py`

### Step 1: 写失败的测试 — 读取默认模型列表

- [ ] **创建测试文件 `tests/test_builtin_models.py`**

```python
"""TDD 测试：内置模型管理"""

import json
from pathlib import Path

import pytest


def test_get_vendors_returns_default_list(tmp_path):
    """get_vendors 应返回默认厂商列表"""
    from app.builtin_models import BuiltinModelsManager

    mgr = BuiltinModelsManager(data_dir=tmp_path)
    vendors = mgr.get_vendors()

    assert isinstance(vendors, list)
    assert len(vendors) >= 10
    ids = [v["id"] for v in vendors]
    assert "anthropic" in ids
    assert "openai" in ids
    assert "deepseek" in ids

    # 每个 vendor 应有 id, name, label
    for v in vendors:
        assert "id" in v
        assert "name" in v
        assert "label" in v


def test_get_builtin_models_returns_default_seed(tmp_path):
    """无 JSON 文件时应返回默认种子模型"""
    from app.builtin_models import BuiltinModelsManager

    mgr = BuiltinModelsManager(data_dir=tmp_path)
    models = mgr.get_builtin_models()

    assert isinstance(models, list)
    assert len(models) >= 9  # 至少 9 个种子模型
    ids = [m["id"] for m in models]
    assert any("claude" in mid for mid in ids)
    assert any("gpt" in mid for mid in ids)
    assert any("deepseek" in mid for mid in ids)

    # 每个 model 应有 id, vendor, enabled
    for m in models:
        assert "id" in m
        assert "vendor" in m
        assert "enabled" in m


def test_get_builtin_models_filter_by_vendor(tmp_path):
    """按厂商过滤"""
    from app.builtin_models import BuiltinModelsManager

    mgr = BuiltinModelsManager(data_dir=tmp_path)
    models = mgr.get_builtin_models(vendor="anthropic")

    assert len(models) >= 1
    for m in models:
        assert m["vendor"] == "anthropic"


def test_get_builtin_models_enabled_only(tmp_path):
    """enabled_only=True 应只返回启用的模型"""
    from app.builtin_models import BuiltinModelsManager

    mgr = BuiltinModelsManager(data_dir=tmp_path)

    # 先禁用一个模型
    all_models = mgr.get_builtin_models()
    all_models[0]["enabled"] = False
    mgr.save_builtin_models({"vendors": mgr.get_vendors(), "models": all_models})

    enabled = mgr.get_builtin_models(enabled_only=True)
    disabled_id = all_models[0]["id"]
    assert disabled_id not in [m["id"] for m in enabled]


def test_save_and_reload(tmp_path):
    """保存后重新加载应一致"""
    from app.builtin_models import BuiltinModelsManager

    mgr = BuiltinModelsManager(data_dir=tmp_path)
    vendors = mgr.get_vendors()
    models = mgr.get_builtin_models()

    # 添加自定义模型
    models.append({"id": "my-custom-model", "vendor": "openai", "enabled": True, "custom": True})
    mgr.save_builtin_models({"vendors": vendors, "models": models})

    # 重新加载
    mgr2 = BuiltinModelsManager(data_dir=tmp_path)
    models2 = mgr2.get_builtin_models()
    ids = [m["id"] for m in models2]
    assert "my-custom-model" in ids


def test_add_model(tmp_path):
    """add_model 应添加一个新模型"""
    from app.builtin_models import BuiltinModelsManager

    mgr = BuiltinModelsManager(data_dir=tmp_path)
    mgr.add_model("gpt-5.1", vendor="openai", custom=True)

    models = mgr.get_builtin_models()
    ids = [m["id"] for m in models]
    assert "gpt-5.1" in ids

    # 重复添加应忽略
    count_before = len(models)
    mgr.add_model("gpt-5.1", vendor="openai", custom=True)
    assert len(mgr.get_builtin_models()) == count_before


def test_remove_model(tmp_path):
    """remove_model 应删除指定模型"""
    from app.builtin_models import BuiltinModelsManager

    mgr = BuiltinModelsManager(data_dir=tmp_path)
    mgr.add_model("temp-model", vendor="openai", custom=True)
    assert "temp-model" in [m["id"] for m in mgr.get_builtin_models()]

    mgr.remove_model("temp-model")
    assert "temp-model" not in [m["id"] for m in mgr.get_builtin_models()]


def test_toggle_model_enabled(tmp_path):
    """toggle_model 应切换模型的 enabled 状态"""
    from app.builtin_models import BuiltinModelsManager

    mgr = BuiltinModelsManager(data_dir=tmp_path)
    models = mgr.get_builtin_models()
    first_id = models[0]["id"]
    original = models[0]["enabled"]

    mgr.toggle_model(first_id)
    updated = mgr.get_builtin_models()
    toggled = next(m for m in updated if m["id"] == first_id)
    assert toggled["enabled"] is not original


def test_migrate_from_old_config(tmp_path):
    """如果存在旧的 models_config.json 应迁移"""
    from app.builtin_models import BuiltinModelsManager

    # 写入旧格式配置
    old_config = tmp_path / "models_config.json"
    old_config.write_text(json.dumps({
        "enabled_models": ["claude-opus-4-6", "gpt-5.2", "custom-xyz"],
        "updated_at": 1000
    }))

    mgr = BuiltinModelsManager(data_dir=tmp_path)
    models = mgr.get_builtin_models()
    ids = [m["id"] for m in models]

    # 旧配置中的模型应在新列表中且为 enabled
    assert "claude-opus-4-6" in ids
    assert "gpt-5.2" in ids
    # 不在默认种子中的 custom-xyz 应作为自定义模型添加
    assert "custom-xyz" in ids
    custom = next(m for m in models if m["id"] == "custom-xyz")
    assert custom.get("custom") is True
```

- [ ] **运行测试确认全部失败**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_builtin_models.py -v
```

Expected: 全部 FAIL（`ModuleNotFoundError: No module named 'app.builtin_models'`）

### Step 2: 实现 `app/builtin_models.py`

- [ ] **创建 `app/builtin_models.py`**

```python
"""内置模型管理 — 自维护的主流模型列表 + 厂商注册表"""

import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("builtin_models")

# 默认厂商注册表
DEFAULT_VENDORS = [
    {"id": "anthropic", "name": "Anthropic", "label": "Anthropic (Claude)"},
    {"id": "openai", "name": "OpenAI", "label": "OpenAI"},
    {"id": "deepseek", "name": "DeepSeek", "label": "DeepSeek"},
    {"id": "qwen", "name": "Qwen", "label": "Qwen (通义千问)"},
    {"id": "google", "name": "Google", "label": "Google (Gemini)"},
    {"id": "mistral", "name": "Mistral", "label": "Mistral"},
    {"id": "cohere", "name": "Cohere", "label": "Cohere"},
    {"id": "bytedance", "name": "ByteDance", "label": "字节 (豆包)"},
    {"id": "zhipu", "name": "Zhipu", "label": "智谱 (GLM)"},
    {"id": "moonshot", "name": "Moonshot", "label": "Moonshot (Kimi)"},
]

# 默认种子模型
DEFAULT_MODELS = [
    {"id": "claude-opus-4-20250514", "vendor": "anthropic", "enabled": True},
    {"id": "claude-sonnet-4-20250514", "vendor": "anthropic", "enabled": True},
    {"id": "claude-haiku-4-20250514", "vendor": "anthropic", "enabled": True},
    {"id": "gpt-4o", "vendor": "openai", "enabled": True},
    {"id": "gpt-4o-mini", "vendor": "openai", "enabled": True},
    {"id": "o3", "vendor": "openai", "enabled": True},
    {"id": "o4-mini", "vendor": "openai", "enabled": True},
    {"id": "deepseek-chat", "vendor": "deepseek", "enabled": True},
    {"id": "deepseek-reasoner", "vendor": "deepseek", "enabled": True},
    {"id": "qwen-max", "vendor": "qwen", "enabled": True},
    {"id": "qwen-plus", "vendor": "qwen", "enabled": True},
    {"id": "gemini-2.5-pro", "vendor": "google", "enabled": True},
    {"id": "gemini-2.5-flash", "vendor": "google", "enabled": True},
    {"id": "mistral-large-latest", "vendor": "mistral", "enabled": True},
    {"id": "glm-4-plus", "vendor": "zhipu", "enabled": True},
    {"id": "moonshot-v1-auto", "vendor": "moonshot", "enabled": True},
    {"id": "doubao-pro-32k", "vendor": "bytedance", "enabled": True},
]

_JSON_FILENAME = "builtin_models.json"
_OLD_CONFIG_FILENAME = "models_config.json"


class BuiltinModelsManager:
    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data"
        self._data_dir = data_dir
        self._json_path = data_dir / _JSON_FILENAME
        self._old_config_path = data_dir / _OLD_CONFIG_FILENAME
        self._data: dict = self._load()

    def _load(self) -> dict:
        """加载 JSON，不存在时用默认值 + 迁移旧配置"""
        if self._json_path.exists():
            try:
                return json.loads(self._json_path.read_text(encoding="utf-8"))
            except Exception as e:
                log.warning("读取 %s 失败: %s", self._json_path, e)

        # 首次使用：用默认值初始化
        data = {
            "vendors": [dict(v) for v in DEFAULT_VENDORS],
            "models": [dict(m) for m in DEFAULT_MODELS],
        }

        # 迁移旧 models_config.json
        if self._old_config_path.exists():
            data = self._migrate_old_config(data)

        self._save(data)
        return data

    def _migrate_old_config(self, data: dict) -> dict:
        """从旧的 models_config.json 迁移"""
        try:
            old = json.loads(self._old_config_path.read_text(encoding="utf-8"))
            old_enabled = old.get("enabled_models", [])
            if not old_enabled:
                return data

            existing_ids = {m["id"] for m in data["models"]}
            # 旧列表中已有的模型 → 确保 enabled=True
            for model in data["models"]:
                if model["id"] in old_enabled:
                    model["enabled"] = True

            # 旧列表中不在默认种子中的 → 作为自定义模型添加
            for model_id in old_enabled:
                if model_id not in existing_ids:
                    data["models"].append({
                        "id": model_id,
                        "vendor": self._guess_vendor(model_id),
                        "enabled": True,
                        "custom": True,
                    })

            log.info("已从旧配置迁移 %d 个模型", len(old_enabled))
        except Exception as e:
            log.warning("迁移旧配置失败: %s", e)
        return data

    @staticmethod
    def _guess_vendor(model_id: str) -> str:
        """根据模型 ID 猜测厂商（仅用于迁移）"""
        mid = model_id.lower()
        if "claude" in mid:
            return "anthropic"
        if "gpt" in mid or mid.startswith("o1") or mid.startswith("o3") or mid.startswith("o4"):
            return "openai"
        if "deepseek" in mid:
            return "deepseek"
        if "qwen" in mid or "qwq" in mid:
            return "qwen"
        if "gemini" in mid or "gemma" in mid:
            return "google"
        if "mistral" in mid or "mixtral" in mid:
            return "mistral"
        if "glm" in mid:
            return "zhipu"
        if "moonshot" in mid or "kimi" in mid:
            return "moonshot"
        if "doubao" in mid:
            return "bytedance"
        return ""

    def _save(self, data: Optional[dict] = None):
        """持久化到 JSON"""
        if data is not None:
            self._data = data
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._json_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_vendors(self) -> list[dict]:
        """返回厂商列表"""
        return list(self._data.get("vendors", DEFAULT_VENDORS))

    def get_builtin_models(
        self,
        vendor: str = "",
        enabled_only: bool = False,
    ) -> list[dict]:
        """返回模型列表，支持按厂商和启用状态过滤"""
        models = list(self._data.get("models", []))
        if vendor:
            models = [m for m in models if m.get("vendor") == vendor]
        if enabled_only:
            models = [m for m in models if m.get("enabled")]
        return models

    def save_builtin_models(self, data: dict):
        """保存完整的 vendors + models 数据"""
        self._save(data)

    def add_model(self, model_id: str, vendor: str = "", custom: bool = False):
        """添加一个模型，已存在则忽略"""
        models = self._data.get("models", [])
        if any(m["id"] == model_id for m in models):
            return
        models.append({
            "id": model_id,
            "vendor": vendor,
            "enabled": True,
            **({"custom": True} if custom else {}),
        })
        self._data["models"] = models
        self._save()

    def remove_model(self, model_id: str):
        """删除一个模型"""
        self._data["models"] = [
            m for m in self._data.get("models", []) if m["id"] != model_id
        ]
        self._save()

    def toggle_model(self, model_id: str):
        """切换模型的 enabled 状态"""
        for m in self._data.get("models", []):
            if m["id"] == model_id:
                m["enabled"] = not m.get("enabled", True)
                break
        self._save()


# 模块级单例
builtin_models_manager = BuiltinModelsManager()
```

- [ ] **运行测试确认全部通过**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_builtin_models.py -v
```

Expected: 全部 PASS

- [ ] **提交**

```bash
git add app/builtin_models.py tests/test_builtin_models.py
git commit -m "feat: 内置模型管理数据层 (builtin_models.py)"
```

---

## Task 2: 后端 API 端点改造

**Files:**
- Modify: `app/server.py` (pricing 路由区域, ~line 1454-1491)
- Modify: `app/pricing.py` (删除 `PROVIDER_MODEL_KEYWORDS`、`get_models_by_provider`、`get_enabled_models`、`save_enabled_models`，新增 `get_library`)
- Create: `tests/test_builtin_models_api.py`

### Step 1: 写失败的 API 测试

- [ ] **创建 `tests/test_builtin_models_api.py`**

```python
"""TDD 测试：内置模型 API 端点"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_get_vendors(client: AsyncClient):
    """GET /api/pricing/vendors 应返回厂商列表"""
    headers = await auth_headers(client)
    resp = await client.get("/api/pricing/vendors", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "vendors" in data
    ids = [v["id"] for v in data["vendors"]]
    assert "anthropic" in ids
    assert "openai" in ids


@pytest.mark.asyncio
async def test_get_models_returns_builtin(client: AsyncClient):
    """GET /api/pricing/models 应返回内置模型列表"""
    headers = await auth_headers(client)
    resp = await client.get("/api/pricing/models", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert len(data["models"]) > 0
    # 每个模型应有 id, vendor, enabled
    for m in data["models"]:
        assert "id" in m
        assert "vendor" in m
        assert "enabled" in m


@pytest.mark.asyncio
async def test_get_models_filter_by_vendor(client: AsyncClient):
    """GET /api/pricing/models?vendor=anthropic 应只返回 anthropic 模型"""
    headers = await auth_headers(client)
    resp = await client.get("/api/pricing/models?vendor=anthropic", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    for m in data["models"]:
        assert m["vendor"] == "anthropic"


@pytest.mark.asyncio
async def test_get_models_enabled_only(client: AsyncClient):
    """GET /api/pricing/models?enabled_only=true 应只返回启用的模型"""
    headers = await auth_headers(client)
    resp = await client.get("/api/pricing/models?enabled_only=true", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    for m in data["models"]:
        assert m["enabled"] is True


@pytest.mark.asyncio
async def test_get_models_config(client: AsyncClient):
    """GET /api/pricing/models-config 应返回完整配置"""
    headers = await auth_headers(client)
    resp = await client.get("/api/pricing/models-config", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "vendors" in data
    assert "models" in data


@pytest.mark.asyncio
async def test_put_models_config_add_model(client: AsyncClient):
    """PUT /api/pricing/models-config 应能添加模型"""
    headers = await auth_headers(client)

    # 先获取当前配置
    resp = await client.get("/api/pricing/models-config", headers=headers)
    config = resp.json()
    original_count = len(config["models"])

    # 添加自定义模型
    config["models"].append({
        "id": "test-custom-model",
        "vendor": "openai",
        "enabled": True,
        "custom": True,
    })
    resp = await client.put(
        "/api/pricing/models-config",
        json=config,
        headers=headers,
    )
    assert resp.status_code == 200

    # 验证已添加
    resp = await client.get("/api/pricing/models-config", headers=headers)
    data = resp.json()
    ids = [m["id"] for m in data["models"]]
    assert "test-custom-model" in ids
    assert len(data["models"]) == original_count + 1


@pytest.mark.asyncio
async def test_get_library(client: AsyncClient):
    """GET /api/pricing/library 应返回 LiteLLM 全量数据"""
    headers = await auth_headers(client)
    resp = await client.get("/api/pricing/library", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_get_library_with_search(client: AsyncClient):
    """GET /api/pricing/library?search=claude 应过滤模型"""
    headers = await auth_headers(client)
    resp = await client.get("/api/pricing/library?search=claude", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    for m in data["models"]:
        assert "claude" in m["id"].lower()
```

- [ ] **运行测试确认失败**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_builtin_models_api.py -v
```

Expected: 部分 FAIL（新端点不存在、旧端点返回格式不匹配）

### Step 2: 改造 `app/pricing.py`

- [ ] **修改 `app/pricing.py`**

删除以下内容：
- `PROVIDER_MODEL_KEYWORDS` 字典（line 32-43）
- `get_models_by_provider` 方法（line 171-197）
- `get_enabled_models` 方法（line 201-209）
- `save_enabled_models` 方法（line 211-220）
- `_MODELS_CONFIG_PATH` 常量（line 28）

新增 `get_library` 方法：

```python
def get_library(
    self, search: str = "", vendor: str = "",
    page: int = 1, page_size: int = 50,
) -> dict:
    """浏览 LiteLLM 全量模型数据，支持搜索和分页"""
    if not self._cache:
        return {"models": [], "total": 0, "page": page, "page_size": page_size}

    items = list(self._cache.items())

    # 按搜索词过滤
    if search:
        search_lower = search.lower()
        items = [(k, v) for k, v in items if search_lower in k.lower()]

    # 按厂商过滤（使用 litellm_provider 字段）
    if vendor:
        vendor_lower = vendor.lower()
        items = [
            (k, v) for k, v in items
            if vendor_lower in (v.get("litellm_provider") or "").lower()
        ]

    total = len(items)

    # 排序
    items.sort(key=lambda x: x[0])

    # 分页
    start = (page - 1) * page_size
    items = items[start:start + page_size]

    return {
        "models": self._format_model_list(items),
        "total": total,
        "page": page,
        "page_size": page_size,
    }
```

### Step 3: 改造 `app/server.py` 路由

- [ ] **修改 `app/server.py`**

将 `# ---- Pricing ----` 区块替换为：

```python
# ---- Pricing / Models ----

@app.get("/api/pricing/vendors")
async def pricing_vendors(user: dict = Depends(get_current_user)):
    """返回厂商列表"""
    from app.builtin_models import builtin_models_manager
    return {"vendors": builtin_models_manager.get_vendors()}


@app.get("/api/pricing/models")
async def pricing_models(
    vendor: str = Query(""),
    enabled_only: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    """返回内置模型列表，附带 LiteLLM 价格信息"""
    from app.builtin_models import builtin_models_manager
    from app.pricing import pricing_service
    models = builtin_models_manager.get_builtin_models(vendor=vendor, enabled_only=enabled_only)
    # 用 LiteLLM 补充价格信息
    for m in models:
        pricing = pricing_service.get_pricing(m["id"])
        if pricing:
            m["input_cost_per_token"] = pricing.get("input_cost_per_token", 0)
            m["output_cost_per_token"] = pricing.get("output_cost_per_token", 0)
        else:
            m.setdefault("input_cost_per_token", 0)
            m.setdefault("output_cost_per_token", 0)
    return {"models": models, "total": len(models)}


@app.get("/api/pricing/models-config")
async def get_models_config(user: dict = Depends(get_current_user)):
    """返回完整的内置模型配置（含 LiteLLM 价格）"""
    from app.builtin_models import builtin_models_manager
    from app.pricing import pricing_service
    models = builtin_models_manager.get_builtin_models()
    for m in models:
        pricing = pricing_service.get_pricing(m["id"])
        if pricing:
            m["input_cost_per_token"] = pricing.get("input_cost_per_token", 0)
            m["output_cost_per_token"] = pricing.get("output_cost_per_token", 0)
        else:
            m.setdefault("input_cost_per_token", 0)
            m.setdefault("output_cost_per_token", 0)
    return {
        "vendors": builtin_models_manager.get_vendors(),
        "models": models,
    }


@app.put("/api/pricing/models-config")
async def put_models_config(body: dict, user: dict = Depends(require_admin)):
    """管理员保存内置模型配置"""
    from app.builtin_models import builtin_models_manager
    vendors = body.get("vendors")
    models = body.get("models")
    if not isinstance(models, list):
        return JSONResponse({"error": "models must be a list"}, status_code=400)
    builtin_models_manager.save_builtin_models(body)
    return {"ok": True, "count": len(models)}


@app.get("/api/pricing/library")
async def pricing_library(
    search: str = Query(""),
    vendor: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    """浏览 LiteLLM 全量模型库"""
    from app.pricing import pricing_service
    return pricing_service.get_library(search=search, vendor=vendor, page=page, page_size=page_size)


@app.post("/api/pricing/refresh")
async def pricing_refresh(user: dict = Depends(require_admin)):
    """管理员手动刷新价格数据"""
    from app.pricing import pricing_service
    await pricing_service.refresh()
    return {"ok": True, "total_models": len(pricing_service._cache)}
```

- [ ] **运行测试确认通过**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_builtin_models_api.py -v
```

Expected: 全部 PASS

- [ ] **运行旧测试确认不回归**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/test_pricing_async.py -v
```

Expected: 全部 PASS

- [ ] **提交**

```bash
git add app/pricing.py app/server.py tests/test_builtin_models_api.py
git commit -m "feat: 改造后端 API — 内置模型取代 LiteLLM 模型列表，新增 vendors/library 端点"
```

---

## Task 3: 前端 API 客户端更新

**Files:**
- Modify: `frontend/src/api/index.js`

### Step 1: 更新 API 函数

- [ ] **修改 `frontend/src/api/index.js`**

替换文件末尾 `// Pricing / Model Config` 区块（约 line 88-97）为：

```javascript
// Models
export const getModels = (baseUrl, apiKey) =>
  api('/api/models', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ base_url: baseUrl, api_key: apiKey }) });

// Pricing / Model Config
export const getVendors = () => api('/api/pricing/vendors');
export const getModelsConfig = () => api('/api/pricing/models-config');
export const putModelsConfig = (data) =>
  api('/api/pricing/models-config', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const getPricingModels = (vendor = '', enabledOnly = false) =>
  api(`/api/pricing/models?vendor=${encodeURIComponent(vendor)}${enabledOnly ? '&enabled_only=true' : ''}`);
export const getLibrary = ({ search = '', vendor = '', page = 1, pageSize = 50 } = {}) => {
  const params = new URLSearchParams({ search, vendor, page, page_size: pageSize });
  return api(`/api/pricing/library?${params}`);
};
```

关键改动：
- `getPricingModels` 参数从 `provider` 改为 `vendor`
- `putModelsConfig` 参数从 `enabledModels` 数组改为完整 `data` 对象（含 vendors + models）
- 新增 `getVendors` 和 `getLibrary`

- [ ] **提交**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && git add frontend/src/api/index.js
git commit -m "feat: 前端 API 客户端更新 — 新增 vendors/library，改造 models-config"
```

---

## Task 4: ModelSelector 通用组件

**Files:**
- Create: `frontend/src/components/ModelSelector.vue`
- Create: `frontend/src/components/__tests__/ModelSelector.test.js`

### Step 1: 写组件测试

- [ ] **创建 `frontend/src/components/__tests__/ModelSelector.test.js`**

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import ModelSelector from '../ModelSelector.vue';

// Mock API
vi.mock('../../api', () => ({
  getPricingModels: vi.fn().mockResolvedValue({
    models: [
      { id: 'claude-sonnet-4', vendor: 'anthropic', enabled: true },
      { id: 'claude-opus-4', vendor: 'anthropic', enabled: true },
      { id: 'gpt-4o', vendor: 'openai', enabled: true },
      { id: 'gpt-4o-mini', vendor: 'openai', enabled: true },
      { id: 'deepseek-chat', vendor: 'deepseek', enabled: true },
    ],
  }),
  getVendors: vi.fn().mockResolvedValue({
    vendors: [
      { id: 'anthropic', name: 'Anthropic', label: 'Anthropic (Claude)' },
      { id: 'openai', name: 'OpenAI', label: 'OpenAI' },
      { id: 'deepseek', name: 'DeepSeek', label: 'DeepSeek' },
    ],
  }),
}));

describe('ModelSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders with empty selection', async () => {
    const wrapper = mount(ModelSelector, {
      props: { modelValue: [] },
    });
    await flushPromises();
    expect(wrapper.find('.model-tags-input').exists()).toBe(true);
    expect(wrapper.find('.model-tag-search').exists()).toBe(true);
  });

  it('loads models and vendors on mount', async () => {
    const { getPricingModels, getVendors } = await import('../../api');
    mount(ModelSelector, { props: { modelValue: [] } });
    await flushPromises();
    expect(getPricingModels).toHaveBeenCalledWith('', true);
    expect(getVendors).toHaveBeenCalled();
  });

  it('shows vendor filter chips when vendorFilter=true', async () => {
    const wrapper = mount(ModelSelector, {
      props: { modelValue: [], vendorFilter: true },
    });
    await flushPromises();
    const chips = wrapper.findAll('.filter-chip');
    // "全部" + 3 vendors
    expect(chips.length).toBe(4);
    expect(chips[0].text()).toBe('全部');
  });

  it('hides vendor filter chips when vendorFilter=false', async () => {
    const wrapper = mount(ModelSelector, {
      props: { modelValue: [], vendorFilter: false },
    });
    await flushPromises();
    expect(wrapper.find('.filter-chips').exists()).toBe(false);
  });

  it('displays selected models as tags', async () => {
    const wrapper = mount(ModelSelector, {
      props: { modelValue: ['claude-sonnet-4', 'gpt-4o'] },
    });
    await flushPromises();
    const tags = wrapper.findAll('.model-tag');
    expect(tags.length).toBe(2);
    expect(tags[0].text()).toContain('claude-sonnet-4');
    expect(tags[1].text()).toContain('gpt-4o');
  });

  it('filters models by vendor chip click', async () => {
    const wrapper = mount(ModelSelector, {
      props: { modelValue: [], vendorFilter: true },
    });
    await flushPromises();

    // Click "Anthropic" chip
    const chips = wrapper.findAll('.filter-chip');
    await chips[1].trigger('click'); // index 1 = first vendor

    // Open dropdown
    await wrapper.find('.model-tag-search').trigger('focus');
    await flushPromises();

    const options = wrapper.findAll('.combobox-option');
    for (const opt of options) {
      // All visible options should be anthropic models
      expect(['claude-sonnet-4', 'claude-opus-4']).toContain(opt.text());
    }
  });

  it('emits update:modelValue when model selected', async () => {
    const wrapper = mount(ModelSelector, {
      props: { modelValue: [] },
    });
    await flushPromises();

    // Open dropdown and select first option
    await wrapper.find('.model-tag-search').trigger('focus');
    await flushPromises();

    const options = wrapper.findAll('.combobox-option');
    await options[0].trigger('mousedown');

    const emitted = wrapper.emitted('update:modelValue');
    expect(emitted).toBeTruthy();
    expect(emitted[0][0]).toContain('claude-sonnet-4');
  });

  it('allows custom model input when allowCustom=true', async () => {
    const wrapper = mount(ModelSelector, {
      props: { modelValue: [], allowCustom: true },
    });
    await flushPromises();

    const input = wrapper.find('.model-tag-search');
    await input.setValue('my-custom-model');
    await input.trigger('keydown', { key: 'Enter' });

    const emitted = wrapper.emitted('update:modelValue');
    expect(emitted).toBeTruthy();
    expect(emitted[0][0]).toContain('my-custom-model');
  });

  it('filters dropdown by search text', async () => {
    const wrapper = mount(ModelSelector, {
      props: { modelValue: [] },
    });
    await flushPromises();

    const input = wrapper.find('.model-tag-search');
    await input.trigger('focus');
    await input.setValue('gpt');
    await flushPromises();

    const options = wrapper.findAll('.combobox-option');
    for (const opt of options) {
      expect(opt.text().toLowerCase()).toContain('gpt');
    }
  });

  it('removes tag on × click', async () => {
    const wrapper = mount(ModelSelector, {
      props: { modelValue: ['claude-sonnet-4', 'gpt-4o'] },
    });
    await flushPromises();

    const removeButtons = wrapper.findAll('.model-tag-remove');
    await removeButtons[0].trigger('click');

    const emitted = wrapper.emitted('update:modelValue');
    expect(emitted).toBeTruthy();
    expect(emitted[0][0]).toEqual(['gpt-4o']);
  });
});
```

- [ ] **运行测试确认失败**

```bash
cd /Users/yakun/linkingrid/AITokenPerf/frontend && npx vitest run src/components/__tests__/ModelSelector.test.js
```

Expected: FAIL（组件文件不存在）

### Step 2: 实现 ModelSelector 组件

- [ ] **创建 `frontend/src/components/ModelSelector.vue`**

```vue
<template>
  <div class="model-selector">
    <!-- Vendor Filter Chips -->
    <div v-if="vendorFilter && vendors.length" class="filter-chips">
      <button
        class="filter-chip"
        :class="{ active: activeVendor === '' }"
        @click="activeVendor = ''"
      >全部</button>
      <button
        v-for="v in vendors"
        :key="v.id"
        class="filter-chip"
        :class="{ active: activeVendor === v.id }"
        @click="activeVendor = v.id"
      >{{ v.name }}</button>
    </div>

    <!-- Tags + Combobox -->
    <div class="combobox" ref="comboboxRef">
      <div class="model-tags-input" @click.stop="dropdownOpen = true">
        <span v-for="(m, i) in modelValue" :key="m" class="model-tag">
          {{ m }}
          <button type="button" class="model-tag-remove" @click.stop="removeModel(i)">&times;</button>
        </span>
        <input
          ref="searchInputRef"
          class="model-tag-search"
          v-model="searchText"
          :placeholder="modelValue.length ? '' : placeholder"
          @focus="dropdownOpen = true"
          @keydown.enter.prevent="onEnter"
          @keydown.backspace="onBackspace"
          @keydown.escape="dropdownOpen = false"
          autocomplete="off"
        >
      </div>
      <button
        class="combobox-toggle"
        type="button"
        @click.stop="dropdownOpen = !dropdownOpen"
        @mousedown.prevent
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4.5l3 3 3-3"/></svg>
      </button>
      <div class="combobox-dropdown" v-show="dropdownOpen">
        <div
          v-for="m in filteredModels"
          :key="m.id"
          class="combobox-option"
          :class="{ active: modelValue.includes(m.id) }"
          @mousedown.prevent="selectModel(m.id)"
        >{{ m.id }}</div>
        <div class="combobox-empty" v-show="!filteredModels.length && searchText && allowCustom">
          无匹配，按回车添加「{{ searchText }}」
        </div>
        <div class="combobox-empty" v-show="!filteredModels.length && searchText && !allowCustom">
          无匹配模型
        </div>
        <div class="combobox-empty" v-show="!filteredModels.length && !searchText && !loading">
          暂无模型数据
        </div>
        <div class="combobox-empty" v-show="loading">
          加载中...
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { getPricingModels, getVendors } from '../api';

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  vendorFilter: { type: Boolean, default: true },
  allowCustom: { type: Boolean, default: true },
  placeholder: { type: String, default: '搜索或选择模型' },
});

const emit = defineEmits(['update:modelValue']);

const comboboxRef = ref(null);
const searchInputRef = ref(null);
const dropdownOpen = ref(false);
const searchText = ref('');
const activeVendor = ref('');
const loading = ref(false);

const allModels = ref([]);
const vendors = ref([]);

onMounted(async () => {
  loading.value = true;
  try {
    const [modelsRes, vendorsRes] = await Promise.all([
      getPricingModels('', true),
      getVendors(),
    ]);
    allModels.value = modelsRes.models || [];
    vendors.value = vendorsRes.vendors || [];
  } catch {
    allModels.value = [];
    vendors.value = [];
  }
  loading.value = false;
});

const filteredModels = computed(() => {
  let list = allModels.value;

  // Filter by vendor
  if (activeVendor.value) {
    list = list.filter(m => m.vendor === activeVendor.value);
  }

  // Exclude already selected
  list = list.filter(m => !props.modelValue.includes(m.id));

  // Filter by search text
  const q = (searchText.value || '').toLowerCase();
  if (q) {
    list = list.filter(m => m.id.toLowerCase().includes(q));
  }

  return list;
});

function selectModel(id) {
  if (!props.modelValue.includes(id)) {
    emit('update:modelValue', [...props.modelValue, id]);
  }
  searchText.value = '';
}

function removeModel(index) {
  const updated = [...props.modelValue];
  updated.splice(index, 1);
  emit('update:modelValue', updated);
}

function onEnter() {
  // If there are filtered results, select the first one
  if (filteredModels.value.length) {
    selectModel(filteredModels.value[0].id);
    return;
  }
  // Otherwise, allow custom input
  if (props.allowCustom && searchText.value.trim()) {
    const val = searchText.value.trim();
    if (!props.modelValue.includes(val)) {
      emit('update:modelValue', [...props.modelValue, val]);
    }
    searchText.value = '';
  }
}

function onBackspace() {
  if (!searchText.value && props.modelValue.length) {
    const updated = [...props.modelValue];
    updated.pop();
    emit('update:modelValue', updated);
  }
}

// Click outside
function handleClickOutside(e) {
  if (comboboxRef.value && !comboboxRef.value.contains(e.target)) {
    dropdownOpen.value = false;
  }
}

onMounted(() => document.addEventListener('mousedown', handleClickOutside));
onUnmounted(() => document.removeEventListener('mousedown', handleClickOutside));
</script>

<style scoped>
.model-selector {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.model-selector .filter-chips {
  display: flex;
  gap: 4px;
  align-items: center;
  flex-wrap: wrap;
}
</style>
```

注意：此组件不定义 `.combobox`、`.model-tags-input`、`.model-tag` 等样式——它们已在全局 `components.css` 中定义。`<style scoped>` 只包含组件自身的布局样式。

- [ ] **运行测试确认通过**

```bash
cd /Users/yakun/linkingrid/AITokenPerf/frontend && npx vitest run src/components/__tests__/ModelSelector.test.js
```

Expected: 全部 PASS

- [ ] **提交**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && git add frontend/src/components/ModelSelector.vue frontend/src/components/__tests__/ModelSelector.test.js
git commit -m "feat: ModelSelector 通用模型选择器组件"
```

---

## Task 5: 改造 SitesView.vue（新建站点弹窗）

**Files:**
- Modify: `frontend/src/views/SitesView.vue`

### Step 1: 替换新建站点弹窗中的模型选择

- [ ] **修改 `frontend/src/views/SitesView.vue`**

**在 `<script setup>` 的 import 区域添加：**

```javascript
import ModelSelector from '../components/ModelSelector.vue';
```

**在 template 中替换新建站点弹窗 (line 116-181) 的模型区域。** 将 line 138-172 的 provider combobox + model combobox 替换为：

```html
        <div class="form-group">
          <label class="form-label">模型 <span class="required">*</span></label>
          <ModelSelector
            v-model="createForm.models"
            :vendor-filter="true"
            :allow-custom="true"
            placeholder="搜索或选择模型"
          />
          <div class="form-hint" v-if="!createForm.models.length && !createErrors.models" style="margin-top:4px">从列表选择或手动输入模型 ID 后回车</div>
          <div class="form-error" v-if="createErrors.models">{{ createErrors.models }}</div>
        </div>
```

**删除以下不再需要的代码：**

从 `<script setup>` 中删除：
- `providerOptions` 数组（line 520-533）
- `providerLabel` computed（line 535-538）
- `providerDropdownOpen`, `providerComboRef` refs（line 541-542）
- `modelDropdownOpen`, `modelComboboxRef`, `modelSearch`, `availableModels`, `managedModels`, `loadingModels` refs（line 545-550）
- `handleDocClick` 函数（line 552-555）
- `filteredModels` computed（line 557-564）
- `toggleModel` 函数（line 566-571）
- `addModelManual` 函数（line 573-578）
- `fetchModelsTimer`, `fetchModels`, `debouncedFetchModels` 函数（line 580-598）
- `watch` for base_url/api_key（line 601）
- `watch` for provider（line 604-607）
- `loadManagedModels` 函数（line 621-631）
- `onMounted` 的 `handleDocClick` 监听（line 695）
- `onUnmounted` 的 `handleDocClick` 移除（line 696）

`createForm` 简化为（去掉 `provider`）：
```javascript
const createForm = ref({
  name: '',
  base_url: '',
  api_key: '',
  models: [],
});
```

`createSite` 函数简化为：
```javascript
function createSite() {
  createForm.value = { name: '', base_url: '', api_key: '', models: [] };
  createErrors.value = {};
  showApiKey.value = false;
  showCreateModal.value = true;
}
```

`submitCreate` 中 body 去掉 `provider` 字段（line 652 附近）。

- [ ] **提交**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && git add frontend/src/views/SitesView.vue
git commit -m "refactor: SitesView 新建站点弹窗改用 ModelSelector 组件"
```

---

## Task 6: 改造 SiteConfigTab.vue（站点编辑）

**Files:**
- Modify: `frontend/src/components/SiteConfigTab.vue`

### Step 1: 替换模型选择器

- [ ] **修改 `frontend/src/components/SiteConfigTab.vue`**

**在 `<script setup>` 的 import 区域添加：**

```javascript
import ModelSelector from './ModelSelector.vue';
```

**在 template 中替换 Provider combobox + Models combobox (line 35-75) 为：**

```html
        <!-- Models -->
        <div class="form-group form-group--full">
          <label class="form-label">绑定模型</label>
          <ModelSelector
            v-model="form.models"
            :vendor-filter="true"
            :allow-custom="true"
            placeholder="选择或输入模型 ID"
          />
        </div>
```

**从 `<script setup>` 中删除：**

- `providerComboboxRef`, `comboboxRef`, `modelSearchInputRef` template refs
- `knownModels`, `modelsApiLoading`, `modelDropdownOpen`, `modelSearch` refs
- `providerDropdownOpen`, `providerSearch` refs
- `providerOptions` 数组（line 143-155）
- `filteredModels` computed（line 161-169）
- `providerLabel` computed（line 171-174）
- `filteredProviders` computed（line 176-180）
- `addModel`, `removeModel`, `selectModel`, `addModelFromSearch`, `onModelBackspace` 函数
- `handleModelOutside`, `addModelListener`, `removeModelListener` 函数 + watcher
- `onProviderFocus`, `onProviderInput`, `selectProvider` 函数
- `handleProviderOutside` 函数 + watcher
- `loadKnownModels` 函数
- `onMounted` 中的 `loadKnownModels` 调用
- `onUnmounted` 中的 listener cleanup

**`form` 去掉 `provider` 字段：**

```javascript
const form = ref({
  base_url: '',
  api_key: '',
  models: [],
});
```

**`initForm` 函数简化：**

```javascript
function initForm() {
  if (!props.profile) return;
  form.value.base_url = props.profile.base_url || '';
  form.value.api_key = props.profile.api_key_display || props.profile.api_key || '';
  form.value.models = props.profile.models || (props.profile.model ? [props.profile.model] : []);
  snapshotConfig();
}
```

**`snapshotConfig` 和 `checkDirty` 相应去掉 `provider`。**

**`saveProfile` 的请求 body 中去掉 `provider`。**

**`watch` 中去掉对 `form.value.provider` 的监听。**

- [ ] **提交**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && git add frontend/src/components/SiteConfigTab.vue
git commit -m "refactor: SiteConfigTab 改用 ModelSelector 组件，去掉 provider 字段"
```

---

## Task 7: 改造 ModelsView.vue（双 Tab）

**Files:**
- Modify: `frontend/src/views/ModelsView.vue`

### Step 1: 重写为双 Tab 结构

- [ ] **重写 `frontend/src/views/ModelsView.vue`**

```vue
<template>
  <section class="tab-content active">
    <!-- Tab Navigation -->
    <div class="models-tabs">
      <button
        class="models-tab"
        :class="{ active: activeTab === 'my' }"
        @click="activeTab = 'my'"
      >我的模型</button>
      <button
        class="models-tab"
        :class="{ active: activeTab === 'library' }"
        @click="activeTab = 'library'; loadLibrary()"
      >模型库</button>
    </div>

    <!-- Tab 1: My Models -->
    <div v-if="activeTab === 'my'" class="models-panel">
      <div class="history-toolbar">
        <div class="search-input-wrap">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input class="form-input" v-model="mySearch" placeholder="搜索模型名…" autocomplete="off">
        </div>
        <div class="filter-chips">
          <button class="filter-chip" :class="{ active: myVendor === '' }" @click="myVendor = ''">全部</button>
          <button v-for="v in vendors" :key="v.id" class="filter-chip" :class="{ active: myVendor === v.id }" @click="myVendor = v.id">{{ v.name }}</button>
        </div>
        <div style="margin-left:auto;display:flex;align-items:center;gap:8px">
          <span class="models-count">
            已启用 <strong>{{ enabledCount }}</strong> · 共 {{ myModels.length }}
          </span>
          <button class="btn btn-ghost btn-sm" @click="showAddForm = !showAddForm" :class="{ active: showAddForm }">+ 自定义</button>
        </div>
      </div>

      <!-- Add Custom Model Panel -->
      <div v-show="showAddForm" class="models-add-panel">
        <input class="form-input" v-model="addForm.id" placeholder="模型 ID" @keydown.enter="addCustomModel" autocomplete="off">
        <select class="form-select" v-model="addForm.vendor" style="width:160px">
          <option value="">选择厂商</option>
          <option v-for="v in vendors" :key="v.id" :value="v.id">{{ v.name }}</option>
        </select>
        <button class="btn btn-primary btn-sm" @click="addCustomModel" :disabled="!addForm.id.trim()">添加</button>
        <button class="btn btn-ghost btn-sm" @click="showAddForm = false">取消</button>
      </div>

      <!-- My Models Table -->
      <div class="card" style="width:100%">
        <div v-if="myLoading" class="models-loading">加载中…</div>
        <div v-else class="models-table-wrap">
          <table class="models-table">
            <thead>
              <tr>
                <th class="models-th-check"><input type="checkbox" :checked="allVisibleEnabled" :indeterminate="someVisibleEnabled && !allVisibleEnabled" @change="toggleVisible"></th>
                <th class="models-th-name" @click="toggleSort('id')">模型名 <span class="models-sort-arrow" v-if="sortKey === 'id'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></th>
                <th class="models-th-provider" @click="toggleSort('vendor')">厂商 <span class="models-sort-arrow" v-if="sortKey === 'vendor'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></th>
                <th class="models-th-price">输入价格</th>
                <th class="models-th-price">输出价格</th>
                <th class="models-th-action"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in sortedMyModels" :key="m.id" :class="{ 'models-row-custom': m.custom }">
                <td class="models-td-check"><input type="checkbox" :checked="m.enabled" @change="toggleModel(m.id)"></td>
                <td class="models-td-name" :title="m.id">{{ m.id }}<span v-if="m.custom" class="models-custom-badge">自定义</span></td>
                <td class="models-td-provider">{{ vendorLabel(m.vendor) }}</td>
                <td class="models-td-price">{{ fmtPrice(m.input_cost_per_token) }}</td>
                <td class="models-td-price">{{ fmtPrice(m.output_cost_per_token) }}</td>
                <td class="models-td-action">
                  <button v-if="m.custom" class="models-remove-btn" @click="removeModel(m.id)" title="删除">×</button>
                </td>
              </tr>
              <tr v-if="!sortedMyModels.length">
                <td colspan="6" class="models-empty">无匹配模型</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="btn-group" style="margin-top:16px">
          <button class="btn btn-primary" @click="saveMyModels" :disabled="saving">{{ saving ? '保存中…' : '保存配置' }}</button>
          <span v-if="savedMsg" class="models-save-msg">{{ savedMsg }}</span>
        </div>
      </div>
    </div>

    <!-- Tab 2: Library -->
    <div v-if="activeTab === 'library'" class="models-panel">
      <div class="history-toolbar">
        <div class="search-input-wrap">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input class="form-input" v-model="libSearch" placeholder="搜索模型名…" @input="debouncedLoadLibrary" autocomplete="off">
        </div>
        <div class="search-input-wrap" style="max-width:200px">
          <input class="form-input" v-model="libVendor" placeholder="按厂商过滤…" @input="debouncedLoadLibrary" autocomplete="off">
        </div>
        <span class="models-count" style="margin-left:auto">共 {{ libTotal }} 个模型</span>
      </div>

      <div class="card" style="width:100%">
        <div v-if="libLoading" class="models-loading">加载中…</div>
        <div v-else class="models-table-wrap">
          <table class="models-table">
            <thead>
              <tr>
                <th class="models-th-name">模型名</th>
                <th class="models-th-provider">厂商</th>
                <th class="models-th-price">输入价格</th>
                <th class="models-th-price">输出价格</th>
                <th style="width:80px">Max Tokens</th>
                <th class="models-th-action">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in libModels" :key="m.id">
                <td class="models-td-name" :title="m.id">{{ m.id }}</td>
                <td class="models-td-provider">{{ m.provider || '-' }}</td>
                <td class="models-td-price">{{ fmtPrice(m.input_cost_per_token) }}</td>
                <td class="models-td-price">{{ fmtPrice(m.output_cost_per_token) }}</td>
                <td style="font-size:11px;font-family:var(--font-mono)">{{ m.max_input_tokens ? fmtNum(m.max_input_tokens) : '-' }}</td>
                <td class="models-td-action">
                  <button v-if="myModelIds.has(m.id)" class="btn btn-ghost btn-sm" disabled style="opacity:0.5">已添加</button>
                  <button v-else class="btn btn-ghost btn-sm" @click="addFromLibrary(m)">添加</button>
                </td>
              </tr>
              <tr v-if="!libModels.length">
                <td colspan="6" class="models-empty">无匹配模型</td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- Pagination -->
        <div v-if="libTotal > libPageSize" class="models-pagination">
          <button class="btn btn-ghost btn-sm" :disabled="libPage <= 1" @click="libPage--; loadLibrary()">上一页</button>
          <span class="models-page-info">第 {{ libPage }} / {{ Math.ceil(libTotal / libPageSize) }} 页</span>
          <button class="btn btn-ghost btn-sm" :disabled="libPage * libPageSize >= libTotal" @click="libPage++; loadLibrary()">下一页</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { getModelsConfig, putModelsConfig, getLibrary, getVendors } from '../api';
import { toast } from '../composables/useToast';

const activeTab = ref('my');

// ---- Shared ----
const vendors = ref([]);

function vendorLabel(vendorId) {
  const v = vendors.value.find(v => v.id === vendorId);
  return v ? v.name : vendorId || '-';
}

function fmtPrice(v) {
  if (!v) return '-';
  return '$' + (v * 1000000).toFixed(2) + '/M';
}

function fmtNum(v) {
  if (v >= 1000000) return (v / 1000000).toFixed(1) + 'M';
  if (v >= 1000) return (v / 1000).toFixed(0) + 'K';
  return String(v);
}

// ---- Tab 1: My Models ----
const myLoading = ref(true);
const saving = ref(false);
const savedMsg = ref('');
const mySearch = ref('');
const myVendor = ref('');
const sortKey = ref('id');
const sortDir = ref('asc');
const showAddForm = ref(false);
const addForm = ref({ id: '', vendor: '' });

const myModels = ref([]);
const myModelIds = computed(() => new Set(myModels.value.map(m => m.id)));
const enabledCount = computed(() => myModels.value.filter(m => m.enabled).length);

const filteredMyModels = computed(() => {
  let list = myModels.value;
  const q = mySearch.value.toLowerCase().trim();
  if (q) list = list.filter(m => m.id.toLowerCase().includes(q));
  if (myVendor.value) list = list.filter(m => m.vendor === myVendor.value);
  return list;
});

const sortedMyModels = computed(() => {
  const list = [...filteredMyModels.value];
  return list.sort((a, b) => {
    let va, vb;
    switch (sortKey.value) {
      case 'id': va = a.id; vb = b.id; break;
      case 'vendor': va = a.vendor || ''; vb = b.vendor || ''; break;
      default: return 0;
    }
    const cmp = va.localeCompare(vb);
    return sortDir.value === 'asc' ? cmp : -cmp;
  });
});

const visibleIds = computed(() => sortedMyModels.value.map(m => m.id));
const allVisibleEnabled = computed(() =>
  visibleIds.value.length > 0 && visibleIds.value.every(id => {
    const m = myModels.value.find(m => m.id === id);
    return m?.enabled;
  })
);
const someVisibleEnabled = computed(() =>
  visibleIds.value.some(id => {
    const m = myModels.value.find(m => m.id === id);
    return m?.enabled;
  })
);

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc';
  } else {
    sortKey.value = key;
    sortDir.value = 'asc';
  }
}

function toggleModel(id) {
  const m = myModels.value.find(m => m.id === id);
  if (m) m.enabled = !m.enabled;
}

function toggleVisible() {
  const target = !allVisibleEnabled.value;
  for (const id of visibleIds.value) {
    const m = myModels.value.find(m => m.id === id);
    if (m) m.enabled = target;
  }
}

function addCustomModel() {
  const id = addForm.value.id.trim();
  if (!id) return;
  if (myModels.value.some(m => m.id === id)) {
    toast('模型已存在', 'error');
    return;
  }
  myModels.value.push({
    id,
    vendor: addForm.value.vendor,
    enabled: true,
    custom: true,
  });
  addForm.value = { id: '', vendor: '' };
}

function removeModel(id) {
  myModels.value = myModels.value.filter(m => m.id !== id);
}

async function saveMyModels() {
  saving.value = true;
  savedMsg.value = '';
  try {
    await putModelsConfig({
      vendors: vendors.value,
      models: myModels.value,
    });
    savedMsg.value = `已保存 ${myModels.value.length} 个模型`;
    toast('模型配置已保存', 'success');
    setTimeout(() => savedMsg.value = '', 3000);
  } catch (e) {
    toast('保存失败: ' + e.message, 'error');
  }
  saving.value = false;
}

// ---- Tab 2: Library ----
const libLoading = ref(false);
const libSearch = ref('');
const libVendor = ref('');
const libModels = ref([]);
const libTotal = ref(0);
const libPage = ref(1);
const libPageSize = 50;

let libTimer = null;
function debouncedLoadLibrary() {
  clearTimeout(libTimer);
  libTimer = setTimeout(() => { libPage.value = 1; loadLibrary(); }, 300);
}

async function loadLibrary() {
  libLoading.value = true;
  try {
    const data = await getLibrary({
      search: libSearch.value,
      vendor: libVendor.value,
      page: libPage.value,
      pageSize: libPageSize,
    });
    libModels.value = data.models || [];
    libTotal.value = data.total || 0;
  } catch (e) {
    toast('加载模型库失败: ' + e.message, 'error');
  }
  libLoading.value = false;
}

function addFromLibrary(model) {
  if (myModels.value.some(m => m.id === model.id)) return;

  // 尝试从 litellm_provider 推断 vendor
  let vendor = '';
  const provider = (model.provider || '').toLowerCase();
  for (const v of vendors.value) {
    if (provider.includes(v.id)) {
      vendor = v.id;
      break;
    }
  }

  myModels.value.push({
    id: model.id,
    vendor,
    enabled: true,
  });
  toast(`已添加 ${model.id}`, 'success');
}

// ---- Init ----
onMounted(async () => {
  try {
    const [configRes, vendorsRes] = await Promise.all([
      getModelsConfig(),
      getVendors(),
    ]);
    vendors.value = vendorsRes.vendors || [];
    myModels.value = configRes.models || [];
  } catch (e) {
    toast('加载失败: ' + e.message, 'error');
  }
  myLoading.value = false;
});
</script>

<style scoped>
/* ---- Tab Navigation ---- */
.models-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 20px;
}

.models-tab {
  padding: 10px 20px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.models-tab:hover {
  color: var(--text-primary);
}

.models-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.models-panel {
  animation: fadeIn 0.15s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ---- Pagination ---- */
.models-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--border-subtle);
}

.models-page-info {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}
</style>
```

- [ ] **提交**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && git add frontend/src/views/ModelsView.vue
git commit -m "feat: ModelsView 改为双 Tab — 我的模型 + 模型库"
```

---

## Task 8: 端到端验证 + 清理

**Files:**
- Modify: `app/pricing.py` (清理死代码)

### Step 1: 运行全部后端测试

- [ ] **运行全部 pytest**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m pytest tests/ -v --timeout=30
```

Expected: 全部 PASS。如果有旧测试引用了被删除的 `get_models_by_provider` / `get_enabled_models` / `save_enabled_models`，需修复。

### Step 2: 运行全部前端测试

- [ ] **运行全部 vitest**

```bash
cd /Users/yakun/linkingrid/AITokenPerf/frontend && npx vitest run
```

Expected: 全部 PASS

### Step 3: 清理 pricing.py 死代码

- [ ] **确认 `pricing.py` 中以下内容已删除：**

- `PROVIDER_MODEL_KEYWORDS` 字典
- `_MODELS_CONFIG_PATH` 常量
- `get_models_by_provider` 方法
- `get_enabled_models` 方法
- `save_enabled_models` 方法

如果 Task 2 中已删除则跳过。

### Step 4: 启动开发服务器做手动验证

- [ ] **启动后端**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && python -m app.server &
```

- [ ] **启动前端**

```bash
cd /Users/yakun/linkingrid/AITokenPerf/frontend && bun run dev
```

- [ ] **手动验证 checklist：**

1. 打开模型管理页 → 看到"我的模型"Tab，默认种子模型已加载
2. 切到"模型库"Tab → 看到 LiteLLM 全量数据，可搜索、可翻页
3. 从模型库中添加一个模型 → 切回"我的模型"Tab 确认已添加
4. 新建站点 → 看到 ModelSelector 组件，厂商 chips 过滤正常，手动输入模型 ID 正常
5. 编辑已有站点 → 模型列表正确加载，可增删
6. 保存配置 → 刷新后数据保持

- [ ] **最终提交**

```bash
cd /Users/yakun/linkingrid/AITokenPerf && git add -A
git commit -m "chore: 模型管理整改 — 清理死代码，端到端验证通过"
```

---

## Task Summary

| Task | Description | Dependencies |
|------|-------------|-------------|
| 1 | 内置模型数据层 (`builtin_models.py`) | None |
| 2 | 后端 API 端点改造 | Task 1 |
| 3 | 前端 API 客户端更新 | Task 2 |
| 4 | ModelSelector 通用组件 | Task 3 |
| 5 | SitesView 新建站点弹窗改造 | Task 4 |
| 6 | SiteConfigTab 站点编辑改造 | Task 4 |
| 7 | ModelsView 双 Tab 重写 | Task 3 |
| 8 | 端到端验证 + 清理 | Task 5, 6, 7 |

Tasks 5, 6, 7 可以并行执行（都依赖 Task 4，互不依赖）。
