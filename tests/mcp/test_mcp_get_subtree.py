# Validates REQ-o00067-A, REQ-o00067-B, REQ-o00067-C, REQ-o00067-D, REQ-o00067-E, REQ-o00067-F
# Validates REQ-d00075-A, REQ-d00075-B, REQ-d00075-C, REQ-d00075-D
# Validates REQ-d00075-E, REQ-d00075-F, REQ-d00075-G
"""Tests for MCP subtree extraction tools.

Tests REQ-o00067: MCP Get Subtree Tool
- _collect_subtree()
- _compute_coverage_summary()
- _subtree_to_markdown()
- _subtree_to_flat()
- _subtree_to_nested()
- _get_subtree()

All tests verify correct graph traversal for subtree extraction and rendering.
"""

from pathlib import Path

import pytest

from elspais.graph import EdgeKind, GraphNode, NodeKind
from elspais.graph.builder import TraceGraph

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def subtree_graph():
    """Create a 3-level TraceGraph for subtree extraction tests.

    Hierarchy:
        PRD: REQ-p00001 "Platform Security" (level=PRD, status=Active)
          ├─ Assertion A: "SHALL encrypt all data at rest"
          ├─ Assertion B: "SHALL use TLS for transit"
          └─ OPS: REQ-o00010 "Security Operations" (implements PRD)
               ├─ Assertion C: "SHALL rotate keys monthly"
               └─ DEV: REQ-d00020 "Encryption Module" (implements OPS)
                    ├─ Assertion D: "SHALL use AES-256"
                    └─ Assertion E: "SHALL support key rotation API"

    Test node linked to assertion A for coverage testing.
    """
    graph = TraceGraph(repo_root=Path("/test/repo"))

    # --- PRD requirement ---
    req_prd = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Platform Security",
    )
    req_prd._content = {"level": "PRD", "status": "Active", "hash": "abc12345"}

    # PRD assertions
    assertion_a = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="SHALL encrypt all data at rest",
    )
    assertion_a._content = {"label": "A", "text": "SHALL encrypt all data at rest"}
    req_prd.add_child(assertion_a)

    assertion_b = GraphNode(
        id="REQ-p00001-B",
        kind=NodeKind.ASSERTION,
        label="SHALL use TLS for transit",
    )
    assertion_b._content = {"label": "B", "text": "SHALL use TLS for transit"}
    req_prd.add_child(assertion_b)

    # --- OPS requirement ---
    req_ops = GraphNode(
        id="REQ-o00010",
        kind=NodeKind.REQUIREMENT,
        label="Security Operations",
    )
    req_ops._content = {"level": "OPS", "status": "Active", "hash": "def67890"}

    # OPS assertion
    assertion_c = GraphNode(
        id="REQ-o00010-C",
        kind=NodeKind.ASSERTION,
        label="SHALL rotate keys monthly",
    )
    assertion_c._content = {"label": "C", "text": "SHALL rotate keys monthly"}
    req_ops.add_child(assertion_c)

    # OPS implements PRD (parent-child + typed edge)
    req_prd.add_child(req_ops)
    req_ops.link(req_prd, EdgeKind.IMPLEMENTS)

    # --- DEV requirement ---
    req_dev = GraphNode(
        id="REQ-d00020",
        kind=NodeKind.REQUIREMENT,
        label="Encryption Module",
    )
    req_dev._content = {"level": "DEV", "status": "Active", "hash": "ghi11111"}

    # DEV assertions
    assertion_d = GraphNode(
        id="REQ-d00020-D",
        kind=NodeKind.ASSERTION,
        label="SHALL use AES-256",
    )
    assertion_d._content = {"label": "D", "text": "SHALL use AES-256"}
    req_dev.add_child(assertion_d)

    assertion_e = GraphNode(
        id="REQ-d00020-E",
        kind=NodeKind.ASSERTION,
        label="SHALL support key rotation API",
    )
    assertion_e._content = {"label": "E", "text": "SHALL support key rotation API"}
    req_dev.add_child(assertion_e)

    # DEV implements OPS (parent-child + typed edge)
    req_ops.add_child(req_dev)
    req_dev.link(req_ops, EdgeKind.IMPLEMENTS)

    # --- TEST node linked to assertion A for coverage ---
    test_node = GraphNode(
        id="test:test_enc.py::test_encryption",
        kind=NodeKind.TEST,
        label="test_encryption",
    )
    test_node._content = {"file": "test_enc.py", "name": "test_encryption"}
    assertion_a.link(test_node, EdgeKind.VALIDATES)

    # Register all nodes in graph index
    graph._index = {
        "REQ-p00001": req_prd,
        "REQ-p00001-A": assertion_a,
        "REQ-p00001-B": assertion_b,
        "REQ-o00010": req_ops,
        "REQ-o00010-C": assertion_c,
        "REQ-d00020": req_dev,
        "REQ-d00020-D": assertion_d,
        "REQ-d00020-E": assertion_e,
        "test:test_enc.py::test_encryption": test_node,
    }
    graph._roots = [req_prd]

    return graph


