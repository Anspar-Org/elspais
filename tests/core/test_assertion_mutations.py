# Validates REQ-o00062-B, REQ-o00062-D, REQ-o00062-E, REQ-o00062-F
# Verifies: REQ-o00062-R
"""Tests for assertion mutation operations (rename, update, add, delete)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from elspais.config import load_config
from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers import ParsedContent
from elspais.graph.parsers.directives import RETIRED_ASSERTION_TEXT, assertion_is_retired
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

    # Verifies: REQ-o00062-B
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

    # Verifies: REQ-o00062-B
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

    # Verifies: REQ-o00062-B
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

    # Verifies: REQ-o00062-S
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


def _assertion_state(graph, req_id: str) -> dict[str, tuple[str, str]]:
    """Each assertion of *req_id*, by id, as (label, text)."""
    req = graph.find_by_id(req_id)
    return {
        child.id: (child.get_field("label"), child.get_label())
        for child in req.iter_children()
        if child.kind == NodeKind.ASSERTION
    }


class TestDeleteAssertion:
    """TraceGraph.delete_assertion() on an active requirement retires in place.

    Requirements here carry the Active status, which is in the active role;
    the provisional, aspirational and retired roles are covered in
    test_assertion_compaction.py and test_retired_requirement_read_only.py.
    """

    @pytest.mark.parametrize("label", ["A", "B", "C"], ids=["first", "middle", "last"])
    # Verifies: REQ-p00017-A
    def test_REQ_p00017_A_delete_leaves_every_other_assertion_unchanged(self, label):
        """No other assertion's id, label or text changes, wherever the deleted
        one stands in the series."""
        graph = build_graph_with_assertions()
        target = f"REQ-p00001-{label}"
        before = _assertion_state(graph, "REQ-p00001")

        graph.delete_assertion(target)

        after = _assertion_state(graph, "REQ-p00001")
        assert set(after) == set(before)
        others_before = {k: v for k, v in before.items() if k != target}
        others_after = {k: v for k, v in after.items() if k != target}
        assert others_after == others_before

    @pytest.mark.parametrize("label", ["A", "B", "C"], ids=["first", "middle", "last"])
    # Verifies: REQ-p00017-K
    def test_REQ_p00017_K_delete_retires_under_the_existing_label(self, label):
        """The deleted assertion stays in the graph under its id and label,
        carrying the RETIRED directive."""
        graph = build_graph_with_assertions()
        target = f"REQ-p00001-{label}"

        entry = graph.delete_assertion(target)

        node = graph.find_by_id(target)
        assert node is not None
        assert node.kind == NodeKind.ASSERTION
        assert node.get_field("label") == label
        assert assertion_is_retired(node)
        assert node.get_label() == RETIRED_ASSERTION_TEXT
        assert target not in {n.id for n in graph.deleted_nodes()}
        assert entry.operation == "delete_assertion"
        assert entry.target_id == target
        assert entry.after_state["text"] == RETIRED_ASSERTION_TEXT

    # Verifies: REQ-p00017-K
    def test_REQ_p00017_K_deleting_a_retired_assertion_is_refused(self):
        """A retired assertion cannot be deleted again; the refusal changes nothing."""
        graph = build_graph_with_assertions()
        parent = graph.find_by_id("REQ-p00001")
        graph.delete_assertion("REQ-p00001-B")
        hash_after_first = parent.get_field("hash")
        logged = len(graph.mutation_log)

        with pytest.raises(ValueError, match="already retired"):
            graph.delete_assertion("REQ-p00001-B")

        assert len(graph.mutation_log) == logged
        assert parent.get_field("hash") == hash_after_first
        assert assertion_is_retired(graph.find_by_id("REQ-p00001-B"))

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

    # Verifies: REQ-p00017-H
    def test_REQ_p00017_H_delete_keeps_the_citation_of_the_label(self):
        """A citation of the deleted assertion keeps naming its label; it is
        not dropped and not widened to the whole requirement."""
        graph = build_graph_with_child_implementing_assertion()

        graph.delete_assertion("REQ-p00001-A")

        assert _cited_labels(graph, "REQ-p00002", "REQ-p00001") == ["A"]

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

    @pytest.mark.parametrize("label", ["A", "B"], ids=["cited", "uncited"])
    # Verifies: REQ-o00062-P
    def test_REQ_o00062_P_undo_restores_the_assertion_and_its_citations(self, label):
        """Undo restores the text, un-retires the assertion, restores the
        parent hash, and leaves every citation naming the label."""
        graph = build_graph_with_child_implementing_assertion()
        parent = graph.find_by_id("REQ-p00001")
        target = f"REQ-p00001-{label}"
        before = _assertion_state(graph, "REQ-p00001")
        original_hash = parent.get_field("hash")

        graph.delete_assertion(target)
        graph.undo_last()

        node = graph.find_by_id(target)
        assert not assertion_is_retired(node)
        assert _assertion_state(graph, "REQ-p00001") == before
        assert parent.get_field("hash") == original_hash
        assert _cited_labels(graph, "REQ-p00002", "REQ-p00001") == ["A"]

    # Verifies: REQ-p00017-A
    def test_REQ_p00017_A_add_after_deleting_the_last_takes_the_next_label(self):
        """The retired last label stays allocated, so the next add skips it."""
        graph = build_graph_with_assertions()

        graph.delete_assertion("REQ-p00001-C")
        entry = graph.add_assertion("REQ-p00001", "The tool SHALL do a fourth thing.")

        assert entry.after_state["label"] == "D"
        assert assertion_is_retired(graph.find_by_id("REQ-p00001-C"))
        assert graph.find_by_id("REQ-p00001-D").get_label() == ("The tool SHALL do a fourth thing.")


class TestDeletionHasNoCompaction:
    """Deletion takes no compaction option on any surface."""

    @pytest.mark.parametrize("surface", ["trace", "federated"])
    # Verifies: REQ-o00062-B
    def test_REQ_o00062_B_compact_keyword_is_refused(self, tmp_path: Path, surface: str):
        root = _write_citing_project(tmp_path)
        federated = build_graph(repo_root=root)
        graph = federated if surface == "federated" else _root_graph(root)[1]

        with pytest.raises(TypeError, match="compact"):
            graph.delete_assertion("REQ-p00001-B", compact=True)

        assert not assertion_is_retired(graph.find_by_id("REQ-p00001-B"))


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
    deletes F — leaving the original A-D and F retired. The mutable_graph
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

    # Verifies: REQ-o00062-B, REQ-p00017-K
    def test_step_4_delete_assertion(self, mutable_graph):
        """Delete assertion F: it stays under its label, retired."""
        mutable_graph.delete_assertion("REQ-p00002-F")
        node = mutable_graph.find_by_id("REQ-p00002-F")
        assert node is not None
        assert assertion_is_retired(node)
        parent = mutable_graph.find_by_id("REQ-p00002")
        assertions = [c for c in parent.iter_children() if c.kind == NodeKind.ASSERTION]
        assert len(assertions) == self.__class__._orig_assertion_count + 1
        live = [c for c in assertions if not assertion_is_retired(c)]
        assert len(live) == self.__class__._orig_assertion_count
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
    pytest.param("e2e-fda-numeric", "PRD-00001", "spec/prd-core.md", id="numeric-0"),
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
        federated.add_assertion(req_id, new_text)
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
        federated.add_assertion(req_id, "The system SHALL archive backups offsite.")
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


# ---------------------------------------------------------------------------
# A mutation of one requirement's Assertion leaves the citations of another
# requirement's Assertions alone (REQ-p00017-J).
#
# Labels repeat across requirements: REQ-p00001 and REQ-p00002 both have an
# Assertion A, and REQ-p00002 also has a C -- the label REQ-p00001-A is renamed
# to. Each Assertion is cited by its own requirement in dev.md.
# ---------------------------------------------------------------------------

_SAME_LABELS_PRD = """# Product

