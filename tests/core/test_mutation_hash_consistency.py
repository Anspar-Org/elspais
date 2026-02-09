"""Tests for hash consistency after assertion mutations (full-text mode).

These tests verify that after each mutation type (add_assertion, update_assertion,
delete_assertion, rename_assertion), the hash computed from the updated body_text
matches what would be computed if we re-parsed the content.

Uses explicit hash_mode="full-text" since these tests verify the invariant that
hash == calculate_hash(body_text), which only holds in full-text mode.
"""

from __future__ import annotations

from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.parsers import ParsedContent
from elspais.utilities.hasher import calculate_hash


def make_req_with_body_text(
    req_id: str,
    title: str = "Test Requirement",
    level: str = "PRD",
    status: str = "Active",
    assertions: list[dict] | None = None,
    body_text: str = "",
) -> ParsedContent:
    """Helper to create a requirement ParsedContent with body_text for hash computation."""
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
            "body_text": body_text,
            "hash": calculate_hash(body_text) if body_text else None,
        },
        start_line=1,
        end_line=10,
        raw_text=f"## {req_id}: {title}",
    )


def build_graph_with_body_text() -> TraceGraph:
    """Build a graph with a requirement containing body_text for hash computation.

    The body_text format matches what the parser would produce:
    - Metadata line (Level/Status/Implements)
    - Introduction text
    - ## Assertions header
    - Assertion lines (A. ..., B. ...)
    """
    body_text = """**Level**: PRD | **Status**: Active | **Implements**: -

Introduction text for the requirement.

## Assertions

A. The system SHALL validate input.
B. The system SHALL log errors."""

    builder = GraphBuilder(hash_mode="full-text")
    builder.add_parsed_content(
        make_req_with_body_text(
            "REQ-p00001",
            "Test Requirement",
            assertions=[
                {"label": "A", "text": "The system SHALL validate input."},
                {"label": "B", "text": "The system SHALL log errors."},
            ],
            body_text=body_text,
        )
    )
    return builder.build()


class TestAddAssertionHashConsistency:
    """Tests verifying hash consistency after add_assertion."""

    def test_add_assertion_updates_body_text_and_hash(self):
        """After add_assertion, body_text contains new assertion and hash matches.

        REQ-o00062-B: Add assertion updates body_text and recomputes hash.
        """
        graph = build_graph_with_body_text()
        parent = graph.find_by_id("REQ-p00001")

        # Capture state before mutation
        old_body_text = parent.get_field("body_text")
        old_hash = parent.get_field("hash")

        # Perform mutation
        graph.add_assertion("REQ-p00001", "C", "The system SHALL notify users.")

        # Verify body_text was updated
        new_body_text = parent.get_field("body_text")
        assert new_body_text != old_body_text
        assert "C. The system SHALL notify users." in new_body_text

        # Verify hash matches what we'd compute from the new body_text
        new_hash = parent.get_field("hash")
        expected_hash = calculate_hash(new_body_text)
        assert new_hash == expected_hash

        # Verify hash actually changed
        assert new_hash != old_hash

    def test_add_assertion_body_text_preserves_structure(self):
        """After add_assertion, body_text maintains proper structure."""
        graph = build_graph_with_body_text()
        parent = graph.find_by_id("REQ-p00001")

        graph.add_assertion("REQ-p00001", "C", "The system SHALL notify users.")

        body_text = parent.get_field("body_text")

        # Verify structure is preserved
        assert "**Level**: PRD" in body_text
        assert "Introduction text" in body_text
        assert "## Assertions" in body_text

        # Verify all assertions are present
        assert "A. The system SHALL validate input." in body_text
        assert "B. The system SHALL log errors." in body_text
        assert "C. The system SHALL notify users." in body_text


