# Validates REQ-d00066-A, REQ-d00066-B, REQ-d00066-C, REQ-d00066-D
# Validates REQ-d00066-E, REQ-d00066-F, REQ-d00066-G
"""Tests for _get_assertion_test_map() MCP server function.

Tests the per-assertion test coverage map used to drive validation
buttons in the file viewer UI. Covers all edge-traversal patterns:
  - Pattern 1: REQ->TEST edges with assertion_targets (targeted coverage)
  - Pattern 2: ASSERTION->TEST edges (fixture pattern)
  - Indirect: REQ->TEST edges without assertion_targets (covers all)

Verifies deduplication, coverage stats, and test result inclusion.
"""

from pathlib import Path

import pytest

from elspais.graph import EdgeKind, GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import SourceLocation

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def assertion_map_graph():
    """Create a TraceGraph with diverse assertion-to-test relationships.

    Structure:
      REQ-p00001 (3 assertions: A, B, C)
        - assertion_a linked to test_node via Pattern 2 (ASSERTION->TEST)
        - req_node linked to test_node2 via Pattern 1 with assertion_targets=["B"]
        - req_node linked to test_node3 via indirect (no assertion_targets, covers all)
        - Each test has a TEST_RESULT child

      REQ-p00002 (1 assertion: A, no tests)
    """
    graph = TraceGraph(repo_root=Path("/test/repo"))

    # -- REQ-p00001 with three assertions --
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

    # -- Pattern 2: ASSERTION->TEST edge (assertion_a -> test_node) --
    test_node = GraphNode(
        id="test:test_encryption.py::test_data_encrypted",
        kind=NodeKind.TEST,
        label="test_data_encrypted",
        source=SourceLocation(path="tests/test_encryption.py", line=10),
    )
    test_node._content = {"file": "tests/test_encryption.py", "name": "test_data_encrypted"}
    assertion_a.link(test_node, EdgeKind.VALIDATES)

    result_node = GraphNode(
        id="result:test_encryption.py::test_data_encrypted",
        kind=NodeKind.TEST_RESULT,
        label="passed",
    )
    result_node._content = {"status": "passed", "duration": 0.5}
    test_node.add_child(result_node)

    # -- Pattern 1: REQ->TEST edge with assertion_targets=["B"] --
    test_node2 = GraphNode(
        id="test:test_tls.py::test_tls_version",
        kind=NodeKind.TEST,
        label="test_tls_version",
        source=SourceLocation(path="tests/test_tls.py", line=25),
    )
    test_node2._content = {"file": "tests/test_tls.py", "name": "test_tls_version"}
    req_node.link(test_node2, EdgeKind.VALIDATES, assertion_targets=["B"])

    result_node2 = GraphNode(
        id="result:test_tls.py::test_tls_version",
        kind=NodeKind.TEST_RESULT,
        label="failed",
    )
    result_node2._content = {"status": "failed", "duration": 1.2}
    test_node2.add_child(result_node2)

    # -- Indirect: REQ->TEST edge WITHOUT assertion_targets (covers all) --
    test_node3 = GraphNode(
        id="test:test_security.py::test_full_security_suite",
        kind=NodeKind.TEST,
        label="test_full_security_suite",
        source=SourceLocation(path="tests/test_security.py", line=42),
    )
    test_node3._content = {"file": "tests/test_security.py", "name": "test_full_security_suite"}
    req_node.link(test_node3, EdgeKind.VALIDATES)

    result_node3 = GraphNode(
        id="result:test_security.py::test_full_security_suite",
        kind=NodeKind.TEST_RESULT,
        label="passed",
    )
    result_node3._content = {"status": "passed", "duration": 3.1}
    test_node3.add_child(result_node3)

    # -- REQ-p00002: one assertion, no tests --
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

    # Register all nodes in the graph index
    graph._index = {
        "REQ-p00001": req_node,
        "REQ-p00001-A": assertion_a,
        "REQ-p00001-B": assertion_b,
        "REQ-p00001-C": assertion_c,
        "REQ-p00002": req_node2,
        "REQ-p00002-A": assertion_d,
        "test:test_encryption.py::test_data_encrypted": test_node,
        "result:test_encryption.py::test_data_encrypted": result_node,
        "test:test_tls.py::test_tls_version": test_node2,
        "result:test_tls.py::test_tls_version": result_node2,
        "test:test_security.py::test_full_security_suite": test_node3,
        "result:test_security.py::test_full_security_suite": result_node3,
    }
    graph._roots = [req_node, req_node2]

    return graph


# -----------------------------------------------------------------------------
# Tests for _get_assertion_test_map()
# -----------------------------------------------------------------------------


