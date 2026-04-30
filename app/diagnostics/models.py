"""统一诊断数据模型"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProbeResult:
    """单个探针的结果"""
    name: str = ""
    display_name: str = ""
    status: str = "pending"  # pending | passed | failed | error | timeout | inconclusive
    latency_ms: float = 0
    ttft_ms: Optional[float] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    detail: str = ""
    error: Optional[str] = None
    response_preview: str = ""
    raw_usage: dict = field(default_factory=dict)
    request_preview: str = ""
    sent_chars: int = 0
    expected_system_tokens: int = 0
    expected_user_tokens: int = 0
    expected_total_tokens: int = 0
    identical_request: bool = False


@dataclass
class CategoryResult:
    """一个测试类别的结果"""
    category: str = ""
    display_name: str = ""
    status: str = "pending"  # passed | warning | failed | error
    probes: list = field(default_factory=list)  # list[ProbeResult]
    summary: dict = field(default_factory=dict)


@dataclass
class DiagnosticReport:
    """完整诊断报告"""
    categories: list = field(default_factory=list)  # list[CategoryResult]
    overall_status: str = "pending"
    overall_risk: str = "unknown"
    confidence: float = 0.0
    model: str = ""
    run_tag: str = ""
