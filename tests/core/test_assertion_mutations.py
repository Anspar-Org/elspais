# Validates REQ-o00062-B, REQ-o00062-D, REQ-o00062-E, REQ-o00062-F
# Verifies: REQ-o00062-R
"""Tests for assertion mutation operations (rename, update, add, delete)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from elspais.config import load_config
from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers import ParsedContent
from elspais.graph.render import render_save
from elspais.utilities.patterns import build_resolver
from tests.core.graph_test_helpers import grammar_for


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
    builder = GraphBuilder(namespace="REQ", resolver=grammar_for("REQ"))
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
    builder = GraphBuilder(namespace="REQ", resolver=grammar_for("REQ"))
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

    # Verifies: REQ-o00062-B
    def test_rename_not_found(self):
        """Renaming non-existent assertion raises KeyError."""
        graph = build_graph_with_assertions()

        with pytest.raises(KeyError, match="not found"):
            graph.rename_assertion("REQ-p00001-Z", "X")

    # Verifies: REQ-o00062-B
    def test_rename_not_assertion(self):
        """Renaming a non-assertion node raises ValueError."""
        graph = build_graph_with_assertions()

        with pytest.raises(ValueError, match="not an assertion"):
            graph.rename_assertion("REQ-p00001", "D")

    # Verifies: REQ-o00062-B
    def test_rename_conflict(self):
        """Renaming to existing assertion raises ValueError."""
        graph = build_graph_with_assertions()

        with pytest.raises(ValueError, match="already exists"):
            graph.rename_assertion("REQ-p00001-A", "B")

    # Verifies: REQ-o00062-B
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

    # Verifies: REQ-o00062-E
    def test_rename_affects_hash(self):
        """Rename operation is marked as affecting hash."""
        graph = build_graph_with_assertions()

        entry = graph.rename_assertion("REQ-p00001-A", "D")
        assert entry.affects_hash is True

    # Verifies: REQ-o00062-E
    def test_rename_logs_mutation(self):
        """Rename operation is logged."""
        graph = build_graph_with_assertions()
        assert len(graph.mutation_log) == 0

        graph.rename_assertion("REQ-p00001-A", "D")

        assert len(graph.mutation_log) == 1
        entry = graph.mutation_log.last()
        assert entry.operation == "rename_assertion"

    # Verifies: REQ-o00062-G
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

    # Verifies: REQ-o00062-G
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

    # Verifies: REQ-o00062-B
    def test_update_not_found(self):
        """Updating non-existent assertion raises KeyError."""
        graph = build_graph_with_assertions()

        with pytest.raises(KeyError, match="not found"):
            graph.update_assertion("REQ-p00001-Z", "New text")

    # Verifies: REQ-o00062-B
    def test_update_not_assertion(self):
        """Updating a non-assertion node raises ValueError."""
        graph = build_graph_with_assertions()

        with pytest.raises(ValueError, match="not an assertion"):
            graph.update_assertion("REQ-p00001", "New text")

    # Verifies: REQ-o00062-U
    def test_update_refuses_end_marker_line(self):
        """Text carrying an End-marker line would end the requirement early on
        reparse, so it is refused rather than stored."""
        graph = build_graph_with_assertions()
        original = graph.find_by_id("REQ-p00001-A").get_label()

        with pytest.raises(ValueError, match="End-marker"):
            graph.update_assertion(
                "REQ-p00001-A", "SHALL do things\n*End* *Requirement with Assertions*"
            )

        assert graph.find_by_id("REQ-p00001-A").get_label() == original
        assert len(graph.mutation_log) == 0

    # Verifies: REQ-o00062-U
    def test_update_refuses_heading_line(self):
        """Text carrying a heading line reads back as a section header."""
        graph = build_graph_with_assertions()

        with pytest.raises(ValueError, match="heading"):
            graph.update_assertion("REQ-p00001-A", "SHALL do things\n## Assertions")

        assert len(graph.mutation_log) == 0

    # Verifies: REQ-o00062-U
    def test_update_accepts_benign_multiline_text(self):
        """Ordinary continuation lines are content, not structure."""
        graph = build_graph_with_assertions()

        text = "SHALL do things\nacross several lines,\nnone of them structural."
        entry = graph.update_assertion("REQ-p00001-A", text)

        assert entry.operation == "update_assertion"
        assert graph.find_by_id("REQ-p00001-A").get_label() == text

    # Verifies: REQ-o00062-E
    def test_update_changes_hash(self):
        """Updating assertion text changes parent hash."""
        graph = build_graph_with_assertions()
        parent = graph.find_by_id("REQ-p00001")
        old_hash = parent.get_field("hash")

        graph.update_assertion("REQ-p00001-A", "Completely different text")

        new_hash = parent.get_field("hash")
        assert new_hash != old_hash

    # Verifies: REQ-o00062-E
    def test_update_affects_hash(self):
        """Update operation is marked as affecting hash."""
        graph = build_graph_with_assertions()

        entry = graph.update_assertion("REQ-p00001-A", "New text")
        assert entry.affects_hash is True

    # Verifies: REQ-o00062-E
    def test_update_logs_mutation(self):
        """Update operation is logged."""
        graph = build_graph_with_assertions()

        graph.update_assertion("REQ-p00001-A", "New text")

        assert len(graph.mutation_log) == 1
        entry = graph.mutation_log.last()
        assert entry.operation == "update_assertion"

    # Verifies: REQ-o00062-G
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

        entry = graph.add_assertion("REQ-p00001", "Fourth assertion")

        assert entry.operation == "add_assertion"
        assert entry.target_id == "REQ-p00001-D"
        assert entry.after_state["label"] == "D"
        assert entry.after_state["text"] == "Fourth assertion"

        node = graph.find_by_id("REQ-p00001-D")
        assert node is not None
        assert node.kind == NodeKind.ASSERTION
        assert node.get_label() == "Fourth assertion"
        assert node.get_field("label") == "D"

    # Verifies: REQ-o00062-B
    def test_add_links_to_parent(self):
        """Added assertion is linked to parent requirement."""
        graph = build_graph_with_assertions()

        graph.add_assertion("REQ-p00001", "Fourth assertion")

        parent = graph.find_by_id("REQ-p00001")
        child = graph.find_by_id("REQ-p00001-D")

        assert parent.has_child(child)
        assert child.has_parent(parent)

    # Verifies: REQ-o00062-B
    def test_add_not_found(self):
        """Adding to non-existent requirement raises KeyError."""
        graph = build_graph_with_assertions()

        with pytest.raises(KeyError, match="not found"):
            graph.add_assertion("REQ-nonexistent", "Text")

    # Verifies: REQ-o00062-B
    def test_add_not_requirement(self):
        """Adding to a non-requirement node raises ValueError."""
        graph = build_graph_with_assertions()

        with pytest.raises(ValueError, match="not a requirement"):
            graph.add_assertion("REQ-p00001-A", "Text")

    # Verifies: REQ-o00062-S
    # Verifies: REQ-o00062-U
    def test_add_refuses_end_marker_line(self):
        """New assertion text carrying an End-marker line is refused."""
        graph = build_graph_with_assertions()

        with pytest.raises(ValueError, match="End-marker"):
            graph.add_assertion("REQ-p00001", "*End* *Anything*")

        assert graph.find_by_id("REQ-p00001-D") is None
        assert len(graph.mutation_log) == 0

    # Verifies: REQ-o00062-U
    def test_add_refuses_heading_line(self):
        """New assertion text carrying a heading line is refused."""
        graph = build_graph_with_assertions()

        with pytest.raises(ValueError, match="heading"):
            graph.add_assertion("REQ-p00001", "SHALL work\n### Rationale")

        assert graph.find_by_id("REQ-p00001-D") is None
        assert len(graph.mutation_log) == 0

    def test_REQ_o00062_S_exhausted_series_refuses_the_add(self):
        """REQ-o00062-S: a requirement filled to the end of its label series
        refuses the next add and creates no out-of-series label."""
        builder = GraphBuilder(namespace="REQ", resolver=grammar_for("REQ"))
        builder.add_parsed_content(
            make_req(
                "REQ-p00001",
                "Full Series",
                assertions=[
                    {"label": chr(ord("A") + i), "text": f"Assertion {i}"} for i in range(26)
                ],
            )
        )
        graph = builder.build()
        parent = graph.find_by_id("REQ-p00001")
        before = {
            c.get_field("label") for c in parent.iter_children() if c.kind == NodeKind.ASSERTION
        }
        assert len(before) == 26

        with pytest.raises(ValueError, match="no assertion label left"):
            graph.add_assertion("REQ-p00001", "The system SHALL do one thing too many.")

        after = {
            c.get_field("label") for c in parent.iter_children() if c.kind == NodeKind.ASSERTION
        }
        assert after == before, "a refused add must leave no new assertion behind"
        assert len(graph.mutation_log) == 0, "a refused add must log no mutation"

    # Verifies: REQ-o00062-E
    def test_add_changes_hash(self):
        """Adding assertion changes parent hash."""
        graph = build_graph_with_assertions()
        parent = graph.find_by_id("REQ-p00001")
        old_hash = parent.get_field("hash")

        graph.add_assertion("REQ-p00001", "New assertion")

        new_hash = parent.get_field("hash")
        assert new_hash != old_hash

    # Verifies: REQ-o00062-E
    def test_add_affects_hash(self):
        """Add operation is marked as affecting hash."""
        graph = build_graph_with_assertions()

        entry = graph.add_assertion("REQ-p00001", "New assertion")
        assert entry.affects_hash is True

    # Verifies: REQ-o00062-E
    def test_add_logs_mutation(self):
        """Add operation is logged."""
        graph = build_graph_with_assertions()

        graph.add_assertion("REQ-p00001", "New assertion")

        assert len(graph.mutation_log) == 1
        entry = graph.mutation_log.last()
        assert entry.operation == "add_assertion"

    # Verifies: REQ-o00062-G
    def test_add_undo(self):
        """Undo removes the added assertion and restores hash."""
        graph = build_graph_with_assertions()
        parent = graph.find_by_id("REQ-p00001")
        original_count = sum(1 for c in parent.iter_children() if c.kind == NodeKind.ASSERTION)

        entry = graph.add_assertion("REQ-p00001", "New assertion")
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

    # Verifies: REQ-o00062-B
    def test_delete_not_found(self):
        """Deleting non-existent assertion raises KeyError."""
        graph = build_graph_with_assertions()

        with pytest.raises(KeyError, match="not found"):
            graph.delete_assertion("REQ-p00001-Z")

    # Verifies: REQ-o00062-B
    def test_delete_not_assertion(self):
        """Deleting a non-assertion node raises ValueError."""
        graph = build_graph_with_assertions()

        with pytest.raises(ValueError, match="not an assertion"):
            graph.delete_assertion("REQ-p00001")

    # Verifies: REQ-o00062-B
    def test_delete_preserves_in_deleted_nodes(self):
        """Deleted assertion is preserved in _deleted_nodes."""
        graph = build_graph_with_assertions()

        graph.delete_assertion("REQ-p00001-B")

        assert graph.has_deletions()
        deleted = graph.deleted_nodes()
        deleted_ids = {n.id for n in deleted}
        assert "REQ-p00001-B" in deleted_ids

    # Verifies: REQ-o00062-B
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

    # Verifies: REQ-o00062-B
    def test_delete_without_compact(self):
        """Delete with compact=False leaves gaps."""
        graph = build_graph_with_assertions()

        graph.delete_assertion("REQ-p00001-B", compact=False)

        # After: A, C (gap at B)
        assert graph.find_by_id("REQ-p00001-A") is not None
        assert graph.find_by_id("REQ-p00001-B") is None
        assert graph.find_by_id("REQ-p00001-C") is not None

    # Verifies: REQ-o00062-B
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

    # Verifies: REQ-o00062-E
    def test_delete_changes_hash(self):
        """Deleting assertion changes parent hash."""
        graph = build_graph_with_assertions()
        parent = graph.find_by_id("REQ-p00001")
        old_hash = parent.get_field("hash")

        graph.delete_assertion("REQ-p00001-B")

        new_hash = parent.get_field("hash")
        assert new_hash != old_hash

    # Verifies: REQ-o00062-E
    def test_delete_affects_hash(self):
        """Delete operation is marked as affecting hash."""
        graph = build_graph_with_assertions()

        entry = graph.delete_assertion("REQ-p00001-B")
        assert entry.affects_hash is True

    # Verifies: REQ-o00062-E
    def test_delete_logs_mutation(self):
        """Delete operation is logged."""
        graph = build_graph_with_assertions()

        graph.delete_assertion("REQ-p00001-B")

        assert len(graph.mutation_log) == 1
        entry = graph.mutation_log.last()
        assert entry.operation == "delete_assertion"

    # Verifies: REQ-o00062-G
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

    # Verifies: REQ-o00062-G
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

    # Verifies: REQ-o00062-B
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

    # Verifies: REQ-o00062-B
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

    # Verifies: REQ-o00062-E
    def test_multiple_mutations_logged(self):
        """Multiple mutations are all logged in order."""
        graph = build_graph_with_assertions()

        graph.update_assertion("REQ-p00001-A", "Updated A")
        graph.add_assertion("REQ-p00001", "Added D")
        graph.rename_assertion("REQ-p00001-D", "E")
        graph.delete_assertion("REQ-p00001-B")

        assert len(graph.mutation_log) == 4
        entries = list(graph.mutation_log.iter_entries())
        assert entries[0].operation == "update_assertion"
        assert entries[1].operation == "add_assertion"
        assert entries[2].operation == "rename_assertion"
        assert entries[3].operation == "delete_assertion"

    # Verifies: REQ-o00062-G
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


@pytest.mark.incremental
class TestAssertionMutationChain:
    """Incremental chain: add an assertion, update it, rename it, delete it.

    Uses REQ-p00002 from the canonical (hht-like) graph which has assertions
    A-D. The chain adds assertion E, updates it, renames it to F, then
    deletes F — leaving exactly the original A-D in place. The mutable_graph
    fixture undoes any remaining mutations after the class, so later tests
    see a pristine canonical graph regardless of where the chain stops.

    State is shared between steps via class-level attributes.
    """

    # Verifies: REQ-o00062-B
    def test_step_1_add_assertion(self, mutable_graph):
        """Add assertion E to REQ-p00002 from the canonical graph."""
        from elspais.graph.GraphNode import NodeKind

        parent = mutable_graph.find_by_id("REQ-p00002")
        assert parent is not None, "REQ-p00002 must exist in canonical graph"
        # Record starting assertion count for later verification
        self.__class__._orig_assertion_count = sum(
            1 for c in parent.iter_children() if c.kind == NodeKind.ASSERTION
        )
        mutable_graph.add_assertion("REQ-p00002", "The system SHALL archive old sessions.")
        node = mutable_graph.find_by_id("REQ-p00002-E")
        assert node is not None
        assert node.get_label() == "The system SHALL archive old sessions."
        assert node.get_field("label") == "E"
        assert len(mutable_graph.mutation_log) == 1

    # Verifies: REQ-o00062-B
    def test_step_2_update_assertion(self, mutable_graph):
        """Update assertion E text."""
        mutable_graph.update_assertion(
            "REQ-p00002-E", "The system SHALL expire old sessions after 24 hours."
        )
        node = mutable_graph.find_by_id("REQ-p00002-E")
        assert node.get_label() == "The system SHALL expire old sessions after 24 hours."
        assert len(mutable_graph.mutation_log) == 2

    # Verifies: REQ-o00062-B
    def test_step_3_rename_assertion(self, mutable_graph):
        """Rename assertion E to F."""
        mutable_graph.rename_assertion("REQ-p00002-E", "F")
        assert mutable_graph.find_by_id("REQ-p00002-E") is None
        node = mutable_graph.find_by_id("REQ-p00002-F")
        assert node is not None
        assert node.get_field("label") == "F"
        assert len(mutable_graph.mutation_log) == 3

    # Verifies: REQ-o00062-B
    def test_step_4_delete_assertion(self, mutable_graph):
        """Delete assertion F, restoring the original assertion count."""
        from elspais.graph.GraphNode import NodeKind

        mutable_graph.delete_assertion("REQ-p00002-F", compact=False)
        assert mutable_graph.find_by_id("REQ-p00002-F") is None
        parent = mutable_graph.find_by_id("REQ-p00002")
        remaining = sum(1 for c in parent.iter_children() if c.kind == NodeKind.ASSERTION)
        assert remaining == self.__class__._orig_assertion_count
        assert len(mutable_graph.mutation_log) == 4

    # Verifies: REQ-o00062-G
    def test_step_5_undo_all_mutations(self, mutable_graph):
        """Undo all 4 mutations in reverse — graph is fully restored."""
        from elspais.graph.GraphNode import NodeKind

        parent = mutable_graph.find_by_id("REQ-p00002")
        for _ in range(4):
            mutable_graph.undo_last()
        # All assertions undone: E and F gone, original A-D back
        assert mutable_graph.find_by_id("REQ-p00002-E") is None
        assert mutable_graph.find_by_id("REQ-p00002-F") is None
        restored = sum(1 for c in parent.iter_children() if c.kind == NodeKind.ASSERTION)
        assert restored == self.__class__._orig_assertion_count
        assert len(mutable_graph.mutation_log) == 0


# ---------------------------------------------------------------------------
# REQ-o00062-R: an added assertion joins the existing run of assertions
# ---------------------------------------------------------------------------

# Verifies: REQ-o00062-R
FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"

# (fixture directory, requirement id, spec file relative to the repo root).
# Covers two configured assertion-label series: uppercase (hht-like) and
# numeric-0 (e2e-fda-numeric). Both requirements end with a trailing
# "Rationale" section, so a mis-placed assertion lands after it.
_PLACEMENT_CASES = [
    pytest.param("hht-like", "REQ-o00002", "spec/ops-deploy.md", id="uppercase"),
    pytest.param("e2e-fda-numeric", "DEV-00001", "spec/dev-audit.md", id="numeric-0"),
]


def _copy_fixture(name: str, tmp_path: Path) -> Path:
    """Copy a fixture repo into tmp_path so mutations never touch tests/."""
    dst = tmp_path / name
    shutil.copytree(FIXTURES_DIR / name, dst)
    return dst


def _root_graph(repo_root: Path):
    """Build a private graph from a repo root and return (federated, root graph)."""
    federated = build_graph(repo_root=repo_root)
    return federated, federated._repos[federated._root_repo].graph


def _assertion_labels(graph, req_id: str) -> list[str]:
    """Labels of a requirement's assertions, in rendered (render_order) order."""
    req = graph.find_by_id(req_id)
    ordered: list[tuple[float, str]] = []
    for edge in req.iter_outgoing_edges():
        if edge.target.kind != NodeKind.ASSERTION:
            continue
        ordered.append((edge.metadata.get("render_order", 0.0), edge.target.get_field("label")))
    return [label for _, label in sorted(ordered, key=lambda pair: pair[0])]


