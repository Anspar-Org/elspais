# Validates REQ-o00063-A
"""Tests for file mutation operations (move_node_to_file, rename_file).

Validates REQ-o00063: file mutation operations with undo support.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.parsers import ParsedContent
from elspais.graph.relations import EdgeKind


def make_file_node(file_id: str) -> GraphNode:
    """Create a FILE node."""
    node = GraphNode(file_id, NodeKind.FILE, label=file_id)
    node.set_field("file_type", "SPEC")
    node.set_field("relative_path", file_id.replace("file:", ""))
    return node


def make_req(
    req_id: str,
    title: str = "Test",
    level: str = "PRD",
    status: str = "Active",
    assertions: list[dict] | None = None,
    implements: list[str] | None = None,
) -> ParsedContent:
    """Helper to create a requirement ParsedContent."""
    return ParsedContent(
        content_type="requirement",
        parsed_data={
            "id": req_id,
            "title": title,
            "level": level,
            "status": status,
            "assertions": assertions or [],
            "implements": implements or [],
            "refines": [],
        },
        start_line=1,
        end_line=5,
        raw_text=f"## {req_id}: {title}",
    )


def build_two_file_graph() -> TraceGraph:
    """Build graph with two FILE nodes, REQ in first.

    Structure:
        FILE: file:spec/main.md
          +-- CONTAINS --> REQ-p00001 "Test Req"
        FILE: file:spec/other.md
          (empty)
    """
    builder = GraphBuilder()
    builder.add_parsed_content(make_req("REQ-p00001", "Test Req"))
    graph = builder.build()

    # Create FILE nodes and wire CONTAINS
    file1 = make_file_node("file:spec/main.md")
    file2 = make_file_node("file:spec/other.md")
    graph._index["file:spec/main.md"] = file1
    graph._index["file:spec/other.md"] = file2
    graph._roots.append(file1)
    graph._roots.append(file2)

    req = graph.find_by_id("REQ-p00001")
    edge = file1.link(req, EdgeKind.CONTAINS)
    edge.metadata["render_order"] = 0.0
    edge.metadata["start_line"] = 1
    edge.metadata["end_line"] = 5

    return graph


class TestMoveNodeToFile:
    """Tests for TraceGraph.move_node_to_file().

    Validates REQ-o00063: move_node_to_file mutation with undo support.
    """

    def test_REQ_o00063_A_move_requirement_to_different_file(self):
        """REQ-o00063-A: Move requirement changes its FILE parent."""
        graph = build_two_file_graph()

        req = graph._index["REQ-p00001"]
        assert req.file_node().id == "file:spec/main.md"

        graph.move_node_to_file("REQ-p00001", "file:spec/other.md")

        assert req.file_node().id == "file:spec/other.md"

    def test_REQ_o00063_A_move_requirement_undo(self):
        """REQ-o00063-A: Undo restores requirement to original file with render_order."""
        graph = build_two_file_graph()

        req = graph._index["REQ-p00001"]
        assert req.file_node().id == "file:spec/main.md"

        graph.move_node_to_file("REQ-p00001", "file:spec/other.md")
        assert req.file_node().id == "file:spec/other.md"

        graph.undo_last()

        assert req.file_node().id == "file:spec/main.md"
        # Verify render_order is restored on the CONTAINS edge
        file1 = graph._index["file:spec/main.md"]
        contains_edges = [
            e
            for e in file1.iter_outgoing_edges()
            if e.kind == EdgeKind.CONTAINS and e.target.id == "REQ-p00001"
        ]
        assert len(contains_edges) == 1
        assert contains_edges[0].metadata["render_order"] == 0.0

    # Implements: REQ-o00063-A
    def test_move_to_non_file_raises(self):
        """ValueError if target is not a FILE node."""
        graph = build_two_file_graph()

        # Try to move to a REQ node (not a FILE)
        with pytest.raises(ValueError):
            graph.move_node_to_file("REQ-p00001", "REQ-p00001")

    # Implements: REQ-o00063-A
    def test_move_orphan_raises(self):
        """ValueError if node has no current FILE parent."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_req("REQ-p00001", "Orphan Req"))
        graph = builder.build()

        # Add a target FILE node but don't wire the req to any file
        file2 = make_file_node("file:spec/other.md")
        graph._index["file:spec/other.md"] = file2
        graph._roots.append(file2)

        with pytest.raises(ValueError):
            graph.move_node_to_file("REQ-p00001", "file:spec/other.md")

    # Implements: REQ-o00062-E
    def test_move_logs_mutation(self):
        """Verify mutation log entry has correct operation and states."""
        graph = build_two_file_graph()
        initial_count = len(graph.mutation_log)

        entry = graph.move_node_to_file("REQ-p00001", "file:spec/other.md")

        assert len(graph.mutation_log) == initial_count + 1
        assert entry.operation == "move_node_to_file"
        assert entry.target_id == "REQ-p00001"
        assert entry.before_state["file_id"] == "file:spec/main.md"
        assert entry.after_state["file_id"] == "file:spec/other.md"

    # Implements: REQ-d00128-E
    def test_move_assigns_render_order_at_end(self):
        """After moving, the moved node has render_order after existing children."""
        graph = build_two_file_graph()

        # Add a second requirement to the target file
        builder2 = GraphBuilder()
        builder2.add_parsed_content(make_req("REQ-p00002", "Existing Req"))
        graph2 = builder2.build()
        req2 = graph2.find_by_id("REQ-p00002")
        graph._index["REQ-p00002"] = req2

        file2 = graph._index["file:spec/other.md"]
        edge2 = file2.link(req2, EdgeKind.CONTAINS)
        edge2.metadata["render_order"] = 0.0

        # Move REQ-p00001 to the target file
        graph.move_node_to_file("REQ-p00001", "file:spec/other.md")

        # Find the CONTAINS edge for the moved requirement
        moved_edges = [
            e
            for e in file2.iter_outgoing_edges()
            if e.kind == EdgeKind.CONTAINS and e.target.id == "REQ-p00001"
        ]
        assert len(moved_edges) == 1
        # render_order should be after the existing child's 0.0
        assert moved_edges[0].metadata["render_order"] > 0.0


