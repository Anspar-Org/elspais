# Verifies: REQ-d00085
"""Tests for gap data collection."""
from __future__ import annotations

from pathlib import Path

import pytest

from elspais.commands.gaps import collect_gaps
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import GraphNode, NodeKind  # noqa: N817
from elspais.graph.metrics import RollupMetrics


def _make_req(req_id: str, title: str, status: str = "Active") -> GraphNode:
    """Create a REQUIREMENT node with status set."""
    node = GraphNode(id=req_id, kind=NodeKind.REQUIREMENT, label=title)
    node.set_field("level", "prd")
    node.set_field("status", status)
    return node


def _make_graph(*nodes: GraphNode) -> FederatedGraph:
    """Wrap requirement nodes in a FederatedGraph for testing."""
    tg = TraceGraph()
    for node in nodes:
        tg._index[node.id] = node
        if node.kind == NodeKind.REQUIREMENT:
            tg._roots.append(node)
    return FederatedGraph.from_single(tg, config=None, repo_root=Path("."))


class TestCollectGaps:
    """Tests for collect_gaps() function."""

    @pytest.fixture
    def gap_graph(self) -> FederatedGraph:
        req1 = _make_req("REQ-p00001", "Covered Requirement", status="Active")
        req2 = _make_req("REQ-p00002", "Uncovered Requirement", status="Active")
        return _make_graph(req1, req2)

    def test_uncovered_finds_zero_coverage_reqs(self, gap_graph: FederatedGraph) -> None:
        """Both REQs have no code refs, so both appear in uncovered list."""
        data = collect_gaps(gap_graph, exclude_status=set())
        ids = {item[0] for item in data.uncovered}
        assert "REQ-p00001" in ids
        assert "REQ-p00002" in ids

    def test_untested_finds_zero_test_reqs(self, gap_graph: FederatedGraph) -> None:
        """Both REQs have no tests, so both appear in untested list."""
        data = collect_gaps(gap_graph, exclude_status=set())
        ids = {item[0] for item in data.untested}
        assert "REQ-p00001" in ids
        assert "REQ-p00002" in ids

    def test_exclude_status_filters(self, gap_graph: FederatedGraph) -> None:
        """Excluding Active status filters out both reqs (both are Active)."""
        data = collect_gaps(gap_graph, exclude_status={"Active"})
        assert len(data.uncovered) == 0
        assert len(data.untested) == 0
        assert len(data.unvalidated) == 0
        assert len(data.failing) == 0

    def test_covered_req_not_in_uncovered(self) -> None:
        """A requirement with coverage_pct > 0 is NOT in uncovered."""
        req = _make_req("REQ-p00001", "Covered")
        metrics = RollupMetrics(total_assertions=1, covered_assertions=1, coverage_pct=100.0)
        req.set_metric("rollup_metrics", metrics)
        graph = _make_graph(req)

        data = collect_gaps(graph, exclude_status=set())
        ids = {item[0] for item in data.uncovered}
        assert "REQ-p00001" not in ids

    def test_tested_req_not_in_untested(self) -> None:
        """A requirement with direct_tested > 0 is NOT in untested."""
        req = _make_req("REQ-p00001", "Tested")
        metrics = RollupMetrics(total_assertions=1, direct_tested=1)
        req.set_metric("rollup_metrics", metrics)
        graph = _make_graph(req)

        data = collect_gaps(graph, exclude_status=set())
        ids = {item[0] for item in data.untested}
        assert "REQ-p00001" not in ids

    def test_failing_test_collected(self) -> None:
        """A requirement with has_failures=True appears in failing with source 'test'."""
        req = _make_req("REQ-p00001", "Failing")
        metrics = RollupMetrics(total_assertions=1, has_failures=True)
        req.set_metric("rollup_metrics", metrics)
        graph = _make_graph(req)

        data = collect_gaps(graph, exclude_status=set())
        assert any(item[0] == "REQ-p00001" and item[2] == "test" for item in data.failing)

    def test_failing_uat_collected(self) -> None:
        """A requirement with uat_has_failures=True appears in failing with source 'uat'."""
        req = _make_req("REQ-p00001", "UAT Failing")
        metrics = RollupMetrics(total_assertions=1, uat_has_failures=True)
        req.set_metric("rollup_metrics", metrics)
        graph = _make_graph(req)

        data = collect_gaps(graph, exclude_status=set())
        assert any(item[0] == "REQ-p00001" and item[2] == "uat" for item in data.failing)
