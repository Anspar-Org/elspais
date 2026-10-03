"""Tests for hash consistency after assertion mutations.

After each mutation type (add_assertion, update_assertion, delete_assertion,
rename_assertion) the stored hash equals the normalized digest of the
requirement's Assertions as they now stand, each spelled out explicitly here.
"""

from __future__ import annotations

from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.parsers import ParsedContent
from elspais.graph.render import reconstruct_body_text
from elspais.utilities.hasher import compute_normalized_hash
from tests.core.graph_test_helpers import grammar_for


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
    builder = GraphBuilder(namespace="REQ", resolver=grammar_for("REQ"))
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


A_TEXT = "The system SHALL validate input."
B_TEXT = "The system SHALL log errors."
RETIRED = "<RETIRED>"


def expected_hash(*assertions: tuple[str, str]) -> str:
    """The normalized digest of exactly these (label, text) Assertions."""
    return compute_normalized_hash(list(assertions))


class TestAddAssertionHashConsistency:
    """Tests verifying hash consistency after add_assertion."""

    # Verifies: REQ-o00062-B
    def test_add_assertion_updates_hash(self):
        """After add_assertion, the stored hash is the digest of its Assertions.

        REQ-o00062-B: Add assertion recomputes hash consistently.
        """
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        old_hash = parent.get_field("hash")

        # Perform mutation
        graph.add_assertion("REQ-p00001", "The system SHALL notify users.")

        # The stored hash is the digest of the Assertions now held
        new_hash = parent.get_field("hash")
        expected = expected_hash(
            ("A", A_TEXT), ("B", B_TEXT), ("C", "The system SHALL notify users.")
        )
        assert new_hash == expected

        # Verify hash actually changed
        assert new_hash != old_hash

    # Verifies: REQ-o00062-B
    def test_add_assertion_reconstructed_body_has_new_assertion(self):
        """After add_assertion, reconstruct_body_text() includes the new assertion."""
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        graph.add_assertion("REQ-p00001", "The system SHALL notify users.")

        body = reconstruct_body_text(parent)
        assert "C. The system SHALL notify users." in body
        assert "A. The system SHALL validate input." in body
        assert "B. The system SHALL log errors." in body


class TestUpdateAssertionHashConsistency:
    """Tests verifying hash consistency after update_assertion."""

    # Verifies: REQ-o00062-B
    def test_update_assertion_updates_hash(self):
        """After update_assertion, the stored hash is the digest of its Assertions.

        REQ-o00062-B: Update assertion recomputes hash consistently.
        """
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        old_hash = parent.get_field("hash")

        # Perform mutation
        graph.update_assertion("REQ-p00001-A", "The system SHALL strictly validate all user input.")

        # The stored hash is the digest of the Assertions now held
        new_hash = parent.get_field("hash")
        expected = expected_hash(
            ("A", "The system SHALL strictly validate all user input."), ("B", B_TEXT)
        )
        assert new_hash == expected

        # Verify hash actually changed
        assert new_hash != old_hash

    # Verifies: REQ-o00062-B
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

    # Verifies: REQ-o00062-B
    def test_delete_assertion_updates_hash(self):
        """After delete_assertion, the stored hash is the digest of its Assertions.

        REQ-o00062-B: Delete assertion recomputes hash consistently.
        """
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        old_hash = parent.get_field("hash")

        graph.delete_assertion("REQ-p00001-A")

        # The stored hash is the digest of the Assertions now held
        new_hash = parent.get_field("hash")
        expected = expected_hash(("A", RETIRED), ("B", B_TEXT))
        assert new_hash == expected

        # Verify hash actually changed
        assert new_hash != old_hash

    # Verifies: REQ-o00062-B, REQ-p00017-K
    def test_delete_assertion_hashes_the_retired_text(self):
        """The recomputed hash covers the retired *Assertion* under its label,
        and every other *Assertion* unchanged."""
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        graph.delete_assertion("REQ-p00001-A")

        body = reconstruct_body_text(parent)
        assert "A. <RETIRED>" in body
        assert "The system SHALL validate input." not in body
        assert "B. The system SHALL log errors." in body


class TestRenameAssertionHashConsistency:
    """Tests verifying hash consistency after rename_assertion."""

    # Verifies: REQ-o00062-B
    def test_rename_assertion_updates_hash(self):
        """After rename_assertion, the stored hash is the digest of its Assertions.

        REQ-o00062-B: Rename assertion recomputes hash consistently.
        """
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        old_hash = parent.get_field("hash")

        # Perform mutation (rename A to X)
        graph.rename_assertion("REQ-p00001-A", "X")

        # The stored hash is the digest of the Assertions now held
        new_hash = parent.get_field("hash")
        expected = expected_hash(("X", A_TEXT), ("B", B_TEXT))
        assert new_hash == expected

        # Verify hash actually changed
        assert new_hash != old_hash

    # Verifies: REQ-o00062-B
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

    # Verifies: REQ-o00062-B
    def test_multiple_add_assertions_maintain_hash_consistency(self):
        """After multiple add_assertion calls, the stored hash is the digest of its Assertions."""
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        # Perform multiple mutations
        graph.add_assertion("REQ-p00001", "Third assertion.")
        graph.add_assertion("REQ-p00001", "Fourth assertion.")

        # Verify hash consistency
        stored_hash = parent.get_field("hash")
        expected = expected_hash(
            ("A", A_TEXT), ("B", B_TEXT), ("C", "Third assertion."), ("D", "Fourth assertion.")
        )
        assert stored_hash == expected

        # Verify assertions are in reconstructed body
        body = reconstruct_body_text(parent)
        assert "C. Third assertion." in body
        assert "D. Fourth assertion." in body

    # Verifies: REQ-o00062-B
    def test_mixed_mutations_maintain_hash_consistency(self):
        """After mixed mutation types, the stored hash is the digest of its Assertions."""
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        # Perform various mutations
        graph.add_assertion("REQ-p00001", "Third assertion.")
        graph.update_assertion("REQ-p00001-A", "Updated first assertion.")
        graph.rename_assertion("REQ-p00001-B", "X")

        # Verify hash consistency
        stored_hash = parent.get_field("hash")
        expected = expected_hash(
            ("A", "Updated first assertion."), ("X", B_TEXT), ("C", "Third assertion.")
        )
        assert stored_hash == expected

    # Verifies: REQ-o00062-B
    def test_delete_then_add_maintains_hash_consistency(self):
        """After delete then add, the stored hash is the digest of its Assertions."""
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        # Retire A, then add: the new assertion takes C, after the retired A
        graph.delete_assertion("REQ-p00001-A")
        graph.add_assertion("REQ-p00001", "New C assertion.")

        # Verify hash consistency
        stored_hash = parent.get_field("hash")
        expected = expected_hash(("A", RETIRED), ("B", B_TEXT), ("C", "New C assertion."))
        assert stored_hash == expected
        assert "C. New C assertion." in reconstruct_body_text(parent)

    # Verifies: REQ-o00062-B
    def test_update_all_assertions_maintains_hash_consistency(self):
        """After updating all assertions, the stored hash is the digest of its Assertions."""
        graph = build_graph_for_hash()
        parent = graph.find_by_id("REQ-p00001")

        # Update both assertions
        graph.update_assertion("REQ-p00001-A", "Completely rewritten A.")
        graph.update_assertion("REQ-p00001-B", "Completely rewritten B.")

        # Verify hash consistency
        stored_hash = parent.get_field("hash")
        expected = expected_hash(("A", "Completely rewritten A."), ("B", "Completely rewritten B."))
        assert stored_hash == expected