class TestUpdateAssertionHashConsistency:
    """Tests verifying hash consistency after update_assertion."""

    def test_update_assertion_updates_body_text_and_hash(self):
        """After update_assertion, body_text reflects new text and hash matches.

        REQ-o00062-B: Update assertion updates body_text and recomputes hash.
        """
        graph = build_graph_with_body_text()
        parent = graph.find_by_id("REQ-p00001")

        # Capture state before mutation
        old_body_text = parent.get_field("body_text")
        old_hash = parent.get_field("hash")

        # Perform mutation
        graph.update_assertion("REQ-p00001-A", "The system SHALL strictly validate all user input.")

        # Verify body_text was updated
        new_body_text = parent.get_field("body_text")
        assert new_body_text != old_body_text
        assert "A. The system SHALL strictly validate all user input." in new_body_text
        assert "A. The system SHALL validate input." not in new_body_text

        # Verify hash matches what we'd compute from the new body_text
        new_hash = parent.get_field("hash")
        expected_hash = calculate_hash(new_body_text)
        assert new_hash == expected_hash

        # Verify hash actually changed
        assert new_hash != old_hash

    def test_update_assertion_preserves_other_assertions(self):
        """After update_assertion, other assertions remain unchanged."""
        graph = build_graph_with_body_text()
        parent = graph.find_by_id("REQ-p00001")

        graph.update_assertion("REQ-p00001-A", "Updated assertion A text.")

        body_text = parent.get_field("body_text")

        # Verify B is unchanged
        assert "B. The system SHALL log errors." in body_text

        # Verify A is updated
        assert "A. Updated assertion A text." in body_text


class TestDeleteAssertionHashConsistency:
    """Tests verifying hash consistency after delete_assertion."""

    def test_delete_assertion_updates_body_text_and_hash(self):
        """After delete_assertion, body_text removes assertion and hash matches.

        REQ-o00062-B: Delete assertion updates body_text and recomputes hash.
        """
        graph = build_graph_with_body_text()
        parent = graph.find_by_id("REQ-p00001")

        # Capture state before mutation
        old_body_text = parent.get_field("body_text")
        old_hash = parent.get_field("hash")

        # Perform mutation (delete A, no compact)
        graph.delete_assertion("REQ-p00001-A", compact=False)

        # Verify body_text was updated
        new_body_text = parent.get_field("body_text")
        assert new_body_text != old_body_text
        assert "A. The system SHALL validate input." not in new_body_text

        # Verify hash matches what we'd compute from the new body_text
        new_hash = parent.get_field("hash")
        expected_hash = calculate_hash(new_body_text)
        assert new_hash == expected_hash

        # Verify hash actually changed
        assert new_hash != old_hash

    def test_delete_assertion_with_compact_updates_body_text_and_hash(self):
        """After delete_assertion with compact, body_text renumbers and hash matches.

        REQ-o00062-B: Delete with compact renumbers assertions in body_text.
        """
        graph = build_graph_with_body_text()
        parent = graph.find_by_id("REQ-p00001")

        # Perform mutation (delete A, with compact)
        graph.delete_assertion("REQ-p00001-A", compact=True)

        # Verify body_text was updated with renumbered assertion
        new_body_text = parent.get_field("body_text")
        assert "A. The system SHALL validate input." not in new_body_text
        # B should now be A after compaction
        assert "A. The system SHALL log errors." in new_body_text

        # Verify hash matches what we'd compute from the new body_text
        new_hash = parent.get_field("hash")
        expected_hash = calculate_hash(new_body_text)
        assert new_hash == expected_hash

    def test_delete_assertion_preserves_other_content(self):
        """After delete_assertion, non-assertion content remains unchanged."""
        graph = build_graph_with_body_text()
        parent = graph.find_by_id("REQ-p00001")

        graph.delete_assertion("REQ-p00001-A", compact=False)

        body_text = parent.get_field("body_text")

        # Verify other content is preserved
        assert "**Level**: PRD" in body_text
        assert "Introduction text" in body_text
        assert "## Assertions" in body_text
        assert "B. The system SHALL log errors." in body_text


