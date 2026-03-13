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


# ---------------------------------------------------------------------------
# Assertion target persistence
# ---------------------------------------------------------------------------


class TestAssertionTargetPersistence:
    """Tests that assertion_targets on edges are preserved when saving to disk."""

    def test_assertion_target_written_to_file(self, tmp_path: Path):
        """Edge with assertion_targets=["A"] produces REQ-p00001-A in file."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        # Delete existing whole-req edge, add assertion-targeted edge
        graph.delete_edge("REQ-t00001", "REQ-p00001")
        graph.add_edge("REQ-t00001", "REQ-p00001", EdgeKind.IMPLEMENTS, assertion_targets=["A"])

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "REQ-p00001-A" in content
        # Should NOT contain bare REQ-p00001 in the Implements line
        # (it was replaced by the assertion-targeted form)
        for line in content.splitlines():
            if "**Implements**:" in line:
                assert "REQ-p00001-A" in line
                # Ensure no bare REQ-p00001 (without -A suffix) on this line
                parts = line.split("REQ-p00001")
                for i, part in enumerate(parts):
                    if i > 0:  # after each occurrence of REQ-p00001
                        assert part.startswith(
                            "-A"
                        ), f"Expected REQ-p00001-A but found bare REQ-p00001 in: {line}"
                break

    def test_whole_req_and_assertion_target_coexist(self, tmp_path: Path):
        """Whole-req ref and assertion-targeted ref coexist in Implements line."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

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

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        # Should have both: whole-req REQ-p00001 and assertion-targeted REQ-p00002-B
        for line in content.splitlines():
            if "**Implements**:" in line:
                assert "REQ-p00001" in line
                assert "REQ-p00002-B" in line
                break
        else:
            raise AssertionError("No Implements line found in file")

    def test_no_duplicate_refs_written(self, tmp_path: Path):
        """Deleting and re-adding the same edge does not produce duplicate refs."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        # Delete and re-add the same edge
        graph.delete_edge("REQ-t00001", "REQ-p00001")
        graph.add_edge("REQ-t00001", "REQ-p00001", EdgeKind.IMPLEMENTS)

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if "**Implements**:" in line:
                # REQ-p00001 should appear exactly once
                count = line.count("REQ-p00001")
                assert count == 1, f"Expected REQ-p00001 exactly once but found {count} in: {line}"
                break
        else:
            raise AssertionError("No Implements line found in file")


# ---------------------------------------------------------------------------
# REFINES edge coalescing
# ---------------------------------------------------------------------------

SPEC_WITH_REFINES = """\
## REQ-t00001: Test Requirement

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001 | **Refines**: REQ-p00002

## Assertions

A. The system SHALL do something.

*End* *Test Requirement* | **Hash**: abcd1234
---
"""

SPEC_WITHOUT_REFINES = """\
## REQ-t00001: Test Requirement

**Level**: DEV | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL do something.