# ─────────────────────────────────────────────────────────────────────────────
# Tests for _collect_subtree() - REQ-d00075-A
# ─────────────────────────────────────────────────────────────────────────────


class TestCollectSubtree:
    """Validates REQ-d00075-A: BFS traversal with depth tracking and dedup."""

    def test_REQ_d00075_A_bfs_traversal_from_root(self, subtree_graph):
        """REQ-d00075-A: BFS traversal collects all nodes in subtree."""
        from elspais.mcp.server import _collect_subtree

        collected = _collect_subtree(subtree_graph, "REQ-p00001")

        # Extract IDs in traversal order
        ids = [node.id for node, _ in collected]

        # Root must be first
        assert ids[0] == "REQ-p00001"

        # All requirement and assertion nodes should be present
        expected_ids = {
            "REQ-p00001",
            "REQ-p00001-A",
            "REQ-p00001-B",
            "REQ-o00010",
            "REQ-o00010-C",
            "REQ-d00020",
            "REQ-d00020-D",
            "REQ-d00020-E",
        }
        assert set(ids) == expected_ids

        # TEST node should NOT be included (default kind filter excludes it)
        assert "test:test_enc.py::test_encryption" not in ids

    def test_REQ_o00067_B_depth_limiting(self, subtree_graph):
        """REQ-o00067-B: depth=1 limits traversal to one level below root."""
        from elspais.mcp.server import _collect_subtree

        collected = _collect_subtree(subtree_graph, "REQ-p00001", depth=1)

        ids = [node.id for node, _ in collected]

        # Root (depth 0) + its direct children (depth 1) only
        assert "REQ-p00001" in ids
        assert "REQ-p00001-A" in ids
        assert "REQ-p00001-B" in ids
        assert "REQ-o00010" in ids

        # DEV and its assertions are at depth 2+, should NOT be present
        assert "REQ-d00020" not in ids
        assert "REQ-d00020-D" not in ids
        assert "REQ-d00020-E" not in ids

    def test_REQ_o00067_E_dag_dedup(self, subtree_graph):
        """REQ-o00067-E: Diamond DAG paths produce each node only once."""
        from elspais.mcp.server import _collect_subtree

        # Create a diamond: PRD -> shared_node AND OPS -> shared_node
        shared = GraphNode(
            id="REQ-shared",
            kind=NodeKind.REQUIREMENT,
            label="Shared Requirement",
        )
        shared._content = {"level": "DEV", "status": "Active", "hash": "zzz99999"}

        prd_node = subtree_graph._index["REQ-p00001"]
        ops_node = subtree_graph._index["REQ-o00010"]

        prd_node.add_child(shared)
        ops_node.add_child(shared)
        subtree_graph._index["REQ-shared"] = shared

        collected = _collect_subtree(subtree_graph, "REQ-p00001")
        ids = [node.id for node, _ in collected]

        # Shared node should appear exactly once despite two paths
        assert ids.count("REQ-shared") == 1

    def test_REQ_o00067_C_kind_filtering(self, subtree_graph):
        """REQ-o00067-C: Custom include_kinds filters out unwanted node types."""
        from elspais.mcp.server import _collect_subtree

        # Only include REQUIREMENT nodes, exclude ASSERTION
        collected = _collect_subtree(
            subtree_graph,
            "REQ-p00001",
            include_kinds={NodeKind.REQUIREMENT},
        )

        ids = [node.id for node, _ in collected]

        # Requirements should be present
        assert "REQ-p00001" in ids
        assert "REQ-o00010" in ids
        assert "REQ-d00020" in ids

        # Assertions should NOT be present
        assert "REQ-p00001-A" not in ids
        assert "REQ-p00001-B" not in ids
        assert "REQ-o00010-C" not in ids

    def test_REQ_d00075_F_conservative_defaults(self, subtree_graph):
        """REQ-d00075-F: Default kind filter includes REQUIREMENT+ASSERTION but not TEST/CODE."""
        from elspais.mcp.server import _collect_subtree

        collected = _collect_subtree(subtree_graph, "REQ-p00001", include_kinds=None)

        kinds = {node.kind for node, _ in collected}

        assert NodeKind.REQUIREMENT in kinds
        assert NodeKind.ASSERTION in kinds
        assert NodeKind.TEST not in kinds
        assert NodeKind.CODE not in kinds


