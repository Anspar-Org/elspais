"""Unified traceability tree data structures.

This module provides the core data structures for representing the full
traceability graph: Requirements → Assertions → Code → Tests → Results.

The tree supports:
- Portable source references (SourceLocation)
- Typed node kinds (NodeKind enum)
- DAG structure with multiple parents
- Mutable metrics for accumulation
- Uniform traversal across all node types
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterator,
)

if TYPE_CHECKING:
    from elspais.core.models import Assertion, Requirement


class NodeKind(Enum):
    """Types of nodes in the traceability tree."""

    REQUIREMENT = "requirement"
    ASSERTION = "assertion"
    CODE = "code"  # Implementation file reference
    TEST = "test"  # Test file reference
    TEST_RESULT = "result"  # Test execution result
    USER_JOURNEY = "journey"  # Optional grouping


@dataclass
class SourceLocation:
    """Portable reference to a location in a file.

    Paths are stored relative to the repository root, enabling
    consistent references across different working directories.
    """

    path: str  # Relative to repo root, e.g., "spec/prd-auth.md"
    line: int  # 1-based line number
    end_line: int | None = None
    repo: str | None = None  # For multi-repo: "CAL", None = core

    def absolute(self, repo_root: Path) -> Path:
        """Resolve to absolute path.

        Args:
            repo_root: The repository root path.

        Returns:
            Absolute path to the file.
        """
        return repo_root / self.path

    def __str__(self) -> str:
        """Return string representation for display."""
        if self.repo:
            return f"{self.repo}:{self.path}:{self.line}"
        return f"{self.path}:{self.line}"


@dataclass
class CodeReference:
    """Reference to implementation code."""

    file_path: str  # Relative to repo root
    line: int
    end_line: int | None = None
    symbol: str | None = None  # Function/class name if known


@dataclass
class TestReference:
    """Reference to a test."""

    file_path: str
    line: int
    test_name: str
    test_class: str | None = None


@dataclass
class TestResult:
    """Result of a test execution."""

    status: str  # "passed", "failed", "skipped", "error"
    duration: float | None = None
    message: str | None = None
    result_file: str | None = None  # JUnit XML or pytest JSON source


@dataclass
class UserJourney:
    """User Journey - non-normative context provider.

    Format: JNY-{Descriptor}-{number} (e.g., JNY-Spec-Author-01)
    User Journeys provide context for requirements but are NOT normative -
    they don't define obligations (no SHALL language).

    Requirements link to journeys via `Addresses: JNY-xxx-NN, ...` field.
    """

    id: str  # e.g., "JNY-Spec-Author-01"
    actor: str  # Who is performing the journey
    goal: str  # What they're trying to accomplish
    context: str | None = None  # Background/situation
    steps: list[str] = field(default_factory=list)  # Ordered steps
    expected_outcome: str | None = None  # Success criteria
    file_path: str | None = None  # Relative path to source file
    line_number: int | None = None


@dataclass
class TraceNode:
    """A node in the traceability tree.

    TraceNode is the unified representation for all entities in the
    traceability graph. The `kind` field determines which typed content
    field is populated (exactly one should be set based on kind).

    Attributes:
        id: Unique identifier for this node.
        kind: The type of node (requirement, assertion, etc.).
        label: Human-readable display label.
        source: Where this node is defined in source files.
        children: Child nodes (populated during tree building).
        parents: Parent nodes (DAG - multiple parents allowed).
        requirement: Populated when kind is REQUIREMENT.
        assertion: Populated when kind is ASSERTION.
        code_ref: Populated when kind is CODE.
        test_ref: Populated when kind is TEST.
        test_result: Populated when kind is TEST_RESULT.
        journey: Populated when kind is USER_JOURNEY.
        metrics: Mutable storage for computed metrics.
    """

    id: str
    kind: NodeKind
    label: str
    source: SourceLocation | None = None
    children: list[TraceNode] = field(default_factory=list)

    # Typed content - exactly one should be set based on kind
    requirement: Requirement | None = None
    assertion: Assertion | None = None
    code_ref: CodeReference | None = None
    test_ref: TestReference | None = None
    test_result: TestResult | None = None
    journey: UserJourney | None = None

    # Mutable storage for computed metrics
    metrics: dict[str, Any] = field(default_factory=dict)

    # Parent references (DAG - multiple parents allowed)
    parents: list[TraceNode] = field(default_factory=list, repr=False)

    @property
    def depth(self) -> int:
        """Calculate depth from root (0 for roots).

        For DAG structures, returns minimum depth (shortest path to a root).
        """
        if not self.parents:
            return 0
        return 1 + min(p.depth for p in self.parents)

    def walk(self, order: str = "pre") -> Iterator[TraceNode]:
        """Iterate over this node and descendants.

        Args:
            order: Traversal order:
                - "pre": Parent first (depth-first, pre-order)
                - "post": Children first (depth-first, post-order)
                - "level": Breadth-first (level order)

        Yields:
            TraceNode instances in the specified order.
        """
        if order == "pre":
            yield from self._walk_preorder()
        elif order == "post":
            yield from self._walk_postorder()
        elif order == "level":
            yield from self._walk_level()
        else:
            raise ValueError(f"Unknown traversal order: {order}")

    def _walk_preorder(self) -> Iterator[TraceNode]:
        """Pre-order traversal (parent before children)."""
        yield self
        for child in self.children:
            yield from child._walk_preorder()

    def _walk_postorder(self) -> Iterator[TraceNode]:
        """Post-order traversal (children before parent)."""
        for child in self.children:
            yield from child._walk_postorder()
        yield self

    def _walk_level(self) -> Iterator[TraceNode]:
        """Level-order (breadth-first) traversal."""
        queue: list[TraceNode] = [self]
        while queue:
            node = queue.pop(0)
            yield node
            queue.extend(node.children)

    def ancestors(self) -> Iterator[TraceNode]:
        """Iterate up through all ancestor paths (BFS).

        For DAG structures, visits each unique ancestor once.

        Yields:
            Ancestor TraceNode instances.
        """
        visited: set[str] = set()
        queue = list(self.parents)
        while queue:
            node = queue.pop(0)
            if node.id not in visited:
                visited.add(node.id)
                yield node
                queue.extend(node.parents)

    def find(self, predicate: Callable[[TraceNode], bool]) -> Iterator[TraceNode]:
        """Find all descendants matching predicate.

        Args:
            predicate: Function that returns True for matching nodes.

        Yields:
            Matching TraceNode instances.
        """
        for node in self.walk():
            if predicate(node):
                yield node

    def find_by_kind(self, kind: NodeKind) -> Iterator[TraceNode]:
        """Find all descendants of a specific kind.

        Args:
            kind: The NodeKind to filter by.

        Yields:
            TraceNode instances of the specified kind.
        """
        return self.find(lambda n: n.kind == kind)


@dataclass
class TraceTree:
    """The complete traceability tree.

    TraceTree is a container for the full traceability graph, providing
    indexed access to all nodes and methods for tree-wide operations.

    Attributes:
        roots: Top-level nodes (PRD reqs with no implements, user journeys).
        repo_root: Path to the repository root.
    """

    roots: list[TraceNode]
    repo_root: Path

    # Index for fast lookup (initialized in __post_init__)
    _index: dict[str, TraceNode] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        """Build index if not provided."""
        if not self._index:
            self._index = {node.id: node for node in self.all_nodes()}

    def find_by_id(self, id: str) -> TraceNode | None:
        """Find node by ID.

        Args:
            id: The node ID to find.

        Returns:
            The matching TraceNode, or None if not found.
        """
        return self._index.get(id)

    def all_nodes(self, order: str = "pre") -> Iterator[TraceNode]:
        """Iterate all nodes in tree.

        Args:
            order: Traversal order ("pre", "post", "level").

        Yields:
            All TraceNode instances in the tree.
        """
        for root in self.roots:
            yield from root.walk(order)

    def nodes_by_kind(self, kind: NodeKind) -> Iterator[TraceNode]:
        """Get all nodes of a specific kind.

        Args:
            kind: The NodeKind to filter by.

        Yields:
            TraceNode instances of the specified kind.
        """
        for node in self.all_nodes():
            if node.kind == kind:
                yield node

    def accumulate(
        self,
        metric_name: str,
        leaf_fn: Callable[[TraceNode], Any],
        combine_fn: Callable[[TraceNode, list[Any]], Any],
    ) -> None:
        """Compute a metric by accumulating from leaves to roots.

        This method traverses the tree in post-order (children first),
        computing a metric value for each node. Leaf nodes get their
        value from `leaf_fn`, while internal nodes combine their
        children's values using `combine_fn`.

        Example - coverage percentage:
            tree.accumulate(
                "coverage",
                leaf_fn=lambda n: 1 if n.metrics.get("test_count", 0) > 0 else 0,
                combine_fn=lambda n, vals: sum(vals) / len(vals) if vals else 0
            )

        Args:
            metric_name: Name of the metric to store in node.metrics.
            leaf_fn: Function to compute metric for leaf nodes.
            combine_fn: Function to combine child metrics for internal nodes.
        """

        def _accumulate(node: TraceNode) -> Any:
            if not node.children:
                # Leaf node
                value = leaf_fn(node)
            else:
                # Internal node - recurse first (post-order)
                child_values = [_accumulate(child) for child in node.children]
                value = combine_fn(node, child_values)
            node.metrics[metric_name] = value
            return value

        for root in self.roots:
            _accumulate(root)

    def node_count(self) -> int:
        """Return total number of nodes in the tree."""
        return len(self._index)

    def count_by_kind(self) -> dict[NodeKind, int]:
        """Return count of nodes by kind.

        Uses the index to ensure unique counts (not affected by DAG structure).

        Returns:
            Dictionary mapping NodeKind to count.
        """
        counts: dict[NodeKind, int] = {}
        for node in self._index.values():
            counts[node.kind] = counts.get(node.kind, 0) + 1
        return counts