*End* *Test Requirement* | **Hash**: abcd1234
---
"""


def _build_refines_graph(
    tmp_path: Path,
    spec_content: str,
    has_refines_edge: bool = False,
) -> tuple[TraceGraph, Path]:
    """Build a graph with optional REFINES edge for testing."""
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text(spec_content, encoding="utf-8")

    graph = TraceGraph(repo_root=tmp_path)
    rel_path = str(spec_file.relative_to(tmp_path))

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

    req = GraphNode(
        id="REQ-t00001",
        kind=NodeKind.REQUIREMENT,
        label="Test Requirement",
        source=SourceLocation(path=rel_path, line=1),
    )
    req._content = {"level": "DEV", "status": "Active", "hash": "abcd1234", "body_text": ""}

    a1 = GraphNode(
        id="REQ-t00001-A",
        kind=NodeKind.ASSERTION,
        label="The system SHALL do something.",
        source=SourceLocation(path=rel_path, line=7),
    )
    a1._content = {"label": "A"}
    req.add_child(a1)

    # IMPLEMENTS edge
    prd1.link(req, EdgeKind.IMPLEMENTS)

    # Optional REFINES edge
    if has_refines_edge:
        prd2.link(req, EdgeKind.REFINES)

    graph._roots = [prd1, prd2]
    graph._index = {
        "REQ-p00001": prd1,
        "REQ-p00002": prd2,
        "REQ-t00001": req,
        "REQ-t00001-A": a1,
    }

    return graph, spec_file


class TestReplayRefinesEdge:
    """Tests for REFINES edge coalescing in replay_mutations_to_disk."""

    def test_add_refines_edge_persisted(self, tmp_path: Path):
        """Adding a REFINES edge is persisted to the Refines field."""
        graph, spec_file = _build_refines_graph(
            tmp_path, SPEC_WITHOUT_REFINES, has_refines_edge=False
        )

        # Add REFINES edge via graph API
        graph.add_edge("REQ-t00001", "REQ-p00002", EdgeKind.REFINES)

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "**Refines**: REQ-p00002" in content
        # Implements should still be there
        assert "**Implements**: REQ-p00001" in content

    def test_add_refines_edge_inserts_field_when_missing(self, tmp_path: Path):
        """When **Refines** field doesn't exist, it is inserted into the metadata line."""
        graph, spec_file = _build_refines_graph(
            tmp_path, SPEC_WITHOUT_REFINES, has_refines_edge=False
        )

        graph.add_edge("REQ-t00001", "REQ-p00002", EdgeKind.REFINES)

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        # Should have inserted | **Refines**: REQ-p00002 into metadata line
        for line in content.splitlines():
            if "**Level**:" in line:
                assert "**Refines**: REQ-p00002" in line
                assert "**Implements**: REQ-p00001" in line
                break
        else:
            raise AssertionError("No metadata line found")

    def test_delete_refines_edge_persisted(self, tmp_path: Path):
        """Deleting a REFINES edge updates the Refines field to '-'."""
        graph, spec_file = _build_refines_graph(tmp_path, SPEC_WITH_REFINES, has_refines_edge=True)

        graph.delete_edge("REQ-t00001", "REQ-p00002")

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "**Refines**: -" in content or "**Refines**:  -" in content
        # Implements should be untouched
        assert "**Implements**: REQ-p00001" in content

    def test_refines_with_assertion_targets(self, tmp_path: Path):
        """REFINES edge with assertion_targets produces qualified IDs."""
        graph, spec_file = _build_refines_graph(
            tmp_path, SPEC_WITHOUT_REFINES, has_refines_edge=False
        )

        graph.add_edge("REQ-t00001", "REQ-p00002", EdgeKind.REFINES, assertion_targets=["A"])

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "REQ-p00002-A" in content

    def test_mixed_implements_and_refines_mutations(self, tmp_path: Path):
        """Both IMPLEMENTS and REFINES edge changes on same req coalesce correctly."""
        graph, spec_file = _build_refines_graph(tmp_path, SPEC_WITH_REFINES, has_refines_edge=True)

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

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        # Implements should have both p00001 and p00003
        assert "REQ-p00001" in content
        assert "REQ-p00003" in content
        # Refines should be empty now
        assert "**Refines**: -" in content or "**Refines**:  -" in content


# ---------------------------------------------------------------------------
# delete_assertion replay
# ---------------------------------------------------------------------------


class TestReplayDeleteAssertion:
    """Tests for replaying delete_assertion mutations to disk."""

    def test_delete_assertion_removes_line(self, tmp_path: Path):
        """delete_assertion mutation removes the assertion line from the spec file."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        # Delete assertion B (with compaction: no renames since it's the last)
        graph.delete_assertion("REQ-t00001-B")

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "A. The system SHALL do something." in content
        assert "B. The system SHALL do another thing." not in content

    def test_delete_assertion_with_compaction(self, tmp_path: Path):
        """Deleting a middle assertion compacts subsequent labels."""
        # Build a spec with 3 assertions
        spec_3 = MINIMAL_SPEC.replace(
            "B. The system SHALL do another thing.",
            "B. The system SHALL do another thing.\nC. The system SHALL do a third thing.",
        )
        graph, spec_file = _build_graph_with_spec(tmp_path, spec_3)

        # Add assertion C to the graph
        assertion_c = GraphNode(
            id="REQ-t00001-C",
            kind=NodeKind.ASSERTION,
            label="The system SHALL do a third thing.",
            source=SourceLocation(path=str(spec_file.relative_to(tmp_path)), line=9),
        )
        assertion_c._content = {"label": "C"}
        graph._index["REQ-t00001"].add_child(assertion_c)
        graph._index["REQ-t00001-C"] = assertion_c

        # Delete assertion A (should compact: B→A, C→B)
        graph.delete_assertion("REQ-t00001-A")

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "A. The system SHALL do another thing." in content
        assert "B. The system SHALL do a third thing." in content
        assert "C." not in content


# ---------------------------------------------------------------------------
# rename_assertion replay
# ---------------------------------------------------------------------------


class TestReplayRenameAssertion:
    """Tests for replaying rename_assertion mutations to disk."""

    def test_rename_assertion_changes_label(self, tmp_path: Path):
        """rename_assertion mutation changes the assertion label in the spec file."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        graph.rename_assertion("REQ-t00001-A", "Z")

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "Z. The system SHALL do something." in content
        assert "A. The system SHALL do something." not in content
        # B should be unchanged
        assert "B. The system SHALL do another thing." in content


# ---------------------------------------------------------------------------
# fix_broken_reference replay
# ---------------------------------------------------------------------------


