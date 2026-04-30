"""测试诊断数据模型"""

from app.diagnostics.models import ProbeResult, CategoryResult, DiagnosticReport


class TestProbeResult:
    def test_default_values(self):
        p = ProbeResult()
        assert p.name == ""
        assert p.status == "pending"
        assert p.latency_ms == 0
        assert p.ttft_ms is None

    def test_custom_values(self):
        p = ProbeResult(name="test", display_name="Test", status="passed", latency_ms=100.5)
        assert p.name == "test"
        assert p.status == "passed"
        assert p.latency_ms == 100.5


class TestCategoryResult:
    def test_default_values(self):
        c = CategoryResult()
        assert c.category == ""
        assert c.status == "pending"
        assert c.probes == []

    def test_with_probes(self):
        p = ProbeResult(name="p1", status="passed")
        c = CategoryResult(category="test", probes=[p])
        assert len(c.probes) == 1


class TestDiagnosticReport:
    def test_default_values(self):
        r = DiagnosticReport()
        assert r.overall_status == "pending"
        assert r.confidence == 0.0
        assert r.categories == []
