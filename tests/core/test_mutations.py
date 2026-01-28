"""Tests for mutation infrastructure (MutationEntry, MutationLog, undo)."""

import pytest
from datetime import datetime

from elspais.graph import MutationEntry, MutationLog
from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.parsers import ParsedContent


def make_req(
    req_id: str,
    title: str = "Test",
    level: str = "PRD",
    implements: list[str] | None = None,
) -> ParsedContent:
    """Helper to create a requirement ParsedContent."""
    return ParsedContent(
        content_type="requirement",
        parsed_data={
            "id": req_id,
            "title": title,
            "level": level,
            "status": "Active",
            "assertions": [],
            "implements": implements or [],
            "refines": [],
        },
        start_line=1,
        end_line=5,
        raw_text=f"## {req_id}: {title}",
    )


class TestMutationEntry:
    """Tests for MutationEntry dataclass."""

    def test_create_entry(self):
        """MutationEntry can be created with required fields."""
        entry = MutationEntry(
            operation="rename_node",
            target_id="REQ-p00001",
            before_state={"id": "REQ-p00001"},
            after_state={"id": "REQ-p00002"},
        )

        assert entry.operation == "rename_node"
        assert entry.target_id == "REQ-p00001"
        assert entry.before_state == {"id": "REQ-p00001"}
        assert entry.after_state == {"id": "REQ-p00002"}
        assert entry.affects_hash is False
        assert entry.id  # Should have auto-generated ID
        assert entry.timestamp  # Should have auto-generated timestamp

    def test_entry_with_affects_hash(self):
        """MutationEntry tracks hash-affecting operations."""
        entry = MutationEntry(
            operation="update_assertion",
            target_id="REQ-p00001-A",
            before_state={"text": "Old text"},
            after_state={"text": "New text"},
            affects_hash=True,
        )

        assert entry.affects_hash is True

    def test_entry_str(self):
        """MutationEntry has readable string representation."""
        entry = MutationEntry(
            operation="rename_node",
            target_id="REQ-p00001",
            before_state={},
            after_state={},
        )
        s = str(entry)
        assert "rename_node" in s
        assert "REQ-p00001" in s

    def test_entry_unique_ids(self):
        """Each MutationEntry gets a unique ID."""
        entry1 = MutationEntry(
            operation="test",
            target_id="A",
            before_state={},
            after_state={},
        )
        entry2 = MutationEntry(
            operation="test",
            target_id="A",
            before_state={},
            after_state={},
        )

        assert entry1.id != entry2.id


class TestMutationLog:
    """Tests for MutationLog class."""

    def test_empty_log(self):
        """New MutationLog is empty."""
        log = MutationLog()
        assert len(log) == 0
        assert log.last() is None
        assert list(log.iter_entries()) == []

    def test_append_and_iterate(self):
        """Entries can be appended and iterated."""
        log = MutationLog()
        entry1 = MutationEntry(
            operation="op1",
            target_id="A",
            before_state={},
            after_state={},
        )
        entry2 = MutationEntry(
            operation="op2",
            target_id="B",
            before_state={},
            after_state={},
        )

        log.append(entry1)
        log.append(entry2)

        assert len(log) == 2
        entries = list(log.iter_entries())
        assert entries == [entry1, entry2]

    def test_last(self):
        """last() returns most recent entry."""
        log = MutationLog()
        entry1 = MutationEntry(
            operation="first",
            target_id="A",
            before_state={},
            after_state={},
        )
        entry2 = MutationEntry(
            operation="second",
            target_id="B",
            before_state={},
            after_state={},
        )

        log.append(entry1)
        assert log.last() == entry1

        log.append(entry2)
        assert log.last() == entry2

    def test_find_by_id(self):
        """find_by_id locates entry by mutation ID."""
        log = MutationLog()
        entry = MutationEntry(
            operation="test",
            target_id="A",
            before_state={},
            after_state={},
        )
        log.append(entry)

        found = log.find_by_id(entry.id)
        assert found == entry

        not_found = log.find_by_id("nonexistent")
        assert not_found is None

    def test_entries_since(self):
        """entries_since returns entries from specified ID."""
        log = MutationLog()
        entries = [
            MutationEntry(operation=f"op{i}", target_id=str(i), before_state={}, after_state={})
            for i in range(5)
        ]
        for e in entries:
            log.append(e)

        # Get entries starting from index 2
        since = log.entries_since(entries[2].id)
        assert len(since) == 3
        assert since[0] == entries[2]
        assert since[-1] == entries[4]

    def test_entries_since_not_found(self):
        """entries_since raises ValueError for unknown ID."""
        log = MutationLog()
        with pytest.raises(ValueError, match="not found"):
            log.entries_since("nonexistent")

    def test_pop(self):
        """pop() removes and returns last entry."""
        log = MutationLog()
        entry1 = MutationEntry(
            operation="first",
            target_id="A",
            before_state={},
            after_state={},
        )
        entry2 = MutationEntry(
            operation="second",
            target_id="B",
            before_state={},
            after_state={},
        )

        log.append(entry1)
        log.append(entry2)

        popped = log.pop()
        assert popped == entry2
        assert len(log) == 1
        assert log.last() == entry1

        popped = log.pop()
        assert popped == entry1
        assert len(log) == 0

        popped = log.pop()
        assert popped is None

    def test_clear(self):
        """clear() removes all entries."""
        log = MutationLog()
        for i in range(3):
            log.append(
                MutationEntry(operation=f"op{i}", target_id=str(i), before_state={}, after_state={})
            )

        assert len(log) == 3
        log.clear()
        assert len(log) == 0


