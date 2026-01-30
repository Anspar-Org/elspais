"""Tests for MCP test coverage tools.

Tests REQ-o00064: MCP Test Coverage Tools
- get_test_coverage()
- get_uncovered_assertions()
- find_assertions_by_keywords()

All tests verify correct graph traversal for test-requirement analysis.
"""

from pathlib import Path

import pytest

from elspais.graph import EdgeKind, GraphNode, NodeKind
from elspais.graph.builder import TraceGraph

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def coverage_graph():
    """Create a TraceGraph with test coverage relationships."""
    graph = TraceGraph(repo_root=Path("/test/repo"))

    # Create requirement with assertions
    req_node = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Platform Security",
    )
    req_node._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "abc12345",
    }

    # Add assertions
    assertion_a = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="SHALL encrypt all data at rest",
    )
    assertion_a._content = {"label": "A", "text": "SHALL encrypt all data at rest"}
    req_node.add_child(assertion_a)

    assertion_b = GraphNode(
        id="REQ-p00001-B",
        kind=NodeKind.ASSERTION,
        label="SHALL use TLS 1.3 for transit",
    )
    assertion_b._content = {"label": "B", "text": "SHALL use TLS 1.3 for transit"}
    req_node.add_child(assertion_b)

    assertion_c = GraphNode(
        id="REQ-p00001-C",
        kind=NodeKind.ASSERTION,
        label="SHALL validate input parameters",
    )
    assertion_c._content = {"label": "C", "text": "SHALL validate input parameters"}
    req_node.add_child(assertion_c)

    # Create TEST node that references assertion A
    test_node = GraphNode(
        id="test:test_encryption.py::test_data_encrypted",
        kind=NodeKind.TEST,
        label="test_data_encrypted",
    )
    test_node._content = {"file": "test_encryption.py", "name": "test_data_encrypted"}

    # Link assertion to test (assertion has test as child with VALIDATES edge)
    assertion_a.link(test_node, EdgeKind.VALIDATES)

    # Create TEST_RESULT for the test
    result_node = GraphNode(
        id="result:test_encryption.py::test_data_encrypted",
        kind=NodeKind.TEST_RESULT,
        label="passed",
    )
    result_node._content = {"status": "passed", "duration": 0.5}
    test_node.add_child(result_node)

    # Add second requirement with no test coverage
    req_node2 = GraphNode(
        id="REQ-p00002",
        kind=NodeKind.REQUIREMENT,
        label="Performance Requirements",
    )
    req_node2._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "xyz98765",
    }

    assertion_d = GraphNode(
        id="REQ-p00002-A",
        kind=NodeKind.ASSERTION,
        label="SHALL respond within 100ms",
    )
    assertion_d._content = {"label": "A", "text": "SHALL respond within 100ms"}
    req_node2.add_child(assertion_d)

    # Register all nodes
    graph._index = {
        "REQ-p00001": req_node,
        "REQ-p00001-A": assertion_a,
        "REQ-p00001-B": assertion_b,
        "REQ-p00001-C": assertion_c,
        "REQ-p00002": req_node2,
        "REQ-p00002-A": assertion_d,
        "test:test_encryption.py::test_data_encrypted": test_node,
        "result:test_encryption.py::test_data_encrypted": result_node,
    }
    graph._roots = [req_node, req_node2]

    # Annotate keywords for keyword-based search
    from elspais.graph.annotators import annotate_keywords

    annotate_keywords(graph)

    return graph


# ─────────────────────────────────────────────────────────────────────────────
# Tests for get_test_coverage() - REQ-d00066
# ─────────────────────────────────────────────────────────────────────────────


