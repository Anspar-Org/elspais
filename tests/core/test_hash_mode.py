"""Tests for configurable hash_mode feature (full-text vs normalized-text).

Integration tests that verify both hash modes using a real graph built
with GraphBuilder. Tests ensure that hash behavior differs correctly
between full-text mode (hashes body_text) and normalized-text mode
(hashes normalized assertion text only).
"""

from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.parsers import ParsedContent
from elspais.utilities.hasher import calculate_hash, compute_normalized_hash


def make_req_with_body_text(
    req_id: str,
    title: str = "Test Requirement",
    level: str = "PRD",
    status: str = "Active",
    assertions: list[dict] | None = None,
    body_text: str = "",
    implements: list[str] | None = None,
) -> ParsedContent:
    """Helper to create a requirement ParsedContent with body_text."""
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
            "body_text": body_text,
            "hash": calculate_hash(body_text) if body_text else None,
        },
        start_line=1,
        end_line=10,
        raw_text=f"## {req_id}: {title}",
    )


BODY_TEXT = """**Level**: PRD | **Status**: Active | **Implements**: -

Introduction text for the requirement.

## Assertions

A. The system SHALL validate input.
B. The system SHALL log errors."""

ASSERTIONS = [
    {"label": "A", "text": "The system SHALL validate input."},
    {"label": "B", "text": "The system SHALL log errors."},
]


def build_graph(hash_mode: str = "full-text") -> TraceGraph:
    """Build a graph with a single requirement containing body_text and assertions.

    Args:
        hash_mode: "full-text" or "normalized-text".

    Returns:
        A TraceGraph with one requirement (REQ-p00001) and two assertions (A, B).
    """
    builder = GraphBuilder(hash_mode=hash_mode)
    builder.add_parsed_content(
        make_req_with_body_text(
            "REQ-p00001",
            "Test Requirement",
            assertions=ASSERTIONS,
            body_text=BODY_TEXT,
        )
    )
    return builder.build()


class TestFullTextMode:
    """Tests for full-text hash mode (default)."""

    def test_hash_mode_full_text_is_default(self):
        """GraphBuilder defaults to full-text hash mode."""
        builder = GraphBuilder()
        assert builder.hash_mode == "full-text"

    def test_hash_mode_full_text_graph_has_mode(self):
        """Built graph preserves the hash_mode setting."""
        graph = build_graph(hash_mode="full-text")
        assert graph.hash_mode == "full-text"

    def test_hash_mode_full_text_body_change_changes_hash(self):
        """In full-text mode, changing body_text causes the hash to change.

        When body_text is modified (even non-assertion content like introduction
        text), the hash must change because full-text hashes the entire body.
        """
        graph = build_graph(hash_mode="full-text")
        parent = graph.find_by_id("REQ-p00001")

        old_hash = parent.get_field("hash")
        assert old_hash is not None

        # Simulate a body_text change via assertion mutation
        graph.update_assertion("REQ-p00001-A", "The system SHALL strictly validate all input.")

        new_hash = parent.get_field("hash")
        assert new_hash != old_hash

    def test_hash_mode_full_text_stable_body_stable_hash(self):
        """In full-text mode, if body_text does not change, hash remains stable.

        Building the same graph twice should produce the same hash.
        """
        graph1 = build_graph(hash_mode="full-text")
        graph2 = build_graph(hash_mode="full-text")

        hash1 = graph1.find_by_id("REQ-p00001").get_field("hash")
        hash2 = graph2.find_by_id("REQ-p00001").get_field("hash")
        assert hash1 == hash2

    def test_hash_mode_full_text_hash_matches_calculate_hash(self):
        """In full-text mode, the stored hash matches calculate_hash(body_text)."""
        graph = build_graph(hash_mode="full-text")
        parent = graph.find_by_id("REQ-p00001")

        # After mutation, hash should match calculate_hash of updated body_text
        graph.update_assertion("REQ-p00001-A", "Updated text.")

        body_text = parent.get_field("body_text")
        stored_hash = parent.get_field("hash")
        expected_hash = calculate_hash(body_text)
        assert stored_hash == expected_hash


