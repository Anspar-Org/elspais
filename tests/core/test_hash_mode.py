"""Tests for the requirement content hash: the normalized digest of its Assertions.

Integration tests over a real graph built with GraphBuilder. The hash covers
a requirement's Assertions alone, normalized; no other part of the
requirement moves it, and no setting selects another digest.
"""

from __future__ import annotations

from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers import ParsedContent
from elspais.graph.relations import EdgeKind
from elspais.graph.render import compute_hash_for_node, iter_hashed_parts
from elspais.utilities.hasher import compute_normalized_hash
from tests.core.graph_test_helpers import grammar_for


def make_req(
    req_id: str,
    title: str = "Test Requirement",
    level: str = "PRD",
    status: str = "Active",
    assertions: list[dict] | None = None,
    implements: list[str] | None = None,
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
        end_line=10,
        raw_text=f"## {req_id}: {title}",
    )


ASSERTIONS = [
    {"label": "A", "text": "The system SHALL validate input."},
    {"label": "B", "text": "The system SHALL log errors."},
]


def build_graph() -> TraceGraph:
    """Build a graph with one requirement (REQ-p00001) and two assertions (A, B)."""
    builder = GraphBuilder(namespace="REQ", resolver=grammar_for("REQ"))
    builder.add_parsed_content(
        make_req(
            "REQ-p00001",
            "Test Requirement",
            assertions=ASSERTIONS,
        )
    )
    return builder.build()


