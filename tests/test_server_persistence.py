# Validates REQ-o00063-A, REQ-o00063-F, REQ-o00063-G, REQ-o00063-H, REQ-o00063-I
# Validates REQ-d00132-A, REQ-d00132-E, REQ-d00132-F
"""Tests for the persistence layer — render-based save.

Validates:
- REQ-o00063-A: mutations are correctly persisted to spec files
- REQ-o00063-F: After file mutations, graph state is synchronized
- REQ-o00063-G: update_title mutations are persisted
- REQ-o00063-H: update_assertion mutations are persisted
- REQ-o00063-I: add_assertion mutations are persisted
- REQ-d00132-A: render_save identifies dirty files and renders to disk
- REQ-d00132-E: mutation log cleared after save
- REQ-d00132-F: derives implements/refines from live graph edges

Note: This file was migrated from replay_mutations_to_disk (persistence.py)
to render_save (graph/render.py) as part of CUR-1082 Task 2.
"""

from __future__ import annotations

from pathlib import Path

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.relations import EdgeKind
from elspais.graph.render import render_save

# ---------------------------------------------------------------------------
# Shared graph builder helpers
# ---------------------------------------------------------------------------


def _build_graph_with_spec(
    tmp_path: Path,
    spec_content: str,
    spec_filename: str = "test_spec.md",
) -> tuple[TraceGraph, Path]:
    """Build a TraceGraph with a real spec file on disk.

    Creates a spec file, builds graph nodes manually with FILE nodes
    and CONTAINS/STRUCTURES edges. This allows render_save to write
    the rendered content back to disk.

    Returns:
        Tuple of (graph, spec_file_path).
    """
    from elspais.graph.GraphNode import FileType

    spec_file = tmp_path / spec_filename
    spec_file.write_text(spec_content, encoding="utf-8")

    # Build graph with nodes that reference the spec file
    graph = TraceGraph(repo_root=tmp_path)

    # Use relative path for source location (relative to repo_root)
    rel_path = str(spec_file.relative_to(tmp_path))

    # Create FILE node for the spec file
    file_node = GraphNode(id=f"file:{rel_path}", kind=NodeKind.FILE, label=spec_filename)
    file_node.set_field("file_type", FileType.SPEC)
    file_node.set_field("relative_path", rel_path)
    file_node.set_field("absolute_path", str(spec_file))
    file_node.set_field("repo", None)

    # PRD root node (needed so REQ-t00001 can implement it)
    prd_node = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Product Requirement",
    )
    prd_node._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "00000000",
        "parse_line": 1,
        "parse_end_line": None,
    }
    file_node.link(prd_node, EdgeKind.CONTAINS)

    # Main requirement node
    req_node = GraphNode(
        id="REQ-t00001",
        kind=NodeKind.REQUIREMENT,
        label="Test Requirement",
    )
    req_node._content = {
        "level": "DEV",
        "status": "Active",
        "hash": "abcd1234",
        "body_text": "",
        "parse_line": 1,
        "parse_end_line": None,
    }

    # Wire CONTAINS edges from FILE to content nodes
    file_node.link(req_node, EdgeKind.CONTAINS)

    # Assertions
    assertion_a = GraphNode(
        id="REQ-t00001-A",
        kind=NodeKind.ASSERTION,
        label="The system SHALL do something.",
    )
    assertion_a._content = {"label": "A", "parse_line": 7, "parse_end_line": None}
    req_node.link(assertion_a, EdgeKind.STRUCTURES)

    assertion_b = GraphNode(
        id="REQ-t00001-B",
        kind=NodeKind.ASSERTION,
        label="The system SHALL do another thing.",
    )
    assertion_b._content = {"label": "B", "parse_line": 8, "parse_end_line": None}
    req_node.link(assertion_b, EdgeKind.STRUCTURES)

    # Link: REQ-t00001 implements REQ-p00001
    prd_node.link(req_node, EdgeKind.IMPLEMENTS)

    # Build graph index
    graph._roots = [prd_node]
    graph._index = {
        f"file:{rel_path}": file_node,
        "REQ-p00001": prd_node,
        "REQ-t00001": req_node,
        "REQ-t00001-A": assertion_a,
        "REQ-t00001-B": assertion_b,
    }

    return graph, spec_file