class TestTraceGraphMutationInfrastructure:
    """Tests for TraceGraph mutation infrastructure."""

    def test_graph_has_mutation_log(self):
        """TraceGraph has a mutation log."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_req("REQ-p00001"))
        graph = builder.build()

        assert hasattr(graph, 'mutation_log')
        assert isinstance(graph.mutation_log, MutationLog)
        assert len(graph.mutation_log) == 0

    def test_graph_deleted_nodes_empty(self):
        """New graph has no deleted nodes."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_req("REQ-p00001"))
        graph = builder.build()

        assert graph.deleted_nodes() == []
        assert graph.has_deletions() is False

    def test_undo_last_empty(self):
        """undo_last on empty log returns None."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_req("REQ-p00001"))
        graph = builder.build()

        result = graph.undo_last()
        assert result is None


class TestUndoRenameNode:
    """Tests for undo of rename_node operations."""

    def test_undo_rename_restores_id(self):
        """Undoing rename restores original node ID."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_req("REQ-p00001", "Test Req"))
        graph = builder.build()

        # Simulate a rename mutation
        node = graph.find_by_id("REQ-p00001")
        assert node is not None

        # Manually perform rename and log it
        old_id = node.id
        new_id = "REQ-p00002"

        entry = MutationEntry(
            operation="rename_node",
            target_id=old_id,
            before_state={"id": old_id},
            after_state={"id": new_id},
        )

        # Apply the rename
        graph._index.pop(old_id)
        node._id = new_id
        graph._index[new_id] = node
        graph._mutation_log.append(entry)

        # Verify rename worked
        assert graph.find_by_id("REQ-p00001") is None
        assert graph.find_by_id("REQ-p00002") is not None

        # Undo the rename
        undone = graph.undo_last()
        assert undone == entry

        # Verify undo worked
        assert graph.find_by_id("REQ-p00001") is not None
        assert graph.find_by_id("REQ-p00002") is None


class TestUndoUpdateTitle:
    """Tests for undo of update_title operations."""

    def test_undo_title_restores_original(self):
        """Undoing title update restores original title."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_req("REQ-p00001", "Original Title"))
        graph = builder.build()

        node = graph.find_by_id("REQ-p00001")
        assert node.label == "Original Title"

        # Simulate title update
        entry = MutationEntry(
            operation="update_title",
            target_id="REQ-p00001",
            before_state={"title": "Original Title"},
            after_state={"title": "New Title"},
        )
        node.label = "New Title"
        graph._mutation_log.append(entry)

        assert node.label == "New Title"

        # Undo
        graph.undo_last()
        assert node.label == "Original Title"


class TestUndoTo:
    """Tests for undo_to batch undo operations."""

    def test_undo_to_multiple(self):
        """undo_to undoes multiple mutations in reverse order."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_req("REQ-p00001", "Title1"))
        graph = builder.build()

        node = graph.find_by_id("REQ-p00001")

        # Make multiple title changes
        entries = []
        for i in range(3):
            old_title = node.label
            new_title = f"Title{i+2}"
            entry = MutationEntry(
                operation="update_title",
                target_id="REQ-p00001",
                before_state={"title": old_title},
                after_state={"title": new_title},
            )
            node.label = new_title
            graph._mutation_log.append(entry)
            entries.append(entry)

        assert node.label == "Title4"
        assert len(graph.mutation_log) == 3

        # Undo back to the first mutation
        undone = graph.undo_to(entries[0].id)
        assert len(undone) == 3
        assert node.label == "Title1"
        assert len(graph.mutation_log) == 0
