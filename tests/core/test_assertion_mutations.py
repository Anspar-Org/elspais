# Validates REQ-o00062-B, REQ-o00062-D, REQ-o00062-E, REQ-o00062-F
"""Tests for assertion mutation operations (rename, update, add, delete)."""
from __future__ import annotations

import pytest

from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers import ParsedContent


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


def build_graph_with_assertions() -> TraceGraph:
    """Build a graph with a requirement that has assertions."""
    builder = GraphBuilder()
    builder.add_parsed_content(
        make_req(
            "REQ-p00001",
            "Requirement with Assertions",
            assertions=[
                {"label": "A", "text": "First assertion"},
                {"label": "B", "text": "Second assertion"},
                {"label": "C", "text": "Third assertion"},
            ],
        )
    )
    return builder.build()


def build_graph_with_child_implementing_assertion() -> TraceGraph:
    """Build a graph where a child implements specific assertions."""
    builder = GraphBuilder()
    builder.add_parsed_content(
        make_req(
            "REQ-p00001",
            "Parent",
            assertions=[
                {"label": "A", "text": "First"},
                {"label": "B", "text": "Second"},
            ],
        )
    )
    # Child implements assertion A
    builder.add_parsed_content(
        make_req(
            "REQ-p00002",
            "Child",
            implements=["REQ-p00001-A"],
        )
    )
    return builder.build()


class TestRenameAssertion:
    """Tests for TraceGraph.rename_assertion()."""

    def test_REQ_o00062_B_rename_updates_assertion_id_and_label(self):
        """REQ-o00062-B: Basic rename updates assertion ID and label."""
        graph = build_graph_with_assertions()

        entry = graph.rename_assertion("REQ-p00001-A", "D")

        assert entry.operation == "rename_assertion"
        assert entry.target_id == "REQ-p00001-A"
        assert entry.before_state["id"] == "REQ-p00001-A"
        assert entry.before_state["label"] == "A"
        assert entry.after_state["id"] == "REQ-p00001-D"
        assert entry.after_state["label"] == "D"

        # Old ID gone, new ID exists
        assert graph.find_by_id("REQ-p00001-A") is None
        assert graph.find_by_id("REQ-p00001-D") is not None

        # Label field updated
        node = graph.find_by_id("REQ-p00001-D")
        assert node.get_field("label") == "D"

    def test_rename_not_found(self):
        """Renaming non-existent assertion raises KeyError."""
        graph = build_graph_with_assertions()

        with pytest.raises(KeyError, match="not found"):
            graph.rename_assertion("REQ-p00001-Z", "X")

    def test_rename_not_assertion(self):
        """Renaming a non-assertion node raises ValueError."""
        graph = build_graph_with_assertions()

        with pytest.raises(ValueError, match="not an assertion"):
            graph.rename_assertion("REQ-p00001", "D")

    def test_rename_conflict(self):
        """Renaming to existing assertion raises ValueError."""
        graph = build_graph_with_assertions()

        with pytest.raises(ValueError, match="already exists"):
            graph.rename_assertion("REQ-p00001-A", "B")

    def test_rename_updates_edges(self):
        """Renaming updates edges with assertion_targets."""
        graph = build_graph_with_child_implementing_assertion()

        # Child implements A
        _child = graph.find_by_id("REQ-p00002")  # noqa: F841 - verify child exists
        parent = graph.find_by_id("REQ-p00001")

        # Find edge from parent to child
        edges = list(parent.iter_outgoing_edges())
        assert any("A" in e.assertion_targets for e in edges)

        # Rename A to D
        graph.rename_assertion("REQ-p00001-A", "D")

        # Edge should now reference D
        edges = list(parent.iter_outgoing_edges())
        assert any("D" in e.assertion_targets for e in edges)
        assert not any("A" in e.assertion_targets for e in edges)

    def test_rename_affects_hash(self):
        """Rename operation is marked as affecting hash."""
        graph = build_graph_with_assertions()

        entry = graph.rename_assertion("REQ-p00001-A", "D")
        assert entry.affects_hash is True

    def test_rename_logs_mutation(self):
        """Rename operation is logged."""
        graph = build_graph_with_assertions()
        assert len(graph.mutation_log) == 0

        graph.rename_assertion("REQ-p00001-A", "D")

        assert len(graph.mutation_log) == 1
        entry = graph.mutation_log.last()
        assert entry.operation == "rename_assertion"

    def test_rename_undo(self):
        """Undo restores original assertion ID and label."""
        graph = build_graph_with_assertions()

        # Capture state before rename
        entry = graph.rename_assertion("REQ-p00001-A", "D")
        original_hash = entry.before_state.get("parent_hash")
        assert graph.find_by_id("REQ-p00001-A") is None

        graph.undo_last()

        assert graph.find_by_id("REQ-p00001-A") is not None
        assert graph.find_by_id("REQ-p00001-D") is None
        assert graph.find_by_id("REQ-p00001-A").get_field("label") == "A"

        # Hash restored (if original was None, it should be None again)
        assert graph.find_by_id("REQ-p00001").get_field("hash") == original_hash

    def test_rename_undo_restores_edges(self):
        """Undo also restores edge assertion_targets."""
        graph = build_graph_with_child_implementing_assertion()

        graph.rename_assertion("REQ-p00001-A", "D")
        graph.undo_last()

        parent = graph.find_by_id("REQ-p00001")
        edges = list(parent.iter_outgoing_edges())
        assert any("A" in e.assertion_targets for e in edges)
        assert not any("D" in e.assertion_targets for e in edges)