def _build_two_req_graph(tmp_path: Path) -> tuple[TraceGraph, Path]:
    """Build a graph with two requirements."""
    from elspais.graph.GraphNode import FileType

    spec_file = tmp_path / "two_reqs.md"
    spec_file.write_text("placeholder", encoding="utf-8")

    graph = TraceGraph(repo_root=tmp_path)
    rel_path = str(spec_file.relative_to(tmp_path))

    # Create FILE node
    file_node = GraphNode(id=f"file:{rel_path}", kind=NodeKind.FILE, label="two_reqs.md")
    file_node.set_field("file_type", FileType.SPEC)
    file_node.set_field("relative_path", rel_path)
    file_node.set_field("absolute_path", str(spec_file))
    file_node.set_field("repo", None)

    # PRD root nodes
    prd1 = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT, label="Product Req 1")
    prd1._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "00000000",
        "parse_line": 1,
        "parse_end_line": None,
    }

    prd2 = GraphNode(id="REQ-p00002", kind=NodeKind.REQUIREMENT, label="Product Req 2")
    prd2._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "00000001",
        "parse_line": 1,
        "parse_end_line": None,
    }

    # First requirement
    req1 = GraphNode(id="REQ-t00001", kind=NodeKind.REQUIREMENT, label="First Requirement")
    req1._content = {
        "level": "DEV",
        "status": "Active",
        "hash": "aaaa1111",
        "body_text": "",
        "parse_line": 1,
        "parse_end_line": None,
    }
    e1 = file_node.link(req1, EdgeKind.CONTAINS)
    e1.metadata = {"render_order": 0.0}

    a1 = GraphNode(
        id="REQ-t00001-A", kind=NodeKind.ASSERTION, label="The system SHALL do the first thing."
    )
    a1._content = {"label": "A", "parse_line": 7, "parse_end_line": None}
    req1.link(a1, EdgeKind.STRUCTURES)

    b1 = GraphNode(
        id="REQ-t00001-B", kind=NodeKind.ASSERTION, label="The system SHALL do the second thing."
    )
    b1._content = {"label": "B", "parse_line": 8, "parse_end_line": None}
    req1.link(b1, EdgeKind.STRUCTURES)

    prd1.link(req1, EdgeKind.IMPLEMENTS)

    # Second requirement
    req2 = GraphNode(id="REQ-t00002", kind=NodeKind.REQUIREMENT, label="Second Requirement")
    req2._content = {
        "level": "DEV",
        "status": "Draft",
        "hash": "bbbb2222",
        "body_text": "",
        "parse_line": 13,
        "parse_end_line": None,
    }
    e2 = file_node.link(req2, EdgeKind.CONTAINS)
    e2.metadata = {"render_order": 1.0}

    a2 = GraphNode(
        id="REQ-t00002-A",
        kind=NodeKind.ASSERTION,
        label="The system SHALL handle the second requirement.",
    )
    a2._content = {"label": "A", "parse_line": 19, "parse_end_line": None}
    req2.link(a2, EdgeKind.STRUCTURES)

    prd2.link(req2, EdgeKind.IMPLEMENTS)

    graph._roots = [prd1, prd2]
    graph._index = {
        f"file:{rel_path}": file_node,
        "REQ-p00001": prd1,
        "REQ-p00002": prd2,
        "REQ-t00001": req1,
        "REQ-t00001-A": a1,
        "REQ-t00001-B": b1,
        "REQ-t00002": req2,
        "REQ-t00002-A": a2,
    }

    return graph, spec_file


# ---------------------------------------------------------------------------
# change_status save (REQ-o00063-A)
# ---------------------------------------------------------------------------