## REQ-p00001: Alpha

**Level**: prd | **Status**: Active

Alpha body.

### Assertions

A. The tool SHALL alpha.

B. The tool SHALL alpha two.

*End* *Alpha* | **Hash**: 00000000

## REQ-p00002: Gamma

**Level**: prd | **Status**: Active

Gamma body.

### Assertions

A. The tool SHALL gamma.

B. The tool SHALL gamma two.

C. The tool SHALL gamma three.

*End* *Gamma* | **Hash**: 00000000
"""

_SAME_LABELS_DEV = """# Dev

## REQ-d00001: Cites alpha A

**Level**: dev | **Status**: Active | **Implements**: REQ-p00001-A

Body.

### Assertions

A. The tool SHALL one.

*End* *Cites alpha A* | **Hash**: 00000000

## REQ-d00002: Cites gamma A

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002-A

Body.

### Assertions

A. The tool SHALL two.

*End* *Cites gamma A* | **Hash**: 00000000

## REQ-d00003: Cites gamma C

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002-C

Body.

### Assertions

A. The tool SHALL three.

*End* *Cites gamma C* | **Hash**: 00000000
"""


@pytest.fixture
def same_labels(tmp_path: Path):
    """A repository whose requirements share Assertion labels, and its graph."""
    (tmp_path / ".elspais.toml").write_text(
        'version = 5\n\n[project]\nname = "labels"\nnamespace = "REQ"\n', encoding="utf-8"
    )
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec" / "prd.md").write_text(_SAME_LABELS_PRD, encoding="utf-8")
    (tmp_path / "spec" / "dev.md").write_text(_SAME_LABELS_DEV, encoding="utf-8")
    graph = build_graph(repo_root=tmp_path)
    return graph, tmp_path


def _cited_labels(graph, citing_id: str, cited_id: str) -> list[str]:
    """The Assertion labels of *cited_id* that *citing_id* implements."""
    citing = graph.find_by_id(citing_id)
    return sorted(
        label
        for edge in citing.iter_incoming_edges()
        if edge.source.id == cited_id
        for label in edge.assertion_targets
    )


class TestAMutationLeavesOtherRequirementsCitationsAlone:
    """Validates REQ-p00017-J."""

    # Verifies: REQ-p00017-J
    def test_REQ_p00017_J_rename_leaves_a_same_label_citation_of_another_requirement(
        self, same_labels
    ):
        graph, _ = same_labels

        graph.rename_assertion("REQ-p00001-A", "C")

        assert _cited_labels(graph, "REQ-d00001", "REQ-p00001") == ["C"]
        assert _cited_labels(graph, "REQ-d00002", "REQ-p00002") == ["A"]
        assert _cited_labels(graph, "REQ-d00003", "REQ-p00002") == ["C"]

    # Verifies: REQ-p00017-J
    def test_REQ_p00017_J_rename_saves_the_other_requirements_citation_unchanged(self, same_labels):
        graph, repo_root = same_labels

        graph.rename_assertion("REQ-p00001-A", "C")
        result = render_save(graph, repo_root=repo_root)

        assert result["success"] is True, result["errors"]
        text = (repo_root / "spec" / "dev.md").read_text(encoding="utf-8")
        assert "**Implements**: REQ-p00001-C" in text
        assert "**Implements**: REQ-p00002-A" in text
        assert "**Implements**: REQ-p00002-C" in text

    # Verifies: REQ-p00017-J
    def test_REQ_p00017_J_undoing_a_rename_leaves_the_other_requirements_citations(
        self, same_labels
    ):
        """Undo respells the renamed Assertion's citations back, and only those."""
        graph, _ = same_labels

        graph.rename_assertion("REQ-p00001-A", "C")
        graph.undo_last()

        assert _cited_labels(graph, "REQ-d00001", "REQ-p00001") == ["A"]
        assert _cited_labels(graph, "REQ-d00002", "REQ-p00002") == ["A"]
        assert _cited_labels(graph, "REQ-d00003", "REQ-p00002") == ["C"]

    # Verifies: REQ-p00017-J
    def test_REQ_p00017_J_delete_leaves_a_same_label_citation_of_another_requirement(
        self, same_labels
    ):
        graph, _ = same_labels

        graph.delete_assertion("REQ-p00001-A")

        assert _cited_labels(graph, "REQ-d00002", "REQ-p00002") == ["A"]
        assert _cited_labels(graph, "REQ-d00003", "REQ-p00002") == ["C"]

    # Verifies: REQ-p00017-J
    def test_REQ_p00017_J_undoing_a_delete_leaves_the_other_requirements_citations(
        self, same_labels
    ):
        graph, _ = same_labels

        graph.delete_assertion("REQ-p00001-A")
        graph.undo_last()

        assert _cited_labels(graph, "REQ-d00002", "REQ-p00002") == ["A"]
        assert _cited_labels(graph, "REQ-d00003", "REQ-p00002") == ["C"]


