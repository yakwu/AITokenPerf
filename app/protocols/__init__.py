#!/usr/bin/env python3
"""协议检测与适配器工厂"""


def detect_protocol(model_name: str, provider: str = "") -> str:
    """根据模型名和 provider 自动检测协议类型。

    返回 'anthropic', 'openai_responses', 或 'openai_chat'
    """
    # provider 优先
    if provider:
        p = provider.lower()
        if p == "anthropic":
            return "anthropic"
        if p == "openai":
            # OpenAI 的 gpt-5+, o3+ 走 responses
            model_lower = model_name.lower()
            if any(kw in model_lower for kw in ["gpt-5", "o3", "o4"]):
                return "openai_responses"
            return "openai_chat"
        # 其他 provider 默认走 OpenAI chat completions 兼容格式
        return "openai_chat"

    # 无 provider 时按模型名推断
    model_lower = model_name.lower()
    if any(kw in model_lower for kw in ["claude", "anthropic"]):
        return "anthropic"
    if any(kw in model_lower for kw in ["gpt-5", "o3", "o4"]):
        return "openai_responses"
    return "openai_chat"


def get_adapter(protocol: str):
    """根据协议名返回适配器实例"""
    if protocol == "anthropic":
        from app.protocols.anthropic import AnthropicAdapter
        return AnthropicAdapter()
    elif protocol == "openai_responses":
        from app.protocols.openai_responses import OpenAIResponsesAdapter
        return OpenAIResponsesAdapter()
    elif protocol == "openai_chat":
        from app.protocols.openai_chat import OpenAIChatAdapter
        return OpenAIChatAdapter()
    else:
        raise ValueError(f"Unknown protocol: {protocol}")
