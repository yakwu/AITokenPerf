"""测试 scheduler 中模型列表提取逻辑（configs_json.models 三级优先链）"""

import pytest


def _extract_models(configs_json: dict, config: dict, profile: dict) -> list[str]:
    """从 scheduler.py 提取出的模型提取函数，用于独立测试。
    优先级：configs_json.models → configs_json.model / config.model → profile.models
    """
    models = configs_json.get("models") or []
    if not models:
        raw_model = configs_json.get("model") or config.get("model", "")
        models = [raw_model] if raw_model else []
    if not models:
        models = profile.get("models", [])
    return models


def test_configs_json_models_takes_priority():
    """configs_json.models 最优先"""
    result = _extract_models(
        configs_json={"models": ["gpt-4", "claude-3"]},
        config={"model": "fallback"},
        profile={"models": ["a", "b", "c"]},
    )
    assert result == ["gpt-4", "claude-3"]


def test_fallback_to_configs_json_model():
    """老数据兼容：configs_json.model 单值"""
    result = _extract_models(
        configs_json={"model": "gpt-4"},
        config={"model": "other"},
        profile={"models": ["a", "b"]},
    )
    assert result == ["gpt-4"]


def test_fallback_to_config_model():
    """configs_json 里没有模型，用 config.model"""
    result = _extract_models(
        configs_json={},
        config={"model": "deepseek-v3"},
        profile={"models": ["a", "b"]},
    )
    assert result == ["deepseek-v3"]


def test_fallback_to_profile_models():
    """都没有，用 profile 全部模型"""
    result = _extract_models(
        configs_json={},
        config={},
        profile={"models": ["gpt-4", "claude-3", "gemini-pro"]},
    )
    assert result == ["gpt-4", "claude-3", "gemini-pro"]


def test_empty_everything():
    """全部为空返回空列表"""
    result = _extract_models(configs_json={}, config={}, profile={})
    assert result == []


def test_configs_json_models_empty_array():
    """configs_json.models 是空数组时 fall through"""
    result = _extract_models(
        configs_json={"models": []},
        config={"model": "fallback"},
        profile={"models": ["a"]},
    )
    assert result == ["fallback"]


def test_configs_json_model_empty_string():
    """configs_json.model 是空字符串时 fall through"""
    result = _extract_models(
        configs_json={"model": ""},
        config={"model": "deepseek"},
        profile={"models": ["a"]},
    )
    assert result == ["deepseek"]