class TestSaveChangeStatus:
    """Tests for saving change_status mutations to disk via render_save."""

    def test_REQ_o00063_A_save_change_status(self, tmp_path: Path):
        """change_status mutation is saved via render_save."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        # Make a status change via graph API
        graph.change_status("REQ-t00001", "Deprecated")

        # Save to disk
        result = render_save(graph, tmp_path)

        assert result["success"] is True
        assert result["saved_count"] >= 1

        # Verify file content
        content = spec_file.read_text(encoding="utf-8")
        assert "**Status**: Deprecated" in content
        # The DEV requirement should now be Deprecated (PRD root still Active)
        for line in content.splitlines():
            if "REQ-t00001" in line and "##" in line:
                # Find the next status line
                idx = content.splitlines().index(line)
                meta_line = content.splitlines()[idx + 2]  # blank line, then metadata
                assert "Deprecated" in meta_line
                break

    def test_REQ_o00063_A_save_clears_mutation_log(self, tmp_path: Path):
        """After successful save, mutation log is cleared."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        graph.change_status("REQ-t00001", "Draft")
        assert len(graph.mutation_log) == 1

        result = render_save(graph, tmp_path)
        assert result["success"] is True
        assert len(graph.mutation_log) == 0


# ---------------------------------------------------------------------------
# update_title save (REQ-o00063-G)
# ---------------------------------------------------------------------------


class TestSaveUpdateTitle:
    """Tests for saving update_title mutations to disk via render_save."""

    def test_REQ_o00063_G_save_update_title(self, tmp_path: Path):
        """update_title mutation is saved via render_save."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        graph.update_title("REQ-t00001", "Updated Title")

        result = render_save(graph, tmp_path)

        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "## REQ-t00001: Updated Title" in content
        assert "## REQ-t00001: Test Requirement" not in content


# ---------------------------------------------------------------------------
# update_assertion save (REQ-o00063-H)
# ---------------------------------------------------------------------------


class TestSaveUpdateAssertion:
    """Tests for saving update_assertion mutations to disk via render_save."""

    def test_REQ_o00063_H_save_update_assertion(self, tmp_path: Path):
        """update_assertion mutation is saved via render_save."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        graph.update_assertion("REQ-t00001-A", "The system SHALL do something new.")

        result = render_save(graph, tmp_path)

        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "A. The system SHALL do something new." in content
        assert "A. The system SHALL do something." not in content
        # Assertion B should be untouched
        assert "B. The system SHALL do another thing." in content


# ---------------------------------------------------------------------------
# add_assertion save (REQ-o00063-I)
# ---------------------------------------------------------------------------


class TestSaveAddAssertion:
    """Tests for saving add_assertion mutations to disk via render_save."""

    def test_REQ_o00063_I_save_add_assertion(self, tmp_path: Path):
        """add_assertion mutation is saved via render_save."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        graph.add_assertion("REQ-t00001", "C", "The system SHALL do a third thing.")

        result = render_save(graph, tmp_path)

        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "C. The system SHALL do a third thing." in content
        # Existing assertions should be untouched
        assert "A. The system SHALL do something." in content
        assert "B. The system SHALL do another thing." in content


# ---------------------------------------------------------------------------
# Edge mutation coalescing (REQ-o00063-A)
# ---------------------------------------------------------------------------


class TestSaveEdgeMutations:
    """Tests for saving edge mutations via render_save."""

    def test_REQ_o00063_A_save_add_edge(self, tmp_path: Path):
        """add_edge mutations are reflected in rendered output."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        # Add a new parent requirement that REQ-t00001 also implements
        prd2 = GraphNode(
            id="REQ-p00002",
            kind=NodeKind.REQUIREMENT,
            label="Second PRD",
        )
        prd2._content = {"level": "PRD", "status": "Active", "hash": "11111111"}
        graph._index["REQ-p00002"] = prd2
        graph._roots.append(prd2)

        # Add edge: REQ-t00001 implements REQ-p00002
        graph.add_edge("REQ-t00001", "REQ-p00002", EdgeKind.IMPLEMENTS)

        result = render_save(graph, tmp_path)

        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        # The implements list should now contain both parents
        assert "REQ-p00001" in content
        assert "REQ-p00002" in content

    def test_REQ_o00063_A_save_delete_edge(self, tmp_path: Path):
        """delete_edge mutations are reflected in rendered output."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        # Delete the existing edge: REQ-t00001 implements REQ-p00001
        graph.delete_edge("REQ-t00001", "REQ-p00001")

        result = render_save(graph, tmp_path)

        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        # Implements should now be "-" (no parents)
        assert "**Implements**: -" in content

    def test_REQ_o00063_A_save_change_edge_kind(self, tmp_path: Path):
        """change_edge_kind mutation is reflected in rendered output."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        # Change the edge from IMPLEMENTS to REFINES
        graph.change_edge_kind("REQ-t00001", "REQ-p00001", EdgeKind.REFINES)

        result = render_save(graph, tmp_path)

        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "**Refines**: REQ-p00001" in content
        # IMPLEMENTS should now be "-" or absent for REQ-p00001
        assert "**Implements**: REQ-p00001" not in content