class TestGetTestCoverage:
    """Tests for get_test_coverage() tool."""

    def test_REQ_d00066_A_finds_test_nodes_targeting_requirement(self, coverage_graph):
        """REQ-d00066-A: SHALL find TEST nodes by searching for edges targeting the requirement."""
        from elspais.mcp.server import _get_test_coverage

        result = _get_test_coverage(coverage_graph, "REQ-p00001")

        assert result["success"] is True
        assert len(result["test_nodes"]) == 1
        assert result["test_nodes"][0]["id"] == "test:test_encryption.py::test_data_encrypted"

    def test_REQ_d00066_B_returns_test_results(self, coverage_graph):
        """REQ-d00066-B: SHALL return TEST_RESULT nodes associated with found TEST nodes."""
        from elspais.mcp.server import _get_test_coverage

        result = _get_test_coverage(coverage_graph, "REQ-p00001")

        assert len(result["result_nodes"]) == 1
        assert result["result_nodes"][0]["status"] == "passed"

    def test_REQ_d00066_C_identifies_coverage_gaps(self, coverage_graph):
        """REQ-d00066-C: SHALL identify assertion coverage gaps."""
        from elspais.mcp.server import _get_test_coverage

        result = _get_test_coverage(coverage_graph, "REQ-p00001")

        # Assertion A is covered, B and C are not
        assert result["covered_assertions"] == ["REQ-p00001-A"]
        assert set(result["uncovered_assertions"]) == {"REQ-p00001-B", "REQ-p00001-C"}

    def test_REQ_d00066_D_returns_coverage_percentage(self, coverage_graph):
        """REQ-d00066-D: SHALL return coverage percentage and breakdown."""
        from elspais.mcp.server import _get_test_coverage

        result = _get_test_coverage(coverage_graph, "REQ-p00001")

        # 1 of 3 assertions covered = 33.3%
        assert result["total_assertions"] == 3
        assert result["covered_count"] == 1
        assert 33 <= result["coverage_pct"] <= 34

    def test_REQ_d00066_E_handles_no_test_coverage(self, coverage_graph):
        """REQ-d00066-E: SHALL handle requirements with no test coverage gracefully."""
        from elspais.mcp.server import _get_test_coverage

        result = _get_test_coverage(coverage_graph, "REQ-p00002")

        assert result["success"] is True
        assert result["test_nodes"] == []
        assert result["coverage_pct"] == 0
        assert result["uncovered_assertions"] == ["REQ-p00002-A"]


# ─────────────────────────────────────────────────────────────────────────────
# Tests for get_uncovered_assertions() - REQ-d00067
# ─────────────────────────────────────────────────────────────────────────────


class TestGetUncoveredAssertions:
    """Tests for get_uncovered_assertions() tool."""

    def test_REQ_d00067_A_iterates_all_assertions_when_no_req_id(self, coverage_graph):
        """REQ-d00067-A: SHALL iterate all ASSERTION nodes when req_id is None."""
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(coverage_graph, req_id=None)

        # Should find B, C from REQ-p00001 and A from REQ-p00002 (A from p00001 is covered)
        uncovered_ids = [a["id"] for a in result["assertions"]]
        assert "REQ-p00001-B" in uncovered_ids
        assert "REQ-p00001-C" in uncovered_ids
        assert "REQ-p00002-A" in uncovered_ids
        assert "REQ-p00001-A" not in uncovered_ids  # This one is covered

    def test_REQ_d00067_B_iterates_child_assertions_when_req_id_provided(self, coverage_graph):
        """REQ-d00067-B: SHALL iterate only child assertions when req_id is provided."""
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(coverage_graph, req_id="REQ-p00001")

        uncovered_ids = [a["id"] for a in result["assertions"]]
        assert "REQ-p00001-B" in uncovered_ids
        assert "REQ-p00001-C" in uncovered_ids
        # Should NOT include assertions from other requirements
        assert "REQ-p00002-A" not in uncovered_ids

    def test_REQ_d00067_D_returns_assertion_context(self, coverage_graph):
        """REQ-d00067-D: SHALL return assertion id, text, label, and parent requirement context."""
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(coverage_graph, req_id="REQ-p00001")

        assertion = next(a for a in result["assertions"] if a["id"] == "REQ-p00001-B")
        assert assertion["label"] == "B"
        assert "TLS" in assertion["text"]
        assert assertion["parent_id"] == "REQ-p00001"

    def test_REQ_d00067_E_sorts_by_parent_requirement(self, coverage_graph):
        """REQ-d00067-E: SHALL sort results by parent requirement for logical grouping."""
        from elspais.mcp.server import _get_uncovered_assertions

        result = _get_uncovered_assertions(coverage_graph, req_id=None)

        # Results should be grouped by parent
        parent_ids = [a["parent_id"] for a in result["assertions"]]
        # Check that same parent assertions are consecutive
        seen_parents = []
        for pid in parent_ids:
            if pid not in seen_parents:
                seen_parents.append(pid)
        # Should be sorted (p00001 before p00002)
        assert seen_parents == sorted(seen_parents)


