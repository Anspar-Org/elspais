# Verifies: REQ-d00085, REQ-d00069-J
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

# ===========================================================================
# REQ-d00069-J: _uncovered_assertions carries per-assertion fractions so
# partially-conducted assertions (0 < fraction < 1) are distinguishable from
# assertions with no coverage at all (fraction 0.0).
# ===========================================================================


def test_uncovered_assertions_carry_fractions() -> None:
    """_uncovered_assertions returns (id, fraction) pairs.

    The canonical hht-like fixture has no REFINES-conduction scenario, so this
    builds the same minimal REFINES scenario used by the REQ-d00069-J
    conduction tests (tests/core/test_coverage_metrics.py::TestUserExample):
    REQ-100 has assertions A-D; REQ-010 refines REQ-100-A but has no coverage
    of its own; REQ-020 implements REQ-100-B directly; a test verifies both A
    and B. Under equal-weight conduction, A's fraction dilutes to 0.5 (direct
    test 1.0 averaged with the empty refiner's 0.0), B is fully covered (1.0,
    excluded from the gap list), and C/D remain at 0.0.
    """
    from elspais.commands.gaps import _uncovered_assertions
    from elspais.graph.annotators import annotate_coverage
    from elspais.graph.relations import EdgeKind
    from tests.core.graph_test_helpers import build_graph, make_requirement, make_test_ref

    graph = build_graph(
        make_requirement(
            "REQ-100",
            level="PRD",
            assertions=[{"label": lbl, "text": f"Assertion {lbl}"} for lbl in "ABCD"],
        ),
        make_requirement("REQ-010", level="OPS", refines=["REQ-100-A"]),
        make_requirement("REQ-020", level="OPS", implements=["REQ-100-B"]),
        make_test_ref(verifies=["REQ-100-A"], source_path="tests/test_a.py"),
        make_test_ref(verifies=["REQ-100-B"], source_path="tests/test_b.py"),
    )
    annotate_coverage(graph)

    node = graph.find_by_id("REQ-100")
    metrics = node.get_metric("rollup_metrics")
    assertion_nodes = [
        child
        for child in node.iter_children(edge_kinds={EdgeKind.STRUCTURES})
        if child.kind == NodeKind.ASSERTION
    ]

    uncov = _uncovered_assertions(metrics, assertion_nodes, "implemented")
    by_id = dict(uncov)

    partial = [(aid, f) for aid, f in uncov if 0 < f < 1]
    assert partial, "expected a partially-conducted assertion in fixture"
    assert by_id["REQ-100-A"] == 0.5
    assert "REQ-100-B" not in by_id  # fully covered (1.0) -- not a gap
    assert by_id["REQ-100-C"] == 0.0
    assert by_id["REQ-100-D"] == 0.0


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
    return FederatedGraph.from_single(
        tg, config={"project": {"name": "test", "namespace": "REQ"}}, repo_root=Path(".")
    )


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
        data = GapData(
            uncovered=[
                GapEntry("REQ-p00001", "Login"),
                GapEntry("REQ-p00002", "Signup"),
            ]
        )
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
        data = GapData(
            uncovered=[
                GapEntry(
                    "REQ-p00001",
                    "Login",
                    [("REQ-p00001-C", 0.0), ("REQ-p00001-D", 0.0)],
                ),
            ]
        )
        output = render_gap_text("uncovered", data)
        assert "REQ-p00001" in output
        assert "[C, D]" in output

    def test_partial_gap_shows_fraction_and_via(self) -> None:
        """A partially-conducted assertion (0 < fraction < 1, REQ-d00069-J) is
        annotated with its percentage and 'via refines-conduction' so it reads
        differently from an assertion with no coverage at all."""
        data = GapData(
            uncovered=[
                GapEntry(
                    "REQ-p00001",
                    "Login",
                    [("REQ-p00001-C", 0.4), ("REQ-p00001-D", 0.0)],
                ),
            ]
        )
        output = render_gap_text("uncovered", data)
        assert "% via refines-conduction" in output
        assert "40% via refines-conduction" in output
        # Fully-uncovered sibling still renders as a bare label
        assert ", D]" in output or "D]" in output


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

    def test_partial_fraction_annotated(self) -> None:
        """A partially-conducted assertion (REQ-d00069-J) shows its percentage
        and 'via refines-conduction' in the markdown table cell."""
        data = GapData(
            uncovered=[
                GapEntry("REQ-p00001", "Login", [("REQ-p00001-C", 0.4)]),
            ]
        )
        output = render_gap_markdown("uncovered", data)
        assert "40% via refines-conduction" in output


