# Verifies: REQ-d00085
"""Tests for gap data collection."""
from __future__ import annotations

from pathlib import Path

import pytest

from elspais.commands.gaps import (
    GapData,
    GapEntry,
    collect_gaps,
    render_gap_markdown,
    render_gap_text,
)
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
    """Wrap nodes in a FederatedGraph for testing.

    REQUIREMENT nodes are added as roots; all nodes are indexed.
    """
    tg = TraceGraph()
    for node in nodes:
        tg._index[node.id] = node
        if node.kind == NodeKind.REQUIREMENT:
            tg._roots.append(node)
        # Index children reachable from this node (e.g. linked CODE nodes)
        for child in node.iter_children():
            if child.id not in tg._index:
                tg._index[child.id] = child
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
        ids = {e.req_id for e in data.uncovered}
        assert "REQ-p00001" in ids
        assert "REQ-p00002" in ids

    def test_untested_finds_zero_test_reqs(self, gap_graph: FederatedGraph) -> None:
        """Both REQs have no tests, so both appear in untested list."""
        data = collect_gaps(gap_graph, exclude_status=set())
        ids = {e.req_id for e in data.untested}
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
        """A requirement with a CODE child is NOT in uncovered."""
        from elspais.graph import EdgeKind

        req = _make_req("REQ-p00001", "Covered")
        code = GraphNode(id="code:foo.py:10", kind=NodeKind.CODE, label="foo")
        req.link(code, EdgeKind.IMPLEMENTS)
        graph = _make_graph(req)

        data = collect_gaps(graph, exclude_status=set())
        ids = {e.req_id for e in data.uncovered}
        assert "REQ-p00001" not in ids

    def test_tested_req_not_in_untested(self) -> None:
        """A requirement with tested.direct > 0 is NOT in untested."""
        from elspais.graph.metrics import CoverageDimension

        req = _make_req("REQ-p00001", "Tested")
        metrics = RollupMetrics(
            total_assertions=1,
            tested=CoverageDimension(total=1, direct=1, indirect=1),
        )
        req.set_metric("rollup_metrics", metrics)
        graph = _make_graph(req)

        data = collect_gaps(graph, exclude_status=set())
        ids = {e.req_id for e in data.untested}
        assert "REQ-p00001" not in ids

    def test_failing_test_collected(self) -> None:
        """A requirement with verified.has_failures=True appears in failing with source 'test'."""
        from elspais.graph.metrics import CoverageDimension

        req = _make_req("REQ-p00001", "Failing")
        metrics = RollupMetrics(
            total_assertions=1,
            verified=CoverageDimension(total=1, has_failures=True),
        )
        req.set_metric("rollup_metrics", metrics)
        graph = _make_graph(req)

        data = collect_gaps(graph, exclude_status=set())
        assert any(item[0] == "REQ-p00001" and item[2] == "test" for item in data.failing)

    def test_failing_uat_collected(self) -> None:
        """uat_verified.has_failures=True appears in failing with source 'uat'."""
        from elspais.graph.metrics import CoverageDimension

        req = _make_req("REQ-p00001", "UAT Failing")
        metrics = RollupMetrics(
            total_assertions=1,
            uat_verified=CoverageDimension(total=1, has_failures=True),
        )
        req.set_metric("rollup_metrics", metrics)
        graph = _make_graph(req)

        data = collect_gaps(graph, exclude_status=set())
        assert any(item[0] == "REQ-p00001" and item[2] == "uat" for item in data.failing)

    def test_collect_gaps_includes_no_assertions(self) -> None:
        # Implements: REQ-d00204
        """A REQ with no ASSERTION children appears in no_assertions."""
        from elspais.graph import EdgeKind

        req_no_assert = _make_req("REQ-p00001", "No Assertions")
        req_with_assert = _make_req("REQ-p00002", "Has Assertions")
        assertion = GraphNode(id="REQ-p00002-A", kind=NodeKind.ASSERTION, label="Assertion A")
        req_with_assert.link(assertion, EdgeKind.STRUCTURES)
        graph = _make_graph(req_no_assert, req_with_assert)

        data = collect_gaps(graph, exclude_status=set())
        ids = {e.req_id for e in data.no_assertions}
        assert "REQ-p00001" in ids
        assert "REQ-p00002" not in ids


# ---- Rendering tests ----


