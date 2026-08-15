# Verifies: REQ-p00006, REQ-o00062-G, REQ-o00062-P
"""Tests for journey mutation operations."""

from pathlib import Path

import pytest

from elspais.graph import NodeKind
from elspais.graph.factory import build_graph as build_repo_graph
from elspais.graph.GraphNode import make_file_id
from elspais.graph.relations import EdgeKind
from elspais.graph.render import render_file
from tests.core.graph_test_helpers import (
    build_graph,
    make_journey,
    make_requirement,
)

# The namespace the helper-built journey graphs declare.
CANONICAL_NAMESPACE = "REQ"


def build_journey_graph():
    """Build a graph with a journey, sections, and linked requirements."""
    return build_graph(
        make_requirement("REQ-p00001", title="Auth", level="PRD"),
        make_requirement("REQ-p00002", title="Billing", level="PRD"),
        make_journey(
            "JNY-LOGIN-01",
            title="User Login Flow",
            actor="End User",
            goal="Access system securely",
            context="Production environment",
            validates=["REQ-p00001"],
            body_lines=["This covers the primary auth flow."],
            sections=[
                {"name": "Steps", "content": "1. Navigate to login\n2. Enter credentials"},
                {"name": "Expected Outcome", "content": "Dashboard loads"},
            ],
        ),
    )


class TestJourneyFieldMutations:
    """Tests for update_journey_field."""

    def test_update_actor(self):
        graph = build_journey_graph()
        entry = graph.update_journey_field("JNY-LOGIN-01", "actor", "Admin User")
        node = graph.find_by_id("JNY-LOGIN-01")
        assert node.get_field("actor") == "Admin User"
        assert entry.operation == "update_journey_field"
        assert "**Actor**: Admin User" in node.get_field("body")

    def test_update_goal(self):
        graph = build_journey_graph()
        graph.update_journey_field("JNY-LOGIN-01", "goal", "Login quickly")
        node = graph.find_by_id("JNY-LOGIN-01")
        assert node.get_field("goal") == "Login quickly"
        assert "**Goal**: Login quickly" in node.get_field("body")

    def test_update_context(self):
        graph = build_journey_graph()
        graph.update_journey_field("JNY-LOGIN-01", "context", "Staging env")
        node = graph.find_by_id("JNY-LOGIN-01")
        assert node.get_field("context") == "Staging env"
        assert "**Context**: Staging env" in node.get_field("body")

    def test_update_preamble(self):
        graph = build_journey_graph()
        graph.update_journey_field("JNY-LOGIN-01", "preamble", "New preamble text.")
        node = graph.find_by_id("JNY-LOGIN-01")
        assert node.get_field("body_lines") == ["New preamble text."]
        assert "New preamble text." in node.get_field("body")

    def test_invalid_field_raises(self):
        graph = build_journey_graph()
        with pytest.raises(ValueError, match="Invalid field"):
            graph.update_journey_field("JNY-LOGIN-01", "invalid", "value")

    def test_non_journey_raises(self):
        graph = build_journey_graph()
        with pytest.raises(ValueError, match="not a user journey"):
            graph.update_journey_field("REQ-p00001", "actor", "Admin")

    def test_not_found_raises(self):
        graph = build_journey_graph()
        with pytest.raises(KeyError, match="not found"):
            graph.update_journey_field("JNY-MISSING-01", "actor", "Admin")