class TestGapEntrySerialization:
    """Round-trip tests for the JSON serialization of GapEntry.assertions
    fraction data (REQ-d00069-J)."""

    def test_gap_entry_to_list_serializes_fraction(self) -> None:
        from elspais.commands.gaps import _gap_entry_to_list

        entry = GapEntry("REQ-p00001", "Login", [("REQ-p00001-C", 0.4), ("REQ-p00001-D", 0.0)])
        result = _gap_entry_to_list(entry)
        assert result == [
            "REQ-p00001",
            "Login",
            [
                {"id": "REQ-p00001-C", "fraction": 0.4},
                {"id": "REQ-p00001-D", "fraction": 0.0},
            ],
        ]

    def test_gap_data_from_dict_round_trips_fraction(self) -> None:
        from elspais.commands.gaps import _gap_data_from_dict

        d = {
            "uncovered": [
                [
                    "REQ-p00001",
                    "Login",
                    [{"id": "REQ-p00001-C", "fraction": 0.4}],
                ]
            ],
            "untested": [],
            "unvalidated": [],
            "failing": [],
            "no_assertions": [],
        }
        gd = _gap_data_from_dict(d)
        assert gd.uncovered[0].assertions == [("REQ-p00001-C", 0.4)]


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


# ===========================================================================
# REQ-d00252-F: Integrates coverage in gaps
# ===========================================================================

_INTEGRATES_FIX = Path(__file__).parents[1] / "fixtures" / "e2e-integrates"


def _federate_integrates(tmp_path):
    """Federate the e2e-integrates fixture (APP-d00001 integrates LIB-d00007)."""
    import shutil

    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    dest = tmp_path / "proj"
    shutil.copytree(_INTEGRATES_FIX, dest)
    return build_graph(
        config=get_config(None, dest / "app"),
        repo_root=dest / "app",
        scan_code=False,
        scan_tests=False,
    )


class TestGapsIntegrates:
    """Validates REQ-d00252-F: an integrating requirement is not an uncovered
    gap and is listed under its owning associate."""

    def test_REQ_d00252_F_integrating_req_not_uncovered(self, tmp_path) -> None:
        """APP-d00001 integrates a library REQ, so it must NOT appear in the
        uncovered gap list."""
        fed = _federate_integrates(tmp_path)
        data = collect_gaps(fed, exclude_status=set())
        uncovered_ids = {e.req_id for e in data.uncovered}
        assert "APP-d00001" not in uncovered_ids

    def test_REQ_d00252_F_integrating_req_grouped_by_associate(self, tmp_path) -> None:
        """APP-d00001 is recorded under the owning associate 'library', and the
        rendered text shows a 'Covered via external associate' segment."""
        from elspais.commands.gaps import render_integrated_text

        fed = _federate_integrates(tmp_path)
        data = collect_gaps(fed, exclude_status=set())
        assert "library" in data.integrated
        assert "APP-d00001" in data.integrated["library"]

        text = render_integrated_text(data)
        assert "Covered via external associate" in text
        assert "library" in text
        assert "APP-d00001" in text

    def test_REQ_d00252_F_gap_data_from_dict_integrated_field(self) -> None:
        """The daemon serialization round-trips a populated ``integrated`` map."""
        from elspais.commands.gaps import _gap_data_from_dict

        d = {
            "uncovered": [],
            "untested": [],
            "unvalidated": [],
            "failing": [],
            "no_assertions": [],
            "integrated": {"lib": ["APP-d00001", "APP-d00002"]},
        }
        gd = _gap_data_from_dict(d)
        assert gd.integrated == {"lib": ["APP-d00001", "APP-d00002"]}

    def test_REQ_d00252_F_gap_data_from_dict_missing_integrated_is_empty(self) -> None:
        """``integrated`` defaults to an empty map when absent from the dict."""
        from elspais.commands.gaps import _gap_data_from_dict

        d = {
            "uncovered": [],
            "untested": [],
            "unvalidated": [],
            "failing": [],
            "no_assertions": [],
        }
        gd = _gap_data_from_dict(d)
        assert gd.integrated == {}