# ---------------------------------------------------------------------------
# Deletion on disk: retirement survives save and rebuild, labels stay
# allocated, and citations of the retired label are reported, not rewritten.
#
# The fixture's REQ-p00001 has A, B and C. REQ-d00001 (another spec file) and a code file
# each cite REQ-p00001-B.
# ---------------------------------------------------------------------------

_CITING_CONFIG = """version = 5

[project]
name = "retire"
namespace = "REQ"

[levels.prd]
rank = 1
letter = "p"
implements = ["prd"]

[levels.dev]
rank = 3
letter = "d"
implements = ["dev", "prd"]

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]
"""

_CITING_PRD = """# REQ-p00001: Parent

**Level**: prd | **Status**: Active | **Implements**: -

## Assertions

A. The tool SHALL do alpha.

B. The tool SHALL do beta.

C. The tool SHALL do gamma.

*End* *Parent* | **Hash**: 00000000
---
"""

_CITING_DEV = """# REQ-d00001: Child

**Level**: dev | **Status**: Active | **Implements**: REQ-p00001-B

## Assertions

A. The tool SHALL do delta.

*End* *Child* | **Hash**: 00000000
---
"""

_CITING_CODE = "# Implements: REQ-p00001-B\ndef f():\n    pass\n"

_CITING_FILES = ("spec/dev.md", "src/m.py")