class TestJourneySectionMutations:
    """Tests for section add/update/delete."""

    def test_update_section_content(self):
        graph = build_journey_graph()
        graph.update_journey_section("JNY-LOGIN-01", "Steps", new_content="1. New step")
        node = graph.find_by_id("JNY-LOGIN-01")
        sections = node.get_field("sections")
        assert sections[0]["content"] == "1. New step"
        assert "1. New step" in node.get_field("body")

    def test_update_section_name(self):
        graph = build_journey_graph()
        graph.update_journey_section("JNY-LOGIN-01", "Steps", new_name="Procedure")
        node = graph.find_by_id("JNY-LOGIN-01")
        sections = node.get_field("sections")
        assert sections[0]["name"] == "Procedure"
        assert "## Procedure" in node.get_field("body")

    def test_update_section_not_found_raises(self):
        graph = build_journey_graph()
        with pytest.raises(ValueError, match="not found"):
            graph.update_journey_section("JNY-LOGIN-01", "Nonexistent", new_content="x")

    def test_add_section(self):
        graph = build_journey_graph()
        graph.add_journey_section("JNY-LOGIN-01", "Postconditions", "User is logged in")
        node = graph.find_by_id("JNY-LOGIN-01")
        sections = node.get_field("sections")
        assert len(sections) == 3
        assert sections[2]["name"] == "Postconditions"
        assert "## Postconditions" in node.get_field("body")

    def test_delete_section(self):
        graph = build_journey_graph()
        graph.delete_journey_section("JNY-LOGIN-01", "Expected Outcome")
        node = graph.find_by_id("JNY-LOGIN-01")
        sections = node.get_field("sections")
        assert len(sections) == 1
        assert sections[0]["name"] == "Steps"
        assert "Expected Outcome" not in node.get_field("body")

    def test_delete_section_not_found_raises(self):
        graph = build_journey_graph()
        with pytest.raises(ValueError, match="not found"):
            graph.delete_journey_section("JNY-LOGIN-01", "Nonexistent")


class TestAddDeleteJourney:
    """Tests for add_journey and delete_journey."""

    def test_add_journey(self):
        graph = build_journey_graph()
        file_node = graph.find_by_id(make_file_id(CANONICAL_NAMESPACE, "spec/journeys.md"))
        assert file_node is not None
        entry = graph.add_journey(
            "JNY-SIGNUP-01", "User Signup", make_file_id(CANONICAL_NAMESPACE, "spec/journeys.md")
        )
        assert entry.operation == "add_journey"
        node = graph.find_by_id("JNY-SIGNUP-01")
        assert node is not None
        assert node.kind == NodeKind.USER_JOURNEY
        assert node.get_label() == "User Signup"
        # Verify CONTAINS edge from file
        assert node.file_node() is file_node

    def test_add_journey_duplicate_raises(self):
        graph = build_journey_graph()
        with pytest.raises(ValueError, match="already exists"):
            graph.add_journey(
                "JNY-LOGIN-01", "Duplicate", make_file_id(CANONICAL_NAMESPACE, "spec/journeys.md")
            )

    def test_add_journey_file_not_found_raises(self):
        graph = build_journey_graph()
        with pytest.raises(KeyError, match="not found"):
            graph.add_journey(
                "JNY-NEW-01", "New", make_file_id(CANONICAL_NAMESPACE, "nonexistent.md")
            )

    def test_delete_journey(self):
        graph = build_journey_graph()
        entry = graph.delete_journey("JNY-LOGIN-01")
        assert entry.operation == "delete_journey"
        assert graph.find_by_id("JNY-LOGIN-01") is None

    def test_delete_non_journey_raises(self):
        graph = build_journey_graph()
        with pytest.raises(ValueError, match="not a user journey"):
            graph.delete_journey("REQ-p00001")

    def test_delete_journey_not_found_raises(self):
        graph = build_journey_graph()
        with pytest.raises(KeyError, match="not found"):
            graph.delete_journey("JNY-MISSING-01")


class TestBodyReconstruction:
    """Tests for body reconstruction round-trip fidelity."""

    def test_body_contains_all_fields(self):
        graph = build_journey_graph()
        # Trigger reconstruction (body starts empty from test fixture)
        graph.reconstruct_journey_body("JNY-LOGIN-01")
        node = graph.find_by_id("JNY-LOGIN-01")
        body = node.get_field("body")
        assert "## JNY-LOGIN-01: User Login Flow" in body
        assert "**Actor**: End User" in body
        assert "**Goal**: Access system securely" in body
        assert "**Context**: Production environment" in body
        assert "This covers the primary auth flow." in body
        assert "## Steps" in body
        assert "1. Navigate to login" in body
        assert "## Expected Outcome" in body
        assert "Dashboard loads" in body
        assert "*End* *User Login Flow*" in body

    def test_body_includes_validates_refs(self):
        graph = build_journey_graph()
        graph.reconstruct_journey_body("JNY-LOGIN-01")
        node = graph.find_by_id("JNY-LOGIN-01")
        body = node.get_field("body")
        assert "Validates: REQ-p00001" in body

    def test_reconstruct_after_title_change(self):
        graph = build_journey_graph()
        graph.update_title("JNY-LOGIN-01", "Revised Login")
        graph.reconstruct_journey_body("JNY-LOGIN-01")
        node = graph.find_by_id("JNY-LOGIN-01")
        body = node.get_field("body")
        assert "## JNY-LOGIN-01: Revised Login" in body

    def test_field_update_preserves_other_fields(self):
        graph = build_journey_graph()
        graph.update_journey_field("JNY-LOGIN-01", "actor", "Admin")
        node = graph.find_by_id("JNY-LOGIN-01")
        body = node.get_field("body")
        # Actor changed
        assert "**Actor**: Admin" in body
        # Other fields preserved
        assert "**Goal**: Access system securely" in body
        assert "## Steps" in body
        assert "Dashboard loads" in body