def _next_label(repo_root: Path, count: int) -> str:
    """The label at position *count* in this repo's configured series."""
    resolver = build_resolver(load_config(repo_root / ".elspais.toml"))
    return resolver.format_assertion_label(count)


def _requirement_block(text: str, req_id: str) -> str:
    """The rendered text of one requirement, from its heading to its *End* marker."""
    start = re.search(rf"^#+ {re.escape(req_id)}\b.*$", text, re.MULTILINE)
    assert start is not None, f"{req_id} not found in rendered file"
    end = re.search(r"^\*End\*.*$", text[start.start() :], re.MULTILINE)
    assert end is not None, f"no *End* marker after {req_id}"
    return text[start.start() : start.start() + end.end()]


class TestAssertionPlacementInSeries:
    """REQ-o00062-R: an added assertion joins the existing run of assertions.

    These build a private graph from a throwaway copy of an on-disk fixture,
    because the behaviour under test is only observable through render + save
    + re-parse. The in-memory ``mutable_graph`` fixture cannot express that,
    and the session-scoped canonical graph must not be written to disk.
    """

    @pytest.mark.parametrize("fixture,req_id,spec_file", _PLACEMENT_CASES)
    # Verifies: REQ-o00062-R
    def test_REQ_o00062_R_added_assertion_renders_in_the_one_run(
        self, tmp_path: Path, fixture: str, req_id: str, spec_file: str
    ):
        """REQ-o00062-R: the new assertion renders after the last existing
        assertion and before the trailing section, leaving one Assertions block."""
        repo_root = _copy_fixture(fixture, tmp_path)
        federated, graph = _root_graph(repo_root)

        existing = _assertion_labels(graph, req_id)
        last_existing_text = graph.find_by_id(
            graph.make_assertion_id(req_id, existing[-1])
        ).get_label()
        new_text = "The system SHALL archive backups offsite."
        graph.add_assertion(req_id, new_text)
        render_save(federated, repo_root=repo_root)

        block = _requirement_block((repo_root / spec_file).read_text(), req_id)

        assertions_headings = list(re.finditer(r"^#+ Assertions\s*$", block, re.MULTILINE))
        assert len(assertions_headings) == 1, (
            "the requirement must render exactly one Assertions block"
        )
        assert block.index(new_text) > block.index(last_existing_text), (
            "the new assertion must render after the existing ones"
        )
        # The first heading after the Assertions block — the trailing section
        # the new assertion must not have jumped past.
        after_assertions = assertions_headings[0].end()
        trailing = re.search(r"^#+ (?!Assertions)\w+", block[after_assertions:], re.MULTILINE)
        assert trailing is not None, "fixture must have a trailing section after the assertions"
        assert block.index(new_text) < after_assertions + trailing.start(), (
            "the new assertion must render before the trailing section"
        )

    @pytest.mark.parametrize("fixture,req_id,spec_file", _PLACEMENT_CASES)
    # Verifies: REQ-o00062-R
    def test_REQ_o00062_R_added_assertion_survives_round_trip(
        self, tmp_path: Path, fixture: str, req_id: str, spec_file: str
    ):
        """REQ-o00062-R: after save and rebuild, every pre-existing assertion is
        still present alongside the new one — adding one must destroy none."""
        repo_root = _copy_fixture(fixture, tmp_path)
        federated, graph = _root_graph(repo_root)

        before = _assertion_labels(graph, req_id)
        new_label = _next_label(repo_root, len(before))
        graph.add_assertion(req_id, "The system SHALL archive backups offsite.")
        render_save(federated, repo_root=repo_root)

        _, rebuilt = _root_graph(repo_root)
        after = _assertion_labels(rebuilt, req_id)

        assert set(before) <= set(after), (
            f"assertions lost on re-parse: {sorted(set(before) - set(after))}"
        )
        assert new_label in after
        assert after == before + [new_label], "rendered order must be label order for the whole run"

    @pytest.mark.parametrize("fixture,req_id,spec_file", _PLACEMENT_CASES)
    # Verifies: REQ-o00062-R
    def test_REQ_o00062_R_label_follows_the_existing_series(
        self, tmp_path: Path, fixture: str, req_id: str, spec_file: str
    ):
        """REQ-o00062-R: the added assertion carries the label that follows the
        existing ones in the configured series, and reports it."""
        repo_root = _copy_fixture(fixture, tmp_path)
        _, graph = _root_graph(repo_root)

        before = _assertion_labels(graph, req_id)
        expected = _next_label(repo_root, len(before))

        entry = graph.add_assertion(req_id, "The system SHALL archive backups offsite.")

        assert entry.after_state["label"] == expected, (
            "the mutation must report the label it assigned"
        )
        assert _assertion_labels(graph, req_id) == before + [expected], (
            "the assigned label must follow the existing series, leaving no gap"
        )

    # Verifies: REQ-o00062-R
    def test_REQ_o00062_R_first_assertion_takes_the_first_label(self):
        """REQ-o00062-R: a requirement with no assertions yet gets the first
        label in the series."""
        builder = GraphBuilder(namespace="REQ", resolver=grammar_for("REQ"))
        builder.add_parsed_content(make_req("REQ-p00001", "No Assertions Yet", assertions=[]))
        graph = builder.build()

        entry = graph.add_assertion("REQ-p00001", "The system SHALL do the first thing.")

        assert entry.after_state["label"] == "A"
        assert _assertion_labels(graph, "REQ-p00001") == ["A"], (
            "the first assertion must take the first label in the series"
        )
