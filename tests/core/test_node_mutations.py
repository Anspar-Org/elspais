# Validates REQ-o00062-A, REQ-o00062-D, REQ-o00062-E, REQ-o00062-F
"""Tests for node mutation operations (rename, update_title, change_status, add, delete)."""

import pytest

from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.parsers import ParsedContent


def make_req(
    req_id: str,
    title: str = "Test",
    level: str = "PRD",
    status: str = "Active",
    implements: list[str] | None = None,
    assertions: list[dict] | None = None,
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
        end_line=5,
        raw_text=f"## {req_id}: {title}",
    )


def build_simple_graph() -> TraceGraph:
    """Build a simple graph with one requirement."""
    builder = GraphBuilder()
    builder.add_parsed_content(make_req("REQ-p00001", "Test Requirement"))
    return builder.build()


def build_hierarchy_graph() -> TraceGraph:
    """Build a graph with parent-child hierarchy."""
    builder = GraphBuilder()
    builder.add_parsed_content(make_req("REQ-p00001", "Parent"))
    builder.add_parsed_content(make_req("REQ-p00002", "Child", implements=["REQ-p00001"]))
    return builder.build()


def build_graph_with_assertions() -> TraceGraph:
    """Build a graph with a requirement that has assertions."""
    builder = GraphBuilder()
    builder.add_parsed_content(
        make_req(
            "REQ-p00001",
            "Requirement with Assertions",
            assertions=[
                {"label": "A", "text": "First assertion"},
                {"label": "B", "text": "Second assertion"},
            ],
        )
    )
    return builder.build()


class TestRenameNode:
    """Tests for TraceGraph.rename_node()."""

    def test_REQ_o00062_A_rename_node_updates_id_and_index(self):
        """REQ-o00062-A: Basic rename updates node ID and index."""
        graph = build_simple_graph()

        entry = graph.rename_node("REQ-p00001", "REQ-p00099")

        assert entry.operation == "rename_node"
        assert entry.target_id == "REQ-p00001"
        assert entry.before_state["id"] == "REQ-p00001"
        assert entry.after_state["id"] == "REQ-p00099"

        # Node should be findable by new ID only
        assert graph.find_by_id("REQ-p00001") is None
        assert graph.find_by_id("REQ-p00099") is not None
        assert graph.find_by_id("REQ-p00099").id == "REQ-p00099"

    def test_rename_not_found(self):
        """Renaming non-existent node raises KeyError."""
        graph = build_simple_graph()

        with pytest.raises(KeyError, match="not found"):
            graph.rename_node("REQ-nonexistent", "REQ-p00099")

    def test_rename_conflict(self):
        """Renaming to existing ID raises ValueError."""
        graph = build_hierarchy_graph()

        with pytest.raises(ValueError, match="already exists"):
            graph.rename_node("REQ-p00001", "REQ-p00002")

    def test_rename_updates_assertions(self):
        """Renaming a requirement also updates its assertion IDs."""
        graph = build_graph_with_assertions()

        # Before rename
        assert graph.find_by_id("REQ-p00001-A") is not None
        assert graph.find_by_id("REQ-p00001-B") is not None

        graph.rename_node("REQ-p00001", "REQ-p00099")

        # After rename - old assertion IDs gone
        assert graph.find_by_id("REQ-p00001-A") is None
        assert graph.find_by_id("REQ-p00001-B") is None

        # New assertion IDs exist
        assert graph.find_by_id("REQ-p00099-A") is not None
        assert graph.find_by_id("REQ-p00099-B") is not None

    def test_rename_preserves_title(self):
        """Renaming preserves the node's title."""
        graph = build_simple_graph()
        node = graph.find_by_id("REQ-p00001")
        original_title = node.get_label()

        graph.rename_node("REQ-p00001", "REQ-p00099")

        renamed = graph.find_by_id("REQ-p00099")
        assert renamed.get_label() == original_title

    def test_rename_logs_mutation(self):
        """Rename operation is logged."""
        graph = build_simple_graph()
        assert len(graph.mutation_log) == 0

        graph.rename_node("REQ-p00001", "REQ-p00099")

        assert len(graph.mutation_log) == 1
        entry = graph.mutation_log.last()
        assert entry.operation == "rename_node"

    def test_rename_undo(self):
        """Undo restores original node ID."""
        graph = build_simple_graph()

        graph.rename_node("REQ-p00001", "REQ-p00099")
        assert graph.find_by_id("REQ-p00001") is None

        graph.undo_last()

        assert graph.find_by_id("REQ-p00001") is not None
        assert graph.find_by_id("REQ-p00099") is None


