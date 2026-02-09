# Validates REQ-o00063-A, REQ-o00063-F, REQ-o00063-G, REQ-o00063-H, REQ-o00063-I
"""Tests for the persistence layer — replay_mutations_to_disk.

Validates:
- REQ-o00063-A: spec_writer functions are called correctly for each mutation type
- REQ-o00063-F: After file mutations, graph state is synchronized
- REQ-o00063-G: modify_title is called for update_title mutations
- REQ-o00063-H: modify_assertion_text is called for update_assertion mutations
- REQ-o00063-I: add_assertion_to_file is called for add_assertion mutations
"""

from __future__ import annotations

import time
from pathlib import Path

from elspais.graph import GraphNode, NodeKind, SourceLocation
from elspais.graph.builder import TraceGraph
from elspais.graph.relations import EdgeKind
from elspais.server.persistence import (
    check_for_external_changes,
    replay_mutations_to_disk,
)

# ---------------------------------------------------------------------------
# Shared spec file content
# ---------------------------------------------------------------------------

MINIMAL_SPEC = """\
## REQ-t00001: Test Requirement

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL do something.
B. The system SHALL do another thing.

## Rationale

This is a test requirement.

*End* *Test Requirement* | **Hash**: abcd1234
---
"""

TWO_REQ_SPEC = """\
## REQ-t00001: First Requirement

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL do the first thing.
B. The system SHALL do the second thing.

*End* *First Requirement* | **Hash**: aaaa1111
---

## REQ-t00002: Second Requirement

**Level**: DEV | **Status**: Draft | **Implements**: REQ-p00002

## Assertions

A. The system SHALL handle the second requirement.

*End* *Second Requirement* | **Hash**: bbbb2222
---
"""


def _build_graph_with_spec(
    tmp_path: Path,
    spec_content: str,
    spec_filename: str = "test_spec.md",
) -> tuple[TraceGraph, Path]:
    """Build a TraceGraph with a real spec file on disk.

    Creates a spec file, builds graph nodes manually with source locations
    pointing at the file. This allows mutations to be replayed to the real file.

    Returns:
        Tuple of (graph, spec_file_path).
    """
    spec_file = tmp_path / spec_filename
    spec_file.write_text(spec_content, encoding="utf-8")

    # Build graph with nodes that reference the spec file
    graph = TraceGraph(repo_root=tmp_path)

    # Use relative path for source location (relative to repo_root)
    rel_path = str(spec_file.relative_to(tmp_path))

    # PRD root node (needed so REQ-t00001 can implement it)
    prd_node = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Product Requirement",
        source=SourceLocation(path=rel_path, line=1),
    )
    prd_node._content = {"level": "PRD", "status": "Active", "hash": "00000000"}

    # Main requirement node
    req_node = GraphNode(
        id="REQ-t00001",
        kind=NodeKind.REQUIREMENT,
        label="Test Requirement",
        source=SourceLocation(path=rel_path, line=1),
    )
    req_node._content = {
        "level": "DEV",
        "status": "Active",
        "hash": "abcd1234",
        "body_text": "",
    }

    # Assertions
    assertion_a = GraphNode(
        id="REQ-t00001-A",
        kind=NodeKind.ASSERTION,
        label="The system SHALL do something.",
        source=SourceLocation(path=rel_path, line=7),
    )
    assertion_a._content = {"label": "A"}
    req_node.add_child(assertion_a)

    assertion_b = GraphNode(
        id="REQ-t00001-B",
        kind=NodeKind.ASSERTION,
        label="The system SHALL do another thing.",
        source=SourceLocation(path=rel_path, line=8),
    )
    assertion_b._content = {"label": "B"}
    req_node.add_child(assertion_b)

    # Link: REQ-t00001 implements REQ-p00001
    prd_node.link(req_node, EdgeKind.IMPLEMENTS)

    # Build graph index
    graph._roots = [prd_node]
    graph._index = {
        "REQ-p00001": prd_node,
        "REQ-t00001": req_node,
        "REQ-t00001-A": assertion_a,
        "REQ-t00001-B": assertion_b,
    }

    return graph, spec_file