class TestRenameAssertionHashConsistency:
    """Tests verifying hash consistency after rename_assertion."""

    def test_rename_assertion_updates_body_text_and_hash(self):
        """After rename_assertion, body_text reflects new label and hash matches.

        REQ-o00062-B: Rename assertion updates body_text and recomputes hash.
        """
        graph = build_graph_with_body_text()
        parent = graph.find_by_id("REQ-p00001")

        # Capture state before mutation
        old_body_text = parent.get_field("body_text")
        old_hash = parent.get_field("hash")

        # Perform mutation (rename A to X)
        graph.rename_assertion("REQ-p00001-A", "X")

        # Verify body_text was updated
        new_body_text = parent.get_field("body_text")
        assert new_body_text != old_body_text
        assert "A. The system SHALL validate input." not in new_body_text
        assert "X. The system SHALL validate input." in new_body_text

        # Verify hash matches what we'd compute from the new body_text
        new_hash = parent.get_field("hash")
        expected_hash = calculate_hash(new_body_text)
        assert new_hash == expected_hash

        # Verify hash actually changed
        assert new_hash != old_hash

    def test_rename_assertion_preserves_other_assertions(self):
        """After rename_assertion, other assertions remain unchanged."""
        graph = build_graph_with_body_text()
        parent = graph.find_by_id("REQ-p00001")

        graph.rename_assertion("REQ-p00001-A", "X")

        body_text = parent.get_field("body_text")

        # Verify B is unchanged
        assert "B. The system SHALL log errors." in body_text

        # Verify A was renamed to X
        assert "X. The system SHALL validate input." in body_text


class TestHashConsistencyAfterMultipleMutations:
    """Tests verifying hash consistency after sequences of mutations."""

    def test_multiple_add_assertions_maintain_hash_consistency(self):
        """After multiple add_assertion calls, hash still matches body_text."""
        graph = build_graph_with_body_text()
        parent = graph.find_by_id("REQ-p00001")

        # Perform multiple mutations
        graph.add_assertion("REQ-p00001", "C", "Third assertion.")
        graph.add_assertion("REQ-p00001", "D", "Fourth assertion.")

        # Verify hash consistency
        body_text = parent.get_field("body_text")
        stored_hash = parent.get_field("hash")
        expected_hash = calculate_hash(body_text)
        assert stored_hash == expected_hash

        # Verify all assertions are in body_text
        assert "C. Third assertion." in body_text
        assert "D. Fourth assertion." in body_text

    def test_mixed_mutations_maintain_hash_consistency(self):
        """After mixed mutation types, hash still matches body_text."""
        graph = build_graph_with_body_text()
        parent = graph.find_by_id("REQ-p00001")

        # Perform various mutations
        graph.add_assertion("REQ-p00001", "C", "Third assertion.")
        graph.update_assertion("REQ-p00001-A", "Updated first assertion.")
        graph.rename_assertion("REQ-p00001-B", "X")

        # Verify hash consistency
        body_text = parent.get_field("body_text")
        stored_hash = parent.get_field("hash")
        expected_hash = calculate_hash(body_text)
        assert stored_hash == expected_hash

        # Verify body_text reflects all changes
        assert "A. Updated first assertion." in body_text
        assert "X." in body_text  # B was renamed to X
        assert "C. Third assertion." in body_text

    def test_delete_then_add_maintains_hash_consistency(self):
        """After delete then add, hash still matches body_text."""
        graph = build_graph_with_body_text()
        parent = graph.find_by_id("REQ-p00001")

        # Delete A (with compact, so B becomes A)
        graph.delete_assertion("REQ-p00001-A", compact=True)
        # Add a new B
        graph.add_assertion("REQ-p00001", "B", "New B assertion.")

        # Verify hash consistency
        body_text = parent.get_field("body_text")
        stored_hash = parent.get_field("hash")
        expected_hash = calculate_hash(body_text)
        assert stored_hash == expected_hash

    def test_update_all_assertions_maintains_hash_consistency(self):
        """After updating all assertions, hash still matches body_text."""
        graph = build_graph_with_body_text()
        parent = graph.find_by_id("REQ-p00001")

        # Update both assertions
        graph.update_assertion("REQ-p00001-A", "Completely rewritten A.")
        graph.update_assertion("REQ-p00001-B", "Completely rewritten B.")

        # Verify hash consistency
        body_text = parent.get_field("body_text")
        stored_hash = parent.get_field("hash")
        expected_hash = calculate_hash(body_text)
        assert stored_hash == expected_hash

        # Verify body_text has both updates
        assert "A. Completely rewritten A." in body_text
        assert "B. Completely rewritten B." in body_text
