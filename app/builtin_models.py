"""内置模型管理 — 自维护的主流模型列表 + 厂商注册表"""

import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("builtin_models")

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

DEFAULT_MODELS = [
    {"id": "claude-opus-4-6", "vendor": "anthropic", "enabled": True},
    {"id": "claude-sonnet-4-6", "vendor": "anthropic", "enabled": True},
    {"id": "claude-haiku-4-5-20251001", "vendor": "anthropic", "enabled": True},
    {"id": "gpt-5.4", "vendor": "openai", "enabled": True},
    {"id": "gpt-5.3-codex", "vendor": "openai", "enabled": True},
    {"id": "gpt-5.2", "vendor": "openai", "enabled": True},
    {"id": "gemini-3-pro-preview", "vendor": "google", "enabled": True},
    {"id": "gemini-3-flash-lite-preview", "vendor": "google", "enabled": True},
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
        if self._json_path.exists():
            try:
                return json.loads(self._json_path.read_text(encoding="utf-8"))
            except Exception as e:
                log.warning("读取 %s 失败: %s", self._json_path, e)

        data = {
            "vendors": [dict(v) for v in DEFAULT_VENDORS],
            "models": [dict(m) for m in DEFAULT_MODELS],
        }

        if self._old_config_path.exists():
            data = self._migrate_old_config(data)

        self._save(data)
        return data

    def _migrate_old_config(self, data: dict) -> dict:
        try:
            old = json.loads(self._old_config_path.read_text(encoding="utf-8"))
            old_enabled = old.get("enabled_models", [])
            if not old_enabled:
                return data

            existing_ids = {m["id"] for m in data["models"]}
            for model in data["models"]:
                if model["id"] in old_enabled:
                    model["enabled"] = True

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
        if "command-r" in mid or "cohere" in mid:
            return "cohere"
        return ""

    def _save(self, data: Optional[dict] = None):
        if data is not None:
            self._data = data
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._json_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_vendors(self) -> list[dict]:
        return list(self._data.get("vendors", DEFAULT_VENDORS))

    def get_builtin_models(self, vendor: str = "", enabled_only: bool = False) -> list[dict]:
        models = list(self._data.get("models", []))
        if vendor:
            models = [m for m in models if m.get("vendor") == vendor]
        if enabled_only:
            models = [m for m in models if m.get("enabled")]
        return models

    def save_builtin_models(self, data: dict):
        self._save(data)

    def add_model(self, model_id: str, vendor: str = "", custom: bool = False):
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
        self._data["models"] = [
            m for m in self._data.get("models", []) if m["id"] != model_id
        ]
        self._save()

    def toggle_model(self, model_id: str):
        for m in self._data.get("models", []):
            if m["id"] == model_id:
                m["enabled"] = not m.get("enabled", True)
                break
        self._save()


builtin_models_manager = BuiltinModelsManager()
