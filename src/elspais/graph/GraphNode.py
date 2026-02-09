# Implements: REQ-p00050-A, REQ-p00050-C
"""GraphNode - Unified node representation for traceability graph.

This module provides the core data structures for Architecture 3.0:
- NodeKind: Enum of node types
- SourceLocation: Portable file location reference
- GraphNode: Unified node with typed content and edge management
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import InitVar, dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from elspais.graph.relations import Edge, EdgeKind


class NodeKind(Enum):
    """Types of nodes in the traceability graph."""

    REQUIREMENT = "requirement"
    ASSERTION = "assertion"
    CODE = "code"
    TEST = "test"
    TEST_RESULT = "result"
    USER_JOURNEY = "journey"
    REMAINDER = "remainder"


@dataclass
class SourceLocation:
    """Portable reference to a location in a file.

    Paths are stored relative to the repository root, enabling
    consistent references across different working directories.
    """

    path: str  # Relative to repo root
    line: int  # 1-based line number
    end_line: int | None = None
    repo: str | None = None  # For multi-repo: "CAL", None = core

    def absolute(self, repo_root: Path) -> Path:
        """Resolve to absolute path."""
        return repo_root / self.path

    def __str__(self) -> str:
        """Return string representation for display."""
        if self.repo:
            return f"{self.repo}:{self.path}:{self.line}"
        return f"{self.path}:{self.line}"


@dataclass
class GraphNode:
    """A node in the traceability graph.

    GraphNode is the unified representation for all entities in the
    traceability graph. The `kind` field determines the expected
    structure of `content`.

    Attributes:
        id: Unique identifier for this node (mutable via set_id()).
        kind: The type of node (requirement, assertion, etc.).
        source: Where this node is defined in source files.
        uuid: Stable 32-char hex string for GUI/DOM referencing.

    Use get_label()/set_label() for label access.
    Use set_id() for ID mutations.
    """

    id: str
    kind: NodeKind
    label: InitVar[str] = ""  # Constructor parameter, stored in _label
    source: SourceLocation | None = None
    uuid: str = field(default_factory=lambda: uuid4().hex)

    # Label stored internally - use get_label()/set_label() or label property
    _label: str = field(default="", init=False)

    # Internal storage (prefixed) - excluded from constructor
    _children: list[GraphNode] = field(default_factory=list, init=False)
    _parents: list[GraphNode] = field(default_factory=list, init=False, repr=False)
    _outgoing_edges: list[Edge] = field(default_factory=list, init=False, repr=False)
    _incoming_edges: list[Edge] = field(default_factory=list, init=False, repr=False)
    _content: dict[str, Any] = field(default_factory=dict, init=False)
    _metrics: dict[str, Any] = field(default_factory=dict, init=False)

    def __post_init__(self, label: str) -> None:
        """Initialize internal label from constructor parameter."""
        self._label = label

    def set_id(self, value: str) -> None:
        """Set the node's unique identifier.

        Use this method for mutations - it allows graph updates
        without breaking the dataclass contract.

        Note: This only changes the node's internal ID. The graph's
        _index must be updated separately by the mutation method.
        """
        # Dataclass field assignment - directly mutate the id attribute
        object.__setattr__(self, "id", value)

    # Label accessors - encapsulated for future hooks (e.g., index updates)
    def get_label(self) -> str:
        """Get the node's display label."""
        return self._label

    def set_label(self, value: str) -> None:
        """Set the node's display label.

        Use this method for mutations - it may trigger graph updates
        in the future (e.g., search index, change tracking).
        """
        self._label = value

    # Iterator access
    def iter_children(self) -> Iterator[GraphNode]:
        """Iterate over child nodes."""
        yield from self._children

    def iter_parents(self) -> Iterator[GraphNode]:
        """Iterate over parent nodes."""
        yield from self._parents

    def iter_outgoing_edges(self) -> Iterator[Edge]:
        """Iterate over outgoing edges."""
        yield from self._outgoing_edges

    def iter_incoming_edges(self) -> Iterator[Edge]:
        """Iterate over incoming edges."""
        yield from self._incoming_edges

    def iter_edges_by_kind(self, edge_kind: EdgeKind) -> Iterator[Edge]:
        """Iterate outgoing edges of a specific kind."""
        for e in self._outgoing_edges:
            if e.kind == edge_kind:
                yield e

    # Count and membership checks (avoid materializing lists)
    def child_count(self) -> int:
        """Return number of children."""
        return len(self._children)

    def parent_count(self) -> int:
        """Return number of parents."""
        return len(self._parents)

    def has_child(self, node: GraphNode) -> bool:
        """Check if node is a child."""
        return node in self._children

    def has_parent(self, node: GraphNode) -> bool:
        """Check if node is a parent."""
        return node in self._parents

    @property
    def is_root(self) -> bool:
        """True if this node has no parents."""
        return len(self._parents) == 0

    @property
    def is_leaf(self) -> bool:
        """True if this node has no children."""
        return len(self._children) == 0

    # Field accessors (return single value)
    def get_field(self, key: str, default: Any = None) -> Any:
        """Get a field from content."""
        return self._content.get(key, default)

    def set_field(self, key: str, value: Any) -> None:
        """Set a field in content."""
        self._content[key] = value

    def get_all_content(self) -> dict[str, Any]:
        """Get a copy of all content fields.

        Returns a shallow copy for serialization purposes.
        Prefer get_field() for accessing individual fields.
        """
        return dict(self._content)

    def get_metric(self, key: str, default: Any = None) -> Any:
        """Get a metric value."""
        return self._metrics.get(key, default)

    def set_metric(self, key: str, value: Any) -> None:
        """Set a metric value."""
        self._metrics[key] = value

    # Convenience properties for common fields
    @property
    def level(self) -> str | None:
        """Get the requirement level (PRD, OPS, DEV)."""
        return self._content.get("level")

    @property
    def status(self) -> str | None:
        """Get the requirement status."""
        return self._content.get("status")

    @property
    def hash(self) -> str | None:
        """Get the content hash."""
        return self._content.get("hash")

    def add_child(self, child: GraphNode) -> None:
        """Add a child node with bidirectional linking.

        This is the simple form without edge type. For typed edges,
        use link() instead.

        Args:
            child: The child node to add.
        """
        if child not in self._children:
            self._children.append(child)
        if self not in child._parents:
            child._parents.append(self)

    def remove_child(self, child: GraphNode) -> bool:
        """Remove a child node and clean up all links.

        Removes the bidirectional node link and any edges between
        this node and the child.

        Args:
            child: The child node to remove.

        Returns:
            True if the child was found and removed, False otherwise.
        """
        if child not in self._children:
            return False

        # Remove bidirectional node links
        self._children.remove(child)
        if self in child._parents:
            child._parents.remove(self)

        # Remove outgoing edges to this child
        self._outgoing_edges = [e for e in self._outgoing_edges if e.target is not child]

        # Remove incoming edges from this parent on the child
        child._incoming_edges = [e for e in child._incoming_edges if e.source is not self]

        return True

    def link(
        self,
        child: GraphNode,
        edge_kind: EdgeKind,
        assertion_targets: list[str] | None = None,
    ) -> Edge:
        """Create a typed edge to a child node.

        Args:
            child: The child node to link.
            edge_kind: The type of relationship.
            assertion_targets: Optional list of assertion labels targeted.

        Returns:
            The created Edge.
        """
        from elspais.graph.relations import Edge

        # Create the edge
        edge = Edge(
            source=self,
            target=child,
            kind=edge_kind,
            assertion_targets=assertion_targets or [],
        )

        # Add bidirectional node links
        if child not in self._children:
            self._children.append(child)
        if self not in child._parents:
            child._parents.append(self)

        # Track edges
        self._outgoing_edges.append(edge)
        child._incoming_edges.append(edge)

        return edge

    @property
    def depth(self) -> int:
        """Calculate depth from root (0 for roots).

        For DAG structures, returns minimum depth (shortest path to root).
        """
        if not self._parents:
            return 0
        return 1 + min(p.depth for p in self._parents)

    def walk(self, order: str = "pre") -> Iterator[GraphNode]:
        """Iterate over this node and descendants.

        Args:
            order: Traversal order:
                - "pre": Parent first (depth-first, pre-order)
                - "post": Children first (depth-first, post-order)
                - "level": Breadth-first (level order)

        Yields:
            GraphNode instances in the specified order.
        """
        if order == "pre":
            yield from self._walk_preorder()
        elif order == "post":
            yield from self._walk_postorder()
        elif order == "level":
            yield from self._walk_level()
        else:
            raise ValueError(f"Unknown traversal order: {order}")

    def _walk_preorder(self) -> Iterator[GraphNode]:
        """Pre-order traversal (parent before children)."""
        yield self
        for child in self._children:
            yield from child._walk_preorder()

    def _walk_postorder(self) -> Iterator[GraphNode]:
        """Post-order traversal (children before parent)."""
        for child in self._children:
            yield from child._walk_postorder()
        yield self

    def _walk_level(self) -> Iterator[GraphNode]:
        """Level-order (breadth-first) traversal."""
        queue: deque[GraphNode] = deque([self])
        while queue:
            node = queue.popleft()
            yield node
            queue.extend(node._children)

    def ancestors(self) -> Iterator[GraphNode]:
        """Iterate up through all ancestor paths (BFS).

        For DAG structures, visits each unique ancestor once.

        Yields:
            Ancestor GraphNode instances.
        """
        visited: set[str] = set()
        queue: deque[GraphNode] = deque(self._parents)
        while queue:
            node = queue.popleft()
            if node.id not in visited:
                visited.add(node.id)
                yield node
                queue.extend(node._parents)

    def find(self, predicate: Callable[[GraphNode], bool]) -> Iterator[GraphNode]:
        """Find all descendants matching predicate.

        Args:
            predicate: Function that returns True for matching nodes.

        Yields:
            Matching GraphNode instances.
        """
        for node in self.walk():
            if predicate(node):
                yield node

    def find_by_kind(self, kind: NodeKind) -> Iterator[GraphNode]:
        """Find all descendants of a specific kind.

        Args:
            kind: The NodeKind to filter by.

        Yields:
            GraphNode instances of the specified kind.
        """
        return self.find(lambda n: n.kind == kind)
