# Verifies: REQ-p00002-A
"""Tests for _check_status_references() in health checks.

Validates REQ-p00002-A: status-based reference checking detects CODE or TEST
nodes that reference requirements with retired, provisional, or aspirational
status roles, with configurable severity and exclude_status support.
"""
from __future__ import annotations

from pathlib import Path

from elspais.commands.health import _check_status_references
from elspais.config.status_roles import StatusRole
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import FileType, GraphNode, NodeKind
from elspais.graph.relations import EdgeKind


def _wrap(graph: TraceGraph) -> FederatedGraph:
    """Wrap a bare TraceGraph in a federation-of-one."""
    return FederatedGraph.from_single(graph, None, graph.repo_root or Path("/test/repo"))


# Default exclude_status matching the real default set
_DEFAULT_EXCLUDES = {
    "Draft",
    "Proposed",
    "Roadmap",
    "Future",
    "Idea",
    "Deprecated",
    "Superseded",
    "Rejected",
}


def _build_graph_with_ref(
    req_status: str,
    source_kind: NodeKind,
    edge_kind: EdgeKind = EdgeKind.IMPLEMENTS,
) -> TraceGraph:
    """Build a minimal graph with a CODE or TEST node referencing an assertion.

    Manually wires an outgoing traceability edge from the source node to
    the assertion, matching the direction _check_status_references expects.
    """
    # --- FILE + REQ + ASSERTION ---
    spec_file = GraphNode(id="file:spec/test.md", kind=NodeKind.FILE, label="test.md")
    spec_file.set_field("file_type", FileType.SPEC)
    spec_file.set_field("relative_path", "spec/test.md")
    spec_file.set_field("absolute_path", "/repo/spec/test.md")
    spec_file.set_field("repo", None)

    req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT, label="Test Req")
    req.set_field("level", "PRD")
    req.set_field("status", req_status)
    req.set_field("parse_line", 1)
    spec_file.link(req, EdgeKind.CONTAINS)

    assertion = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION, label="Assertion A")
    assertion.set_field("parse_line", 5)
    req.link(assertion, EdgeKind.STRUCTURES)

    # --- Source FILE + CODE/TEST node ---
    if source_kind == NodeKind.CODE:
        src_path = "src/module.py"
        ft = FileType.CODE
        node_id = "code:src/module.py:1"
    else:
        src_path = "tests/test_module.py"
        ft = FileType.TEST
        node_id = "test:tests/test_module.py::test_func"

    src_file = GraphNode(id=f"file:{src_path}", kind=NodeKind.FILE, label=Path(src_path).name)
    src_file.set_field("file_type", ft)
    src_file.set_field("relative_path", src_path)
    src_file.set_field("absolute_path", f"/repo/{src_path}")
    src_file.set_field("repo", None)

    source_node = GraphNode(id=node_id, kind=source_kind, label=node_id)
    source_node.set_field("parse_line", 1)
    src_file.link(source_node, EdgeKind.CONTAINS)

    # Wire traceability edge: assertion -> source (parent links child)
    # This matches how GraphBuilder wires edges: target.link(source, kind)
    assertion.link(source_node, edge_kind)

    # Assemble TraceGraph manually
    graph = TraceGraph()
    for node in (spec_file, req, assertion, src_file, source_node):
        graph._index[node.id] = node
    graph._roots.append(spec_file)
    graph._roots.append(src_file)

    return graph


class TestStatusReferenceChecks:
    """Validates REQ-p00002-A: status-based reference checks in health."""

    def test_REQ_p00002_A_code_retired_reference_detected(self) -> None:
        """CODE implementing a Deprecated REQ should produce a finding."""
        graph = _build_graph_with_ref("Deprecated", NodeKind.CODE)
        fg = _wrap(graph)
        check = _check_status_references(
            fg, NodeKind.CODE, StatusRole.RETIRED, "warning", exclude_status=_DEFAULT_EXCLUDES
        )
        assert not check.passed
        assert len(check.findings) == 1
        assert "REQ-p00001" in check.findings[0].message
        assert "retired" in check.findings[0].message

    def test_REQ_p00002_A_code_active_reference_no_finding(self) -> None:
        """CODE implementing an Active REQ should not produce a finding."""
        graph = _build_graph_with_ref("Active", NodeKind.CODE)
        fg = _wrap(graph)
        check = _check_status_references(
            fg, NodeKind.CODE, StatusRole.RETIRED, "warning", exclude_status=_DEFAULT_EXCLUDES
        )
        assert check.passed
        assert len(check.findings) == 0

    def test_REQ_p00002_A_test_provisional_reference_detected(self) -> None:
        """TEST verifying a Draft REQ should produce a finding (provisional role)."""
        graph = _build_graph_with_ref("Draft", NodeKind.TEST, edge_kind=EdgeKind.VERIFIES)
        fg = _wrap(graph)
        check = _check_status_references(
            fg, NodeKind.TEST, StatusRole.PROVISIONAL, "info", exclude_status=_DEFAULT_EXCLUDES
        )
        assert not check.passed
        assert len(check.findings) == 1
        assert "REQ-p00001" in check.findings[0].message
        assert "provisional" in check.findings[0].message

    def test_REQ_p00002_A_status_promoted_by_exclude_skips_check(self) -> None:
        """When Draft is NOT in exclude_status (promoted by --status), no finding."""
        graph = _build_graph_with_ref("Draft", NodeKind.CODE)
        fg = _wrap(graph)
        # Simulate --status Draft: remove Draft from excludes
        promoted_excludes = _DEFAULT_EXCLUDES - {"Draft"}
        check = _check_status_references(
            fg, NodeKind.CODE, StatusRole.PROVISIONAL, "info", exclude_status=promoted_excludes
        )
        assert check.passed
        assert len(check.findings) == 0

    def test_REQ_p00002_A_severity_from_config(self) -> None:
        """Verify the severity of the check matches the configured value."""
        graph = _build_graph_with_ref("Deprecated", NodeKind.CODE)
        fg = _wrap(graph)
        for severity in ("info", "warning", "error"):
            check = _check_status_references(
                fg, NodeKind.CODE, StatusRole.RETIRED, severity, exclude_status=_DEFAULT_EXCLUDES
            )
            assert check.severity == severity, f"Expected severity={severity}, got {check.severity}"