# ─────────────────────────────────────────────────────────────────────────────
# Tests for find_assertions_by_keywords() - REQ-d00068
# ─────────────────────────────────────────────────────────────────────────────


class TestFindAssertionsByKeywords:
    """Tests for find_assertions_by_keywords() tool."""

    def test_REQ_d00068_A_searches_assertion_text(self, coverage_graph):
        """REQ-d00068-A: SHALL iterate ASSERTION nodes and check text content."""
        from elspais.mcp.server import _find_assertions_by_keywords

        result = _find_assertions_by_keywords(coverage_graph, keywords=["encrypt"])

        assert len(result["assertions"]) == 1
        assert result["assertions"][0]["id"] == "REQ-p00001-A"

    def test_REQ_d00068_B_match_all_true_requires_all_keywords(self, coverage_graph):
        """REQ-d00068-B: SHALL support match_all=True for AND logic."""
        from elspais.mcp.server import _find_assertions_by_keywords

        # Both keywords must match
        result = _find_assertions_by_keywords(
            coverage_graph, keywords=["encrypt", "data"], match_all=True
        )
        assert len(result["assertions"]) == 1

        # These won't both match
        result = _find_assertions_by_keywords(
            coverage_graph, keywords=["encrypt", "TLS"], match_all=True
        )
        assert len(result["assertions"]) == 0

    def test_REQ_d00068_C_match_all_false_accepts_any_keyword(self, coverage_graph):
        """REQ-d00068-C: SHALL support match_all=False for OR logic."""
        from elspais.mcp.server import _find_assertions_by_keywords

        result = _find_assertions_by_keywords(
            coverage_graph, keywords=["encrypt", "TLS"], match_all=False
        )

        # Should find both encryption and TLS assertions
        ids = [a["id"] for a in result["assertions"]]
        assert "REQ-p00001-A" in ids  # encrypt
        assert "REQ-p00001-B" in ids  # TLS

    def test_REQ_d00068_D_returns_assertion_context(self, coverage_graph):
        """REQ-d00068-D: SHALL return assertion id, text, label, and parent context."""
        from elspais.mcp.server import _find_assertions_by_keywords

        result = _find_assertions_by_keywords(coverage_graph, keywords=["validate"])

        assert len(result["assertions"]) == 1
        assertion = result["assertions"][0]
        assert assertion["id"] == "REQ-p00001-C"
        assert assertion["label"] == "C"
        assert "validate" in assertion["text"].lower()
        assert assertion["parent_id"] == "REQ-p00001"

    def test_REQ_d00068_E_case_insensitive_matching(self, coverage_graph):
        """REQ-d00068-E: SHALL normalize keywords to lowercase for case-insensitive matching."""
        from elspais.mcp.server import _find_assertions_by_keywords

        # Uppercase keyword should still match
        result = _find_assertions_by_keywords(coverage_graph, keywords=["ENCRYPT"])
        assert len(result["assertions"]) == 1

        result = _find_assertions_by_keywords(coverage_graph, keywords=["Tls"])
        assert len(result["assertions"]) == 1
