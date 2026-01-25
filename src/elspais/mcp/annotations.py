"""
elspais.mcp.annotations - Session-scoped annotation storage.

Provides ephemeral annotations and tags for nodes that persist within
the current session but are not written to files. Useful for tracking
review status, marking nodes for attention, and organizing work.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Set


@dataclass
class Annotation:
    """
    A single annotation on a node.

    Attributes:
        key: The annotation key (e.g., "review_status", "priority")
        value: The annotation value
        created_at: When the annotation was created
        source: Optional source identifier (e.g., "claude", "user")
    """

    key: str
    value: Any
    created_at: datetime = field(default_factory=datetime.now)
    source: Optional[str] = None


@dataclass
class NodeAnnotations:
    """
    All annotations for a single node.

    Attributes:
        node_id: The ID of the annotated node
        annotations: Dict mapping keys to Annotation objects
        tags: Set of tags applied to this node
    """

    node_id: str
    annotations: Dict[str, Annotation] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)


class AnnotationStore:
    """
    Session-scoped storage for node annotations and tags.

    Provides ephemeral annotations that don't modify files, useful for:
    - Tracking review status (e.g., "needs_work", "approved")
    - Flagging nodes for attention (e.g., "flagged-for-review")
    - Adding temporary notes during analysis
    - Organizing work across session

    All data is cleared when the session ends or clear() is called.

    Example usage:
        store = AnnotationStore()
        store.add_annotation("REQ-p00001", "review_status", "needs_work")
        store.add_tag("REQ-p00001", "high-priority")
        store.add_tag("REQ-p00002", "high-priority")

        # Find all high-priority nodes
        high_priority = store.list_tagged("high-priority")
    """

    def __init__(self):
        """Initialize an empty annotation store."""
        self._nodes: Dict[str, NodeAnnotations] = {}
        self._tags_index: Dict[str, Set[str]] = {}  # tag -> set of node_ids
        self._created_at = datetime.now()

    def _get_or_create_node(self, node_id: str) -> NodeAnnotations:
        """Get or create NodeAnnotations for a node ID."""
        if node_id not in self._nodes:
            self._nodes[node_id] = NodeAnnotations(node_id=node_id)
        return self._nodes[node_id]

    def add_annotation(
        self,
        node_id: str,
        key: str,
        value: Any,
        source: Optional[str] = None,
    ) -> Annotation:
        """
        Add or update an annotation on a node.

        If an annotation with the same key exists, it will be replaced.

        Args:
            node_id: The ID of the node to annotate
            key: The annotation key
            value: The annotation value
            source: Optional source identifier

        Returns:
            The created Annotation object
        """
        node = self._get_or_create_node(node_id)
        annotation = Annotation(key=key, value=value, source=source)
        node.annotations[key] = annotation
        return annotation

    def get_annotation(
        self,
        node_id: str,
        key: str,
    ) -> Optional[Any]:
        """
        Get a specific annotation value.

        Args:
            node_id: The ID of the node
            key: The annotation key

        Returns:
            The annotation value, or None if not found
        """
        if node_id not in self._nodes:
            return None
        annotation = self._nodes[node_id].annotations.get(key)
        return annotation.value if annotation else None

    def get_annotations(self, node_id: str) -> Dict[str, Any]:
        """
        Get all annotations for a node.

        Args:
            node_id: The ID of the node

        Returns:
            Dict mapping keys to values
        """
        if node_id not in self._nodes:
            return {}
        return {k: v.value for k, v in self._nodes[node_id].annotations.items()}

    def get_annotations_full(self, node_id: str) -> Dict[str, Annotation]:
        """
        Get all annotation objects for a node (including metadata).

        Args:
            node_id: The ID of the node

        Returns:
            Dict mapping keys to Annotation objects
        """
        if node_id not in self._nodes:
            return {}
        return dict(self._nodes[node_id].annotations)

    def remove_annotation(self, node_id: str, key: str) -> bool:
        """
        Remove a specific annotation from a node.

        Args:
            node_id: The ID of the node
            key: The annotation key to remove

        Returns:
            True if the annotation was removed, False if not found
        """
        if node_id not in self._nodes:
            return False
        if key in self._nodes[node_id].annotations:
            del self._nodes[node_id].annotations[key]
            return True
        return False

    def add_tag(self, node_id: str, tag: str) -> bool:
        """
        Add a tag to a node.

        Tags are lightweight markers for categorizing nodes.

        Args:
            node_id: The ID of the node to tag
            tag: The tag to add

        Returns:
            True if the tag was added, False if already present
        """
        node = self._get_or_create_node(node_id)
        if tag in node.tags:
            return False

        node.tags.add(tag)

        # Update tags index
        if tag not in self._tags_index:
            self._tags_index[tag] = set()
        self._tags_index[tag].add(node_id)

        return True

    def remove_tag(self, node_id: str, tag: str) -> bool:
        """
        Remove a tag from a node.

        Args:
            node_id: The ID of the node
            tag: The tag to remove

        Returns:
            True if the tag was removed, False if not found
        """
        if node_id not in self._nodes:
            return False
        if tag not in self._nodes[node_id].tags:
            return False

        self._nodes[node_id].tags.discard(tag)

        # Update tags index
        if tag in self._tags_index:
            self._tags_index[tag].discard(node_id)

        return True

    def get_tags(self, node_id: str) -> Set[str]:
        """
        Get all tags for a node.

        Args:
            node_id: The ID of the node

        Returns:
            Set of tag names
        """
        if node_id not in self._nodes:
            return set()
        return set(self._nodes[node_id].tags)

    def has_tag(self, node_id: str, tag: str) -> bool:
        """
        Check if a node has a specific tag.

        Args:
            node_id: The ID of the node
            tag: The tag to check

        Returns:
            True if the node has the tag
        """
        if node_id not in self._nodes:
            return False
        return tag in self._nodes[node_id].tags

    def list_tagged(self, tag: str) -> List[str]:
        """
        Get all node IDs with a specific tag.

        Args:
            tag: The tag to search for

        Returns:
            List of node IDs with this tag
        """
        if tag not in self._tags_index:
            return []
        return list(self._tags_index[tag])

    def list_all_tags(self) -> List[str]:
        """
        Get all unique tags in use.

        Returns:
            List of tag names
        """
        return list(self._tags_index.keys())

    def list_annotated_nodes(self) -> List[str]:
        """
        Get all node IDs that have any annotations or tags.

        Returns:
            List of node IDs
        """
        return list(self._nodes.keys())

    def nodes_with_annotation(
        self,
        key: str,
        value: Optional[Any] = None,
    ) -> Iterator[str]:
        """
        Find nodes with a specific annotation.

        Args:
            key: The annotation key to search for
            value: Optional value to match (if None, matches any value)

        Yields:
            Node IDs with matching annotations
        """
        for node_id, node in self._nodes.items():
            if key in node.annotations:
                if value is None or node.annotations[key].value == value:
                    yield node_id

    def clear(self) -> int:
        """
        Clear all annotations and tags.

        Returns:
            Number of nodes that were cleared
        """
        count = len(self._nodes)
        self._nodes.clear()
        self._tags_index.clear()
        return count

    def clear_node(self, node_id: str) -> bool:
        """
        Clear all annotations and tags for a specific node.

        Args:
            node_id: The ID of the node to clear

        Returns:
            True if the node was found and cleared
        """
        if node_id not in self._nodes:
            return False

        # Remove from tags index
        for tag in self._nodes[node_id].tags:
            if tag in self._tags_index:
                self._tags_index[tag].discard(node_id)

        del self._nodes[node_id]
        return True

    def stats(self) -> Dict[str, Any]:
        """
        Get statistics about the annotation store.

        Returns:
            Dict with stats about nodes, annotations, and tags
        """
        total_annotations = sum(
            len(node.annotations) for node in self._nodes.values()
        )
        total_tags = sum(len(node.tags) for node in self._nodes.values())

        return {
            "nodes_with_annotations": len(self._nodes),
            "total_annotations": total_annotations,
            "total_tags": total_tags,
            "unique_tags": len(self._tags_index),
            "created_at": self._created_at.isoformat(),
        }

    def export(self) -> Dict[str, Any]:
        """
        Export all annotations and tags as a dict.

        Useful for debugging or persisting session state.

        Returns:
            Dict with all annotation data
        """
        return {
            "nodes": {
                node_id: {
                    "annotations": {
                        k: {
                            "value": v.value,
                            "created_at": v.created_at.isoformat(),
                            "source": v.source,
                        }
                        for k, v in node.annotations.items()
                    },
                    "tags": list(node.tags),
                }
                for node_id, node in self._nodes.items()
            },
            "stats": self.stats(),
        }