class TestNormalizedTextMode:
    """Tests for normalized-text hash mode."""

    def test_hash_mode_normalized_text_graph_has_mode(self):
        """Built graph preserves the normalized-text hash_mode setting."""
        graph = build_graph(hash_mode="normalized-text")
        assert graph.hash_mode == "normalized-text"

    def test_hash_mode_normalized_non_assertion_body_change_hash_unchanged(self):
        """In normalized-text mode, changing non-assertion body text does NOT change hash.

        The normalized-text mode only hashes assertion text. Changes to
        introduction text, metadata lines, or other non-assertion content
        in body_text should have no effect on the hash.
        """
        graph = build_graph(hash_mode="normalized-text")
        parent = graph.find_by_id("REQ-p00001")

        # First recompute hash in normalized-text mode to get the baseline
        # (the initial hash from build is set by the parser using full-text)
        graph._recompute_requirement_hash(parent)
        hash_before = parent.get_field("hash")

        # Directly modify the body_text with non-assertion content change
        # then trigger a recompute.
        old_body = parent.get_field("body_text")
        new_body = old_body.replace(
            "Introduction text for the requirement.",
            "Completely different introduction text.",
        )
        parent.set_field("body_text", new_body)

        # Recompute the hash in normalized-text mode
        graph._recompute_requirement_hash(parent)

        hash_after = parent.get_field("hash")
        assert (
            hash_before == hash_after
        ), "Non-assertion body text change should NOT affect hash in normalized-text mode"

    def test_hash_mode_normalized_assertion_text_change_hash_changes(self):
        """In normalized-text mode, changing assertion text DOES change hash.

        Assertion text is the source of truth for normalized-text hashing.
        """
        graph = build_graph(hash_mode="normalized-text")
        parent = graph.find_by_id("REQ-p00001")

        hash_before = parent.get_field("hash")

        # Update assertion text via the mutation API
        graph.update_assertion("REQ-p00001-A", "The system SHALL reject invalid input.")

        hash_after = parent.get_field("hash")
        assert (
            hash_before != hash_after
        ), "Assertion text change SHOULD affect hash in normalized-text mode"

    def test_hash_mode_normalized_assertion_reorder_hash_changes(self):
        """In normalized-text mode, reordering assertions DOES change hash.

        Hash is computed from assertions in physical order. A rename that
        effectively reorders them must produce a different hash.
        """
        graph = build_graph(hash_mode="normalized-text")
        parent = graph.find_by_id("REQ-p00001")

        hash_before = parent.get_field("hash")

        # Rename A -> X (this changes the assertion label which affects normalized hash)
        graph.rename_assertion("REQ-p00001-A", "X")

        hash_after = parent.get_field("hash")
        assert (
            hash_before != hash_after
        ), "Assertion label rename SHOULD affect hash in normalized-text mode"

    def test_hash_mode_normalized_trailing_space_hash_unchanged(self):
        """In normalized-text mode, trailing spaces on assertion text do NOT change hash.

        Normalization strips trailing whitespace, so adding trailing spaces
        should not affect the computed hash.
        """
        # Build two graphs: one with clean text, one with trailing spaces
        assertions_clean = [
            {"label": "A", "text": "The system SHALL validate input."},
            {"label": "B", "text": "The system SHALL log errors."},
        ]
        assertions_trailing = [
            {"label": "A", "text": "The system SHALL validate input.   "},
            {"label": "B", "text": "The system SHALL log errors.  "},
        ]

        builder_clean = GraphBuilder(hash_mode="normalized-text")
        builder_clean.add_parsed_content(
            make_req_with_body_text(
                "REQ-p00001",
                assertions=assertions_clean,
                body_text=BODY_TEXT,
            )
        )
        graph_clean = builder_clean.build()

        builder_trailing = GraphBuilder(hash_mode="normalized-text")
        builder_trailing.add_parsed_content(
            make_req_with_body_text(
                "REQ-p00001",
                assertions=assertions_trailing,
                body_text=BODY_TEXT,
            )
        )
        graph_trailing = builder_trailing.build()

        # Recompute hashes in normalized-text mode
        parent_clean = graph_clean.find_by_id("REQ-p00001")
        parent_trailing = graph_trailing.find_by_id("REQ-p00001")
        graph_clean._recompute_requirement_hash(parent_clean)
        graph_trailing._recompute_requirement_hash(parent_trailing)

        hash_clean = parent_clean.get_field("hash")
        hash_trailing = parent_trailing.get_field("hash")
        assert (
            hash_clean == hash_trailing
        ), "Trailing whitespace should NOT affect hash in normalized-text mode"

    def test_hash_mode_normalized_case_change_hash_changes(self):
        """In normalized-text mode, case changes in assertion text DO change hash.

        'SHALL' and 'shall' are different text, so the hash must differ.
        """
        # Build with normal case
        graph = build_graph(hash_mode="normalized-text")
        parent = graph.find_by_id("REQ-p00001")
        graph._recompute_requirement_hash(parent)
        hash_upper = parent.get_field("hash")

        # Update assertion to lowercase
        graph.update_assertion("REQ-p00001-A", "the system shall validate input.")
        hash_lower = parent.get_field("hash")

        assert (
            hash_upper != hash_lower
        ), "Case change in assertion text SHOULD affect hash in normalized-text mode"

    def test_hash_mode_normalized_hash_matches_compute_normalized_hash(self):
        """In normalized-text mode, stored hash matches compute_normalized_hash output.

        The hash produced by the graph mutation must match what
        compute_normalized_hash() would produce given the same assertion data.
        """
        graph = build_graph(hash_mode="normalized-text")
        parent = graph.find_by_id("REQ-p00001")

        # Recompute via graph
        graph._recompute_requirement_hash(parent)
        stored_hash = parent.get_field("hash")

        # Compute directly
        expected_hash = compute_normalized_hash(
            [
                ("A", "The system SHALL validate input."),
                ("B", "The system SHALL log errors."),
            ]
        )

        assert stored_hash == expected_hash

    def test_hash_mode_normalized_add_assertion_changes_hash(self):
        """In normalized-text mode, adding an assertion changes the hash."""
        graph = build_graph(hash_mode="normalized-text")
        parent = graph.find_by_id("REQ-p00001")
        graph._recompute_requirement_hash(parent)
        hash_before = parent.get_field("hash")

        graph.add_assertion("REQ-p00001", "C", "The system SHALL notify users.")
        hash_after = parent.get_field("hash")

        assert (
            hash_before != hash_after
        ), "Adding an assertion SHOULD change the hash in normalized-text mode"

    def test_hash_mode_normalized_delete_assertion_changes_hash(self):
        """In normalized-text mode, deleting an assertion changes the hash."""
        graph = build_graph(hash_mode="normalized-text")
        parent = graph.find_by_id("REQ-p00001")
        graph._recompute_requirement_hash(parent)
        hash_before = parent.get_field("hash")

        graph.delete_assertion("REQ-p00001-A", compact=False)
        hash_after = parent.get_field("hash")

        assert (
            hash_before != hash_after
        ), "Deleting an assertion SHOULD change the hash in normalized-text mode"


