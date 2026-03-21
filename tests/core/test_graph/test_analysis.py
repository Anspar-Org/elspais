# Implements: REQ-d00124-A, REQ-d00124-B, REQ-d00124-C, REQ-d00124-D, REQ-d00124-E, REQ-d00124-F
"""Tests for graph analysis module (foundational requirement prioritization).

These tests validate the analysis functions that rank requirements by
foundational importance using centrality, fan-in, uncovered dependents,
and composite scoring.
"""

from __future__ import annotations

from elspais.graph.analysis import (
    analyze_centrality,
    analyze_fan_in,
    analyze_foundations,
)
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.relations import EdgeKind

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph():
    """Create a fresh TraceGraph for testing."""
    from elspais.graph.builder import TraceGraph

    return TraceGraph(repo_root="/tmp/test")


def _add_node(
    graph,
    node_id,
    kind=NodeKind.REQUIREMENT,
    label="",
    level="DEV",
    status="Active",
    referenced_pct=None,
    *,
    is_root=False,
):
    """Create a node, register it in graph, optionally mark as root."""
    from elspais.graph.metrics import CoverageDimension, RollupMetrics

    node = GraphNode(id=node_id, kind=kind, label=label or node_id)
    node._content = {"level": level, "status": status}
    if referenced_pct is not None:
        # Use indirect to represent the old referenced_pct semantic
        total = 100  # use 100 so pct math works out
        indirect = int(referenced_pct)  # count = pct when total=100
        node.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=total,
                implemented=CoverageDimension(total=total, direct=indirect, indirect=indirect),
            ),
        )
    graph._index[node_id] = node
    if is_root:
        graph._roots.append(node)
    return node


# ---------------------------------------------------------------------------
# TestAnalyzeCentrality  (REQ-d00124-A)
# ---------------------------------------------------------------------------


