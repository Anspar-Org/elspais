"""GraphNode - Unified node representation for traceability graph.

This module provides the core data structures for Architecture 3.0:
- NodeKind: Enum of node types
- SourceLocation: Portable file location reference
- GraphNode: Unified node with typed content and edge management
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterator

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
    TODO = "todo"


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
        id: Unique identifier for this node.
        kind: The type of node (requirement, assertion, etc.).
        label: Human-readable display label.
        source: Where this node is defined in source files.
        content: Typed data based on node kind (dict for flexibility).
        children: Child nodes (populated via link()).
        parents: Parent nodes (DAG - multiple parents allowed).
        outgoing_edges: Edges from this node to children.
        incoming_edges: Edges from parents to this node.
        metrics: Mutable storage for computed metrics.
    """

    id: str
    kind: NodeKind
    label: str = ""
    source: SourceLocation | None = None
    content: dict[str, Any] = field(default_factory=dict)
    children: list[GraphNode] = field(default_factory=list)
    parents: list[GraphNode] = field(default_factory=list, repr=False)
    outgoing_edges: list[Edge] = field(default_factory=list, repr=False)
    incoming_edges: list[Edge] = field(default_factory=list, repr=False)
    metrics: dict[str, Any] = field(default_factory=dict)

    def add_child(self, child: GraphNode) -> None:
        """Add a child node with bidirectional linking.

        This is the simple form without edge type. For typed edges,
        use link() instead.

        Args:
            child: The child node to add.
        """
        if child not in self.children:
            self.children.append(child)
        if self not in child.parents:
            child.parents.append(self)

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
        if child not in self.children:
            self.children.append(child)
        if self not in child.parents:
            child.parents.append(self)

        # Track edges
        self.outgoing_edges.append(edge)
        child.incoming_edges.append(edge)

        return edge

    def edges_by_kind(self, edge_kind: EdgeKind) -> list[Edge]:
        """Get outgoing edges of a specific kind.

        Args:
            edge_kind: The edge type to filter by.

        Returns:
            List of matching edges.
        """
        return [e for e in self.outgoing_edges if e.kind == edge_kind]

    @property
    def depth(self) -> int:
        """Calculate depth from root (0 for roots).

        For DAG structures, returns minimum depth (shortest path to root).
        """
        if not self.parents:
            return 0
        return 1 + min(p.depth for p in self.parents)

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
        for child in self.children:
            yield from child._walk_preorder()

    def _walk_postorder(self) -> Iterator[GraphNode]:
        """Post-order traversal (children before parent)."""
        for child in self.children:
            yield from child._walk_postorder()
        yield self

    def _walk_level(self) -> Iterator[GraphNode]:
        """Level-order (breadth-first) traversal."""
        queue: deque[GraphNode] = deque([self])
        while queue:
            node = queue.popleft()
            yield node
            queue.extend(node.children)

    def ancestors(self) -> Iterator[GraphNode]:
        """Iterate up through all ancestor paths (BFS).

        For DAG structures, visits each unique ancestor once.

        Yields:
            Ancestor GraphNode instances.
        """
        visited: set[str] = set()
        queue: deque[GraphNode] = deque(self.parents)
        while queue:
            node = queue.popleft()
            if node.id not in visited:
                visited.add(node.id)
                yield node
                queue.extend(node.parents)

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