class TestUpdateTitle:
    """Tests for TraceGraph.update_title()."""

    def test_REQ_o00062_A_update_title_changes_field(self):
        """REQ-o00062-A: Basic title update works."""
        graph = build_simple_graph()

        entry = graph.update_title("REQ-p00001", "New Title")

        assert entry.operation == "update_title"
        assert entry.before_state["title"] == "Test Requirement"
        assert entry.after_state["title"] == "New Title"

        node = graph.find_by_id("REQ-p00001")
        assert node.get_label() == "New Title"

    def test_update_title_not_found(self):
        """Updating title of non-existent node raises KeyError."""
        graph = build_simple_graph()

        with pytest.raises(KeyError, match="not found"):
            graph.update_title("REQ-nonexistent", "New Title")

    def test_update_title_logs_mutation(self):
        """Title update is logged."""
        graph = build_simple_graph()

        graph.update_title("REQ-p00001", "New Title")

        assert len(graph.mutation_log) == 1
        entry = graph.mutation_log.last()
        assert entry.operation == "update_title"

    def test_update_title_undo(self):
        """Undo restores original title."""
        graph = build_simple_graph()
        original = graph.find_by_id("REQ-p00001").get_label()

        graph.update_title("REQ-p00001", "New Title")
        assert graph.find_by_id("REQ-p00001").get_label() == "New Title"

        graph.undo_last()
        assert graph.find_by_id("REQ-p00001").get_label() == original


class TestChangeStatus:
    """Tests for TraceGraph.change_status()."""

    def test_REQ_o00062_A_change_status_updates_field(self):
        """REQ-o00062-A: Basic status change works."""
        graph = build_simple_graph()

        entry = graph.change_status("REQ-p00001", "Deprecated")

        assert entry.operation == "change_status"
        assert entry.before_state["status"] == "Active"
        assert entry.after_state["status"] == "Deprecated"

        node = graph.find_by_id("REQ-p00001")
        assert node.get_field("status") == "Deprecated"

    def test_change_status_not_found(self):
        """Changing status of non-existent node raises KeyError."""
        graph = build_simple_graph()

        with pytest.raises(KeyError, match="not found"):
            graph.change_status("REQ-nonexistent", "Active")

    def test_change_status_logs_mutation(self):
        """Status change is logged."""
        graph = build_simple_graph()

        graph.change_status("REQ-p00001", "Draft")

        assert len(graph.mutation_log) == 1
        entry = graph.mutation_log.last()
        assert entry.operation == "change_status"

    def test_change_status_undo(self):
        """Undo restores original status."""
        graph = build_simple_graph()

        graph.change_status("REQ-p00001", "Deprecated")
        assert graph.find_by_id("REQ-p00001").get_field("status") == "Deprecated"

        graph.undo_last()
        assert graph.find_by_id("REQ-p00001").get_field("status") == "Active"