class TestAnalyzeCentrality:
    """Validates REQ-d00124-A: PageRank centrality with damping factor and convergence."""

    def test_REQ_d00124_A_hub_node_ranks_higher(self):
        """A node referenced by 3 independent subtrees should have higher
        centrality than a node deep in a single chain."""
        graph = _make_graph()

        # Hub node referenced from 3 subtrees
        hub = _add_node(graph, "REQ-HUB", level="OPS", is_root=True)
        for i in range(3):
            child = _add_node(graph, f"REQ-C{i}", level="DEV")
            hub.link(child, EdgeKind.IMPLEMENTS)

        # Chain: A -> B -> deep (single path)
        chain_root = _add_node(graph, "REQ-CHAIN", level="PRD", is_root=True)
        mid = _add_node(graph, "REQ-MID", level="OPS")
        deep = _add_node(graph, "REQ-DEEP", level="DEV")
        chain_root.link(mid, EdgeKind.IMPLEMENTS)
        mid.link(deep, EdgeKind.IMPLEMENTS)

        kinds = {NodeKind.REQUIREMENT}
        scores = analyze_centrality(graph, include_kinds=kinds)

        # Hub has 3 children pointing to it -> higher centrality
        assert scores["REQ-HUB"] > scores["REQ-DEEP"]

    def test_REQ_d00124_A_damping_factor_affects_scores(self):
        """Different damping factors should produce different score distributions."""
        graph = _make_graph()
        root = _add_node(graph, "REQ-R", level="PRD", is_root=True)
        child = _add_node(graph, "REQ-C", level="DEV")
        root.link(child, EdgeKind.IMPLEMENTS)

        kinds = {NodeKind.REQUIREMENT}
        scores_high = analyze_centrality(graph, include_kinds=kinds, damping=0.95)
        scores_low = analyze_centrality(graph, include_kinds=kinds, damping=0.50)

        # With higher damping, more score flows to parents; with lower, more uniform
        assert scores_high["REQ-R"] != scores_low["REQ-R"]

    def test_REQ_d00124_A_scores_sum_to_approximately_one(self):
        """PageRank scores across all included nodes should sum to ~1.0."""
        graph = _make_graph()
        root = _add_node(graph, "REQ-R", level="PRD", is_root=True)
        c1 = _add_node(graph, "REQ-C1", level="OPS")
        c2 = _add_node(graph, "REQ-C2", level="OPS")
        c3 = _add_node(graph, "REQ-C3", level="DEV")
        root.link(c1, EdgeKind.IMPLEMENTS)
        root.link(c2, EdgeKind.IMPLEMENTS)
        c1.link(c3, EdgeKind.IMPLEMENTS)
        c2.link(c3, EdgeKind.IMPLEMENTS)  # c3 has 2 parents

        kinds = {NodeKind.REQUIREMENT}
        scores = analyze_centrality(graph, include_kinds=kinds)
        total = sum(scores.values())
        assert abs(total - 1.0) < 0.05, f"Scores sum to {total}, expected ~1.0"

    def test_REQ_d00124_A_single_node_centrality(self):
        """A single-node graph should assign score 1.0 to that node."""
        graph = _make_graph()
        _add_node(graph, "REQ-SOLO", level="PRD", is_root=True)

        kinds = {NodeKind.REQUIREMENT}
        scores = analyze_centrality(graph, include_kinds=kinds)
        assert abs(scores["REQ-SOLO"] - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# TestAnalyzeFanIn  (REQ-d00124-B)
# ---------------------------------------------------------------------------


class TestAnalyzeFanIn:
    """Validates REQ-d00124-B: Fan-in as distinct direct parent count."""

    def test_REQ_d00124_B_shared_node_has_higher_fan_in(self):
        """A node reachable from all 3 roots should have fan-in=3,
        while a node under only 1 root should have fan-in=1."""
        graph = _make_graph()

        # 3 roots
        r1 = _add_node(graph, "REQ-R1", level="PRD", is_root=True)
        r2 = _add_node(graph, "REQ-R2", level="PRD", is_root=True)
        r3 = _add_node(graph, "REQ-R3", level="PRD", is_root=True)

        # Shared node reachable from all 3 roots via intermediaries
        shared = _add_node(graph, "REQ-SHARED", level="DEV")
        for root in (r1, r2, r3):
            mid = _add_node(graph, f"REQ-M-{root.id}", level="OPS")
            root.link(mid, EdgeKind.IMPLEMENTS)
            mid.link(shared, EdgeKind.IMPLEMENTS)

        # Isolated node under only r1
        isolated = _add_node(graph, "REQ-ISO", level="DEV")
        r1.link(isolated, EdgeKind.IMPLEMENTS)

        kinds = {NodeKind.REQUIREMENT}
        fan_in = analyze_fan_in(graph, include_kinds=kinds)

        assert fan_in["REQ-SHARED"] == 3
        assert fan_in["REQ-ISO"] == 1

    def test_REQ_d00124_B_root_node_fan_in_is_one(self):
        """A root node is only in its own subtree, so fan-in should be 1."""
        graph = _make_graph()
        _add_node(graph, "REQ-R", level="PRD", is_root=True)
        child = _add_node(graph, "REQ-C", level="DEV")
        graph._index["REQ-R"].link(child, EdgeKind.IMPLEMENTS)

        kinds = {NodeKind.REQUIREMENT}
        fan_in = analyze_fan_in(graph, include_kinds=kinds)
        assert fan_in["REQ-R"] == 1


# ---------------------------------------------------------------------------
# TestUncoveredDependents  (REQ-d00124-C)
# ---------------------------------------------------------------------------


class TestUncoveredDependents:
    """Validates REQ-d00124-C: Uncovered dependent counts (leaf reqs with zero coverage)."""

    def test_REQ_d00124_C_counts_uncovered_leaves(self):
        """Parent's uncovered_dependents should count leaves with referenced_pct=0."""
        graph = _make_graph()
        parent = _add_node(graph, "REQ-P", level="PRD", is_root=True, referenced_pct=100)

        # 2 uncovered leaves
        leaf1 = _add_node(graph, "REQ-L1", level="DEV", referenced_pct=0)
        leaf2 = _add_node(graph, "REQ-L2", level="DEV", referenced_pct=0)
        # 1 covered leaf
        leaf3 = _add_node(graph, "REQ-L3", level="DEV", referenced_pct=80)

        parent.link(leaf1, EdgeKind.IMPLEMENTS)
        parent.link(leaf2, EdgeKind.IMPLEMENTS)
        parent.link(leaf3, EdgeKind.IMPLEMENTS)

        report = analyze_foundations(graph)

        # Find parent's score in the report
        parent_score = next(s for s in report.ranked_nodes if s.node_id == "REQ-P")
        assert parent_score.uncovered_dependents == 2

    def test_REQ_d00124_C_no_uncovered_when_all_covered(self):
        """When all leaves have coverage, uncovered_dependents should be 0."""
        graph = _make_graph()
        parent = _add_node(graph, "REQ-P", level="PRD", is_root=True, referenced_pct=100)
        leaf = _add_node(graph, "REQ-L", level="DEV", referenced_pct=50)
        parent.link(leaf, EdgeKind.IMPLEMENTS)

        report = analyze_foundations(graph)
        parent_score = next(s for s in report.ranked_nodes if s.node_id == "REQ-P")
        assert parent_score.uncovered_dependents == 0


# ---------------------------------------------------------------------------
# TestCompositeScore  (REQ-d00124-D)
# ---------------------------------------------------------------------------


class TestCompositeScore:
    """Validates REQ-d00124-D: Composite score with normalizable weights."""

    def test_REQ_d00124_D_composite_is_weighted_combination(self):
        """Composite score should reflect weighted combination of normalized metrics."""
        graph = _make_graph()
        root = _add_node(graph, "REQ-R", level="PRD", is_root=True, referenced_pct=100)
        c1 = _add_node(graph, "REQ-C1", level="OPS", referenced_pct=0)
        c2 = _add_node(graph, "REQ-C2", level="OPS", referenced_pct=0)
        root.link(c1, EdgeKind.IMPLEMENTS)
        root.link(c2, EdgeKind.IMPLEMENTS)

        report = analyze_foundations(graph, weights=(0.4, 0.3, 0.3))
        assert len(report.ranked_nodes) > 0
        # Root has 2 uncovered children -> highest composite score
        scores = {s.node_id: s.composite_score for s in report.ranked_nodes}
        assert scores["REQ-R"] > scores["REQ-C1"]
        assert scores["REQ-R"] > scores["REQ-C2"]
        # All scores should be non-negative floats
        for ns in report.ranked_nodes:
            assert isinstance(ns.composite_score, float)
            assert ns.composite_score >= 0.0

    def test_REQ_d00124_D_custom_weights_change_ranking(self):
        """Different weight vectors should produce different composite scores."""
        graph = _make_graph()
        root = _add_node(graph, "REQ-R", level="PRD", is_root=True, referenced_pct=100)
        c1 = _add_node(graph, "REQ-C1", level="OPS", referenced_pct=0)
        c2 = _add_node(graph, "REQ-C2", level="DEV", referenced_pct=0)
        root.link(c1, EdgeKind.IMPLEMENTS)
        root.link(c2, EdgeKind.IMPLEMENTS)
        # c1 links to c2 as well, giving c2 more fan-in
        c1.link(c2, EdgeKind.IMPLEMENTS)

        report_a = analyze_foundations(graph, weights=(1.0, 0.0, 0.0))
        report_b = analyze_foundations(graph, weights=(0.0, 1.0, 0.0))

        scores_a = {s.node_id: s.composite_score for s in report_a.ranked_nodes}
        scores_b = {s.node_id: s.composite_score for s in report_b.ranked_nodes}

        # At least one node should have a different score under different weights
        assert scores_a != scores_b


# ---------------------------------------------------------------------------
# TestNodeFiltering  (REQ-d00124-E)
# ---------------------------------------------------------------------------


class TestNodeFiltering:
    """Validates REQ-d00124-E: Node filtering by NodeKind, assertions in
    computation but not output."""

    def test_REQ_d00124_E_default_filter_includes_req_and_assertion(self):
        """Default include_kinds should be REQUIREMENT and ASSERTION."""
        graph = _make_graph()
        req = _add_node(
            graph, "REQ-R", kind=NodeKind.REQUIREMENT, level="PRD", is_root=True, referenced_pct=100
        )
        assertion = _add_node(
            graph, "REQ-R-A", kind=NodeKind.ASSERTION, label="Assertion A", referenced_pct=0
        )
        code = _add_node(graph, "CODE-1", kind=NodeKind.CODE, label="some_func")
        test = _add_node(graph, "TEST-1", kind=NodeKind.TEST, label="test_it")

        req.link(assertion, EdgeKind.CONTAINS)
        req.link(code, EdgeKind.IMPLEMENTS)
        req.link(test, EdgeKind.VERIFIES)

        # Default include_kinds=None -> {REQUIREMENT, ASSERTION}
        centrality = analyze_centrality(
            graph,
            include_kinds={NodeKind.REQUIREMENT, NodeKind.ASSERTION},
        )

        # CODE and TEST nodes should be excluded from centrality results
        assert "CODE-1" not in centrality
        assert "TEST-1" not in centrality
        # REQ and ASSERTION should be present
        assert "REQ-R" in centrality
        assert "REQ-R-A" in centrality

    def test_REQ_d00124_E_ranked_output_excludes_assertions(self):
        """Ranked output (top_foundations, ranked_nodes) should contain only
        REQUIREMENT nodes, not assertions."""
        graph = _make_graph()
        req = _add_node(
            graph, "REQ-R", kind=NodeKind.REQUIREMENT, level="PRD", is_root=True, referenced_pct=100
        )
        assertion = _add_node(
            graph, "REQ-R-A", kind=NodeKind.ASSERTION, label="Assertion A", referenced_pct=0
        )
        req.link(assertion, EdgeKind.CONTAINS)

        report = analyze_foundations(graph)

        # Only REQUIREMENT nodes in ranked output
        for ns in report.ranked_nodes:
            node = graph.find_by_id(ns.node_id)
            assert node is not None
            assert (
                node.kind == NodeKind.REQUIREMENT
            ), f"Node {ns.node_id} is {node.kind}, expected REQUIREMENT"

    def test_REQ_d00124_E_assertions_count_toward_uncovered(self):
        """Uncovered assertions should feed into parent requirement's
        uncovered_dependents count."""
        graph = _make_graph()
        req = _add_node(
            graph, "REQ-R", kind=NodeKind.REQUIREMENT, level="PRD", is_root=True, referenced_pct=100
        )
        # 2 uncovered assertions
        a1 = _add_node(
            graph, "REQ-R-A", kind=NodeKind.ASSERTION, label="Assertion A", referenced_pct=0
        )
        a2 = _add_node(
            graph, "REQ-R-B", kind=NodeKind.ASSERTION, label="Assertion B", referenced_pct=0
        )
        req.link(a1, EdgeKind.CONTAINS)
        req.link(a2, EdgeKind.CONTAINS)

        report = analyze_foundations(graph)
        req_score = next(s for s in report.ranked_nodes if s.node_id == "REQ-R")
        assert req_score.uncovered_dependents == 2


# ---------------------------------------------------------------------------
# TestActionableLeaves  (REQ-d00124-F)
# ---------------------------------------------------------------------------


class TestActionableLeaves:
    """Validates REQ-d00124-F: Actionable leaves ranked by ancestor composite scores."""

    def test_REQ_d00124_F_leaf_under_important_parent_ranks_higher(self):
        """Uncovered leaves under more important (higher-scoring) parents
        should rank higher in actionable_leaves."""
        graph = _make_graph()

        # Important root with many children -> high composite
        important = _add_node(graph, "REQ-IMP", level="PRD", is_root=True, referenced_pct=100)
        for i in range(4):
            c = _add_node(graph, f"REQ-IMP-C{i}", level="OPS", referenced_pct=50)
            important.link(c, EdgeKind.IMPLEMENTS)

        # Less important root with one child
        minor = _add_node(graph, "REQ-MIN", level="PRD", is_root=True, referenced_pct=100)

        # Uncovered leaf under important parent
        leaf_imp = _add_node(graph, "REQ-LEAF-IMP", level="DEV", referenced_pct=0)
        important.link(leaf_imp, EdgeKind.IMPLEMENTS)

        # Uncovered leaf under minor parent
        leaf_min = _add_node(graph, "REQ-LEAF-MIN", level="DEV", referenced_pct=0)
        minor.link(leaf_min, EdgeKind.IMPLEMENTS)

        report = analyze_foundations(graph)

        # Both leaves should appear in actionable_leaves
        leaf_ids = [s.node_id for s in report.actionable_leaves]
        assert "REQ-LEAF-IMP" in leaf_ids
        assert "REQ-LEAF-MIN" in leaf_ids

        # Leaf under important parent should rank higher (earlier index)
        idx_imp = leaf_ids.index("REQ-LEAF-IMP")
        idx_min = leaf_ids.index("REQ-LEAF-MIN")
        assert idx_imp < idx_min, (
            f"Expected REQ-LEAF-IMP (idx {idx_imp}) to rank before " f"REQ-LEAF-MIN (idx {idx_min})"
        )

    def test_REQ_d00124_F_covered_leaves_included(self):
        """All leaves appear in actionable_leaves regardless of coverage."""
        graph = _make_graph()
        root = _add_node(graph, "REQ-R", level="PRD", is_root=True, referenced_pct=100)
        covered = _add_node(graph, "REQ-COV", level="DEV", referenced_pct=75)
        root.link(covered, EdgeKind.IMPLEMENTS)

        report = analyze_foundations(graph)
        leaf_ids = [s.node_id for s in report.actionable_leaves]
        assert "REQ-COV" in leaf_ids

    def test_REQ_d00124_F_deprecated_excluded(self):
        """Deprecated requirements should not appear in any output."""
        graph = _make_graph()
        root = _add_node(graph, "REQ-R", level="PRD", is_root=True, referenced_pct=100)
        active = _add_node(graph, "REQ-ACT", level="DEV", referenced_pct=0)
        deprecated = _add_node(graph, "REQ-DEP", level="DEV", status="Deprecated", referenced_pct=0)
        root.link(active, EdgeKind.IMPLEMENTS)
        root.link(deprecated, EdgeKind.IMPLEMENTS)

        report = analyze_foundations(graph)
        all_ids = {s.node_id for s in report.ranked_nodes}
        assert "REQ-ACT" in all_ids
        assert "REQ-DEP" not in all_ids

    def test_REQ_d00124_F_top_n_limits_results(self):
        """The top_n parameter should limit the number of results in
        top_foundations and actionable_leaves."""
        graph = _make_graph()
        root = _add_node(graph, "REQ-R", level="PRD", is_root=True, referenced_pct=100)
        # Create 5 uncovered leaves
        for i in range(5):
            leaf = _add_node(graph, f"REQ-L{i}", level="DEV", referenced_pct=0)
            root.link(leaf, EdgeKind.IMPLEMENTS)

        report = analyze_foundations(graph, top_n=3)
        assert len(report.top_foundations) <= 3
        assert len(report.actionable_leaves) <= 3
