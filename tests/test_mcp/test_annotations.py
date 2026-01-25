"""
Tests for elspais.mcp.annotations module.
"""

import pytest
from datetime import datetime


class TestAnnotationStore:
    """Tests for AnnotationStore."""

    def test_create_store(self):
        """Test creating an annotation store."""
        from elspais.mcp.annotations import AnnotationStore

        store = AnnotationStore()
        assert store._nodes == {}
        assert store._tags_index == {}

    def test_add_annotation(self):
        """Test adding an annotation."""
        from elspais.mcp.annotations import AnnotationStore

        store = AnnotationStore()
        annotation = store.add_annotation(
            "REQ-p00001",
            "review_status",
            "needs_work",
            source="claude",
        )

        assert annotation.key == "review_status"
        assert annotation.value == "needs_work"
        assert annotation.source == "claude"
        assert isinstance(annotation.created_at, datetime)

    def test_get_annotation(self):
        """Test getting a specific annotation."""
        from elspais.mcp.annotations import AnnotationStore

        store = AnnotationStore()
        store.add_annotation("REQ-p00001", "priority", "high")

        value = store.get_annotation("REQ-p00001", "priority")
        assert value == "high"

        # Non-existent annotation
        value = store.get_annotation("REQ-p00001", "nonexistent")
        assert value is None

        # Non-existent node
        value = store.get_annotation("REQ-p99999", "priority")
        assert value is None

    def test_get_annotations(self):
        """Test getting all annotations for a node."""
        from elspais.mcp.annotations import AnnotationStore

        store = AnnotationStore()
        store.add_annotation("REQ-p00001", "priority", "high")
        store.add_annotation("REQ-p00001", "status", "in_review")

        annotations = store.get_annotations("REQ-p00001")
        assert annotations == {"priority": "high", "status": "in_review"}

        # Non-existent node
        annotations = store.get_annotations("REQ-p99999")
        assert annotations == {}

    def test_update_annotation(self):
        """Test that adding an annotation with same key updates it."""
        from elspais.mcp.annotations import AnnotationStore

        store = AnnotationStore()
        store.add_annotation("REQ-p00001", "priority", "low")
        store.add_annotation("REQ-p00001", "priority", "high")

        value = store.get_annotation("REQ-p00001", "priority")
        assert value == "high"

    def test_remove_annotation(self):
        """Test removing an annotation."""
        from elspais.mcp.annotations import AnnotationStore

        store = AnnotationStore()
        store.add_annotation("REQ-p00001", "priority", "high")

        removed = store.remove_annotation("REQ-p00001", "priority")
        assert removed is True
        assert store.get_annotation("REQ-p00001", "priority") is None

        # Removing non-existent
        removed = store.remove_annotation("REQ-p00001", "priority")
        assert removed is False

    def test_add_tag(self):
        """Test adding a tag."""
        from elspais.mcp.annotations import AnnotationStore

        store = AnnotationStore()
        added = store.add_tag("REQ-p00001", "high-priority")

        assert added is True
        assert store.has_tag("REQ-p00001", "high-priority")

        # Adding same tag again
        added = store.add_tag("REQ-p00001", "high-priority")
        assert added is False

    def test_remove_tag(self):
        """Test removing a tag."""
        from elspais.mcp.annotations import AnnotationStore

        store = AnnotationStore()
        store.add_tag("REQ-p00001", "high-priority")

        removed = store.remove_tag("REQ-p00001", "high-priority")
        assert removed is True
        assert not store.has_tag("REQ-p00001", "high-priority")

        # Removing non-existent
        removed = store.remove_tag("REQ-p00001", "high-priority")
        assert removed is False

    def test_get_tags(self):
        """Test getting all tags for a node."""
        from elspais.mcp.annotations import AnnotationStore

        store = AnnotationStore()
        store.add_tag("REQ-p00001", "high-priority")
        store.add_tag("REQ-p00001", "needs-review")

        tags = store.get_tags("REQ-p00001")
        assert tags == {"high-priority", "needs-review"}

        # Non-existent node
        tags = store.get_tags("REQ-p99999")
        assert tags == set()

    def test_list_tagged(self):
        """Test finding nodes by tag."""
        from elspais.mcp.annotations import AnnotationStore

        store = AnnotationStore()
        store.add_tag("REQ-p00001", "high-priority")
        store.add_tag("REQ-p00002", "high-priority")
        store.add_tag("REQ-p00003", "low-priority")

        nodes = store.list_tagged("high-priority")
        assert set(nodes) == {"REQ-p00001", "REQ-p00002"}

        nodes = store.list_tagged("nonexistent")
        assert nodes == []

    def test_list_all_tags(self):
        """Test listing all unique tags."""
        from elspais.mcp.annotations import AnnotationStore

        store = AnnotationStore()
        store.add_tag("REQ-p00001", "high-priority")
        store.add_tag("REQ-p00002", "needs-review")
        store.add_tag("REQ-p00003", "high-priority")

        tags = store.list_all_tags()
        assert set(tags) == {"high-priority", "needs-review"}

    def test_nodes_with_annotation(self):
        """Test finding nodes by annotation."""
        from elspais.mcp.annotations import AnnotationStore

        store = AnnotationStore()
        store.add_annotation("REQ-p00001", "priority", "high")
        store.add_annotation("REQ-p00002", "priority", "low")
        store.add_annotation("REQ-p00003", "priority", "high")

        # Find by key only
        nodes = list(store.nodes_with_annotation("priority"))
        assert set(nodes) == {"REQ-p00001", "REQ-p00002", "REQ-p00003"}

        # Find by key and value
        nodes = list(store.nodes_with_annotation("priority", "high"))
        assert set(nodes) == {"REQ-p00001", "REQ-p00003"}

    def test_clear(self):
        """Test clearing all annotations."""
        from elspais.mcp.annotations import AnnotationStore

        store = AnnotationStore()
        store.add_annotation("REQ-p00001", "priority", "high")
        store.add_tag("REQ-p00002", "flagged")

        count = store.clear()
        assert count == 2
        assert store._nodes == {}
        assert store._tags_index == {}

    def test_clear_node(self):
        """Test clearing annotations for a specific node."""
        from elspais.mcp.annotations import AnnotationStore

        store = AnnotationStore()
        store.add_annotation("REQ-p00001", "priority", "high")
        store.add_tag("REQ-p00001", "flagged")
        store.add_annotation("REQ-p00002", "priority", "low")

        cleared = store.clear_node("REQ-p00001")
        assert cleared is True
        assert store.get_annotation("REQ-p00001", "priority") is None
        assert not store.has_tag("REQ-p00001", "flagged")
        # Other node unaffected
        assert store.get_annotation("REQ-p00002", "priority") == "low"

    def test_stats(self):
        """Test getting statistics."""
        from elspais.mcp.annotations import AnnotationStore

        store = AnnotationStore()
        store.add_annotation("REQ-p00001", "priority", "high")
        store.add_annotation("REQ-p00001", "status", "in_review")
        store.add_tag("REQ-p00001", "flagged")
        store.add_tag("REQ-p00002", "flagged")

        stats = store.stats()
        assert stats["nodes_with_annotations"] == 2
        assert stats["total_annotations"] == 2
        assert stats["total_tags"] == 2
        assert stats["unique_tags"] == 1
        assert "created_at" in stats

    def test_export(self):
        """Test exporting all data."""
        from elspais.mcp.annotations import AnnotationStore

        store = AnnotationStore()
        store.add_annotation("REQ-p00001", "priority", "high")
        store.add_tag("REQ-p00001", "flagged")

        data = store.export()
        assert "nodes" in data
        assert "REQ-p00001" in data["nodes"]
        assert data["nodes"]["REQ-p00001"]["annotations"]["priority"]["value"] == "high"
        assert "flagged" in data["nodes"]["REQ-p00001"]["tags"]
        assert "stats" in data


class TestAnnotation:
    """Tests for Annotation dataclass."""

    def test_annotation_creation(self):
        """Test creating an Annotation."""
        from elspais.mcp.annotations import Annotation

        annotation = Annotation(
            key="review_status",
            value="approved",
            source="user",
        )

        assert annotation.key == "review_status"
        assert annotation.value == "approved"
        assert annotation.source == "user"
        assert isinstance(annotation.created_at, datetime)

    def test_annotation_complex_value(self):
        """Test annotation with complex value."""
        from elspais.mcp.annotations import Annotation

        annotation = Annotation(
            key="metadata",
            value={"items": [1, 2, 3], "name": "test"},
        )

        assert annotation.value == {"items": [1, 2, 3], "name": "test"}
