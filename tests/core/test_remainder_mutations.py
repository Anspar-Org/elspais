"""Tests for REMAINDER node CRUD mutations (update, add, delete)."""

from __future__ import annotations

import pytest

from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers import ParsedContent
from elspais.graph.relations import EdgeKind


def make_req(
    req_id: str,
    title: str = "Test",
    level: str = "PRD",
    status: str = "Active",
    implements: list[str] | None = None,
    assertions: list[dict] | None = None,
    sections: list[dict] | None = None,
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
            "sections": sections or [],
        },
        start_line=1,
        end_line=5,
        raw_text=f"## {req_id}: {title}",
    )


def build_graph_with_sections() -> TraceGraph:
    """Build a graph with a requirement that has sections."""
    builder = GraphBuilder()
    builder.add_parsed_content(
        make_req(
            "REQ-p00001",
            "Requirement with Sections",
            sections=[
                {"heading": "preamble", "content": "Some preamble text", "line": 2},
                {"heading": "Rationale", "content": "Why we need this", "line": 4},
            ],
        )
    )
    return builder.build()


def build_graph_with_definition_block() -> TraceGraph:
    """Build a graph with a requirement that has a definition block."""
    builder = GraphBuilder()
    content = ParsedContent(
        content_type="requirement",
        parsed_data={
            "id": "REQ-p00002",
            "title": "Req with Definitions",
            "level": "PRD",
            "status": "Active",
            "assertions": [],
            "implements": [],
            "refines": [],
            "sections": [],
            "definitions": [
                {"term": "Widget", "definition": "A reusable UI component", "line": 3},
            ],
        },
        start_line=1,
        end_line=5,
        raw_text="## REQ-p00002: Req with Definitions",
    )
    builder.add_parsed_content(content)
    return builder.build()


def _find_structures_edge(parent, child):
    """Find the STRUCTURES edge from parent to child."""
    for edge in parent.iter_outgoing_edges():
        if edge.kind == EdgeKind.STRUCTURES and edge.target is child:
            return edge
    return None


class TestUpdateRemainder:
    """Tests for TraceGraph.update_remainder()."""

    def test_update_text(self):
        """Updating text field changes it and recomputes parent hash."""
        graph = build_graph_with_sections()
        parent = graph.find_by_id("REQ-p00001")
        old_hash = parent.get_field("hash")
        section = graph.find_by_id("REQ-p00001:section:1")

        entry = graph.update_remainder("REQ-p00001:section:1", text="Updated rationale")

        assert entry.operation == "update_remainder"
        assert section.get_field("text") == "Updated rationale"
        assert parent.get_field("hash") != old_hash

    def test_update_heading(self):
        """Updating heading field changes it."""
        graph = build_graph_with_sections()
        section = graph.find_by_id("REQ-p00001:section:1")

        graph.update_remainder("REQ-p00001:section:1", heading="New Heading")

        assert section.get_field("heading") == "New Heading"

    def test_update_both(self):
        """Updating both text and heading works."""
        graph = build_graph_with_sections()
        section = graph.find_by_id("REQ-p00001:section:1")

        graph.update_remainder("REQ-p00001:section:1", text="New text", heading="New Heading")

        assert section.get_field("text") == "New text"
        assert section.get_field("heading") == "New Heading"

    def test_rejects_definition_block(self):
        """ValueError when node is a definition_block."""
        graph = build_graph_with_definition_block()

        with pytest.raises(ValueError, match="definition_block"):
            graph.update_remainder("REQ-p00002:def:0", text="New text")

    def test_rejects_non_remainder(self):
        """ValueError when node is not a REMAINDER."""
        graph = build_graph_with_sections()

        with pytest.raises(ValueError, match="not a REMAINDER"):
            graph.update_remainder("REQ-p00001", text="New text")

    def test_not_found(self):
        """KeyError for missing node."""
        graph = build_graph_with_sections()

        with pytest.raises(KeyError, match="not found"):
            graph.update_remainder("REQ-p00001:section:99", text="New text")

    def test_requires_at_least_one_field(self):
        """ValueError when both text and heading are None."""
        graph = build_graph_with_sections()

        with pytest.raises(ValueError, match="At least one"):
            graph.update_remainder("REQ-p00001:section:1")

    def test_undo(self):
        """Update then undo restores original values."""
        graph = build_graph_with_sections()
        section = graph.find_by_id("REQ-p00001:section:1")
        parent = graph.find_by_id("REQ-p00001")
        original_text = section.get_field("text")
        original_heading = section.get_field("heading")
        original_hash = parent.get_field("hash")

        graph.update_remainder("REQ-p00001:section:1", text="Changed", heading="Changed Heading")
        assert section.get_field("text") == "Changed"

        graph.undo_last()

        assert section.get_field("text") == original_text
        assert section.get_field("heading") == original_heading
        assert parent.get_field("hash") == original_hash