class TestUpdateAssertion:
    """Tests for TraceGraph.update_assertion()."""

    def test_REQ_o00062_B_update_assertion_text(self):
        """REQ-o00062-B: Basic text update works."""
        graph = build_graph_with_assertions()

        entry = graph.update_assertion("REQ-p00001-A", "Updated assertion text")

        assert entry.operation == "update_assertion"
        assert entry.before_state["text"] == "First assertion"
        assert entry.after_state["text"] == "Updated assertion text"

        node = graph.find_by_id("REQ-p00001-A")
        assert node.get_label() == "Updated assertion text"

    def test_update_not_found(self):
        """Updating non-existent assertion raises KeyError."""
        graph = build_graph_with_assertions()

        with pytest.raises(KeyError, match="not found"):
            graph.update_assertion("REQ-p00001-Z", "New text")

    def test_update_not_assertion(self):
        """Updating a non-assertion node raises ValueError."""
        graph = build_graph_with_assertions()

        with pytest.raises(ValueError, match="not an assertion"):
            graph.update_assertion("REQ-p00001", "New text")

    def test_update_changes_hash(self):
        """Updating assertion text changes parent hash."""
        graph = build_graph_with_assertions()
        parent = graph.find_by_id("REQ-p00001")
        old_hash = parent.get_field("hash")

        graph.update_assertion("REQ-p00001-A", "Completely different text")

        new_hash = parent.get_field("hash")
        assert new_hash != old_hash

    def test_update_affects_hash(self):
        """Update operation is marked as affecting hash."""
        graph = build_graph_with_assertions()

        entry = graph.update_assertion("REQ-p00001-A", "New text")
        assert entry.affects_hash is True

    def test_update_logs_mutation(self):
        """Update operation is logged."""
        graph = build_graph_with_assertions()

        graph.update_assertion("REQ-p00001-A", "New text")

        assert len(graph.mutation_log) == 1
        entry = graph.mutation_log.last()
        assert entry.operation == "update_assertion"

    def test_update_undo(self):
        """Undo restores original text and hash."""
        graph = build_graph_with_assertions()
        parent = graph.find_by_id("REQ-p00001")
        original_text = graph.find_by_id("REQ-p00001-A").get_label()

        entry = graph.update_assertion("REQ-p00001-A", "New text")
        original_hash = entry.before_state.get("parent_hash")
        assert graph.find_by_id("REQ-p00001-A").get_label() == "New text"

        graph.undo_last()

        assert graph.find_by_id("REQ-p00001-A").get_label() == original_text
        assert parent.get_field("hash") == original_hash