class TestJourneyUndo:
    """Tests for undo of journey mutations."""

    def test_undo_field_update(self):
        graph = build_journey_graph()
        graph.update_journey_field("JNY-LOGIN-01", "actor", "Admin")
        node = graph.find_by_id("JNY-LOGIN-01")
        assert node.get_field("actor") == "Admin"
        graph.undo_last()
        assert node.get_field("actor") == "End User"

    def test_undo_add_section(self):
        graph = build_journey_graph()
        graph.add_journey_section("JNY-LOGIN-01", "Postconditions", "Done")
        node = graph.find_by_id("JNY-LOGIN-01")
        assert len(node.get_field("sections")) == 3
        graph.undo_last()
        assert len(node.get_field("sections")) == 2

    def test_undo_delete_section(self):
        graph = build_journey_graph()
        graph.delete_journey_section("JNY-LOGIN-01", "Steps")
        node = graph.find_by_id("JNY-LOGIN-01")
        assert len(node.get_field("sections")) == 1
        graph.undo_last()
        assert len(node.get_field("sections")) == 2
        assert node.get_field("sections")[1]["name"] == "Steps"

    def test_undo_update_section(self):
        graph = build_journey_graph()
        graph.update_journey_section("JNY-LOGIN-01", "Steps", new_name="Procedure")
        node = graph.find_by_id("JNY-LOGIN-01")
        assert node.get_field("sections")[0]["name"] == "Procedure"
        graph.undo_last()
        assert node.get_field("sections")[0]["name"] == "Steps"

    def test_undo_add_journey(self):
        graph = build_journey_graph()
        graph.add_journey(
            "JNY-NEW-01", "New", make_file_id(CANONICAL_NAMESPACE, "spec/journeys.md")
        )
        assert graph.find_by_id("JNY-NEW-01") is not None
        graph.undo_last()
        assert graph.find_by_id("JNY-NEW-01") is None

    def test_undo_delete_journey(self):
        graph = build_journey_graph()
        graph.delete_journey("JNY-LOGIN-01")
        assert graph.find_by_id("JNY-LOGIN-01") is None
        graph.undo_last()
        assert graph.find_by_id("JNY-LOGIN-01") is not None


CANONICAL_JOURNEY_ID = "JNY-001"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
# The namespace the hht-like fixture declares; structural node ids carry it.


@pytest.fixture
def journey_graph_from_disk():
    """A private build of the hht-like fixture for delete/undo round trips.

    A delete_journey + undo round trip is exactly reversible today -- the
    replayed VALIDATES edges carry their ``assertion_targets`` -- and the
    tests below pin that. The copy stays private (deliberately NOT the
    session-scoped ``canonical_graph``/``mutable_graph``) so that if a
    regression ever makes the round trip lossy again, the damage is confined
    to this module instead of leaking into every later test. Same fixture
    content -- mirrors ``rebuilt_graph`` in test_node_version.py.
    """
    fg = build_repo_graph(repo_root=FIXTURES_DIR / "hht-like")
    return fg._repos[fg._root_repo].graph


def _contains_edge(file_node, journey_id):
    """Return the FILE -> journey CONTAINS edge, or None if detached."""
    for edge in file_node.iter_outgoing_edges():
        if edge.kind == EdgeKind.CONTAINS and edge.target.id == journey_id:
            return edge
    return None