class TestHashModeDifference:
    """Tests verifying that full-text and normalized-text modes produce different hashes."""

    def test_hash_mode_modes_produce_different_hashes(self):
        """full-text and normalized-text modes compute different hashes for same content.

        These modes hash different inputs (body_text vs normalized assertions),
        so they should produce different hash values.
        """
        graph_full = build_graph(hash_mode="full-text")
        graph_norm = build_graph(hash_mode="normalized-text")

        parent_full = graph_full.find_by_id("REQ-p00001")
        parent_norm = graph_norm.find_by_id("REQ-p00001")

        # Recompute both to ensure we're comparing apples to apples
        graph_full._recompute_requirement_hash(parent_full)
        graph_norm._recompute_requirement_hash(parent_norm)

        hash_full = parent_full.get_field("hash")
        hash_norm = parent_norm.get_field("hash")

        # They hash different content, so should differ
        # (body_text includes metadata, intro text, etc. vs just assertion text)
        assert hash_full != hash_norm, (
            "full-text and normalized-text modes should produce different hashes "
            "because they hash different content"
        )

    def test_hash_mode_normalized_stable_across_non_assertion_changes(self):
        """Normalized-text hash is stable when non-assertion content varies.

        Two requirements with identical assertions but different body_text
        preambles should have the same hash in normalized-text mode.
        """
        body1 = """**Level**: PRD | **Status**: Active | **Implements**: -

Introduction version 1.

## Assertions

A. The system SHALL validate input.
B. The system SHALL log errors."""

        body2 = """**Level**: PRD | **Status**: Active | **Implements**: -

Completely different introduction for version 2.
With extra lines and different content.

## Assertions

A. The system SHALL validate input.
B. The system SHALL log errors."""

        builder1 = GraphBuilder(hash_mode="normalized-text")
        builder1.add_parsed_content(
            make_req_with_body_text("REQ-p00001", assertions=ASSERTIONS, body_text=body1)
        )
        graph1 = builder1.build()

        builder2 = GraphBuilder(hash_mode="normalized-text")
        builder2.add_parsed_content(
            make_req_with_body_text("REQ-p00001", assertions=ASSERTIONS, body_text=body2)
        )
        graph2 = builder2.build()

        parent1 = graph1.find_by_id("REQ-p00001")
        parent2 = graph2.find_by_id("REQ-p00001")

        graph1._recompute_requirement_hash(parent1)
        graph2._recompute_requirement_hash(parent2)

        hash1 = parent1.get_field("hash")
        hash2 = parent2.get_field("hash")

        assert hash1 == hash2, (
            "Normalized-text hashes should be identical when assertions are the same, "
            "regardless of differences in non-assertion body text"
        )

    def test_hash_mode_full_text_sensitive_to_non_assertion_changes(self):
        """Full-text hash changes when non-assertion content varies.

        Two requirements with identical assertions but different body_text
        preambles should have different hashes in full-text mode.
        """
        body1 = """Introduction version 1.

A. The system SHALL validate input."""

        body2 = """Introduction version 2 (different).

A. The system SHALL validate input."""

        assertions = [{"label": "A", "text": "The system SHALL validate input."}]

        builder1 = GraphBuilder(hash_mode="full-text")
        builder1.add_parsed_content(
            make_req_with_body_text("REQ-p00001", assertions=assertions, body_text=body1)
        )
        graph1 = builder1.build()

        builder2 = GraphBuilder(hash_mode="full-text")
        builder2.add_parsed_content(
            make_req_with_body_text("REQ-p00001", assertions=assertions, body_text=body2)
        )
        graph2 = builder2.build()

        parent1 = graph1.find_by_id("REQ-p00001")
        parent2 = graph2.find_by_id("REQ-p00001")

        graph1._recompute_requirement_hash(parent1)
        graph2._recompute_requirement_hash(parent2)

        hash1 = parent1.get_field("hash")
        hash2 = parent2.get_field("hash")

        assert hash1 != hash2, (
            "Full-text hashes should differ when body text differs, "
            "even if assertions are identical"
        )