class TestAddRequirement:
    """Tests for TraceGraph.add_requirement()."""

    def test_REQ_o00062_A_add_requirement_creates_node(self):
        """REQ-o00062-A: Basic add creates a new node."""
        graph = build_simple_graph()

        entry = graph.add_requirement(
            req_id="REQ-p00099",
            title="New Requirement",
            level="DEV",
        )

        assert entry.operation == "add_requirement"
        assert entry.target_id == "REQ-p00099"

        node = graph.find_by_id("REQ-p00099")
        assert node is not None
        assert node.get_label() == "New Requirement"
        assert node.get_field("level") == "DEV"
        assert node.get_field("status") == "Draft"  # Default

    def test_add_requirement_with_parent(self):
        """Add with parent creates linked node."""
        graph = build_simple_graph()

        graph.add_requirement(
            req_id="REQ-p00099",
            title="Child Requirement",
            level="OPS",
            parent_id="REQ-p00001",
        )

        parent = graph.find_by_id("REQ-p00001")
        child = graph.find_by_id("REQ-p00099")

        assert child is not None
        assert parent.has_child(child)
        assert child.has_parent(parent)

    def test_add_requirement_with_custom_status(self):
        """Add can specify custom status."""
        graph = build_simple_graph()

        graph.add_requirement(
            req_id="REQ-p00099",
            title="Active Req",
            level="PRD",
            status="Active",
        )

        node = graph.find_by_id("REQ-p00099")
        assert node.get_field("status") == "Active"

    def test_add_requirement_computes_hash(self):
        """Add computes an initial hash."""
        graph = build_simple_graph()

        graph.add_requirement(
            req_id="REQ-p00099",
            title="Hashed Req",
            level="PRD",
        )

        node = graph.find_by_id("REQ-p00099")
        assert node.get_field("hash") is not None
        assert len(node.get_field("hash")) == 8  # 8-char hash

    def test_add_requirement_duplicate_raises(self):
        """Adding duplicate ID raises ValueError."""
        graph = build_simple_graph()

        with pytest.raises(ValueError, match="already exists"):
            graph.add_requirement(
                req_id="REQ-p00001",
                title="Duplicate",
                level="PRD",
            )

    def test_add_requirement_missing_parent_raises(self):
        """Adding with non-existent parent raises KeyError."""
        graph = build_simple_graph()

        with pytest.raises(KeyError, match="not found"):
            graph.add_requirement(
                req_id="REQ-p00099",
                title="Orphan",
                level="PRD",
                parent_id="REQ-nonexistent",
            )

    def test_add_requirement_logs_mutation(self):
        """Add operation is logged."""
        graph = build_simple_graph()

        graph.add_requirement(
            req_id="REQ-p00099",
            title="Logged",
            level="PRD",
        )

        assert len(graph.mutation_log) == 1
        entry = graph.mutation_log.last()
        assert entry.operation == "add_requirement"

    def test_add_requirement_undo(self):
        """Undo removes the added node."""
        graph = build_simple_graph()
        original_count = graph.node_count()

        graph.add_requirement(
            req_id="REQ-p00099",
            title="Temporary",
            level="PRD",
        )
        assert graph.find_by_id("REQ-p00099") is not None

        graph.undo_last()

        assert graph.find_by_id("REQ-p00099") is None
        assert graph.node_count() == original_count

    def test_add_requirement_without_parent_becomes_root(self):
        """Adding without parent makes node a root."""
        graph = build_simple_graph()
        original_root_count = graph.root_count()

        graph.add_requirement(
            req_id="REQ-p00099",
            title="New Root",
            level="PRD",
        )

        assert graph.root_count() == original_root_count + 1
        assert graph.has_root("REQ-p00099")