def _write_citing_project(tmp_path: Path) -> Path:
    """Write the citing project into *tmp_path* and return its root."""
    root = tmp_path / "repo"
    (root / "spec").mkdir(parents=True)
    (root / "src").mkdir()
    (root / ".elspais.toml").write_text(_CITING_CONFIG, encoding="utf-8")
    (root / "spec" / "prd.md").write_text(_CITING_PRD, encoding="utf-8")
    (root / "spec" / "dev.md").write_text(_CITING_DEV, encoding="utf-8")
    (root / "src" / "m.py").write_text(_CITING_CODE, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


def _code_node_ids(graph) -> list[str]:
    return [node.id for node in graph.iter_by_kind(NodeKind.CODE)]


class TestDeletionOnDisk:
    """Deleting from an active requirement retires the assertion in the saved
    file and leaves citing files alone."""

    # Verifies: REQ-p00017-K
    def test_REQ_p00017_K_saved_file_carries_the_retired_assertion(self, tmp_path: Path):
        root = _write_citing_project(tmp_path)
        graph = build_graph(repo_root=root)

        graph.delete_assertion("REQ-p00001-B")
        result = render_save(graph, repo_root=root)

        assert result["success"] is True, result.get("errors")
        lines = (root / "spec" / "prd.md").read_text(encoding="utf-8").splitlines()
        assert "B. <RETIRED>" in lines
        assert "A. The tool SHALL do alpha." in lines
        assert "C. The tool SHALL do gamma." in lines
        rebuilt = build_graph(repo_root=root)
        assert assertion_is_retired(rebuilt.find_by_id("REQ-p00001-B"))

    @pytest.mark.parametrize("save_between", [False, True], ids=["in-memory", "after-rebuild"])
    # Verifies: REQ-p00017-A
    def test_REQ_p00017_A_deleted_last_label_is_not_given_again(
        self, tmp_path: Path, save_between: bool
    ):
        """After the last assertion is deleted, an add takes the next label --
        also when the deletion was saved and the graph rebuilt from disk."""
        root = _write_citing_project(tmp_path)
        graph = build_graph(repo_root=root)

        graph.delete_assertion("REQ-p00001-C")
        if save_between:
            assert render_save(graph, repo_root=root)["success"] is True
            graph = build_graph(repo_root=root)
        entry = graph.add_assertion("REQ-p00001", "The tool SHALL do zeta.")

        assert entry.after_state["label"] == "D"
        assert assertion_is_retired(graph.find_by_id("REQ-p00001-C"))
        assert render_save(graph, repo_root=root)["success"] is True
        rebuilt = build_graph(repo_root=root)
        assert assertion_is_retired(rebuilt.find_by_id("REQ-p00001-C"))
        assert rebuilt.find_by_id("REQ-p00001-D").get_label() == "The tool SHALL do zeta."

    # Verifies: REQ-p00017-H
    def test_REQ_p00017_H_citing_files_are_not_rewritten(self, tmp_path: Path):
        root = _write_citing_project(tmp_path)
        before = {name: (root / name).read_bytes() for name in _CITING_FILES}
        graph = build_graph(repo_root=root)

        graph.delete_assertion("REQ-p00001-B")
        result = render_save(graph, repo_root=root)

        assert result["success"] is True, result.get("errors")
        assert [Path(f).name for f in result["files_modified"]] == ["prd.md"]
        assert {name: (root / name).read_bytes() for name in _CITING_FILES} == before

    # Verifies: REQ-p00017-H
    def test_REQ_p00017_H_citation_of_a_retired_assertion_is_unresolved(self, tmp_path: Path):
        """After rebuild, each citation of the retired assertion is reported
        as unresolved, and no edge binds it to the requirement."""
        root = _write_citing_project(tmp_path)
        graph = build_graph(repo_root=root)
        graph.delete_assertion("REQ-p00001-B")
        assert render_save(graph, repo_root=root)["success"] is True

        rebuilt = build_graph(repo_root=root)

        code_ids = _code_node_ids(rebuilt)
        assert len(code_ids) == 1
        faults = {(f.source_id, f.target_id) for f in rebuilt.unresolved_references()}
        assert ("REQ-d00001", "REQ-p00001-B") in faults
        assert (code_ids[0], "REQ-p00001-B") in faults
        parent = rebuilt.find_by_id("REQ-p00001")
        bound = {edge.target.id for edge in parent.iter_outgoing_edges()}
        assert "REQ-d00001" not in bound
        assert code_ids[0] not in bound

    # Verifies: REQ-p00017-H
    def test_REQ_p00017_H_citations_resolve_before_the_deletion(self, tmp_path: Path):
        """Control for the test above: the same citations bind while B is live."""
        root = _write_citing_project(tmp_path)
        graph = build_graph(repo_root=root)

        faults = {(f.source_id, f.target_id) for f in graph.unresolved_references()}
        assert not any(target == "REQ-p00001-B" for _, target in faults)
        assert _cited_labels(graph, "REQ-d00001", "REQ-p00001") == ["B"]


# ---------------------------------------------------------------------------
# The same guarantees under a multi-character label series: labels 1..12, the
# cited assertion 10 has later siblings 11 and 12.
# ---------------------------------------------------------------------------

_NUMERIC_CONFIG = (
    _CITING_CONFIG
    + """
[id-patterns.assertions]
label_style = "numeric_1based"
max_count = 99
"""
)

_NUMERIC_PRD = (
    "# REQ-p00001: Parent\n\n"
    "**Level**: prd | **Status**: Active | **Implements**: -\n\n"
    "## Assertions\n\n"
    + "".join(f"{n}. The tool SHALL do thing {n}.\n\n" for n in range(1, 13))
    + "*End* *Parent* | **Hash**: 00000000\n---\n"
)

_NUMERIC_DEV = _CITING_DEV.replace("REQ-p00001-B", "REQ-p00001-10")


def _write_numeric_project(tmp_path: Path) -> Path:
    """Write the numeric-label project into *tmp_path* and return its root."""
    root = tmp_path / "numeric"
    (root / "spec").mkdir(parents=True)
    (root / ".elspais.toml").write_text(_NUMERIC_CONFIG, encoding="utf-8")
    (root / "spec" / "prd.md").write_text(_NUMERIC_PRD, encoding="utf-8")
    (root / "spec" / "dev.md").write_text(_NUMERIC_DEV, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


class TestDeletionUnderMultiCharacterLabels:
    """Deleting cited assertion 10 of 1..12 of an active requirement moves no
    label and drops no citation."""

    # Verifies: REQ-p00017-A
    def test_REQ_p00017_A_later_siblings_keep_their_ids_and_texts(self, tmp_path: Path):
        root = _write_numeric_project(tmp_path)
        graph = build_graph(repo_root=root)
        before = _assertion_state(graph, "REQ-p00001")
        assert _cited_labels(graph, "REQ-d00001", "REQ-p00001") == ["10"]

        graph.delete_assertion("REQ-p00001-10")

        after = _assertion_state(graph, "REQ-p00001")
        assert set(after) == set(before)
        for label in ("11", "12"):
            assert after[f"REQ-p00001-{label}"] == (label, f"The tool SHALL do thing {label}.")
        assert after["REQ-p00001-10"] == ("10", RETIRED_ASSERTION_TEXT)
        assert _cited_labels(graph, "REQ-d00001", "REQ-p00001") == ["10"]

    # Verifies: REQ-p00017-A
    def test_REQ_p00017_A_saved_deletion_leaves_the_citation_unresolved(self, tmp_path: Path):
        root = _write_numeric_project(tmp_path)
        dev_before = (root / "spec" / "dev.md").read_bytes()
        graph = build_graph(repo_root=root)

        graph.delete_assertion("REQ-p00001-10")
        assert render_save(graph, repo_root=root)["success"] is True

        assert (root / "spec" / "dev.md").read_bytes() == dev_before
        lines = (root / "spec" / "prd.md").read_text(encoding="utf-8").splitlines()
        assert "10. <RETIRED>" in lines
        assert "11. The tool SHALL do thing 11." in lines
        assert "12. The tool SHALL do thing 12." in lines
        rebuilt = build_graph(repo_root=root)
        faults = {(f.source_id, f.target_id) for f in rebuilt.unresolved_references()}
        assert ("REQ-d00001", "REQ-p00001-10") in faults
        assert _cited_labels(rebuilt, "REQ-d00001", "REQ-p00001") == []
        assert rebuilt.find_by_id("REQ-p00001-11").get_label() == "The tool SHALL do thing 11."

    # Verifies: REQ-p00017-A
    def test_REQ_p00017_A_undo_restores_the_deleted_assertion(self, tmp_path: Path):
        root = _write_numeric_project(tmp_path)
        graph = build_graph(repo_root=root)
        before = _assertion_state(graph, "REQ-p00001")

        graph.delete_assertion("REQ-p00001-10")
        graph.undo_last()

        assert _assertion_state(graph, "REQ-p00001") == before
        assert not assertion_is_retired(graph.find_by_id("REQ-p00001-10"))
        assert _cited_labels(graph, "REQ-d00001", "REQ-p00001") == ["10"]
