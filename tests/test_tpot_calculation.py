"""测试 RequestMetrics.tpot 计算（issue #29）。

回归点：TPOT 此前按 SSE delta 事件间隔均值计算，会被中转代理的 chunk 聚合
污染（delta 数 ≪ token 数 → TPOT 被系统性高估）。改为用 usage 的
output_tokens 当分母：(e2e - ttft) / (output_tokens - 1)。
"""

from app.client import RequestMetrics


def test_tpot_uses_output_tokens_not_delta_count():
    """有 output_tokens 时，按 token 数计算，不受 SSE delta(chunk) 数影响。"""
    m = RequestMetrics(request_id=1)
    m.start_time = 100.0
    m.first_token_time = 100.5      # ttft = 0.5
    m.end_time = 110.5              # e2e = 10.5，gen_time = 10.0
    m.output_tokens = 11           # (11-1)=10 → tpot = 10.0/10 = 1.0
    # 只有 2 个 delta 时间戳（chunk 聚合场景）：旧逻辑会得 0.1，被污染
    m.token_timestamps = [100.5, 100.6]

    assert m.tpot is not None
    assert abs(m.tpot - 1.0) < 1e-9, "应按 output_tokens 计算得 1.0，而非 delta 间隔的 0.1"


def test_tpot_falls_back_to_timestamps_when_no_output_tokens():
    """output_tokens 不可用（0）时，回退到 SSE 时间戳间隔均值（旧逻辑）。"""
    m = RequestMetrics(request_id=2)
    m.start_time = 100.0
    m.first_token_time = 100.5
    m.end_time = 101.0
    m.output_tokens = 0            # 不可用
    m.token_timestamps = [100.5, 100.7, 100.9]  # 间隔 0.2, 0.2 → 0.2

    assert m.tpot is not None
    assert abs(m.tpot - 0.2) < 1e-9


def test_tpot_none_when_single_token_and_no_intervals():
    """单 token 且无足够时间戳间隔时返回 None。"""
    m = RequestMetrics(request_id=3)
    m.start_time = 100.0
    m.first_token_time = 100.5
    m.end_time = 100.5
    m.output_tokens = 1
    m.token_timestamps = [100.5]

    assert m.tpot is None


def test_tpot_none_when_no_data():
    """既无 output_tokens 也无时间戳 → None。"""
    m = RequestMetrics(request_id=4)
    assert m.tpot is None


def test_tpot_guards_nonpositive_generation_time():
    """gen_time <= 0（首 token 与结束几乎同时）时不产生负/零除，回退时间戳。"""
    m = RequestMetrics(request_id=5)
    m.start_time = 100.0
    m.first_token_time = 105.0
    m.end_time = 105.0             # e2e - ttft = 0
    m.output_tokens = 5
    m.token_timestamps = [105.0, 105.3]  # 回退 → 0.3

    assert m.tpot is not None
    assert abs(m.tpot - 0.3) < 1e-9