class TestAddAssertion:
    """Tests for TraceGraph.add_assertion()."""

    def test_REQ_o00062_B_add_creates_new_assertion(self):
        """REQ-o00062-B: Basic add creates a new assertion."""
        graph = build_graph_with_assertions()

        entry = graph.add_assertion("REQ-p00001", "D", "Fourth assertion")

        assert entry.operation == "add_assertion"
        assert entry.target_id == "REQ-p00001-D"
        assert entry.after_state["label"] == "D"
        assert entry.after_state["text"] == "Fourth assertion"

        node = graph.find_by_id("REQ-p00001-D")
        assert node is not None
        assert node.kind == NodeKind.ASSERTION
        assert node.get_label() == "Fourth assertion"
        assert node.get_field("label") == "D"

    def test_add_links_to_parent(self):
        """Added assertion is linked to parent requirement."""
        graph = build_graph_with_assertions()

        graph.add_assertion("REQ-p00001", "D", "Fourth assertion")

        parent = graph.find_by_id("REQ-p00001")
        child = graph.find_by_id("REQ-p00001-D")

        assert parent.has_child(child)
        assert child.has_parent(parent)

    def test_add_not_found(self):
        """Adding to non-existent requirement raises KeyError."""
        graph = build_graph_with_assertions()

        with pytest.raises(KeyError, match="not found"):
            graph.add_assertion("REQ-nonexistent", "A", "Text")

    def test_add_not_requirement(self):
        """Adding to a non-requirement node raises ValueError."""
        graph = build_graph_with_assertions()

        with pytest.raises(ValueError, match="not a requirement"):
            graph.add_assertion("REQ-p00001-A", "X", "Text")

    def test_add_duplicate(self):
        """Adding duplicate assertion raises ValueError."""
        graph = build_graph_with_assertions()

        with pytest.raises(ValueError, match="already exists"):
            graph.add_assertion("REQ-p00001", "A", "Duplicate")

    def test_add_changes_hash(self):
        """Adding assertion changes parent hash."""
        graph = build_graph_with_assertions()
        parent = graph.find_by_id("REQ-p00001")
        old_hash = parent.get_field("hash")

        graph.add_assertion("REQ-p00001", "D", "New assertion")

        new_hash = parent.get_field("hash")
        assert new_hash != old_hash

    def test_add_affects_hash(self):
        """Add operation is marked as affecting hash."""
        graph = build_graph_with_assertions()

        entry = graph.add_assertion("REQ-p00001", "D", "New assertion")
        assert entry.affects_hash is True

    def test_add_logs_mutation(self):
        """Add operation is logged."""
        graph = build_graph_with_assertions()

        graph.add_assertion("REQ-p00001", "D", "New assertion")

        assert len(graph.mutation_log) == 1
        entry = graph.mutation_log.last()
        assert entry.operation == "add_assertion"

    def test_add_undo(self):
        """Undo removes the added assertion and restores hash."""
        graph = build_graph_with_assertions()
        parent = graph.find_by_id("REQ-p00001")
        original_count = sum(1 for c in parent.iter_children() if c.kind == NodeKind.ASSERTION)

        entry = graph.add_assertion("REQ-p00001", "D", "New assertion")
        original_hash = entry.before_state.get("parent_hash")
        assert graph.find_by_id("REQ-p00001-D") is not None

        graph.undo_last()

        assert graph.find_by_id("REQ-p00001-D") is None
        assert parent.get_field("hash") == original_hash
        new_count = sum(1 for c in parent.iter_children() if c.kind == NodeKind.ASSERTION)
        assert new_count == original_count


