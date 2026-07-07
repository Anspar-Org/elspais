# Verifies: REQ-d00069-A, REQ-d00258-A
"""Tests for MCP UAT coverage tools."""
from elspais.graph.annotators import annotate_coverage
from tests.core.graph_test_helpers import (
    build_graph,
    make_code_ref,
    make_journey,
    make_requirement,
)


def _make_uat_graph():
    """REQ-p00001 with A IMPLEMENTED + UAT-validated (but untested), B bare.

    A is implemented so it is a genuine *testing* gap under the MCP surface's
    implemented-scoped denominator (REQ-d00258) -- UAT coverage does not satisfy
    the test axis. B is neither implemented nor validated.
    """
    req = make_requirement(
        "REQ-p00001",
        assertions=[
            {"label": "A", "text": "assertion A"},
            {"label": "B", "text": "assertion B"},
        ],
    )
    code = make_code_ref(implements=["REQ-p00001-A"], source_path="src/a.py")
    jny = make_journey("JNY-TST-001", validates=["REQ-p00001-A"])
    graph = build_graph(req, code, jny)
    annotate_coverage(graph)
    return graph


class TestGetTestCoverageUATSection:
    """Validates REQ-d00069-A: get_test_coverage returns uat section."""

    def test_get_test_coverage_includes_uat_section_REQ_d00069_A(self):
        """_get_test_coverage returns a 'uat' section alongside 'test' data."""
        from elspais.mcp.server import _get_test_coverage

        graph = _make_uat_graph()
        result = _get_test_coverage(graph, "REQ-p00001")
        assert result["success"] is True
        assert "uat" in result
        assert "referenced_pct" in result["uat"]
        assert "validated_pct" in result["uat"]

    def test_get_test_coverage_uat_referenced_pct_REQ_d00069_A(self):
        """uat.referenced_pct reflects JNY Validates coverage (1/2 assertions = 50%)."""
        from elspais.mcp.server import _get_test_coverage

        graph = _make_uat_graph()
        result = _get_test_coverage(graph, "REQ-p00001")
        assert result["uat"]["referenced_pct"] == 50.0

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
        assert "B" in result["uncovered_labels"]
        assert "A" not in result["uncovered_labels"]  # A is covered by JNY

    def test_uncovered_assertions_default_source_is_test_REQ_d00069_A(self):
        """Default source='test' — JNY coverage doesn't count as test coverage.

        A is IMPLEMENTED and UAT-validated but has no automated test, so it is a
        testing gap: UAT coverage does not satisfy the test axis (REQ-d00258).
        """
        from elspais.mcp.server import _get_uncovered_assertions

        graph = _make_uat_graph()
        result = _get_uncovered_assertions(graph, req_id="REQ-p00001", source="test")
        assert result["success"] is True
        assert "A" in result["uncovered_labels"]  # JNY doesn't count as automated test

    def test_uncovered_assertions_source_both_REQ_d00069_A(self):
        """source='both' — union of per-axis gaps (REQ-d00258).

        An assertion is uncovered under 'both' iff it is a testing gap
        (implemented AND untested) OR a UAT gap (unvalidated). A is a testing
        gap (implemented, untested) despite its UAT coverage, so it surfaces; B
        is a UAT gap (unvalidated). This is a union of GAPS, not of covered
        axes.
        """
        from elspais.mcp.server import _get_uncovered_assertions

        graph = _make_uat_graph()
        result = _get_uncovered_assertions(graph, req_id="REQ-p00001", source="both")
        assert result["success"] is True
        assert "A" in result["uncovered_labels"]  # testing gap: implemented, untested
        assert "B" in result["uncovered_labels"]  # UAT gap: unvalidated
