# Implements: REQ-p00006
"""Tests for journey mutation operations."""

import pytest

from elspais.graph import NodeKind
from tests.core.graph_test_helpers import (
    build_graph,
    make_journey,
    make_requirement,
)


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
        file_node = graph.find_by_id("file:spec/journeys.md")
        assert file_node is not None
        entry = graph.add_journey("JNY-SIGNUP-01", "User Signup", "file:spec/journeys.md")
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
            graph.add_journey("JNY-LOGIN-01", "Duplicate", "file:spec/journeys.md")

    def test_add_journey_file_not_found_raises(self):
        graph = build_journey_graph()
        with pytest.raises(KeyError, match="not found"):
            graph.add_journey("JNY-NEW-01", "New", "file:nonexistent.md")

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
        assert "*End* *JNY-LOGIN-01*" in body

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
        graph.add_journey("JNY-NEW-01", "New", "file:spec/journeys.md")
        assert graph.find_by_id("JNY-NEW-01") is not None
        graph.undo_last()
        assert graph.find_by_id("JNY-NEW-01") is None

    def test_undo_delete_journey(self):
        graph = build_journey_graph()
        graph.delete_journey("JNY-LOGIN-01")
        assert graph.find_by_id("JNY-LOGIN-01") is None
        graph.undo_last()
        assert graph.find_by_id("JNY-LOGIN-01") is not None