# ---------------------------------------------------------------------------
# Multiple mutations to same requirement
# ---------------------------------------------------------------------------


class TestMultipleMutationsSameReq:
    """Tests for multiple mutations targeting the same requirement."""

    def test_REQ_o00063_A_multiple_mutations_same_req(self, tmp_path: Path):
        """Multiple mutations to the same requirement all apply correctly."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        # Apply multiple mutations
        graph.change_status("REQ-t00001", "Deprecated")
        graph.update_title("REQ-t00001", "Updated Requirement")
        graph.update_assertion("REQ-t00001-A", "The system SHALL do something updated.")

        result = render_save(graph, tmp_path)

        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "**Status**: Deprecated" in content
        assert "## REQ-t00001: Updated Requirement" in content
        assert "A. The system SHALL do something updated." in content
        # Assertion B should still be intact
        assert "B. The system SHALL do another thing." in content

    def test_REQ_o00063_A_multiple_mutations_different_reqs(self, tmp_path: Path):
        """Mutations to different requirements all apply correctly."""
        graph, spec_file = _build_two_req_graph(tmp_path)

        graph.change_status("REQ-t00001", "Deprecated")
        graph.update_title("REQ-t00002", "Renamed Second")

        result = render_save(graph, tmp_path)

        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        # First requirement's status changed
        assert "**Status**: Deprecated" in content
        # Second requirement's title changed
        assert "## REQ-t00002: Renamed Second" in content


# ---------------------------------------------------------------------------
# No-source-file handling
# ---------------------------------------------------------------------------


class TestNoSourceFile:
    """Tests for mutations on nodes without FILE ancestors."""

    def test_REQ_o00063_A_skips_node_without_source(self, tmp_path: Path):
        """Mutations on nodes without FILE ancestry have no dirty files."""
        graph = TraceGraph(repo_root=tmp_path)

        node = GraphNode(
            id="REQ-nosource",
            kind=NodeKind.REQUIREMENT,
            label="No Source",
        )
        node._content = {"level": "DEV", "status": "Active", "hash": "00000000"}

        graph._roots = [node]
        graph._index = {"REQ-nosource": node}

        graph.change_status("REQ-nosource", "Draft")

        result = render_save(graph, tmp_path)

        # Should succeed with no files written (node has no FILE ancestor)
        assert result["success"] is True
        assert result["saved_count"] == 0


# ---------------------------------------------------------------------------
# Empty mutation log
# ---------------------------------------------------------------------------


class TestEmptyMutationLog:
    """Tests for saving with no mutations."""

    def test_REQ_o00063_F_empty_log_is_noop(self, tmp_path: Path):
        """Saving with an empty mutation log is a no-op success."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        result = render_save(graph, tmp_path)

        assert result["success"] is True
        assert result["saved_count"] == 0


# ---------------------------------------------------------------------------
# Edge coalescing with multiple add/delete
# ---------------------------------------------------------------------------


