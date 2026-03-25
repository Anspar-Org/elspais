"""Tests for hash consistency after assertion mutations (full-text mode).

These tests verify that after each mutation type (add_assertion, update_assertion,
delete_assertion, rename_assertion), the hash is recomputed consistently from the
structured graph content via reconstruct_body_text().

Uses explicit hash_mode="full-text" since these tests verify the invariant that
hash == calculate_hash(reconstruct_body_text(node)), which only holds in full-text mode.
"""

from __future__ import annotations

from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.parsers import ParsedContent
from elspais.graph.render import reconstruct_body_text
from elspais.utilities.hasher import calculate_hash


def make_req(
    req_id: str,
    title: str = "Test Requirement",
    level: str = "PRD",
    status: str = "Active",
    assertions: list[dict] | None = None,
) -> ParsedContent:
    """Helper to create a requirement ParsedContent for hash computation."""
    return ParsedContent(
        content_type="requirement",
        parsed_data={
            "id": req_id,
            "title": title,
            "level": level,
            "status": status,
            "assertions": assertions or [],
            "implements": [],
            "refines": [],
        },
        start_line=1,
        end_line=10,
        raw_text=f"## {req_id}: {title}",
    )


def build_graph_for_hash() -> TraceGraph:
    """Build a graph with a requirement containing assertions for hash testing."""
    builder = GraphBuilder(hash_mode="full-text")
    builder.add_parsed_content(
        make_req(
            "REQ-p00001",
            "Test Requirement",
            assertions=[
                {"label": "A", "text": "The system SHALL validate input."},
                {"label": "B", "text": "The system SHALL log errors."},
            ],
        )
    )
    return builder.build()


class TestAddAssertionHashConsistency:
    """Tests verifying hash consistency after add_assertion."""

    # Implements: REQ-o00062-B
    def test_add_assertion_updates_hash(self):
        """After add_assertion, hash matches reconstruct_body_text().

        REQ-o00062-B: Add assertion recomputes hash consistently.
        """
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        old_hash = parent.get_field("hash")

        # Perform mutation
        graph.add_assertion("REQ-p00001", "C", "The system SHALL notify users.")

        # Verify hash matches what we'd compute from reconstructed body_text
        new_hash = parent.get_field("hash")
        expected_hash = calculate_hash(reconstruct_body_text(parent))
        assert new_hash == expected_hash

        # Verify hash actually changed
        assert new_hash != old_hash

    # Implements: REQ-o00062-B
    def test_add_assertion_reconstructed_body_has_new_assertion(self):
        """After add_assertion, reconstruct_body_text() includes the new assertion."""
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        graph.add_assertion("REQ-p00001", "C", "The system SHALL notify users.")

        body = reconstruct_body_text(parent)
        assert "C. The system SHALL notify users." in body
        assert "A. The system SHALL validate input." in body
        assert "B. The system SHALL log errors." in body


class TestUpdateAssertionHashConsistency:
    """Tests verifying hash consistency after update_assertion."""

    # Implements: REQ-o00062-B
    def test_update_assertion_updates_hash(self):
        """After update_assertion, hash matches reconstruct_body_text().

        REQ-o00062-B: Update assertion recomputes hash consistently.
        """
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        old_hash = parent.get_field("hash")

        # Perform mutation
        graph.update_assertion("REQ-p00001-A", "The system SHALL strictly validate all user input.")

        # Verify hash matches reconstructed body_text
        new_hash = parent.get_field("hash")
        expected_hash = calculate_hash(reconstruct_body_text(parent))
        assert new_hash == expected_hash

        # Verify hash actually changed
        assert new_hash != old_hash

    # Implements: REQ-o00062-B
    def test_update_assertion_preserves_other_assertions(self):
        """After update_assertion, other assertions remain in reconstructed body."""
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        graph.update_assertion("REQ-p00001-A", "Updated assertion A text.")

        body = reconstruct_body_text(parent)
        assert "B. The system SHALL log errors." in body
        assert "A. Updated assertion A text." in body