class TestDeleteAssertion:
    """Tests for TraceGraph.delete_assertion()."""

    def test_REQ_o00062_B_delete_removes_and_preserves(self):
        """REQ-o00062-B: Basic delete removes assertion from index (with default compact)."""
        graph = build_graph_with_assertions()

        # Before: A, B, C
        # After (with compact): A, B (was C)
        entry = graph.delete_assertion("REQ-p00001-B")

        assert entry.operation == "delete_assertion"
        assert entry.target_id == "REQ-p00001-B"

        # The original B was deleted, but C was compacted to B
        # So find_by_id("REQ-p00001-B") returns the compacted node
        # Check that deleted_nodes contains the original B
        deleted = graph.deleted_nodes()
        deleted_ids = {n.id for n in deleted}
        assert "REQ-p00001-B" in deleted_ids

        # The old C (now B) has C's original text
        compacted = graph.find_by_id("REQ-p00001-B")
        assert compacted.get_label() == "Third assertion"

    def test_delete_not_found(self):
        """Deleting non-existent assertion raises KeyError."""
        graph = build_graph_with_assertions()

        with pytest.raises(KeyError, match="not found"):
            graph.delete_assertion("REQ-p00001-Z")

    def test_delete_not_assertion(self):
        """Deleting a non-assertion node raises ValueError."""
        graph = build_graph_with_assertions()

        with pytest.raises(ValueError, match="not an assertion"):
            graph.delete_assertion("REQ-p00001")

    def test_delete_preserves_in_deleted_nodes(self):
        """Deleted assertion is preserved in _deleted_nodes."""
        graph = build_graph_with_assertions()

        graph.delete_assertion("REQ-p00001-B")

        assert graph.has_deletions()
        deleted = graph.deleted_nodes()
        deleted_ids = {n.id for n in deleted}
        assert "REQ-p00001-B" in deleted_ids

    def test_delete_with_compact(self):
        """Delete with compact=True renumbers subsequent assertions."""
        graph = build_graph_with_assertions()

        # Before: A, B, C
        assert graph.find_by_id("REQ-p00001-A") is not None
        assert graph.find_by_id("REQ-p00001-B") is not None
        assert graph.find_by_id("REQ-p00001-C") is not None

        # Delete B with compact
        entry = graph.delete_assertion("REQ-p00001-B", compact=True)

        # After: A, B (was C)
        assert graph.find_by_id("REQ-p00001-A") is not None
        assert graph.find_by_id("REQ-p00001-B") is not None  # Was C
        assert graph.find_by_id("REQ-p00001-C") is None

        # The compacted B should have C's text
        compacted = graph.find_by_id("REQ-p00001-B")
        assert compacted.get_label() == "Third assertion"
        assert compacted.get_field("label") == "B"

        # Check renames were recorded
        assert len(entry.before_state["renames"]) == 1
        rename = entry.before_state["renames"][0]
        assert rename["old_label"] == "C"
        assert rename["new_label"] == "B"

    def test_delete_without_compact(self):
        """Delete with compact=False leaves gaps."""
        graph = build_graph_with_assertions()

        graph.delete_assertion("REQ-p00001-B", compact=False)

        # After: A, C (gap at B)
        assert graph.find_by_id("REQ-p00001-A") is not None
        assert graph.find_by_id("REQ-p00001-B") is None
        assert graph.find_by_id("REQ-p00001-C") is not None

    def test_delete_removes_edges(self):
        """Delete removes edges referencing the assertion."""
        graph = build_graph_with_child_implementing_assertion()

        parent = graph.find_by_id("REQ-p00001")

        # Before: edge has A in assertion_targets
        edges = list(parent.iter_outgoing_edges())
        assert any("A" in e.assertion_targets for e in edges)

        graph.delete_assertion("REQ-p00001-A", compact=False)

        # After: no edges reference A
        edges = list(parent.iter_outgoing_edges())
        assert not any("A" in e.assertion_targets for e in edges)

    def test_delete_changes_hash(self):
        """Deleting assertion changes parent hash."""
        graph = build_graph_with_assertions()
        parent = graph.find_by_id("REQ-p00001")
        old_hash = parent.get_field("hash")

        graph.delete_assertion("REQ-p00001-B")

        new_hash = parent.get_field("hash")
        assert new_hash != old_hash

    def test_delete_affects_hash(self):
        """Delete operation is marked as affecting hash."""
        graph = build_graph_with_assertions()

        entry = graph.delete_assertion("REQ-p00001-B")
        assert entry.affects_hash is True

    def test_delete_logs_mutation(self):
        """Delete operation is logged."""
        graph = build_graph_with_assertions()

        graph.delete_assertion("REQ-p00001-B")

        assert len(graph.mutation_log) == 1
        entry = graph.mutation_log.last()
        assert entry.operation == "delete_assertion"

    def test_delete_undo_without_compact(self):
        """Undo restores the deleted assertion (no compact)."""
        graph = build_graph_with_assertions()
        parent = graph.find_by_id("REQ-p00001")

        entry = graph.delete_assertion("REQ-p00001-B", compact=False)
        original_hash = entry.before_state.get("parent_hash")
        assert graph.find_by_id("REQ-p00001-B") is None

        graph.undo_last()

        node = graph.find_by_id("REQ-p00001-B")
        assert node is not None
        assert node.get_label() == "Second assertion"
        assert node.get_field("label") == "B"
        assert parent.get_field("hash") == original_hash

    def test_delete_undo_with_compact(self):
        """Undo restores the deleted assertion and un-compacts."""
        graph = build_graph_with_assertions()
        parent = graph.find_by_id("REQ-p00001")

        # Get original C text
        original_c_text = graph.find_by_id("REQ-p00001-C").get_label()

        entry = graph.delete_assertion("REQ-p00001-B", compact=True)
        original_hash = entry.before_state.get("parent_hash")

        # After delete+compact: A, B (was C)
        assert graph.find_by_id("REQ-p00001-B").get_label() == "Third assertion"

        graph.undo_last()

        # Restored: A, B, C
        assert graph.find_by_id("REQ-p00001-A") is not None
        assert graph.find_by_id("REQ-p00001-B") is not None
        assert graph.find_by_id("REQ-p00001-C") is not None

        # B should have original text
        assert graph.find_by_id("REQ-p00001-B").get_label() == "Second assertion"

        # C should have original text
        assert graph.find_by_id("REQ-p00001-C").get_label() == original_c_text

        # Hash restored
        assert parent.get_field("hash") == original_hash

    def test_delete_first_assertion(self):
        """Deleting first assertion compacts correctly."""
        graph = build_graph_with_assertions()

        graph.delete_assertion("REQ-p00001-A", compact=True)

        # After: A (was B), B (was C)
        assert graph.find_by_id("REQ-p00001-A") is not None
        assert graph.find_by_id("REQ-p00001-B") is not None
        assert graph.find_by_id("REQ-p00001-C") is None

        assert graph.find_by_id("REQ-p00001-A").get_label() == "Second assertion"
        assert graph.find_by_id("REQ-p00001-B").get_label() == "Third assertion"

    def test_delete_last_assertion(self):
        """Deleting last assertion requires no compaction."""
        graph = build_graph_with_assertions()

        entry = graph.delete_assertion("REQ-p00001-C", compact=True)

        # After: A, B
        assert graph.find_by_id("REQ-p00001-A") is not None
        assert graph.find_by_id("REQ-p00001-B") is not None
        assert graph.find_by_id("REQ-p00001-C") is None

        # No renames needed
        assert len(entry.before_state["renames"]) == 0


