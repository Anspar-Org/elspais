# Validates: REQ-o00062-C, REQ-o00062-D, REQ-o00062-E, REQ-o00062-F
"""Tests for edge mutation operations (add, change_kind, delete, fix_broken)."""

import pytest

from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.parsers import ParsedContent
from elspais.graph.relations import EdgeKind


def make_req(
    req_id: str,
    title: str = "Test",
    level: str = "PRD",
    status: str = "Active",
    implements: list[str] | None = None,
    assertions: list[dict] | None = None,
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


def build_disconnected_graph() -> TraceGraph:
    """Build a graph with two unconnected requirements."""
    builder = GraphBuilder()
    builder.add_parsed_content(make_req("REQ-p00001", "Parent"))
    builder.add_parsed_content(make_req("REQ-p00002", "Child"))
    return builder.build()


def build_hierarchy_graph() -> TraceGraph:
    """Build a graph with parent-child hierarchy."""
    builder = GraphBuilder()
    builder.add_parsed_content(make_req("REQ-p00001", "Parent"))
    builder.add_parsed_content(make_req("REQ-p00002", "Child", implements=["REQ-p00001"]))
    return builder.build()


def build_graph_with_assertions() -> TraceGraph:
    """Build a graph with assertions on the parent."""
    builder = GraphBuilder()
    builder.add_parsed_content(
        make_req(
            "REQ-p00001",
            "Parent",
            assertions=[
                {"label": "A", "text": "First assertion"},
                {"label": "B", "text": "Second assertion"},
            ],
        )
    )
    builder.add_parsed_content(make_req("REQ-p00002", "Child"))
    return builder.build()


def build_graph_with_broken_reference() -> TraceGraph:
    """Build a graph with a broken reference."""
    builder = GraphBuilder()
    builder.add_parsed_content(make_req("REQ-p00001", "Parent"))
    # Child implements non-existent requirement
    builder.add_parsed_content(make_req("REQ-p00002", "Child", implements=["REQ-nonexistent"]))
    return builder.build()


class TestAddEdge:
    """Tests for TraceGraph.add_edge()."""

    def test_REQ_o00062_C_add_edge_creates_relationship(self):
        """REQ-o00062-C: Basic add edge creates relationship."""
        graph = build_disconnected_graph()

        # Initially no edge
        parent = graph.find_by_id("REQ-p00001")
        child = graph.find_by_id("REQ-p00002")
        assert not parent.has_child(child)

        entry = graph.add_edge("REQ-p00002", "REQ-p00001", EdgeKind.IMPLEMENTS)

        assert entry.operation == "add_edge"
        assert entry.target_id == "REQ-p00002"
        assert entry.after_state["edge_kind"] == "implements"

        # Now edge exists
        assert parent.has_child(child)
        assert child.has_parent(parent)

    def test_add_edge_with_assertion_targets(self):
        """Add edge with assertion targets."""
        graph = build_graph_with_assertions()

        entry = graph.add_edge(
            "REQ-p00002",
            "REQ-p00001",
            EdgeKind.IMPLEMENTS,
            assertion_targets=["A", "B"],
        )

        assert entry.after_state["assertion_targets"] == ["A", "B"]

        # Check edge has assertion targets
        parent = graph.find_by_id("REQ-p00001")
        edges = list(parent.iter_outgoing_edges())
        assert len(edges) == 1
        assert "A" in edges[0].assertion_targets
        assert "B" in edges[0].assertion_targets

    def test_add_edge_source_not_found(self):
        """Adding edge with non-existent source raises KeyError."""
        graph = build_disconnected_graph()

        with pytest.raises(KeyError, match="not found"):
            graph.add_edge("REQ-nonexistent", "REQ-p00001", EdgeKind.IMPLEMENTS)

    def test_add_edge_target_not_found_creates_broken_ref(self):
        """Adding edge with non-existent target creates broken reference."""
        graph = build_disconnected_graph()
        initial_broken_count = len(graph.broken_references())

        entry = graph.add_edge("REQ-p00002", "REQ-nonexistent", EdgeKind.IMPLEMENTS)

        assert entry.after_state.get("broken") is True
        assert len(graph.broken_references()) == initial_broken_count + 1

        # Find the broken reference
        broken = graph.broken_references()[-1]
        assert broken.source_id == "REQ-p00002"
        assert broken.target_id == "REQ-nonexistent"
        assert broken.edge_kind == "implements"

    def test_add_edge_removes_orphan_status(self):
        """Adding edge removes source from orphans."""
        graph = build_disconnected_graph()
        # Mark child as orphan manually for this test
        graph._orphaned_ids.add("REQ-p00002")
        assert "REQ-p00002" in graph._orphaned_ids

        graph.add_edge("REQ-p00002", "REQ-p00001", EdgeKind.IMPLEMENTS)

        assert "REQ-p00002" not in graph._orphaned_ids

    def test_add_edge_logs_mutation(self):
        """Add edge is logged."""
        graph = build_disconnected_graph()
        assert len(graph.mutation_log) == 0

        graph.add_edge("REQ-p00002", "REQ-p00001", EdgeKind.IMPLEMENTS)

        assert len(graph.mutation_log) == 1
        entry = graph.mutation_log.last()
        assert entry.operation == "add_edge"

    def test_add_edge_undo(self):
        """Undo removes the edge."""
        graph = build_disconnected_graph()

        graph.add_edge("REQ-p00002", "REQ-p00001", EdgeKind.IMPLEMENTS)

        parent = graph.find_by_id("REQ-p00001")
        child = graph.find_by_id("REQ-p00002")
        assert parent.has_child(child)

        graph.undo_last()

        assert not parent.has_child(child)

    def test_add_edge_undo_restores_orphan_status(self):
        """Undo restores orphan status if node was orphan before."""
        graph = build_disconnected_graph()
        graph._orphaned_ids.add("REQ-p00002")

        graph.add_edge("REQ-p00002", "REQ-p00001", EdgeKind.IMPLEMENTS)
        assert "REQ-p00002" not in graph._orphaned_ids

        graph.undo_last()

        assert "REQ-p00002" in graph._orphaned_ids

    def test_add_edge_undo_removes_broken_ref(self):
        """Undo removes broken reference if target didn't exist."""
        graph = build_disconnected_graph()
        initial_broken_count = len(graph.broken_references())

        graph.add_edge("REQ-p00002", "REQ-nonexistent", EdgeKind.IMPLEMENTS)
        assert len(graph.broken_references()) == initial_broken_count + 1

        graph.undo_last()

        assert len(graph.broken_references()) == initial_broken_count


class TestChangeEdgeKind:
    """Tests for TraceGraph.change_edge_kind()."""

    def test_REQ_o00062_C_change_edge_kind_switches_relationship(self):
        """REQ-o00062-C: Basic change edge kind works."""
        graph = build_hierarchy_graph()

        # Initially implements
        child = graph.find_by_id("REQ-p00002")
        edges = list(child.iter_incoming_edges())
        assert len(edges) == 1
        assert edges[0].kind == EdgeKind.IMPLEMENTS

        entry = graph.change_edge_kind("REQ-p00002", "REQ-p00001", EdgeKind.REFINES)

        assert entry.operation == "change_edge_kind"
        assert entry.before_state["edge_kind"] == "implements"
        assert entry.after_state["edge_kind"] == "refines"

        # Edge kind updated
        edges = list(child.iter_incoming_edges())
        assert edges[0].kind == EdgeKind.REFINES

    def test_change_edge_kind_source_not_found(self):
        """Changing edge kind with non-existent source raises KeyError."""
        graph = build_hierarchy_graph()

        with pytest.raises(KeyError, match="not found"):
            graph.change_edge_kind("REQ-nonexistent", "REQ-p00001", EdgeKind.REFINES)

    def test_change_edge_kind_target_not_found(self):
        """Changing edge kind with non-existent target raises KeyError."""
        graph = build_hierarchy_graph()

        with pytest.raises(KeyError, match="not found"):
            graph.change_edge_kind("REQ-p00002", "REQ-nonexistent", EdgeKind.REFINES)

    def test_change_edge_kind_no_edge(self):
        """Changing edge kind when no edge exists raises ValueError."""
        graph = build_disconnected_graph()

        with pytest.raises(ValueError, match="No edge exists"):
            graph.change_edge_kind("REQ-p00002", "REQ-p00001", EdgeKind.REFINES)

    def test_change_edge_kind_preserves_assertion_targets(self):
        """Changing edge kind preserves assertion targets."""
        graph = build_graph_with_assertions()
        graph.add_edge("REQ-p00002", "REQ-p00001", EdgeKind.IMPLEMENTS, ["A"])

        entry = graph.change_edge_kind("REQ-p00002", "REQ-p00001", EdgeKind.REFINES)

        assert entry.before_state["assertion_targets"] == ["A"]
        assert entry.after_state["assertion_targets"] == ["A"]

        # Edge still has assertion targets
        parent = graph.find_by_id("REQ-p00001")
        edges = list(parent.iter_outgoing_edges())
        assert "A" in edges[0].assertion_targets

    def test_change_edge_kind_logs_mutation(self):
        """Change edge kind is logged."""
        graph = build_hierarchy_graph()

        graph.change_edge_kind("REQ-p00002", "REQ-p00001", EdgeKind.REFINES)

        assert len(graph.mutation_log) == 1
        entry = graph.mutation_log.last()
        assert entry.operation == "change_edge_kind"

    def test_change_edge_kind_undo(self):
        """Undo restores original edge kind."""
        graph = build_hierarchy_graph()

        graph.change_edge_kind("REQ-p00002", "REQ-p00001", EdgeKind.REFINES)

        child = graph.find_by_id("REQ-p00002")
        edges = list(child.iter_incoming_edges())
        assert edges[0].kind == EdgeKind.REFINES

        graph.undo_last()

        edges = list(child.iter_incoming_edges())
        assert edges[0].kind == EdgeKind.IMPLEMENTS


class TestDeleteEdge:
    """Tests for TraceGraph.delete_edge()."""

    def test_REQ_o00062_C_delete_edge_removes_relationship(self):
        """REQ-o00062-C: Basic delete edge removes relationship."""
        graph = build_hierarchy_graph()

        parent = graph.find_by_id("REQ-p00001")
        child = graph.find_by_id("REQ-p00002")
        assert parent.has_child(child)

        entry = graph.delete_edge("REQ-p00002", "REQ-p00001")

        assert entry.operation == "delete_edge"
        assert entry.target_id == "REQ-p00002"
        assert entry.before_state["edge_kind"] == "implements"

        # Edge removed
        assert not parent.has_child(child)
        assert not child.has_parent(parent)

    def test_delete_edge_source_not_found(self):
        """Deleting edge with non-existent source raises KeyError."""
        graph = build_hierarchy_graph()

        with pytest.raises(KeyError, match="not found"):
            graph.delete_edge("REQ-nonexistent", "REQ-p00001")

    def test_delete_edge_target_not_found(self):
        """Deleting edge with non-existent target raises KeyError."""
        graph = build_hierarchy_graph()

        with pytest.raises(KeyError, match="not found"):
            graph.delete_edge("REQ-p00002", "REQ-nonexistent")

    def test_delete_edge_no_edge(self):
        """Deleting edge when no edge exists raises ValueError."""
        graph = build_disconnected_graph()

        with pytest.raises(ValueError, match="No edge exists"):
            graph.delete_edge("REQ-p00002", "REQ-p00001")

    def test_delete_edge_source_becomes_orphan(self):
        """Deleting last parent edge makes source orphan."""
        graph = build_hierarchy_graph()

        # Child has one parent
        child = graph.find_by_id("REQ-p00002")
        assert child.parent_count() == 1
        assert "REQ-p00002" not in graph._orphaned_ids

        entry = graph.delete_edge("REQ-p00002", "REQ-p00001")

        assert entry.after_state.get("became_orphan") is True
        assert "REQ-p00002" in graph._orphaned_ids

    def test_delete_edge_root_not_orphaned(self):
        """Deleting edge from root node doesn't mark as orphan."""
        # Create a graph where a root has an edge to another root
        builder = GraphBuilder()
        builder.add_parsed_content(make_req("REQ-p00001", "Parent"))
        builder.add_parsed_content(make_req("REQ-p00002", "Child", implements=["REQ-p00001"]))
        graph = builder.build()

        # REQ-p00001 is a root
        assert graph.has_root("REQ-p00001")

        # Add an edge from REQ-p00001 to REQ-p00002 so REQ-p00001 has a parent
        graph.add_edge("REQ-p00001", "REQ-p00002", EdgeKind.IMPLEMENTS)

        # Now delete that edge
        graph.delete_edge("REQ-p00001", "REQ-p00002")

        # REQ-p00001 is still a root, not orphaned
        assert graph.has_root("REQ-p00001")
        assert "REQ-p00001" not in graph._orphaned_ids

    def test_delete_edge_records_assertion_targets(self):
        """Delete edge records assertion targets for undo."""
        graph = build_graph_with_assertions()
        graph.add_edge("REQ-p00002", "REQ-p00001", EdgeKind.IMPLEMENTS, ["A", "B"])

        entry = graph.delete_edge("REQ-p00002", "REQ-p00001")

        assert entry.before_state["assertion_targets"] == ["A", "B"]

    def test_delete_edge_logs_mutation(self):
        """Delete edge is logged."""
        graph = build_hierarchy_graph()

        graph.delete_edge("REQ-p00002", "REQ-p00001")

        # First entry may be from initial build, check last
        entry = graph.mutation_log.last()
        assert entry.operation == "delete_edge"

    def test_delete_edge_undo(self):
        """Undo restores the edge."""
        graph = build_hierarchy_graph()

        graph.delete_edge("REQ-p00002", "REQ-p00001")

        parent = graph.find_by_id("REQ-p00001")
        child = graph.find_by_id("REQ-p00002")
        assert not parent.has_child(child)

        graph.undo_last()

        assert parent.has_child(child)

    def test_delete_edge_undo_restores_assertion_targets(self):
        """Undo restores assertion targets."""
        graph = build_graph_with_assertions()
        graph.add_edge("REQ-p00002", "REQ-p00001", EdgeKind.IMPLEMENTS, ["A"])

        graph.delete_edge("REQ-p00002", "REQ-p00001")
        graph.undo_last()

        parent = graph.find_by_id("REQ-p00001")
        edges = list(parent.iter_outgoing_edges())
        assert len(edges) == 1
        assert "A" in edges[0].assertion_targets

    def test_delete_edge_undo_removes_orphan_status(self):
        """Undo removes orphan status if node became orphan after delete."""
        graph = build_hierarchy_graph()

        _entry = graph.delete_edge("REQ-p00002", "REQ-p00001")  # noqa: F841
        assert "REQ-p00002" in graph._orphaned_ids

        graph.undo_last()

        assert "REQ-p00002" not in graph._orphaned_ids


class TestFixBrokenReference:
    """Tests for TraceGraph.fix_broken_reference()."""

    def test_REQ_o00062_C_fix_broken_reference_creates_valid_edge(self):
        """REQ-o00062-C: Basic fix creates valid edge."""
        graph = build_graph_with_broken_reference()

        # Has broken reference
        broken = graph.broken_references()
        assert len(broken) == 1
        assert broken[0].source_id == "REQ-p00002"
        assert broken[0].target_id == "REQ-nonexistent"

        entry = graph.fix_broken_reference("REQ-p00002", "REQ-nonexistent", "REQ-p00001")

        assert entry.operation == "fix_broken_reference"
        assert entry.before_state["old_target_id"] == "REQ-nonexistent"
        assert entry.after_state["new_target_id"] == "REQ-p00001"
        assert entry.after_state.get("fixed") is True

        # Broken reference removed
        assert len(graph.broken_references()) == 0

        # Valid edge created
        parent = graph.find_by_id("REQ-p00001")
        child = graph.find_by_id("REQ-p00002")
        assert parent.has_child(child)

    def test_fix_broken_reference_source_not_found(self):
        """Fixing with non-existent source raises KeyError."""
        graph = build_graph_with_broken_reference()

        with pytest.raises(KeyError, match="not found"):
            graph.fix_broken_reference("REQ-nonexistent", "REQ-foo", "REQ-p00001")

    def test_fix_broken_reference_no_broken_ref(self):
        """Fixing non-existent broken reference raises ValueError."""
        graph = build_disconnected_graph()

        with pytest.raises(ValueError, match="No broken reference"):
            graph.fix_broken_reference("REQ-p00002", "REQ-nonexistent", "REQ-p00001")

    def test_fix_broken_reference_new_target_not_found(self):
        """Fixing to non-existent target keeps reference broken."""
        graph = build_graph_with_broken_reference()

        entry = graph.fix_broken_reference("REQ-p00002", "REQ-nonexistent", "REQ-also-nonexistent")

        assert entry.after_state.get("still_broken") is True

        # Still has broken reference (with new target)
        broken = graph.broken_references()
        assert len(broken) == 1
        assert broken[0].source_id == "REQ-p00002"
        assert broken[0].target_id == "REQ-also-nonexistent"

    def test_fix_broken_reference_removes_orphan_status(self):
        """Fixing broken reference removes orphan status."""
        graph = build_graph_with_broken_reference()
        graph._orphaned_ids.add("REQ-p00002")

        graph.fix_broken_reference("REQ-p00002", "REQ-nonexistent", "REQ-p00001")

        assert "REQ-p00002" not in graph._orphaned_ids

    def test_fix_broken_reference_logs_mutation(self):
        """Fix broken reference is logged."""
        graph = build_graph_with_broken_reference()

        graph.fix_broken_reference("REQ-p00002", "REQ-nonexistent", "REQ-p00001")

        entry = graph.mutation_log.last()
        assert entry.operation == "fix_broken_reference"

    def test_fix_broken_reference_undo(self):
        """Undo restores original broken reference."""
        graph = build_graph_with_broken_reference()

        graph.fix_broken_reference("REQ-p00002", "REQ-nonexistent", "REQ-p00001")

        # Edge exists
        parent = graph.find_by_id("REQ-p00001")
        child = graph.find_by_id("REQ-p00002")
        assert parent.has_child(child)
        assert len(graph.broken_references()) == 0

        graph.undo_last()

        # Edge removed, broken reference restored
        assert not parent.has_child(child)
        broken = graph.broken_references()
        assert len(broken) == 1
        assert broken[0].source_id == "REQ-p00002"
        assert broken[0].target_id == "REQ-nonexistent"

    def test_fix_broken_reference_undo_restores_orphan_status(self):
        """Undo restores orphan status if node was orphan before fix."""
        graph = build_graph_with_broken_reference()
        graph._orphaned_ids.add("REQ-p00002")

        graph.fix_broken_reference("REQ-p00002", "REQ-nonexistent", "REQ-p00001")
        assert "REQ-p00002" not in graph._orphaned_ids

        graph.undo_last()

        assert "REQ-p00002" in graph._orphaned_ids

    def test_fix_broken_reference_undo_still_broken(self):
        """Undo restores original broken reference when fix kept it broken."""
        graph = build_graph_with_broken_reference()

        # Fix to another non-existent target
        graph.fix_broken_reference("REQ-p00002", "REQ-nonexistent", "REQ-also-nonexistent")

        broken = graph.broken_references()
        assert broken[0].target_id == "REQ-also-nonexistent"

        graph.undo_last()

        broken = graph.broken_references()
        assert len(broken) == 1
        assert broken[0].target_id == "REQ-nonexistent"


class TestMultipleEdgeMutations:
    """Tests for sequences of edge mutations."""

    def test_multiple_mutations_logged(self):
        """Multiple edge mutations are all logged in order."""
        graph = build_disconnected_graph()

        graph.add_edge("REQ-p00002", "REQ-p00001", EdgeKind.IMPLEMENTS)
        graph.change_edge_kind("REQ-p00002", "REQ-p00001", EdgeKind.REFINES)
        graph.delete_edge("REQ-p00002", "REQ-p00001")

        assert len(graph.mutation_log) == 3
        entries = list(graph.mutation_log.iter_entries())
        assert entries[0].operation == "add_edge"
        assert entries[1].operation == "change_edge_kind"
        assert entries[2].operation == "delete_edge"

    def test_undo_multiple_in_reverse(self):
        """Multiple undos reverse operations correctly."""
        graph = build_disconnected_graph()

        graph.add_edge("REQ-p00002", "REQ-p00001", EdgeKind.IMPLEMENTS)
        graph.change_edge_kind("REQ-p00002", "REQ-p00001", EdgeKind.REFINES)

        parent = graph.find_by_id("REQ-p00001")
        child = graph.find_by_id("REQ-p00002")

        # Current state: REFINES edge
        edges = list(child.iter_incoming_edges())
        assert edges[0].kind == EdgeKind.REFINES

        graph.undo_last()  # Undo change_edge_kind

        edges = list(child.iter_incoming_edges())
        assert edges[0].kind == EdgeKind.IMPLEMENTS

        graph.undo_last()  # Undo add_edge

        assert not parent.has_child(child)