class TestEdgeCoalescing:
    """Tests for edge mutation coalescing behavior."""

    def test_REQ_o00063_A_add_then_delete_edge_coalesces(self, tmp_path: Path):
        """Adding then deleting an edge results in no net change."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        # Add a new parent
        prd2 = GraphNode(
            id="REQ-p00002",
            kind=NodeKind.REQUIREMENT,
            label="Second PRD",
        )
        prd2._content = {"level": "PRD", "status": "Active", "hash": "11111111"}
        graph._index["REQ-p00002"] = prd2
        graph._roots.append(prd2)

        # Add and then delete the edge
        graph.add_edge("REQ-t00001", "REQ-p00002", EdgeKind.IMPLEMENTS)
        graph.delete_edge("REQ-t00001", "REQ-p00002")

        result = render_save(graph, tmp_path)

        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        # Should still only implement REQ-p00001 (net effect is no change)
        assert "REQ-p00001" in content
        assert "REQ-p00002" not in content

    def test_REQ_o00063_A_multiple_edge_adds_coalesce(self, tmp_path: Path):
        """Multiple add_edge mutations to the same req coalesce into one write."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        # Create two more PRD nodes
        for i in range(2, 4):
            prd = GraphNode(
                id=f"REQ-p0000{i}",
                kind=NodeKind.REQUIREMENT,
                label=f"PRD {i}",
            )
            prd._content = {"level": "PRD", "status": "Active", "hash": f"{i}0000000"}
            graph._index[f"REQ-p0000{i}"] = prd
            graph._roots.append(prd)
            graph.add_edge("REQ-t00001", f"REQ-p0000{i}", EdgeKind.IMPLEMENTS)

        result = render_save(graph, tmp_path)

        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "REQ-p00001" in content
        assert "REQ-p00002" in content
        assert "REQ-p00003" in content


# ---------------------------------------------------------------------------
# Assertion target persistence
# ---------------------------------------------------------------------------