class TestAddRemainder:
    """Tests for TraceGraph.add_remainder()."""

    def test_add_section(self):
        """Creates node with correct ID format, linked via STRUCTURES."""
        graph = build_graph_with_sections()

        entry = graph.add_remainder("REQ-p00001", "Notes", "Some notes text")

        assert entry.operation == "add_remainder"
        new_id = entry.target_id
        assert ":section:m" in new_id

        node = graph.find_by_id(new_id)
        assert node is not None
        assert node.kind == NodeKind.REMAINDER
        assert node.get_field("heading") == "Notes"
        assert node.get_field("text") == "Some notes text"

        # Linked via STRUCTURES
        parent = graph.find_by_id("REQ-p00001")
        edge = _find_structures_edge(parent, node)
        assert edge is not None

    def test_render_order(self):
        """New node gets render_order > max existing STRUCTURES edge render_order."""
        graph = build_graph_with_sections()
        parent = graph.find_by_id("REQ-p00001")

        # Find max existing render_order on STRUCTURES edges
        max_ro = -1.0
        for edge in parent.iter_outgoing_edges():
            if edge.kind == EdgeKind.STRUCTURES:
                ro = edge.metadata.get("render_order", -1.0)
                if ro > max_ro:
                    max_ro = ro

        entry = graph.add_remainder("REQ-p00001", "Notes", "Text")
        node = graph.find_by_id(entry.target_id)
        edge = _find_structures_edge(parent, node)

        assert edge.metadata.get("render_order") == max_ro + 1.0

        # Second add should use the first's render_order as max
        entry2 = graph.add_remainder("REQ-p00001", "More Notes", "More text")
        node2 = graph.find_by_id(entry2.target_id)
        edge2 = _find_structures_edge(parent, node2)

        assert edge2.metadata.get("render_order") == edge.metadata["render_order"] + 1.0

    def test_hash_recomputed(self):
        """Parent hash changes after adding a section."""
        graph = build_graph_with_sections()
        parent = graph.find_by_id("REQ-p00001")
        old_hash = parent.get_field("hash")

        graph.add_remainder("REQ-p00001", "Notes", "Text")

        assert parent.get_field("hash") != old_hash

    def test_rejects_non_requirement(self):
        """ValueError for non-requirement parent."""
        graph = build_graph_with_sections()
        section = graph.find_by_id("REQ-p00001:section:0")

        with pytest.raises(ValueError, match="not a requirement"):
            graph.add_remainder(section.id, "Heading", "Text")

    def test_not_found(self):
        """KeyError for missing parent."""
        graph = build_graph_with_sections()

        with pytest.raises(KeyError, match="not found"):
            graph.add_remainder("REQ-nonexistent", "Heading", "Text")

    def test_undo(self):
        """Add then undo removes node from index."""
        graph = build_graph_with_sections()
        parent = graph.find_by_id("REQ-p00001")
        original_hash = parent.get_field("hash")

        entry = graph.add_remainder("REQ-p00001", "Notes", "Text")
        new_id = entry.target_id
        assert graph.find_by_id(new_id) is not None

        graph.undo_last()

        assert graph.find_by_id(new_id) is None
        assert parent.get_field("hash") == original_hash


class TestDeleteRemainder:
    """Tests for TraceGraph.delete_remainder()."""

    def test_delete_section(self):
        """Removes node from index and parent."""
        graph = build_graph_with_sections()
        section_id = "REQ-p00001:section:1"
        assert graph.find_by_id(section_id) is not None

        graph.delete_remainder(section_id)

        assert graph.find_by_id(section_id) is None

    def test_rejects_definition_block(self):
        """ValueError for definition_block nodes."""
        graph = build_graph_with_definition_block()

        with pytest.raises(ValueError, match="definition_block"):
            graph.delete_remainder("REQ-p00002:def:0")

    def test_rejects_non_remainder(self):
        """ValueError for non-REMAINDER nodes."""
        graph = build_graph_with_sections()

        with pytest.raises(ValueError, match="not a REMAINDER"):
            graph.delete_remainder("REQ-p00001")

    def test_hash_recomputed(self):
        """Parent hash changes after deleting a section."""
        graph = build_graph_with_sections()
        parent = graph.find_by_id("REQ-p00001")
        old_hash = parent.get_field("hash")

        graph.delete_remainder("REQ-p00001:section:1")

        assert parent.get_field("hash") != old_hash

    def test_undo(self):
        """Delete then undo restores node with render_order on edge."""
        graph = build_graph_with_sections()
        parent = graph.find_by_id("REQ-p00001")

        # First add a section with explicit render_order so undo can restore it
        entry = graph.add_remainder("REQ-p00001", "Extras", "Extra content")
        added_id = entry.target_id
        added_node = graph.find_by_id(added_id)
        edge = _find_structures_edge(parent, added_node)
        original_order = edge.metadata.get("render_order")
        original_text = added_node.get_field("text")
        original_heading = added_node.get_field("heading")
        hash_before_delete = parent.get_field("hash")

        graph.delete_remainder(added_id)
        assert graph.find_by_id(added_id) is None

        graph.undo_last()

        restored = graph.find_by_id(added_id)
        assert restored is not None
        assert restored.get_field("text") == original_text
        assert restored.get_field("heading") == original_heading
        assert parent.get_field("hash") == hash_before_delete

        # Verify render_order restored on STRUCTURES edge
        restored_edge = _find_structures_edge(parent, restored)
        assert restored_edge is not None
        assert restored_edge.metadata.get("render_order") == original_order


class TestPreambleEditing:
    """Tests for editing preamble REMAINDER nodes."""

    def test_update_preamble_text(self):
        """update_remainder works on preamble nodes."""
        graph = build_graph_with_sections()
        preamble_id = "REQ-p00001:section:0"
        preamble = graph.find_by_id(preamble_id)
        assert preamble.get_field("heading") == "preamble"

        graph.update_remainder(preamble_id, text="Updated preamble content")

        assert preamble.get_field("text") == "Updated preamble content"