class TestMultipleAssertionMutations:
    """Tests for sequences of assertion mutations."""

    def test_multiple_mutations_logged(self):
        """Multiple mutations are all logged in order."""
        graph = build_graph_with_assertions()

        graph.update_assertion("REQ-p00001-A", "Updated A")
        graph.add_assertion("REQ-p00001", "D", "Added D")
        graph.rename_assertion("REQ-p00001-D", "E")
        graph.delete_assertion("REQ-p00001-B")

        assert len(graph.mutation_log) == 4
        entries = list(graph.mutation_log.iter_entries())
        assert entries[0].operation == "update_assertion"
        assert entries[1].operation == "add_assertion"
        assert entries[2].operation == "rename_assertion"
        assert entries[3].operation == "delete_assertion"

    def test_undo_multiple_in_reverse(self):
        """Multiple undos reverse operations correctly."""
        graph = build_graph_with_assertions()
        original_a_text = graph.find_by_id("REQ-p00001-A").get_label()

        graph.update_assertion("REQ-p00001-A", "Updated once")
        graph.update_assertion("REQ-p00001-A", "Updated twice")

        graph.undo_last()
        assert graph.find_by_id("REQ-p00001-A").get_label() == "Updated once"

        graph.undo_last()
        assert graph.find_by_id("REQ-p00001-A").get_label() == original_a_text