class TestReplayFixBrokenReference:
    """Tests for replaying fix_broken_reference mutations to disk."""

    def test_fix_broken_reference_updates_file(self, tmp_path: Path):
        """fix_broken_reference redirects a reference in the spec file."""
        # Use a spec that references a non-existent req
        broken_spec = MINIMAL_SPEC.replace("REQ-p00001", "REQ-p99999")
        spec_file = tmp_path / "test_spec.md"
        spec_file.write_text(broken_spec, encoding="utf-8")

        graph = TraceGraph(repo_root=tmp_path)
        rel_path = str(spec_file.relative_to(tmp_path))

        # Real target
        prd = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            label="Product Req",
            source=SourceLocation(path=rel_path, line=1),
        )
        prd._content = {"level": "PRD", "status": "Active", "hash": "00000000"}

        # Source with broken ref
        req = GraphNode(
            id="REQ-t00001",
            kind=NodeKind.REQUIREMENT,
            label="Test Requirement",
            source=SourceLocation(path=rel_path, line=1),
        )
        req._content = {"level": "DEV", "status": "Active", "hash": "abcd1234"}

        graph._roots = [prd, req]
        graph._index = {"REQ-p00001": prd, "REQ-t00001": req}

        # Add a broken reference manually
        from elspais.graph.builder import BrokenReference

        graph._broken_references.append(
            BrokenReference(
                source_id="REQ-t00001",
                target_id="REQ-p99999",
                edge_kind="implements",
            )
        )

        # Fix the broken reference
        graph.fix_broken_reference("REQ-t00001", "REQ-p99999", "REQ-p00001")

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "REQ-p00001" in content
        assert "REQ-p99999" not in content


# ---------------------------------------------------------------------------
# rename_node replay
# ---------------------------------------------------------------------------


class TestReplayRenameNode:
    """Tests for replaying rename_node mutations to disk."""

    def test_rename_node_updates_header(self, tmp_path: Path):
        """rename_node changes the requirement ID in the header."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        graph.rename_node("REQ-t00001", "REQ-t00099")

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "## REQ-t00099:" in content
        assert "REQ-t00001" not in content

    def test_rename_node_updates_references_in_other_reqs(self, tmp_path: Path):
        """rename_node also updates references in other requirements."""
        graph, spec_file = _build_two_req_graph(tmp_path)

        # Change the spec so REQ-t00002 implements REQ-t00001
        content = spec_file.read_text(encoding="utf-8")
        content = content.replace(
            "**Implements**: REQ-p00002",
            "**Implements**: REQ-t00001",
        )
        spec_file.write_text(content, encoding="utf-8")

        # Add IMPLEMENTS edge: REQ-t00002 -> REQ-t00001
        graph._index["REQ-t00001"].link(graph._index["REQ-t00002"], EdgeKind.IMPLEMENTS)

        graph.rename_node("REQ-t00001", "REQ-t00099")

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "## REQ-t00099:" in content
        # The reference from REQ-t00002 should also be updated
        assert "**Implements**: REQ-t00099" in content
        assert "REQ-t00001" not in content


# ---------------------------------------------------------------------------
# add_requirement replay
# ---------------------------------------------------------------------------


class TestReplayAddRequirement:
    """Tests for replaying add_requirement mutations to disk."""

    def test_add_requirement_appends_to_parent_file(self, tmp_path: Path):
        """add_requirement appends a requirement block to the parent's file."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        graph.add_requirement(
            "REQ-t00002",
            "New Requirement",
            "DEV",
            status="Draft",
            parent_id="REQ-p00001",
        )

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "## REQ-t00002: New Requirement" in content
        assert "**Level**: DEV" in content
        assert "**Implements**: REQ-p00001" in content
        assert "*End* *New Requirement*" in content

    def test_add_requirement_without_parent_skips(self, tmp_path: Path):
        """add_requirement without parent_id is skipped (no target file)."""
        graph, spec_file = _build_graph_with_spec(tmp_path, MINIMAL_SPEC)

        graph.add_requirement("REQ-t00099", "Orphan Req", "DEV")

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True
        assert any("no target file" in s for s in result["skipped"])


# ---------------------------------------------------------------------------
# delete_requirement replay
# ---------------------------------------------------------------------------


class TestReplayDeleteRequirement:
    """Tests for replaying delete_requirement mutations to disk."""

    def test_delete_requirement_removes_block(self, tmp_path: Path):
        """delete_requirement removes the entire requirement block from the file."""
        graph, spec_file = _build_two_req_graph(tmp_path)

        graph.delete_requirement("REQ-t00002")

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "REQ-t00001" in content  # First req should remain
        assert "REQ-t00002" not in content  # Second req should be gone
        assert "Second Requirement" not in content

    def test_delete_requirement_preserves_other_reqs(self, tmp_path: Path):
        """Deleting one requirement doesn't affect others in the same file."""
        graph, spec_file = _build_two_req_graph(tmp_path)

        graph.delete_requirement("REQ-t00001")

        result = replay_mutations_to_disk(graph, tmp_path)
        assert result["success"] is True

        content = spec_file.read_text(encoding="utf-8")
        assert "REQ-t00002" in content
        assert "Second Requirement" in content
        assert "First Requirement" not in content