class TestDeleteAssertionHashConsistency:
    """Tests verifying hash consistency after delete_assertion."""

    # Implements: REQ-o00062-B
    def test_delete_assertion_updates_hash(self):
        """After delete_assertion, hash matches reconstruct_body_text().

        REQ-o00062-B: Delete assertion recomputes hash consistently.
        """
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        old_hash = parent.get_field("hash")

        # Perform mutation (delete A, no compact)
        graph.delete_assertion("REQ-p00001-A", compact=False)

        # Verify hash matches reconstructed body_text
        new_hash = parent.get_field("hash")
        expected_hash = calculate_hash(reconstruct_body_text(parent))
        assert new_hash == expected_hash

        # Verify hash actually changed
        assert new_hash != old_hash

    # Implements: REQ-o00062-B
    def test_delete_assertion_with_compact_updates_hash(self):
        """After delete_assertion with compact, hash matches reconstruct_body_text().

        REQ-o00062-B: Delete with compact renumbers assertions and recomputes hash.
        """
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        # Perform mutation (delete A, with compact)
        graph.delete_assertion("REQ-p00001-A", compact=True)

        # Verify hash matches reconstructed body_text
        new_hash = parent.get_field("hash")
        expected_hash = calculate_hash(reconstruct_body_text(parent))
        assert new_hash == expected_hash

        # B should now be A after compaction
        body = reconstruct_body_text(parent)
        assert "A. The system SHALL log errors." in body

    # Implements: REQ-o00062-B
    def test_delete_assertion_preserves_other_content(self):
        """After delete_assertion, remaining assertions are in reconstructed body."""
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        graph.delete_assertion("REQ-p00001-A", compact=False)

        body = reconstruct_body_text(parent)
        assert "B. The system SHALL log errors." in body


class TestRenameAssertionHashConsistency:
    """Tests verifying hash consistency after rename_assertion."""

    # Implements: REQ-o00062-B
    def test_rename_assertion_updates_hash(self):
        """After rename_assertion, hash matches reconstruct_body_text().

        REQ-o00062-B: Rename assertion recomputes hash consistently.
        """
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        old_hash = parent.get_field("hash")

        # Perform mutation (rename A to X)
        graph.rename_assertion("REQ-p00001-A", "X")

        # Verify hash matches reconstructed body_text
        new_hash = parent.get_field("hash")
        expected_hash = calculate_hash(reconstruct_body_text(parent))
        assert new_hash == expected_hash

        # Verify hash actually changed
        assert new_hash != old_hash

    # Implements: REQ-o00062-B
    def test_rename_assertion_preserves_other_assertions(self):
        """After rename_assertion, other assertions remain in reconstructed body."""
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        graph.rename_assertion("REQ-p00001-A", "X")

        body = reconstruct_body_text(parent)
        assert "B. The system SHALL log errors." in body
        assert "X. The system SHALL validate input." in body


class TestHashConsistencyAfterMultipleMutations:
    """Tests verifying hash consistency after sequences of mutations."""

    # Implements: REQ-o00062-B
    def test_multiple_add_assertions_maintain_hash_consistency(self):
        """After multiple add_assertion calls, hash still matches reconstruct_body_text()."""
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        # Perform multiple mutations
        graph.add_assertion("REQ-p00001", "C", "Third assertion.")
        graph.add_assertion("REQ-p00001", "D", "Fourth assertion.")

        # Verify hash consistency
        stored_hash = parent.get_field("hash")
        expected_hash = calculate_hash(reconstruct_body_text(parent))
        assert stored_hash == expected_hash

        # Verify assertions are in reconstructed body
        body = reconstruct_body_text(parent)
        assert "C. Third assertion." in body
        assert "D. Fourth assertion." in body

    # Implements: REQ-o00062-B
    def test_mixed_mutations_maintain_hash_consistency(self):
        """After mixed mutation types, hash still matches reconstruct_body_text()."""
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        # Perform various mutations
        graph.add_assertion("REQ-p00001", "C", "Third assertion.")
        graph.update_assertion("REQ-p00001-A", "Updated first assertion.")
        graph.rename_assertion("REQ-p00001-B", "X")

        # Verify hash consistency
        stored_hash = parent.get_field("hash")
        expected_hash = calculate_hash(reconstruct_body_text(parent))
        assert stored_hash == expected_hash

    # Implements: REQ-o00062-B
    def test_delete_then_add_maintains_hash_consistency(self):
        """After delete then add, hash still matches reconstruct_body_text()."""
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        # Delete A (with compact, so B becomes A)
        graph.delete_assertion("REQ-p00001-A", compact=True)
        # Add a new B
        graph.add_assertion("REQ-p00001", "B", "New B assertion.")

        # Verify hash consistency
        stored_hash = parent.get_field("hash")
        expected_hash = calculate_hash(reconstruct_body_text(parent))
        assert stored_hash == expected_hash

    # Implements: REQ-o00062-B
    def test_update_all_assertions_maintains_hash_consistency(self):
        """After updating all assertions, hash still matches reconstruct_body_text()."""
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        # Update both assertions
        graph.update_assertion("REQ-p00001-A", "Completely rewritten A.")
        graph.update_assertion("REQ-p00001-B", "Completely rewritten B.")

        # Verify hash consistency
        stored_hash = parent.get_field("hash")
        expected_hash = calculate_hash(reconstruct_body_text(parent))
        assert stored_hash == expected_hash