class TestDeleteRequirement:
    """Tests for TraceGraph.delete_requirement()."""

    def test_REQ_o00062_A_delete_requirement_removes_node(self):
        """REQ-o00062-A: Basic delete removes node from index."""
        graph = build_simple_graph()

        entry = graph.delete_requirement("REQ-p00001")

        assert entry.operation == "delete_requirement"
        assert entry.target_id == "REQ-p00001"
        assert graph.find_by_id("REQ-p00001") is None

    def test_delete_requirement_not_found(self):
        """Deleting non-existent node raises KeyError."""
        graph = build_simple_graph()

        with pytest.raises(KeyError, match="not found"):
            graph.delete_requirement("REQ-nonexistent")

    def test_delete_requirement_preserves_in_deleted_nodes(self):
        """Deleted node is preserved in _deleted_nodes."""
        graph = build_simple_graph()

        graph.delete_requirement("REQ-p00001")

        assert graph.has_deletions()
        deleted = graph.deleted_nodes()
        assert len(deleted) == 1
        assert deleted[0].id == "REQ-p00001"

    def test_delete_requirement_removes_from_roots(self):
        """Deleting a root removes it from roots list."""
        graph = build_simple_graph()
        assert graph.has_root("REQ-p00001")

        graph.delete_requirement("REQ-p00001")

        assert not graph.has_root("REQ-p00001")

    def test_delete_requirement_orphans_children(self):
        """Deleting a parent orphans its non-assertion children."""
        graph = build_hierarchy_graph()

        graph.delete_requirement("REQ-p00001")

        # Child should now be an orphan
        assert "REQ-p00002" in graph._orphaned_ids

    def test_delete_requirement_deletes_assertions(self):
        """Deleting a requirement also deletes its assertions."""
        graph = build_graph_with_assertions()

        assert graph.find_by_id("REQ-p00001-A") is not None
        assert graph.find_by_id("REQ-p00001-B") is not None

        graph.delete_requirement("REQ-p00001")

        assert graph.find_by_id("REQ-p00001-A") is None
        assert graph.find_by_id("REQ-p00001-B") is None

        # Assertions should also be in deleted_nodes
        deleted = graph.deleted_nodes()
        deleted_ids = {n.id for n in deleted}
        assert "REQ-p00001-A" in deleted_ids
        assert "REQ-p00001-B" in deleted_ids

    def test_delete_requirement_logs_mutation(self):
        """Delete operation is logged."""
        graph = build_simple_graph()

        graph.delete_requirement("REQ-p00001")

        assert len(graph.mutation_log) == 1
        entry = graph.mutation_log.last()
        assert entry.operation == "delete_requirement"

    def test_delete_requirement_undo(self):
        """Undo restores the deleted node."""
        graph = build_simple_graph()
        original_label = graph.find_by_id("REQ-p00001").get_label()

        graph.delete_requirement("REQ-p00001")
        assert graph.find_by_id("REQ-p00001") is None

        graph.undo_last()

        node = graph.find_by_id("REQ-p00001")
        assert node is not None
        assert node.get_label() == original_label

    def test_delete_records_before_state(self):
        """Delete entry records full before state for undo."""
        graph = build_simple_graph()

        entry = graph.delete_requirement("REQ-p00001")

        assert "title" in entry.before_state
        assert "level" in entry.before_state
        assert "status" in entry.before_state
        assert "was_root" in entry.before_state


class TestMultipleMutations:
    """Tests for sequences of mutations."""

    def test_multiple_mutations_logged(self):
        """Multiple mutations are all logged in order."""
        graph = build_simple_graph()

        graph.update_title("REQ-p00001", "Title 1")
        graph.update_title("REQ-p00001", "Title 2")
        graph.change_status("REQ-p00001", "Deprecated")

        assert len(graph.mutation_log) == 3
        entries = list(graph.mutation_log.iter_entries())
        assert entries[0].operation == "update_title"
        assert entries[1].operation == "update_title"
        assert entries[2].operation == "change_status"

    def test_undo_multiple_in_reverse(self):
        """Multiple undos reverse operations in order."""
        graph = build_simple_graph()

        graph.update_title("REQ-p00001", "Title 1")
        graph.update_title("REQ-p00001", "Title 2")

        graph.undo_last()  # Undo Title 2
        assert graph.find_by_id("REQ-p00001").get_label() == "Title 1"

        graph.undo_last()  # Undo Title 1
        assert graph.find_by_id("REQ-p00001").get_label() == "Test Requirement"

    def test_undo_to_specific_mutation(self):
        """undo_to reverts to specific point in history."""
        graph = build_simple_graph()

        entry1 = graph.update_title("REQ-p00001", "Title 1")
        graph.update_title("REQ-p00001", "Title 2")
        graph.update_title("REQ-p00001", "Title 3")

        assert len(graph.mutation_log) == 3

        # Undo back to (and including) entry1
        undone = graph.undo_to(entry1.id)

        assert len(undone) == 3
        assert len(graph.mutation_log) == 0
        assert graph.find_by_id("REQ-p00001").get_label() == "Test Requirement"