class TestAssertionHash:
    """The hash follows the Assertions and nothing else."""

    # Verifies: REQ-d00131-J+S
    def test_hash_non_assertion_body_change_hash_unchanged(self):
        """Changing non-assertion body text does NOT change hash.

        The hash covers assertion text alone. Changes to the requirement
        title or status (non-assertion content) have no effect on it.
        """
        graph = build_graph()
        parent = graph.find_by_id("REQ-p00001")

        # Recompute to get the baseline (the fixture carries no stored hash)
        graph._recompute_requirement_hash(parent)
        hash_before = parent.get_field("hash")

        # Modify non-assertion content (title/status) then trigger a recompute.
        parent.set_field("status", "Draft")
        parent.set_label("Completely Different Title")

        # Recompute the hash
        graph._recompute_requirement_hash(parent)

        hash_after = parent.get_field("hash")
        assert hash_before == hash_after, "Non-assertion body text change should NOT affect hash"

    # Verifies: REQ-d00131-J
    def test_hash_assertion_text_change_hash_changes(self):
        """Changing assertion text DOES change hash.

        Assertion text is what the hash covers.
        """
        graph = build_graph()
        parent = graph.find_by_id("REQ-p00001")

        hash_before = parent.get_field("hash")

        # Update assertion text via the mutation API
        graph.update_assertion("REQ-p00001-A", "The system SHALL reject invalid input.")

        hash_after = parent.get_field("hash")
        assert hash_before != hash_after, "Assertion text change SHOULD affect hash"

    # Verifies: REQ-d00131-J
    def test_hash_assertion_label_rename_hash_changes(self):
        """Renaming an assertion's label DOES change the hash.

        The label is part of each normalized assertion line, so a rename moves
        the hash even though the assertion text is unchanged.
        """
        graph = build_graph()
        parent = graph.find_by_id("REQ-p00001")

        hash_before = parent.get_field("hash")

        # Rename A -> X (this changes the assertion label which affects normalized hash)
        graph.rename_assertion("REQ-p00001-A", "X")

        hash_after = parent.get_field("hash")
        assert hash_before != hash_after, "Assertion label rename SHOULD affect hash"

    # Verifies: REQ-d00131-J
    def test_hash_trailing_space_hash_unchanged(self):
        """Trailing spaces on assertion text do NOT change hash.

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

        builder_clean = GraphBuilder(namespace="REQ", resolver=grammar_for("REQ"))
        builder_clean.add_parsed_content(
            make_req(
                "REQ-p00001",
                assertions=assertions_clean,
            )
        )
        graph_clean = builder_clean.build()

        builder_trailing = GraphBuilder(namespace="REQ", resolver=grammar_for("REQ"))
        builder_trailing.add_parsed_content(
            make_req(
                "REQ-p00001",
                assertions=assertions_trailing,
            )
        )
        graph_trailing = builder_trailing.build()

        # Recompute hashes
        parent_clean = graph_clean.find_by_id("REQ-p00001")
        parent_trailing = graph_trailing.find_by_id("REQ-p00001")
        graph_clean._recompute_requirement_hash(parent_clean)
        graph_trailing._recompute_requirement_hash(parent_trailing)

        hash_clean = parent_clean.get_field("hash")
        hash_trailing = parent_trailing.get_field("hash")
        assert hash_clean == hash_trailing, "Trailing whitespace should NOT affect hash"

    # Verifies: REQ-d00131-J
    def test_hash_case_change_hash_changes(self):
        """Case changes in assertion text DO change hash.

        'SHALL' and 'shall' are different text, so the hash must differ.
        """
        # Build with normal case
        graph = build_graph()
        parent = graph.find_by_id("REQ-p00001")
        graph._recompute_requirement_hash(parent)
        hash_upper = parent.get_field("hash")

        # Update assertion to lowercase
        graph.update_assertion("REQ-p00001-A", "the system shall validate input.")
        hash_lower = parent.get_field("hash")

        assert hash_upper != hash_lower, "Case change in assertion text SHOULD affect hash"

    # Verifies: REQ-d00131-J
    def test_hash_matches_compute_normalized_hash(self):
        """Stored hash matches compute_normalized_hash output.

        The hash produced by the graph mutation must match what
        compute_normalized_hash() would produce given the same assertion data.
        """
        graph = build_graph()
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

    # Verifies: REQ-d00131-J
    def test_hash_add_assertion_changes_hash(self):
        """Adding an assertion changes the hash."""
        graph = build_graph()
        parent = graph.find_by_id("REQ-p00001")
        graph._recompute_requirement_hash(parent)
        hash_before = parent.get_field("hash")

        graph.add_assertion("REQ-p00001", "The system SHALL notify users.")
        hash_after = parent.get_field("hash")

        assert hash_before != hash_after, "Adding an assertion SHOULD change the hash"

    # Verifies: REQ-d00131-J
    def test_hash_delete_assertion_changes_hash(self):
        """Deleting an assertion changes the hash."""
        graph = build_graph()
        parent = graph.find_by_id("REQ-p00001")
        graph._recompute_requirement_hash(parent)
        hash_before = parent.get_field("hash")

        graph.delete_assertion("REQ-p00001-A")
        hash_after = parent.get_field("hash")

        assert hash_before != hash_after, "Deleting an assertion SHOULD change the hash"


class TestOnlyAssertionsAreHashed:
    """No surviving path folds a requirement's prose into its hash."""

    @staticmethod
    def _build_with_preamble(preamble: str) -> TraceGraph:
        """One requirement with the shared Assertions and the given preamble section."""
        builder = GraphBuilder(namespace="REQ", resolver=grammar_for("REQ"))
        builder.add_parsed_content(
            ParsedContent(
                content_type="requirement",
                parsed_data={
                    "id": "REQ-p00001",
                    "title": "Test Requirement",
                    "level": "PRD",
                    "status": "Active",
                    "assertions": ASSERTIONS,
                    "implements": [],
                    "refines": [],
                    "sections": [{"heading": "preamble", "content": preamble, "line": 3}],
                },
                start_line=1,
                end_line=10,
                raw_text="## REQ-p00001: Test Requirement",
            )
        )
        return builder.build()

    # Verifies: REQ-d00131-S
    def test_hash_ignores_preamble_prose(self):
        """Two requirements differing only in preamble prose hash identically,
        and that hash is the digest of their Assertions alone."""
        node1 = self._build_with_preamble("Introduction version 1.").find_by_id("REQ-p00001")
        node2 = self._build_with_preamble("A different introduction.").find_by_id("REQ-p00001")
        assert any(c.kind == NodeKind.REMAINDER for c in node1.iter_children()), (
            "fixture must hold a REMAINDER section for the property to mean anything"
        )

        expected = compute_normalized_hash([(a["label"], a["text"]) for a in ASSERTIONS])
        assert compute_hash_for_node(node1) == expected
        assert compute_hash_for_node(node2) == expected

    # Verifies: REQ-d00131-S, REQ-d00132-L
    def test_iter_hashed_parts_yields_only_assertions(self):
        """A requirement holding a REMAINDER section yields its Assertions alone."""
        node = self._build_with_preamble("Introduction text.").find_by_id("REQ-p00001")
        assert any(
            c.kind == NodeKind.REMAINDER
            for c in node.iter_children(edge_kinds={EdgeKind.STRUCTURES})
        ), "fixture must hold a REMAINDER section beneath the requirement"

        parts = list(iter_hashed_parts(node))
        assert [p.kind for p in parts] == [NodeKind.ASSERTION, NodeKind.ASSERTION]
        assert sorted(p.get_field("label") for p in parts) == ["A", "B"]

    # Verifies: REQ-d00131-S
    def test_editing_a_section_leaves_the_hash_unmoved(self):
        """update_remainder rewrites a section's text without moving the hash."""
        graph = self._build_with_preamble("Introduction text.")
        parent = graph.find_by_id("REQ-p00001")
        graph._recompute_requirement_hash(parent)
        hash_before = parent.get_field("hash")

        remainder = next(c for c in parent.iter_children() if c.kind == NodeKind.REMAINDER)
        graph.update_remainder(remainder.id, text="Entirely rewritten introduction.")

        assert parent.get_field("hash") == hash_before