class TestRenameFile:
    """Tests for TraceGraph.rename_file().

    Validates REQ-o00063: rename_file mutation with undo support.
    """

    def test_REQ_o00063_A_rename_file(self):
        """REQ-o00063-A: Rename updates FILE node ID, index, and path fields."""
        graph = build_two_file_graph()

        graph.rename_file("file:spec/main.md", "spec/renamed.md")

        # New ID is findable
        node = graph.find_by_id("file:spec/renamed.md")
        assert node is not None
        # Old ID is gone
        assert graph.find_by_id("file:spec/main.md") is None
        # Path field updated
        assert node.get_field("relative_path") == "spec/renamed.md"

    def test_REQ_o00063_A_rename_file_undo(self):
        """REQ-o00063-A: Undo restores original file ID and paths."""
        graph = build_two_file_graph()

        graph.rename_file("file:spec/main.md", "spec/renamed.md")
        assert graph.find_by_id("file:spec/renamed.md") is not None

        graph.undo_last()

        # Original ID is back
        node = graph.find_by_id("file:spec/main.md")
        assert node is not None
        # Renamed ID is gone
        assert graph.find_by_id("file:spec/renamed.md") is None
        # Path field restored
        assert node.get_field("relative_path") == "spec/main.md"

    # Implements: REQ-o00063-A
    def test_rename_non_file_raises(self):
        """ValueError if node is not a FILE node."""
        graph = build_two_file_graph()

        with pytest.raises(ValueError):
            graph.rename_file("REQ-p00001", "spec/renamed.md")

    # Implements: REQ-o00062-E
    def test_rename_file_logs_mutation(self):
        """Verify mutation log entry has correct operation and states."""
        graph = build_two_file_graph()
        initial_count = len(graph.mutation_log)

        entry = graph.rename_file("file:spec/main.md", "spec/renamed.md")

        assert len(graph.mutation_log) == initial_count + 1
        assert entry.operation == "rename_file"
        assert entry.target_id == "file:spec/main.md"
        assert entry.before_state["id"] == "file:spec/main.md"
        assert entry.before_state["relative_path"] == "spec/main.md"
        assert entry.after_state["id"] == "file:spec/renamed.md"
        assert entry.after_state["relative_path"] == "spec/renamed.md"

    # Implements: REQ-o00063-A
    def test_rename_file_updates_absolute_path(self):
        """When repo_root is provided, absolute_path is updated."""
        graph = build_two_file_graph()

        graph.rename_file(
            "file:spec/main.md",
            "spec/renamed.md",
            repo_root=Path("/repo"),
        )

        node = graph.find_by_id("file:spec/renamed.md")
        assert node is not None
        assert node.get_field("absolute_path") == str(Path("/repo") / "spec/renamed.md")

    # Implements: REQ-o00063-A
    def test_rename_file_not_found(self):
        """KeyError if file_id doesn't exist."""
        graph = build_two_file_graph()

        with pytest.raises(KeyError):
            graph.rename_file("file:spec/nonexistent.md", "spec/renamed.md")