class TestAssertionTargetPersistence:
    """Tests that assertion_targets on edges are preserved when saving to disk."""

    def test_assertion_target_written_to_file(self, tmp_path: Path):
        """Edge with assertion_targets=["A"] produces REQ-p00001-A in file."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        # Delete existing whole-req edge, add assertion-targeted edge
        graph.delete_edge("REQ-t00001", "REQ-p00001")
        graph.add_edge("REQ-t00001", "REQ-p00001", EdgeKind.IMPLEMENTS, assertion_targets=["A"])

        result = render_save(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "REQ-p00001-A" in content
        # Check the DEV requirement's Implements line has REQ-p00001-A
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if "REQ-t00001:" in line:
                # Find the metadata line within the next few lines
                for meta_line in lines[i + 1 : i + 5]:
                    if "**Implements**:" in meta_line:
                        assert "REQ-p00001-A" in meta_line
                        break
                break

    def test_whole_req_and_assertion_target_coexist(self, tmp_path: Path):
        """Whole-req ref and assertion-targeted ref coexist in Implements line."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        # Add a second parent REQ-p00002 with assertion target ["B"]
        prd2 = GraphNode(
            id="REQ-p00002",
            kind=NodeKind.REQUIREMENT,
            label="Second PRD",
        )
        prd2._content = {"level": "PRD", "status": "Active", "hash": "11111111"}
        graph._index["REQ-p00002"] = prd2
        graph._roots.append(prd2)

        graph.add_edge("REQ-t00001", "REQ-p00002", EdgeKind.IMPLEMENTS, assertion_targets=["B"])

        result = render_save(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        # Should have both: whole-req REQ-p00001 and assertion-targeted REQ-p00002-B
        lines = content.splitlines()
        found = False
        for i, line in enumerate(lines):
            if "REQ-t00001:" in line:
                for meta_line in lines[i + 1 : i + 5]:
                    if "**Implements**:" in meta_line:
                        assert "REQ-p00001" in meta_line
                        assert "REQ-p00002-B" in meta_line
                        found = True
                        break
                break
        assert found, "No Implements line found for REQ-t00001"

    def test_no_duplicate_refs_written(self, tmp_path: Path):
        """Deleting and re-adding the same edge does not produce duplicate refs."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        # Delete and re-add the same edge
        graph.delete_edge("REQ-t00001", "REQ-p00001")
        graph.add_edge("REQ-t00001", "REQ-p00001", EdgeKind.IMPLEMENTS)

        result = render_save(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        lines = content.splitlines()
        found = False
        for i, line in enumerate(lines):
            if "REQ-t00001:" in line:
                for meta_line in lines[i + 1 : i + 5]:
                    if "**Implements**:" in meta_line:
                        count = meta_line.count("REQ-p00001")
                        assert (
                            count == 1
                        ), f"Expected REQ-p00001 exactly once but found {count} in: {meta_line}"
                        found = True
                        break
                break
        assert found, "No Implements line found for REQ-t00001"


# ---------------------------------------------------------------------------
# REFINES edge rendering
# ---------------------------------------------------------------------------


def _build_refines_graph(
    tmp_path: Path,
    has_refines_edge: bool = False,
) -> tuple[TraceGraph, Path]:
    """Build a graph with optional REFINES edge for testing."""
    from elspais.graph.GraphNode import FileType

    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text("placeholder", encoding="utf-8")

    graph = TraceGraph(repo_root=tmp_path)
    rel_path = str(spec_file.relative_to(tmp_path))

    # Create FILE node
    file_node = GraphNode(id=f"file:{rel_path}", kind=NodeKind.FILE, label="test_spec.md")
    file_node.set_field("file_type", FileType.SPEC)
    file_node.set_field("relative_path", rel_path)
    file_node.set_field("absolute_path", str(spec_file))
    file_node.set_field("repo", None)

    prd1 = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT, label="Product Req 1")
    prd1._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "00000000",
        "parse_line": 1,
        "parse_end_line": None,
    }

    prd2 = GraphNode(id="REQ-p00002", kind=NodeKind.REQUIREMENT, label="Product Req 2")
    prd2._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "00000001",
        "parse_line": 1,
        "parse_end_line": None,
    }

    req = GraphNode(id="REQ-t00001", kind=NodeKind.REQUIREMENT, label="Test Requirement")
    req._content = {
        "level": "DEV",
        "status": "Active",
        "hash": "abcd1234",
        "body_text": "",
        "parse_line": 1,
        "parse_end_line": None,
    }
    file_node.link(req, EdgeKind.CONTAINS)

    a1 = GraphNode(
        id="REQ-t00001-A", kind=NodeKind.ASSERTION, label="The system SHALL do something."
    )
    a1._content = {"label": "A", "parse_line": 7, "parse_end_line": None}
    req.link(a1, EdgeKind.STRUCTURES)

    # IMPLEMENTS edge
    prd1.link(req, EdgeKind.IMPLEMENTS)

    # Optional REFINES edge
    if has_refines_edge:
        prd2.link(req, EdgeKind.REFINES)

    graph._roots = [prd1, prd2]
    graph._index = {
        f"file:{rel_path}": file_node,
        "REQ-p00001": prd1,
        "REQ-p00002": prd2,
        "REQ-t00001": req,
        "REQ-t00001-A": a1,
    }

    return graph, spec_file


class TestSaveRefinesEdge:
    """Tests for REFINES edge rendering in render_save."""

    def test_add_refines_edge_persisted(self, tmp_path: Path):
        """Adding a REFINES edge is persisted to the Refines field."""
        graph, spec_file = _build_refines_graph(tmp_path, has_refines_edge=False)

        # Add REFINES edge via graph API
        graph.add_edge("REQ-t00001", "REQ-p00002", EdgeKind.REFINES)

        result = render_save(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "**Refines**: REQ-p00002" in content
        # Implements should still be there
        assert "**Implements**: REQ-p00001" in content

    def test_delete_refines_edge_persisted(self, tmp_path: Path):
        """Deleting a REFINES edge removes it from the output."""
        graph, spec_file = _build_refines_graph(tmp_path, has_refines_edge=True)

        graph.delete_edge("REQ-t00001", "REQ-p00002")

        result = render_save(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        # Refines line should not be present (no refines edges)
        assert "**Refines**:" not in content
        # Implements should be untouched
        assert "**Implements**: REQ-p00001" in content

    def test_refines_with_assertion_targets(self, tmp_path: Path):
        """REFINES edge with assertion_targets produces qualified IDs."""
        graph, spec_file = _build_refines_graph(tmp_path, has_refines_edge=False)

        graph.add_edge("REQ-t00001", "REQ-p00002", EdgeKind.REFINES, assertion_targets=["A"])

        result = render_save(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "REQ-p00002-A" in content

    def test_mixed_implements_and_refines_mutations(self, tmp_path: Path):
        """Both IMPLEMENTS and REFINES edge changes on same req render correctly."""
        graph, spec_file = _build_refines_graph(tmp_path, has_refines_edge=True)

        # Add a third PRD and IMPLEMENTS edge
        prd3 = GraphNode(
            id="REQ-p00003",
            kind=NodeKind.REQUIREMENT,
            label="Product Req 3",
        )
        prd3._content = {"level": "PRD", "status": "Active", "hash": "00000002"}
        graph._index["REQ-p00003"] = prd3
        graph._roots.append(prd3)

        graph.add_edge("REQ-t00001", "REQ-p00003", EdgeKind.IMPLEMENTS)
        # Also delete the REFINES edge
        graph.delete_edge("REQ-t00001", "REQ-p00002")

        result = render_save(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        # Implements should have both p00001 and p00003
        assert "REQ-p00001" in content
        assert "REQ-p00003" in content
        # Refines should be absent (no refines edges)
        assert "**Refines**:" not in content


# ---------------------------------------------------------------------------
# delete_assertion save
# ---------------------------------------------------------------------------


class TestSaveDeleteAssertion:
    """Tests for saving delete_assertion mutations to disk via render_save."""

    def test_delete_assertion_removes_line(self, tmp_path: Path):
        """delete_assertion mutation removes the assertion from rendered output."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        # Delete assertion B
        graph.delete_assertion("REQ-t00001-B")

        result = render_save(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "A. The system SHALL do something." in content
        assert "B. The system SHALL do another thing." not in content


# ---------------------------------------------------------------------------
# rename_assertion save
# ---------------------------------------------------------------------------


class TestSaveRenameAssertion:
    """Tests for saving rename_assertion mutations to disk via render_save."""

    def test_rename_assertion_changes_label(self, tmp_path: Path):
        """rename_assertion mutation changes the assertion label in rendered output."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        graph.rename_assertion("REQ-t00001-A", "Z")

        result = render_save(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "Z. The system SHALL do something." in content
        assert "A. The system SHALL do something." not in content
        # B should be unchanged
        assert "B. The system SHALL do another thing." in content


# ---------------------------------------------------------------------------
# add_requirement save
# ---------------------------------------------------------------------------


class TestSaveAddRequirement:
    """Tests for saving add_requirement mutations to disk via render_save."""

    def test_add_requirement_renders_to_parent_file(self, tmp_path: Path):
        """add_requirement renders the new requirement to the parent's file."""
        graph, spec_file = _build_graph_with_spec(tmp_path, "placeholder")

        graph.add_requirement(
            "REQ-t00002",
            "New Requirement",
            "DEV",
            status="Draft",
            parent_id="REQ-p00001",
        )

        result = render_save(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "## REQ-t00002: New Requirement" in content
        assert "**Level**: DEV" in content
        assert "*End* *New Requirement*" in content


# ---------------------------------------------------------------------------
# delete_requirement save
# ---------------------------------------------------------------------------


class TestSaveDeleteRequirement:
    """Tests for saving delete_requirement mutations to disk via render_save."""

    def test_delete_requirement_removes_block(self, tmp_path: Path):
        """delete_requirement removes the requirement from rendered output."""
        graph, spec_file = _build_two_req_graph(tmp_path)

        graph.delete_requirement("REQ-t00002")

        result = render_save(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "REQ-t00001" in content  # First req should remain
        assert "REQ-t00002" not in content  # Second req should be gone
        assert "Second Requirement" not in content

    def test_delete_requirement_preserves_other_reqs(self, tmp_path: Path):
        """Deleting one requirement doesn't affect others in the same file."""
        graph, spec_file = _build_two_req_graph(tmp_path)

        graph.delete_requirement("REQ-t00001")

        result = render_save(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "REQ-t00002" in content
        assert "Second Requirement" in content
        assert "First Requirement" not in content