def _build_two_req_graph(tmp_path: Path) -> tuple[TraceGraph, Path]:
    """Build a graph with two requirements from TWO_REQ_SPEC."""
    spec_file = tmp_path / "two_reqs.md"
    spec_file.write_text(TWO_REQ_SPEC, encoding="utf-8")

    graph = TraceGraph(repo_root=tmp_path)
    rel_path = str(spec_file.relative_to(tmp_path))

    # PRD root nodes
    prd1 = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Product Req 1",
        source=SourceLocation(path=rel_path, line=1),
    )
    prd1._content = {"level": "PRD", "status": "Active", "hash": "00000000"}

    prd2 = GraphNode(
        id="REQ-p00002",
        kind=NodeKind.REQUIREMENT,
        label="Product Req 2",
        source=SourceLocation(path=rel_path, line=1),
    )
    prd2._content = {"level": "PRD", "status": "Active", "hash": "00000001"}

    # First requirement
    req1 = GraphNode(
        id="REQ-t00001",
        kind=NodeKind.REQUIREMENT,
        label="First Requirement",
        source=SourceLocation(path=rel_path, line=1),
    )
    req1._content = {"level": "DEV", "status": "Active", "hash": "aaaa1111", "body_text": ""}

    a1 = GraphNode(
        id="REQ-t00001-A",
        kind=NodeKind.ASSERTION,
        label="The system SHALL do the first thing.",
        source=SourceLocation(path=rel_path, line=7),
    )
    a1._content = {"label": "A"}
    req1.add_child(a1)

    b1 = GraphNode(
        id="REQ-t00001-B",
        kind=NodeKind.ASSERTION,
        label="The system SHALL do the second thing.",
        source=SourceLocation(path=rel_path, line=8),
    )
    b1._content = {"label": "B"}
    req1.add_child(b1)

    prd1.link(req1, EdgeKind.IMPLEMENTS)

    # Second requirement
    req2 = GraphNode(
        id="REQ-t00002",
        kind=NodeKind.REQUIREMENT,
        label="Second Requirement",
        source=SourceLocation(path=rel_path, line=13),
    )
    req2._content = {"level": "DEV", "status": "Draft", "hash": "bbbb2222", "body_text": ""}

    a2 = GraphNode(
        id="REQ-t00002-A",
        kind=NodeKind.ASSERTION,
        label="The system SHALL handle the second requirement.",
        source=SourceLocation(path=rel_path, line=19),
    )
    a2._content = {"label": "A"}
    req2.add_child(a2)

    prd2.link(req2, EdgeKind.IMPLEMENTS)

    graph._roots = [prd1, prd2]
    graph._index = {
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
# change_status replay (REQ-o00063-A)
# ---------------------------------------------------------------------------


class TestReplayChangeStatus:
    """Tests for replaying change_status mutations to disk."""

    def test_REQ_o00063_A_replay_change_status(self, tmp_path: Path):
        """change_status mutation is replayed via modify_status."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        # Make a status change via graph API
        graph.change_status("REQ-t00001", "Deprecated")

        # Replay to disk
        result = replay_mutations_to_disk(graph, tmp_path)

        assert result["success"] is True
        assert result["saved_count"] == 1
        assert len(result["files_modified"]) == 1

        # Verify file content
        content = spec_file.read_text(encoding="utf-8")
        assert "**Status**: Deprecated" in content
        assert "**Status**: Active" not in content

    def test_REQ_o00063_A_replay_clears_mutation_log(self, tmp_path: Path):
        """After successful replay, mutation log is cleared."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        graph.change_status("REQ-t00001", "Draft")
        assert len(graph.mutation_log) == 1

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True
        assert len(graph.mutation_log) == 0


# ---------------------------------------------------------------------------
# update_title replay (REQ-o00063-G)
# ---------------------------------------------------------------------------


class TestReplayUpdateTitle:
    """Tests for replaying update_title mutations to disk."""

    def test_REQ_o00063_G_replay_update_title(self, tmp_path: Path):
        """update_title mutation is replayed via modify_title."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        graph.update_title("REQ-t00001", "Updated Title")

        result = replay_mutations_to_disk(graph, tmp_path)

        assert result["success"] is True
        assert result["saved_count"] == 1

        content = spec_file.read_text(encoding="utf-8")
        assert "## REQ-t00001: Updated Title" in content
        assert "## REQ-t00001: Test Requirement" not in content


# ---------------------------------------------------------------------------
# update_assertion replay (REQ-o00063-H)
# ---------------------------------------------------------------------------


class TestReplayUpdateAssertion:
    """Tests for replaying update_assertion mutations to disk."""

    def test_REQ_o00063_H_replay_update_assertion(self, tmp_path: Path):
        """update_assertion mutation is replayed via modify_assertion_text."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        graph.update_assertion("REQ-t00001-A", "The system SHALL do something new.")

        result = replay_mutations_to_disk(graph, tmp_path)

        assert result["success"] is True
        assert result["saved_count"] == 1

        content = spec_file.read_text(encoding="utf-8")
        assert "A. The system SHALL do something new." in content
        assert "A. The system SHALL do something." not in content
        # Assertion B should be untouched
        assert "B. The system SHALL do another thing." in content


# ---------------------------------------------------------------------------
# add_assertion replay (REQ-o00063-I)
# ---------------------------------------------------------------------------


class TestReplayAddAssertion:
    """Tests for replaying add_assertion mutations to disk."""

    def test_REQ_o00063_I_replay_add_assertion(self, tmp_path: Path):
        """add_assertion mutation is replayed via add_assertion_to_file."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        graph.add_assertion("REQ-t00001", "C", "The system SHALL do a third thing.")

        result = replay_mutations_to_disk(graph, tmp_path)

        assert result["success"] is True
        assert result["saved_count"] == 1

        content = spec_file.read_text(encoding="utf-8")
        assert "C. The system SHALL do a third thing." in content
        # Existing assertions should be untouched
        assert "A. The system SHALL do something." in content
        assert "B. The system SHALL do another thing." in content


# ---------------------------------------------------------------------------
# Edge mutation coalescing (REQ-o00063-A)
# ---------------------------------------------------------------------------


class TestReplayEdgeMutations:
    """Tests for replaying edge mutations with coalescing."""

    def test_REQ_o00063_A_replay_add_edge_coalesces(self, tmp_path: Path):
        """add_edge mutations are coalesced into a single modify_implements call."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

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

        result = replay_mutations_to_disk(graph, tmp_path)

        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        # The implements list should now contain both parents
        assert "REQ-p00001" in content
        assert "REQ-p00002" in content

    def test_REQ_o00063_A_replay_delete_edge_coalesces(self, tmp_path: Path):
        """delete_edge mutations are coalesced into the final implements list."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        # Delete the existing edge: REQ-t00001 implements REQ-p00001
        graph.delete_edge("REQ-t00001", "REQ-p00001")

        result = replay_mutations_to_disk(graph, tmp_path)

        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        # Implements should now be "-" (no parents)
        assert "**Implements**: -" in content or "**Implements**:  -" in content

    def test_REQ_o00063_A_replay_change_edge_kind(self, tmp_path: Path):
        """change_edge_kind mutation calls change_reference_type."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        # Change the edge from IMPLEMENTS to REFINES
        graph.change_edge_kind("REQ-t00001", "REQ-p00001", EdgeKind.REFINES)

        result = replay_mutations_to_disk(graph, tmp_path)

        assert result["success"] is True
        assert result["saved_count"] == 1

        content = spec_file.read_text(encoding="utf-8")
        assert "**Refines**: REQ-p00001" in content
        assert "**Implements**: REQ-p00001" not in content


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


class TestConflictDetection:
    """Tests for external change conflict detection."""

    def test_REQ_o00063_F_detect_external_changes(self, tmp_path: Path):
        """Modified spec files are detected before replay."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        # Record build time in the past
        build_time = time.time() - 10

        # Touch the spec file to simulate external modification
        spec_file.write_text(MINIMAL_SPEC.replace("Active", "Modified"), encoding="utf-8")

        conflicts = check_for_external_changes(graph, tmp_path, build_time)
        assert len(conflicts) >= 1

    def test_REQ_o00063_F_no_conflicts_when_unmodified(self, tmp_path: Path):
        """No conflicts reported when files are not modified externally."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        # Build time is in the future (or at least after file creation)
        build_time = time.time() + 10

        conflicts = check_for_external_changes(graph, tmp_path, build_time)
        assert len(conflicts) == 0

    def test_REQ_o00063_F_replay_aborts_on_conflict(self, tmp_path: Path):
        """replay_mutations_to_disk aborts if external changes detected."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        # Record build time in the past
        build_time = time.time() - 10

        # Touch the file
        spec_file.write_text(MINIMAL_SPEC + "\n<!-- modified -->\n", encoding="utf-8")

        # Make a mutation
        graph.change_status("REQ-t00001", "Deprecated")

        result = replay_mutations_to_disk(graph, tmp_path, build_time=build_time)

        assert result["success"] is False
        assert len(result["conflicts"]) >= 1
        assert "External changes" in result["errors"][0]

        # File should NOT have been modified by replay
        content = spec_file.read_text(encoding="utf-8")
        assert "**Status**: Active" in content  # original status preserved
        assert "Deprecated" not in content


# ---------------------------------------------------------------------------
# Multiple mutations to same requirement
# ---------------------------------------------------------------------------


class TestMultipleMutationsSameReq:
    """Tests for multiple mutations targeting the same requirement."""

    def test_REQ_o00063_A_multiple_mutations_same_req(self, tmp_path: Path):
        """Multiple mutations to the same requirement all apply correctly."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        # Apply multiple mutations
        graph.change_status("REQ-t00001", "Deprecated")
        graph.update_title("REQ-t00001", "Updated Requirement")
        graph.update_assertion("REQ-t00001-A", "The system SHALL do something updated.")

        result = replay_mutations_to_disk(graph, tmp_path)

        assert result["success"] is True
        assert result["saved_count"] == 3

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

        result = replay_mutations_to_disk(graph, tmp_path)

        assert result["success"] is True
        assert result["saved_count"] == 2

        content = spec_file.read_text(encoding="utf-8")
        # First requirement's status changed
        assert "**Status**: Deprecated" in content
        # Second requirement's title changed
        assert "## REQ-t00002: Renamed Second" in content


# ---------------------------------------------------------------------------
# No-source-file handling
# ---------------------------------------------------------------------------


class TestNoSourceFile:
    """Tests for mutations on nodes without source file references."""

    def test_REQ_o00063_A_skips_node_without_source(self, tmp_path: Path):
        """Mutations on nodes without source location are skipped gracefully."""
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

        result = replay_mutations_to_disk(graph, tmp_path)

        # Should succeed but with skipped entries
        assert result["success"] is True
        assert len(result["skipped"]) == 1
        assert "no source file" in result["skipped"][0]


# ---------------------------------------------------------------------------
# Empty mutation log
# ---------------------------------------------------------------------------


class TestEmptyMutationLog:
    """Tests for replaying with no mutations."""

    def test_REQ_o00063_F_empty_log_is_noop(self, tmp_path: Path):
        """Replaying an empty mutation log is a no-op success."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        result = replay_mutations_to_disk(graph, tmp_path)

        assert result["success"] is True
        assert result["saved_count"] == 0
        assert len(result["files_modified"]) == 0
        assert len(result["errors"]) == 0

        # File should be unchanged
        content = spec_file.read_text(encoding="utf-8")
        assert content == MINIMAL_SPEC


# ---------------------------------------------------------------------------
# Edge coalescing with multiple add/delete
# ---------------------------------------------------------------------------


class TestEdgeCoalescing:
    """Tests for edge mutation coalescing behavior."""

    def test_REQ_o00063_A_add_then_delete_edge_coalesces(self, tmp_path: Path):
        """Adding then deleting an edge results in no net change."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

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

        result = replay_mutations_to_disk(graph, tmp_path)

        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        # Should still only implement REQ-p00001 (net effect is no change)
        assert "REQ-p00001" in content
        assert "REQ-p00002" not in content

    def test_REQ_o00063_A_multiple_edge_adds_coalesce(self, tmp_path: Path):
        """Multiple add_edge mutations to the same req coalesce into one write."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

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

        result = replay_mutations_to_disk(graph, tmp_path)

        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "REQ-p00001" in content
        assert "REQ-p00002" in content
        assert "REQ-p00003" in content
