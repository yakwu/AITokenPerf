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
    assert len(models) >= 9
    ids = [m["id"] for m in models]
    assert any("claude" in mid for mid in ids)
    assert any("gpt" in mid for mid in ids)
    assert any("deepseek" in mid for mid in ids)

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

    models.append({"id": "my-custom-model", "vendor": "openai", "enabled": True, "custom": True})
    mgr.save_builtin_models({"vendors": vendors, "models": models})

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

    old_config = tmp_path / "models_config.json"
    old_config.write_text(json.dumps({
        "enabled_models": ["claude-opus-4-6", "gpt-5.2", "custom-xyz"],
        "updated_at": 1000
    }))

    mgr = BuiltinModelsManager(data_dir=tmp_path)
    models = mgr.get_builtin_models()
    ids = [m["id"] for m in models]

    assert "claude-opus-4-6" in ids
    assert "gpt-5.2" in ids
    assert "custom-xyz" in ids
    custom = next(m for m in models if m["id"] == "custom-xyz")
    assert custom.get("custom") is True

    claude_model = next(m for m in models if m["id"] == "claude-opus-4-6")
    assert claude_model["vendor"] == "anthropic"

    gpt_model = next(m for m in models if m["id"] == "gpt-5.2")
    assert gpt_model["vendor"] == "openai"

    assert custom["vendor"] == ""  # unknown model, no vendor guessed
