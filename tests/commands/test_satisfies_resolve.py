# Validates REQ-p00014-E
"""Tests for the spec.satisfies_resolve health check.

Validates REQ-p00014-E: Satisfies references on a requirement must resolve to
an existing requirement or assertion. Unresolved targets are reported as
warnings (matching the severity of spec.implements_resolve and
spec.refines_resolve).
"""

from __future__ import annotations

from elspais.commands.health import (
    HealthFinding,
    check_spec_refines_resolve,
    check_spec_satisfies_resolve,
)
from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import GraphNode, NodeKind


def _make_requirement(graph: TraceGraph, req_id: str, label: str = "Req") -> GraphNode:
    """Insert a minimal REQUIREMENT node into the graph index."""
    node = GraphNode(id=req_id, kind=NodeKind.REQUIREMENT, label=label)
    node.set_field("level", "PRD")
    node.set_field("status", "Active")
    graph._index[req_id] = node
    return node


def _make_assertion(graph: TraceGraph, assertion_id: str, label: str = "Assertion") -> GraphNode:
    """Insert a minimal ASSERTION node into the graph index."""
    node = GraphNode(id=assertion_id, kind=NodeKind.ASSERTION, label=label)
    graph._index[assertion_id] = node
    return node


class TestSatisfiesResolve:
    """Validates REQ-p00014-E: Satisfies references must resolve to req or assertion."""

    # Implements: REQ-p00014-E
    def test_REQ_p00014_E_satisfies_resolves_to_existing_requirement(self) -> None:
        """A Satisfies target pointing to an existing REQ should pass."""
        graph = TraceGraph()
        _make_requirement(graph, "REQ-p00001", label="Template")
        node_b = _make_requirement(graph, "REQ-p00002", label="Concrete")
        node_b.set_field("satisfies", ["REQ-p00001"])

        check = check_spec_satisfies_resolve(graph)

        assert check.passed, f"Expected pass, got: {check.message}"
        assert check.name == "spec.satisfies_resolve"
        # On pass, severity defaults to "error" but check is passed; severity matters
        # most on failure. Match the sibling pass message style.
        assert check.category == "spec"

    # Implements: REQ-p00014-E
    def test_REQ_p00014_E_satisfies_resolves_to_existing_assertion(self) -> None:
        """A Satisfies target pointing to an assertion (REQ-x-A) should resolve.

        The function should accept assertion-shaped refs by splitting on the last
        hyphen and verifying the parent requirement exists, mirroring the
        Implements/Refines resolve checks.
        """
        graph = TraceGraph()
        _make_requirement(graph, "REQ-p00001", label="Template")
        _make_assertion(graph, "REQ-p00001-A", label="An assertion")
        node_b = _make_requirement(graph, "REQ-p00002", label="Concrete")
        node_b.set_field("satisfies", ["REQ-p00001-A"])

        check = check_spec_satisfies_resolve(graph)

        assert check.passed, f"Expected pass for assertion target, got: {check.message}"
        assert check.name == "spec.satisfies_resolve"

    # Implements: REQ-p00014-E
    def test_REQ_p00014_E_unresolved_satisfies_target_fails(self) -> None:
        """A Satisfies target that doesn't exist in the graph fails as a warning."""
        graph = TraceGraph()
        node_b = _make_requirement(graph, "REQ-p00002", label="Concrete")
        node_b.set_field("satisfies", ["REQ-NONEXISTENT"])

        check = check_spec_satisfies_resolve(graph)

        assert not check.passed, "Expected fail for unresolved Satisfies target"
        assert check.name == "spec.satisfies_resolve"
        assert (
            check.severity == "warning"
        ), f"Severity should match implements/refines (warning), got: {check.severity}"
        assert len(check.findings) >= 1
        finding = check.findings[0]
        assert isinstance(finding, HealthFinding)
        assert finding.node_id == "REQ-p00002"
        assert "REQ-NONEXISTENT" in (finding.related or [])
        # details payload should record the unresolved entry, mirroring siblings
        unresolved = check.details.get("unresolved", [])
        assert any(
            u.get("from") == "REQ-p00002" and u.get("to") == "REQ-NONEXISTENT" for u in unresolved
        ), f"Expected unresolved entry from=REQ-p00002 to=REQ-NONEXISTENT in details: {unresolved}"

    # Implements: REQ-p00014-E
    def test_REQ_p00014_E_mixed_resolved_and_unresolved(self) -> None:
        """When some Satisfies targets resolve and others don't, only the unresolved
        ones are reported and the check fails."""
        graph = TraceGraph()
        _make_requirement(graph, "REQ-p00001", label="Template")
        _make_assertion(graph, "REQ-p00001-A", label="An assertion")
        node_b = _make_requirement(graph, "REQ-p00002", label="Concrete")
        node_b.set_field(
            "satisfies",
            ["REQ-p00001", "REQ-NONEXISTENT", "REQ-p00001-A"],
        )

        check = check_spec_satisfies_resolve(graph)

        assert not check.passed, "Expected fail when at least one target is unresolved"
        assert check.severity == "warning"

        # Only one unresolved should be reported (REQ-NONEXISTENT)
        unresolved = check.details.get("unresolved", [])
        assert (
            len(unresolved) == 1
        ), f"Expected exactly one unresolved target, got {len(unresolved)}: {unresolved}"
        assert unresolved[0]["from"] == "REQ-p00002"
        assert unresolved[0]["to"] == "REQ-NONEXISTENT"

        # findings should reflect the same single failure
        assert len(check.findings) == 1
        finding = check.findings[0]
        assert finding.node_id == "REQ-p00002"
        assert "REQ-NONEXISTENT" in (finding.related or [])
        # The resolved targets should NOT appear anywhere in the failure surface
        assert "REQ-p00001-A" not in (finding.related or [])
        for u in unresolved:
            assert u["to"] != "REQ-p00001"
            assert u["to"] != "REQ-p00001-A"

    # Implements: REQ-p00014-E
    def test_REQ_p00014_E_no_satisfies_anywhere_passes(self) -> None:
        """A graph with no Satisfies references at all should pass cleanly."""
        graph = TraceGraph()
        _make_requirement(graph, "REQ-p00001", label="A")
        _make_requirement(graph, "REQ-p00002", label="B")
        # No satisfies field set on either node.

        check = check_spec_satisfies_resolve(graph)

        assert check.passed, f"Expected pass when no Satisfies refs exist, got: {check.message}"
        assert check.name == "spec.satisfies_resolve"
        assert len(check.findings) == 0
        # Pass message should be a non-empty success string (mirrors sibling format)
        assert check.message, "Pass message must not be empty"

    # Implements: REQ-p00014-E
    def test_REQ_p00014_E_severity_matches_refines_resolve(self) -> None:
        """The severity on a failed satisfies_resolve must match refines_resolve.

        Build two structurally-parallel graphs (one with an unresolved
        Refines target, one with an unresolved Satisfies target) and assert
        the failed checks report the same severity.
        """
        # Refines-shaped failure
        refines_graph = TraceGraph()
        rnode = _make_requirement(refines_graph, "REQ-p00010", label="Refines case")
        rnode.set_field("refines", ["REQ-MISSING"])
        refines_check = check_spec_refines_resolve(refines_graph)

        # Satisfies-shaped failure
        satisfies_graph = TraceGraph()
        snode = _make_requirement(satisfies_graph, "REQ-p00010", label="Satisfies case")
        snode.set_field("satisfies", ["REQ-MISSING"])
        satisfies_check = check_spec_satisfies_resolve(satisfies_graph)

        assert not refines_check.passed
        assert not satisfies_check.passed
        assert satisfies_check.severity == refines_check.severity, (
            f"satisfies_resolve severity {satisfies_check.severity!r} should match "
            f"refines_resolve severity {refines_check.severity!r}"
        )
        # And explicitly: warning, per REQ-p00014-E acceptance text.
        assert satisfies_check.severity == "warning"