class TestGetAssertionTestMap:
    """Tests for _get_assertion_test_map() per-assertion coverage mapping."""

    def test_REQ_d00066_A_requirement_not_found_returns_error(self, assertion_map_graph):
        """REQ-d00066-A: SHALL return error when requirement is not found in the graph."""
        from elspais.mcp.server import _get_assertion_test_map

        result = _get_assertion_test_map(assertion_map_graph, "REQ-nonexistent")

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_REQ_d00066_B_requirement_with_no_assertions(self, assertion_map_graph):
        """REQ-d00066-B: SHALL return empty assertion_tests for requirement with no assertions."""
        from elspais.mcp.server import _get_assertion_test_map

        # Add a bare requirement with no assertion children
        bare_req = GraphNode(
            id="REQ-p00099",
            kind=NodeKind.REQUIREMENT,
            label="Empty Requirement",
        )
        bare_req._content = {"level": "PRD", "status": "Active", "hash": "00000000"}
        assertion_map_graph._index["REQ-p00099"] = bare_req

        result = _get_assertion_test_map(assertion_map_graph, "REQ-p00099")

        assert result["success"] is True
        assert result["assertion_tests"] == {}
        assert result["total_assertions"] == 0
        assert result["covered_count"] == 0
        assert result["coverage_pct"] == 0.0

    def test_REQ_d00066_C_assertions_with_no_tests(self, assertion_map_graph):
        """REQ-d00066-C: SHALL return empty test lists for assertions with no coverage."""
        from elspais.mcp.server import _get_assertion_test_map

        result = _get_assertion_test_map(assertion_map_graph, "REQ-p00002")

        assert result["success"] is True
        assert result["total_assertions"] == 1
        assert "A" in result["assertion_tests"]
        assert result["assertion_tests"]["A"]["assertion_id"] == "REQ-p00002-A"
        assert result["assertion_tests"]["A"]["tests"] == []
        assert result["covered_count"] == 0
        assert result["coverage_pct"] == 0.0

    def test_REQ_d00066_D_pattern1_targeted_assertion_coverage(self, assertion_map_graph):
        """REQ-d00066-D: Pattern 1 - REQ->TEST with assertion_targets."""
        from elspais.mcp.server import _get_assertion_test_map

        result = _get_assertion_test_map(assertion_map_graph, "REQ-p00001")

        # test_node2 (test_tls_version) was linked with assertion_targets=["B"]
        # It should appear under assertion B but NOT under A or C (except via indirect)
        b_tests = result["assertion_tests"]["B"]["tests"]
        b_ids = [t["id"] for t in b_tests]
        assert "test:test_tls.py::test_tls_version" in b_ids

    def test_REQ_d00066_E_pattern2_assertion_to_test_edge(self, assertion_map_graph):
        """REQ-d00066-E: Pattern 2 - ASSERTION->TEST edge links test to specific assertion."""
        from elspais.mcp.server import _get_assertion_test_map

        result = _get_assertion_test_map(assertion_map_graph, "REQ-p00001")

        # test_node (test_data_encrypted) was linked via assertion_a.link()
        a_tests = result["assertion_tests"]["A"]["tests"]
        a_ids = [t["id"] for t in a_tests]
        assert "test:test_encryption.py::test_data_encrypted" in a_ids

    def test_REQ_d00066_F_indirect_coverage_covers_all_assertions(self, assertion_map_graph):
        """REQ-d00066-F: Indirect - REQ->TEST without assertion_targets covers ALL assertions."""
        from elspais.mcp.server import _get_assertion_test_map

        result = _get_assertion_test_map(assertion_map_graph, "REQ-p00001")

        # test_node3 (test_full_security_suite) was linked without assertion_targets
        # It should appear in ALL assertion buckets (A, B, C)
        indirect_id = "test:test_security.py::test_full_security_suite"
        for label in ("A", "B", "C"):
            ids = [t["id"] for t in result["assertion_tests"][label]["tests"]]
            assert indirect_id in ids, f"Indirect test should appear under assertion {label}"

    def test_REQ_d00066_G_test_results_included(self, assertion_map_graph):
        """REQ-d00066-G: SHALL include test results in each test entry."""
        from elspais.mcp.server import _get_assertion_test_map

        result = _get_assertion_test_map(assertion_map_graph, "REQ-p00001")

        # Find test_data_encrypted under assertion A
        a_tests = result["assertion_tests"]["A"]["tests"]
        encryption_test = next(
            t for t in a_tests if t["id"] == "test:test_encryption.py::test_data_encrypted"
        )
        assert len(encryption_test["results"]) == 1
        assert encryption_test["results"][0]["status"] == "passed"
        assert encryption_test["results"][0]["duration"] == 0.5

        # Find test_tls_version under assertion B
        b_tests = result["assertion_tests"]["B"]["tests"]
        tls_test = next(t for t in b_tests if t["id"] == "test:test_tls.py::test_tls_version")
        assert len(tls_test["results"]) == 1
        assert tls_test["results"][0]["status"] == "failed"
        assert tls_test["results"][0]["duration"] == 1.2

    def test_REQ_d00066_A_coverage_stats_correct(self, assertion_map_graph):
        """REQ-d00066-A: SHALL compute correct coverage statistics."""
        from elspais.mcp.server import _get_assertion_test_map

        result = _get_assertion_test_map(assertion_map_graph, "REQ-p00001")

        # All 3 assertions (A, B, C) have at least one test via indirect coverage
        assert result["total_assertions"] == 3
        assert result["covered_count"] == 3
        assert result["coverage_pct"] == 100.0

    def test_REQ_d00066_B_coverage_stats_partial(self, assertion_map_graph):
        """REQ-d00066-B: SHALL compute correct partial coverage when some assertions lack tests."""
        from elspais.mcp.server import _get_assertion_test_map

        result = _get_assertion_test_map(assertion_map_graph, "REQ-p00002")

        assert result["total_assertions"] == 1
        assert result["covered_count"] == 0
        assert result["coverage_pct"] == 0.0

    def test_REQ_d00066_C_deduplication_same_test_via_both_patterns(self, assertion_map_graph):
        """REQ-d00066-C: SHALL deduplicate when same test reached via multiple patterns."""
        from elspais.mcp.server import _get_assertion_test_map

        # Link test_node (already under assertion A via Pattern 2) also via
        # Pattern 1 with assertion_targets=["A"] to create a duplicate path
        req_node = assertion_map_graph._index["REQ-p00001"]
        test_node = assertion_map_graph._index["test:test_encryption.py::test_data_encrypted"]
        req_node.link(test_node, EdgeKind.VALIDATES, assertion_targets=["A"])

        result = _get_assertion_test_map(assertion_map_graph, "REQ-p00001")

        # test_data_encrypted should appear only ONCE under assertion A
        a_tests = result["assertion_tests"]["A"]["tests"]
        encryption_ids = [
            t["id"] for t in a_tests if t["id"] == "test:test_encryption.py::test_data_encrypted"
        ]
        assert (
            len(encryption_ids) == 1
        ), "Same test reached via both patterns should not be duplicated"

    def test_REQ_d00066_D_test_entry_fields(self, assertion_map_graph):
        """REQ-d00066-D: SHALL include id, label, file, line, and results in test entries."""
        from elspais.mcp.server import _get_assertion_test_map

        result = _get_assertion_test_map(assertion_map_graph, "REQ-p00001")

        # Check a test entry from Pattern 1 (test_tls_version under B)
        b_tests = result["assertion_tests"]["B"]["tests"]
        tls_test = next(t for t in b_tests if t["id"] == "test:test_tls.py::test_tls_version")
        assert tls_test["id"] == "test:test_tls.py::test_tls_version"
        assert tls_test["label"] == "test_tls_version"
        assert tls_test["file"] == "tests/test_tls.py"
        assert tls_test["line"] == 25
        assert isinstance(tls_test["results"], list)

    def test_REQ_d00066_E_response_structure(self, assertion_map_graph):
        """REQ-d00066-E: SHALL return correct top-level response structure."""
        from elspais.mcp.server import _get_assertion_test_map

        result = _get_assertion_test_map(assertion_map_graph, "REQ-p00001")

        assert result["success"] is True
        assert result["req_id"] == "REQ-p00001"
        assert isinstance(result["assertion_tests"], dict)
        assert isinstance(result["total_assertions"], int)
        assert isinstance(result["covered_count"], int)
        assert isinstance(result["coverage_pct"], float)

    def test_REQ_d00066_F_non_requirement_node_returns_error(self, assertion_map_graph):
        """REQ-d00066-F: SHALL return error when node exists but is not a requirement."""
        from elspais.mcp.server import _get_assertion_test_map

        result = _get_assertion_test_map(assertion_map_graph, "REQ-p00001-A")

        assert result["success"] is False
        assert "not a requirement" in result["error"]

    def test_REQ_d00066_G_assertion_labels_as_keys(self, assertion_map_graph):
        """REQ-d00066-G: SHALL use assertion labels (A, B, C) as keys in assertion_tests."""
        from elspais.mcp.server import _get_assertion_test_map

        result = _get_assertion_test_map(assertion_map_graph, "REQ-p00001")

        assert set(result["assertion_tests"].keys()) == {"A", "B", "C"}
        assert result["assertion_tests"]["A"]["assertion_id"] == "REQ-p00001-A"
        assert result["assertion_tests"]["B"]["assertion_id"] == "REQ-p00001-B"
        assert result["assertion_tests"]["C"]["assertion_id"] == "REQ-p00001-C"