# ─────────────────────────────────────────────────────────────────────────────
# Tests for _compute_coverage_summary() - REQ-d00075-B
# ─────────────────────────────────────────────────────────────────────────────


class TestComputeCoverageSummary:
    """Validates REQ-d00075-B: Coverage summary reuses _iter_assertion_coverage()."""

    def test_REQ_d00075_B_coverage_with_tests(self, subtree_graph):
        """REQ-d00075-B: Requirement with one covered assertion returns correct summary."""
        from elspais.mcp.server import _compute_coverage_summary

        req_prd = subtree_graph._index["REQ-p00001"]
        result = _compute_coverage_summary(req_prd)

        # REQ-p00001 has 2 assertions (A, B); assertion A is covered by a test
        assert result["total"] == 2
        assert result["covered"] == 1
        assert result["pct"] == 50.0

    def test_REQ_d00075_B_coverage_no_tests(self, subtree_graph):
        """REQ-d00075-B: Requirement with no tests returns zero coverage."""
        from elspais.mcp.server import _compute_coverage_summary

        req_dev = subtree_graph._index["REQ-d00020"]
        result = _compute_coverage_summary(req_dev)

        # REQ-d00020 has 2 assertions (D, E); none covered
        assert result["total"] == 2
        assert result["covered"] == 0
        assert result["pct"] == 0.0

    def test_REQ_d00075_B_coverage_no_assertions(self):
        """REQ-d00075-B: Requirement with no assertions returns zero totals."""
        from elspais.mcp.server import _compute_coverage_summary

        bare_req = GraphNode(
            id="REQ-bare",
            kind=NodeKind.REQUIREMENT,
            label="Bare Requirement",
        )
        bare_req._content = {"level": "PRD", "status": "Active", "hash": "000"}

        result = _compute_coverage_summary(bare_req)

        assert result["total"] == 0
        assert result["covered"] == 0
        assert result["pct"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Tests for _subtree_to_markdown() - REQ-d00075-C
# ─────────────────────────────────────────────────────────────────────────────


class TestSubtreeToMarkdown:
    """Validates REQ-d00075-C: Markdown format rendering."""

    def test_REQ_d00075_C_markdown_headings_and_assertions(self, subtree_graph):
        """REQ-d00075-C: Markdown output has headings with node IDs and assertion bullets."""
        from elspais.mcp.server import _collect_subtree, _subtree_to_markdown

        collected = _collect_subtree(subtree_graph, "REQ-p00001")
        md = _subtree_to_markdown(collected, subtree_graph)

        # Root requirement should appear as a heading
        assert "REQ-p00001" in md
        assert "Platform Security" in md

        # Assertions should appear as bullet items with labels
        assert "**A**:" in md
        assert "SHALL encrypt all data at rest" in md
        assert "**B**:" in md
        assert "SHALL use TLS for transit" in md

        # Nested requirements should also appear
        assert "REQ-o00010" in md
        assert "REQ-d00020" in md

    def test_REQ_d00075_C_markdown_empty_subtree(self, subtree_graph):
        """REQ-d00075-C: Empty collected list returns empty subtree marker."""
        from elspais.mcp.server import _subtree_to_markdown

        md = _subtree_to_markdown([], subtree_graph)

        assert md == "*(empty subtree)*"

    def test_REQ_o00067_F_markdown_includes_coverage(self, subtree_graph):
        """REQ-o00067-F: Coverage stats appear in markdown output for requirements."""
        from elspais.mcp.server import _collect_subtree, _subtree_to_markdown

        collected = _collect_subtree(subtree_graph, "REQ-p00001")
        md = _subtree_to_markdown(collected, subtree_graph)

        # Coverage stats for PRD (1/2 covered, 50.0%)
        assert "1/2 covered" in md
        assert "50.0%" in md

        # Coverage stats for OPS (0/1 covered, 0.0%)
        assert "0/1 covered" in md

        # Coverage stats for DEV (0/2 covered, 0.0%)
        assert "0/2 covered" in md


# ─────────────────────────────────────────────────────────────────────────────
# Tests for _subtree_to_flat() - REQ-d00075-D
# ─────────────────────────────────────────────────────────────────────────────


class TestSubtreeToFlat:
    """Validates REQ-d00075-D: Flat JSON format."""

    def test_REQ_d00075_D_flat_structure(self, subtree_graph):
        """REQ-d00075-D: Flat output has root_id, nodes, edges, stats keys."""
        from elspais.mcp.server import _collect_subtree, _subtree_to_flat

        collected = _collect_subtree(subtree_graph, "REQ-p00001")
        result = _subtree_to_flat(collected, subtree_graph, "REQ-p00001")

        assert "root_id" in result
        assert result["root_id"] == "REQ-p00001"
        assert "nodes" in result
        assert "edges" in result
        assert "stats" in result

    def test_REQ_d00075_D_flat_nodes_have_depth(self, subtree_graph):
        """REQ-d00075-D: Each node entry has a depth key."""
        from elspais.mcp.server import _collect_subtree, _subtree_to_flat

        collected = _collect_subtree(subtree_graph, "REQ-p00001")
        result = _subtree_to_flat(collected, subtree_graph, "REQ-p00001")

        for node_entry in result["nodes"]:
            assert "depth" in node_entry, f"Node {node_entry['id']} missing 'depth' key"

        # Root should be at depth 0
        root_entry = next(n for n in result["nodes"] if n["id"] == "REQ-p00001")
        assert root_entry["depth"] == 0

    def test_REQ_d00075_D_flat_stats_counts(self, subtree_graph):
        """REQ-d00075-D: Stats has correct requirement and assertion counts."""
        from elspais.mcp.server import _collect_subtree, _subtree_to_flat

        collected = _collect_subtree(subtree_graph, "REQ-p00001")
        result = _subtree_to_flat(collected, subtree_graph, "REQ-p00001")

        stats = result["stats"]

        # 3 requirements: PRD, OPS, DEV
        assert stats["requirements"] == 3

        # 5 assertions: A, B, C, D, E
        assert stats["assertions"] == 5

        # Total = 3 + 5 = 8
        assert stats["total_nodes"] == 8


# ─────────────────────────────────────────────────────────────────────────────
# Tests for _subtree_to_nested() - REQ-d00075-E
# ─────────────────────────────────────────────────────────────────────────────


class TestSubtreeToNested:
    """Validates REQ-d00075-E: Nested JSON format."""

    def test_REQ_d00075_E_nested_children_arrays(self, subtree_graph):
        """REQ-d00075-E: Root has children, children have children recursively."""
        from elspais.mcp.server import _subtree_to_nested

        root_node = subtree_graph._index["REQ-p00001"]
        kind_filter = {NodeKind.REQUIREMENT, NodeKind.ASSERTION}

        result = _subtree_to_nested(root_node, 0, kind_filter, subtree_graph)

        assert result["id"] == "REQ-p00001"
        assert "children" in result
        assert len(result["children"]) > 0

        # Find the OPS child among root children
        child_ids = [c["id"] for c in result["children"]]
        assert "REQ-o00010" in child_ids

        # OPS should have its own children (assertion C and DEV)
        ops_child = next(c for c in result["children"] if c["id"] == "REQ-o00010")
        assert "children" in ops_child
        ops_child_ids = [c["id"] for c in ops_child["children"]]
        assert "REQ-o00010-C" in ops_child_ids
        assert "REQ-d00020" in ops_child_ids

    def test_REQ_d00075_E_nested_depth_limit(self, subtree_graph):
        """REQ-d00075-E: depth_limit=1 means children of children are empty."""
        from elspais.mcp.server import _subtree_to_nested

        root_node = subtree_graph._index["REQ-p00001"]
        kind_filter = {NodeKind.REQUIREMENT, NodeKind.ASSERTION}

        result = _subtree_to_nested(root_node, 1, kind_filter, subtree_graph)

        assert result["id"] == "REQ-p00001"
        # Root's direct children should be present
        assert len(result["children"]) > 0

        # But children of children should be empty (depth limit reached)
        for child in result["children"]:
            assert (
                child["children"] == []
            ), f"Child {child['id']} should have no children at depth_limit=1"


# ─────────────────────────────────────────────────────────────────────────────
# Tests for _get_subtree() - REQ-o00067
# ─────────────────────────────────────────────────────────────────────────────


class TestGetSubtree:
    """Validates REQ-o00067-A through REQ-o00067-F: Full dispatcher."""

    def test_REQ_o00067_A_subtree_markdown_format(self, subtree_graph):
        """REQ-o00067-A: format='markdown' returns markdown content."""
        from elspais.mcp.server import _get_subtree

        result = _get_subtree(subtree_graph, "REQ-p00001", format="markdown")

        assert result["format"] == "markdown"
        assert result["root_id"] == "REQ-p00001"
        assert "content" in result
        assert isinstance(result["content"], str)
        assert "REQ-p00001" in result["content"]

    def test_REQ_o00067_D_subtree_flat_format(self, subtree_graph):
        """REQ-o00067-D: format='flat' returns flat structure with nodes, edges, stats."""
        from elspais.mcp.server import _get_subtree

        result = _get_subtree(subtree_graph, "REQ-p00001", format="flat")

        assert result["format"] == "flat"
        assert result["root_id"] == "REQ-p00001"
        assert "nodes" in result
        assert "edges" in result
        assert "stats" in result
        assert isinstance(result["nodes"], list)
        assert isinstance(result["edges"], list)

    def test_REQ_o00067_D_subtree_nested_format(self, subtree_graph):
        """REQ-o00067-D: format='nested' returns nested tree structure."""
        from elspais.mcp.server import _get_subtree

        result = _get_subtree(subtree_graph, "REQ-p00001", format="nested")

        assert result["format"] == "nested"
        assert result["root_id"] == "REQ-p00001"
        assert "tree" in result
        assert result["tree"]["id"] == "REQ-p00001"
        assert "children" in result["tree"]

    def test_REQ_o00067_A_subtree_not_found(self, subtree_graph):
        """REQ-o00067-A: Non-existent root_id returns error."""
        from elspais.mcp.server import _get_subtree

        result = _get_subtree(subtree_graph, "REQ-nonexistent")

        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_REQ_o00067_C_subtree_invalid_kind(self, subtree_graph):
        """REQ-o00067-C: Invalid kind string returns error."""
        from elspais.mcp.server import _get_subtree

        result = _get_subtree(
            subtree_graph,
            "REQ-p00001",
            include_kinds="invalid_kind",
        )

        assert "error" in result
        assert "unknown node kind" in result["error"].lower()

    def test_REQ_d00075_G_no_graph_modification(self, subtree_graph):
        """REQ-d00075-G: Graph is unchanged after subtree extraction."""
        from elspais.mcp.server import _get_subtree

        index_count_before = len(subtree_graph._index)
        root_count_before = len(subtree_graph._roots)

        # Run all three formats
        _get_subtree(subtree_graph, "REQ-p00001", format="markdown")
        _get_subtree(subtree_graph, "REQ-p00001", format="flat")
        _get_subtree(subtree_graph, "REQ-p00001", format="nested")

        assert len(subtree_graph._index) == index_count_before
        assert len(subtree_graph._roots) == root_count_before