class TestRenderGapText:
    """Tests for render_gap_text()."""

    def test_uncovered_section(self) -> None:
        data = GapData(uncovered=[
            GapEntry("REQ-p00001", "Login"), GapEntry("REQ-p00002", "Signup"),
        ])
        output = render_gap_text("uncovered", data)
        assert "UNCOVERED (no code refs)" in output
        assert "(2)" in output
        assert "REQ-p00001" in output
        assert "REQ-p00002" in output

    def test_empty_shows_none(self) -> None:
        data = GapData()
        output = render_gap_text("uncovered", data)
        assert "none" in output

    def test_failing_shows_source(self) -> None:
        data = GapData(failing=[("REQ-p00001", "Login", "test")])
        output = render_gap_text("failing", data)
        assert "[test]" in output
        assert "REQ-p00001" in output

    def test_untested_section(self) -> None:
        data = GapData(untested=[GapEntry("REQ-p00003", "Search")])
        output = render_gap_text("untested", data)
        assert "UNTESTED (no test coverage)" in output
        assert "(1)" in output

    def test_unvalidated_section(self) -> None:
        data = GapData(unvalidated=[GapEntry("REQ-p00004", "Payment")])
        output = render_gap_text("unvalidated", data)
        assert "UNVALIDATED (no UAT coverage)" in output

    def test_no_assertions_section(self) -> None:
        # Implements: REQ-d00204
        """no_assertions gap type renders with NOT TESTABLE label."""
        data = GapData(no_assertions=[GapEntry("REQ-p00005", "No Asserts")])
        output = render_gap_text("no_assertions", data)
        assert "NOT TESTABLE (no assertions)" in output
        assert "(1)" in output
        assert "REQ-p00005" in output

    def test_sorted_output(self) -> None:
        data = GapData(uncovered=[GapEntry("REQ-p00002", "B"), GapEntry("REQ-p00001", "A")])
        output = render_gap_text("uncovered", data)
        pos_a = output.index("REQ-p00001")
        pos_b = output.index("REQ-p00002")
        assert pos_a < pos_b

    def test_partial_gap_shows_assertions(self) -> None:
        """Partial gap (some assertions uncovered) shows assertion labels."""
        data = GapData(uncovered=[
            GapEntry("REQ-p00001", "Login", ["REQ-p00001-C", "REQ-p00001-D"]),
        ])
        output = render_gap_text("uncovered", data)
        assert "REQ-p00001" in output
        assert "[C, D]" in output


class TestRenderGapMarkdown:
    """Tests for render_gap_markdown()."""

    def test_uncovered_section(self) -> None:
        data = GapData(uncovered=[GapEntry("REQ-p00001", "Login")])
        output = render_gap_markdown("uncovered", data)
        assert "## UNCOVERED" in output
        assert "| REQ-p00001" in output
        assert "| Requirement | Title |" in output

    def test_empty_shows_no_gaps(self) -> None:
        data = GapData()
        output = render_gap_markdown("uncovered", data)
        assert "No gaps found" in output

    def test_failing_has_source_column(self) -> None:
        data = GapData(failing=[("REQ-p00001", "Login", "test")])
        output = render_gap_markdown("failing", data)
        assert "| Requirement | Source | Title |" in output
        assert "| REQ-p00001 | test | Login |" in output

    def test_markdown_table_format(self) -> None:
        data = GapData(uncovered=[GapEntry("REQ-p00001", "Login")])
        output = render_gap_markdown("uncovered", data)
        lines = output.strip().split("\n")
        # Header, separator, data row
        assert any("|---" in line for line in lines)


class TestRenderSection:
    """Tests for render_section()."""

    def test_text_format_all_gaps(self) -> None:
        from elspais.commands.gaps import render_section

        graph = _make_graph(_make_req("REQ-p00001", "Test"))
        output, exit_code = render_section(graph, {}, _make_args(format="text"))
        assert exit_code == 0
        assert "UNCOVERED" in output
        assert "UNTESTED" in output
        assert "UNVALIDATED" in output
        assert "FAILING" in output

    def test_markdown_format(self) -> None:
        from elspais.commands.gaps import render_section

        graph = _make_graph(_make_req("REQ-p00001", "Test"))
        output, exit_code = render_section(graph, {}, _make_args(format="markdown"))
        assert exit_code == 0
        assert "##" in output

    def test_json_format(self) -> None:
        import json

        from elspais.commands.gaps import render_section

        graph = _make_graph(_make_req("REQ-p00001", "Test"))
        output, exit_code = render_section(graph, {}, _make_args(format="json"))
        assert exit_code == 0
        parsed = json.loads(output)
        assert "uncovered" in parsed

    def test_specific_gap_types(self) -> None:
        from elspais.commands.gaps import render_section

        graph = _make_graph(_make_req("REQ-p00001", "Test"))
        output, exit_code = render_section(
            graph, {}, _make_args(format="text"), gap_types=["uncovered"]
        )
        assert "UNCOVERED" in output
        assert "UNTESTED" not in output


def _make_args(**kwargs: object) -> object:
    """Create a simple namespace with given attributes."""
    import argparse

    ns = argparse.Namespace()
    ns.format = kwargs.get("format", "text")
    ns.status = kwargs.get("status", None)
    ns.command = kwargs.get("command", "gaps")
    return ns


# ---- Composability tests ----


class TestGapComposability:
    def test_gap_sections_registered(self) -> None:
        from elspais.commands.report import COMPOSABLE_SECTIONS

        for name in ("uncovered", "untested", "unvalidated", "failing", "no_assertions", "gaps"):
            assert name in COMPOSABLE_SECTIONS

    def test_gap_format_support(self) -> None:
        from elspais.commands.report import FORMAT_SUPPORT

        for name in ("uncovered", "untested", "unvalidated", "failing", "no_assertions", "gaps"):
            assert "text" in FORMAT_SUPPORT[name]
            assert "markdown" in FORMAT_SUPPORT[name]
            assert "json" in FORMAT_SUPPORT[name]

    def test_checks_renamed_from_health(self) -> None:
        from elspais.commands.report import COMPOSABLE_SECTIONS

        assert "checks" in COMPOSABLE_SECTIONS
        assert "health" not in COMPOSABLE_SECTIONS