def _edge_signature(node):
    """Structural fingerprint of a node's attachment: file + both edge sets.

    Edge tuples are sorted but duplicates are retained, so a lost or
    duplicated edge changes the signature. ``assertion_targets`` is part of
    the fingerprint: a replayed VALIDATES edge that comes back without its
    per-assertion targets is a lossy undo, and this signature must catch it.
    """
    file_node = node.file_node()
    return {
        "file_id": file_node.id if file_node is not None else None,
        "incoming": sorted(
            (e.source.id, e.kind.value, tuple(e.assertion_targets or ()))
            for e in node.iter_incoming_edges()
        ),
        "outgoing": sorted(
            (e.target.id, e.kind.value, tuple(e.assertion_targets or ()))
            for e in node.iter_outgoing_edges()
        ),
    }


class TestUndoDeleteJourneyRestoresAttachment:
    """Validates REQ-o00062-G: undoing delete_journey SHALL reverse the mutation.

    Reversal means the journey comes back *attached* -- restoring index
    membership alone leaves it orphaned (no FILE parent, zero edges), so it
    renders into no file and the next save silently drops it.
    """

    def test_undo_restores_file_parent_and_edge_counts_reqo00062g(self, journey_graph_from_disk):
        journey = journey_graph_from_disk.find_by_id(CANONICAL_JOURNEY_ID)
        before = _edge_signature(journey)
        # Guard: the canonical fixture journey must actually be attached,
        # otherwise the round-trip below would compare orphan to orphan.
        assert before["file_id"] == make_file_id(CANONICAL_NAMESPACE, "spec/journeys.md")
        assert before["incoming"] and before["outgoing"]

        journey_graph_from_disk.delete_journey(CANONICAL_JOURNEY_ID)
        assert journey_graph_from_disk.find_by_id(CANONICAL_JOURNEY_ID) is None

        journey_graph_from_disk.undo_last()
        restored = journey_graph_from_disk.find_by_id(CANONICAL_JOURNEY_ID)
        assert restored is not None
        assert _edge_signature(restored) == before

    def test_undo_restores_journey_to_rendered_file_reqo00062g(self, journey_graph_from_disk):
        journey = journey_graph_from_disk.find_by_id(CANONICAL_JOURNEY_ID)
        file_node = journey.file_node()
        before_text = render_file(file_node)
        assert "JNY-001: Login Flow" in before_text

        journey_graph_from_disk.delete_journey(CANONICAL_JOURNEY_ID)
        assert "JNY-001: Login Flow" not in render_file(file_node)

        journey_graph_from_disk.undo_last()
        after_text = render_file(file_node)
        # The real consequence: an orphaned journey belongs to no file, so
        # render_file()/render_save() would write the file back without it.
        assert "JNY-001: Login Flow" in after_text
        assert after_text == before_text

    def test_undo_preserves_contains_render_order_reqo00062g(self, journey_graph_from_disk):
        journey = journey_graph_from_disk.find_by_id(CANONICAL_JOURNEY_ID)
        file_node = journey.file_node()
        before_edge = _contains_edge(file_node, CANONICAL_JOURNEY_ID)
        assert before_edge is not None
        before_order = before_edge.metadata.get("render_order")
        assert before_order is not None
        before_position = [
            e.target.id
            for e in sorted(
                (e for e in file_node.iter_outgoing_edges() if e.kind == EdgeKind.CONTAINS),
                key=lambda e: e.metadata.get("render_order", 0.0),
            )
        ].index(CANONICAL_JOURNEY_ID)

        journey_graph_from_disk.delete_journey(CANONICAL_JOURNEY_ID)
        journey_graph_from_disk.undo_last()

        after_edge = _contains_edge(file_node, CANONICAL_JOURNEY_ID)
        assert after_edge is not None
        assert after_edge.metadata.get("render_order") == before_order
        after_position = [
            e.target.id
            for e in sorted(
                (e for e in file_node.iter_outgoing_edges() if e.kind == EdgeKind.CONTAINS),
                key=lambda e: e.metadata.get("render_order", 0.0),
            )
        ].index(CANONICAL_JOURNEY_ID)
        assert after_position == before_position
