# Implements: REQ-d00069-A
"""Tests for MCP UAT coverage tools."""
from tests.core.graph_test_helpers import build_graph, make_journey, make_requirement


def _make_uat_graph():
    req = make_requirement(
        "REQ-p00001",
        assertions=[
            {"label": "A", "text": "assertion A"},
            {"label": "B", "text": "assertion B"},
        ],
    )
    jny = make_journey("JNY-TST-001", validates=["REQ-p00001-A"])
    return build_graph(req, jny)


class TestGetTestCoverageUATSection:
    """Validates REQ-d00069-A: get_test_coverage returns uat section."""

    def test_get_test_coverage_includes_uat_section_REQ_d00069_A(self):
        """_get_test_coverage returns a 'uat' section alongside 'test' data."""
        from elspais.mcp.server import _get_test_coverage

        graph = _make_uat_graph()
        result = _get_test_coverage(graph, "REQ-p00001")
        assert result["success"] is True
        assert "uat" in result
        assert "coverage_pct" in result["uat"]
        assert "validated_pct" in result["uat"]

    def test_get_test_coverage_uat_coverage_pct_REQ_d00069_A(self):
        """uat.coverage_pct reflects JNY Validates coverage (1/2 assertions = 50%)."""
        from elspais.mcp.server import _get_test_coverage

        graph = _make_uat_graph()
        result = _get_test_coverage(graph, "REQ-p00001")
        assert result["uat"]["coverage_pct"] == 50.0

    def test_get_test_coverage_uat_has_jny_nodes_REQ_d00069_A(self):
        """uat section includes jny_nodes list."""
        from elspais.mcp.server import _get_test_coverage

        graph = _make_uat_graph()
        result = _get_test_coverage(graph, "REQ-p00001")
        assert "jny_nodes" in result["uat"]
        assert len(result["uat"]["jny_nodes"]) == 1


class TestGetUncoveredAssertionsSource:
    """Validates REQ-d00069-A: get_uncovered_assertions source parameter."""

    def test_uncovered_assertions_source_uat_REQ_d00069_A(self):
        """source='uat' returns UAT-uncovered assertions (B not covered by JNY)."""
        from elspais.mcp.server import _get_uncovered_assertions

        graph = _make_uat_graph()
        result = _get_uncovered_assertions(graph, req_id="REQ-p00001", source="uat")
        assert result["success"] is True
        labels = [a["label"] for a in result["uncovered_assertions"]]
        assert "B" in labels
        assert "A" not in labels  # A is covered by JNY

    def test_uncovered_assertions_default_source_is_test_REQ_d00069_A(self):
        """Default source='test' — JNY coverage doesn't count as test coverage."""
        from elspais.mcp.server import _get_uncovered_assertions

        graph = _make_uat_graph()
        result = _get_uncovered_assertions(graph, req_id="REQ-p00001", source="test")
        assert result["success"] is True
        labels = [a["label"] for a in result["uncovered_assertions"]]
        assert "A" in labels  # JNY doesn't count as automated test

    def test_uncovered_assertions_source_both_REQ_d00069_A(self):
        """source='both' — assertion covered by either test or JNY is not uncovered."""
        from elspais.mcp.server import _get_uncovered_assertions

        graph = _make_uat_graph()
        result = _get_uncovered_assertions(graph, req_id="REQ-p00001", source="both")
        assert result["success"] is True
        labels = [a["label"] for a in result["uncovered_assertions"]]
        assert "A" not in labels  # covered by JNY
        assert "B" in labels  # not covered by either
